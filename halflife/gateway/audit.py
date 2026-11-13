"""Gateway audit: how much of what Bifrost served is stale, per model and virtual key.

    uv run python -m halflife.gateway.audit [--hours 24] [--sample-cap 50] [--budget 60] [--refit]

1. Pull recent successful chat requests from Bifrost's logging API (GET /api/logs, roots_only so a
   fallback chain counts once), newest first, capped at --sample-cap. Half-Life's own extract/judge
   calls (virtual key `halflife-dev`) are excluded.
2. Read each answer through GET /api/logs/{id} (the list view omits output_message), at most 4 at once.
3. Extract claims from every sampled answer (one Haiku call each), rank all time-sensitive claims across
   the run by the extractor's outdated-probability (half-life fallback), verify the top --budget claims.
4. Record every answer report in the fact ledger (the ONLY ledger writer), aggregate stale rate by
   (model, virtual key), and write data/gateway_summary.json for the API and UI.
"""

import argparse
import asyncio
import json
import random
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from halflife.clients.bifrost import BifrostClient, ChatModel
from halflife.clients.tavily import DiskCache, Searcher, TavilyViaRelay
from halflife.config import ROOT, load_settings
from halflife.extract import extract_claims
from halflife.gateway.estimate import estimate, strata_of, stratified_sample
from halflife.ledger import Ledger
from halflife.pipeline import (CheckOptions, MeteredModel, assess_risk, build_claim_report, is_time_sensitive,
                               select_for_verification)
from halflife.risk import answer_score
from halflife.schemas import AnswerReport, GatewaySummary, StaleRateRow, Usage
from halflife.verify import VerifyOutcome, verify_claim

SUMMARY_PATH = ROOT / "data" / "gateway_summary.json"
INTERNAL_VKS = {"halflife-dev"}
CONCURRENCY = 4
# Reliable knowledge cutoffs (Anthropic models pages, checked 2026-11-12). Unknown models: the answer's
# own timestamp is used as as-of, which treats it as fresh (P(stale) from age 0).
MODEL_CUTOFFS = {"claude-haiku-5-5": date(2026, 6, 30), "claude-haiku-4-5": date(2025, 2, 28)}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # content blocks
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def parse_log(row: dict) -> dict | None:
    out = row.get("output_message") or {}
    answer = _text(out.get("content"))
    history = row.get("input_history") or []
    question = next((_text(m.get("content")) for m in reversed(history) if m.get("role") == "user"), "")
    if not answer.strip():
        return None
    return {"id": row["id"], "model": f"{row.get('provider')}/{row.get('model')}", "bare_model": row.get("model") or "",
            "virtual_key": row.get("virtual_key_name"), "timestamp": row.get("timestamp"),
            "question": question, "answer": answer}


async def _detail_when_written(bf: BifrostClient, log_id: str, tries: int = 10) -> dict | None:
    """Log rows are written asynchronously after the response; poll until the answer is stored."""
    for _ in range(tries):
        try:
            d = await bf.get_log(log_id)
            if (d.get("output_message") or {}).get("content"):
                return d
        except Exception:  # 404 before the async write lands
            pass
        await asyncio.sleep(1)
    return None


async def sample_logs(bf: BifrostClient, *, hours: float, cap: int, request_ids: set[str] | None = None,
                      vk_ids: list[str] | None = None) -> tuple[list[dict], int]:
    if request_ids is not None:  # explicit ids (tests, proxy joins): read each by id
        details = await asyncio.gather(*(_detail_when_written(bf, i) for i in list(request_ids)[:cap]))
        return [p for d in details if d and (p := parse_log(d))], len(request_ids)
    since = datetime.now(UTC) - timedelta(hours=hours)
    # Scan deeper than the cap: Half-Life's own extract/judge calls share the log and are skipped.
    filters = {"status": "success", **({"virtual_key_ids": ",".join(vk_ids)} if vk_ids else {})}
    rows = await bf.list_logs(max_rows=min(max(cap * 10, 100), 1000), **filters)
    scanned = len(rows)
    picked = []
    for r in rows:
        if r.get("virtual_key_name") in INTERNAL_VKS:
            continue
        ts = r.get("timestamp")
        if ts and datetime.fromisoformat(ts.replace("Z", "+00:00")) < since:
            continue
        if r.get("object") and "chat" not in str(r.get("object")):
            continue
        picked.append(r["id"])
        if len(picked) >= cap:
            break
    details = await asyncio.gather(*(bf.get_log(i) for i in picked), return_exceptions=True)  # get_log caps at 4
    parsed = [p for d in details if isinstance(d, dict) and (p := parse_log(d))]
    return parsed, scanned


async def audit(bf: BifrostClient, model: ChatModel, searcher: Searcher, *, hours: float = 24, cap: int = 50,
                budget: int = 60, today: date | None = None, half_lives: dict | None = None,
                request_ids: set[str] | None = None, ledger: Ledger | None = None,
                random_share: float = 0.3, seed: int = 0, vk_ids: list[str] | None = None) -> tuple[GatewaySummary, list[AnswerReport]]:
    today = today or datetime.now(UTC).date()
    started = datetime.now(UTC)
    logs, scanned = await sample_logs(bf, hours=hours, cap=cap, request_ids=request_ids, vk_ids=vk_ids)
    metered = MeteredModel(model)
    sem = asyncio.Semaphore(CONCURRENCY)

    async def extract(log: dict):
        cutoff = MODEL_CUTOFFS.get(log["bare_model"]) or date.fromisoformat(log["timestamp"][:10])
        opts = CheckOptions(as_of=cutoff, today=today, mode="gateway", answer_model=log["model"], request_id=log["id"])
        async with sem:
            ex = await extract_claims(log["answer"], metered, as_of=opts.as_of, today=today)
        risks = [assess_risk(c, opts, half_lives or {}) for c in ex.claims]
        return log, opts, ex, risks

    extracted = await asyncio.gather(*(extract(lg) for lg in logs))
    # Rank every time-sensitive claim across the run; verify the top `budget`.
    pool = [(ai, ci, ex.claims[ci], risks[ci]) for ai, (_, _, ex, risks) in enumerate(extracted) for ci in range(len(ex.claims))]
    # Budget split: (1 - random_share) to the riskiest claims, random_share to a stratified random sample of ALL
    # time-sensitive claims (for the traffic-wide estimate). A claim in both sets is verified once.
    n_random = round(budget * random_share)
    order = select_for_verification([p[2] for p in pool], [p[3] for p in pool], budget - n_random)
    ts = [i for i, p in enumerate(pool) if is_time_sensitive(p[2])]
    ts_scores = [pool[i][3].rank_score for i in ts]
    ts_strata = strata_of(ts_scores)
    sample = [ts[j] for j in stratified_sample(ts_scores, n_random, random.Random(seed))] if ts else []
    stratum_of = {ts[j]: ts_strata[j] for j in range(len(ts))}
    chosen = {(pool[i][0], pool[i][1]) for i in list(order) + sample}

    async def verify(key):
        ai, ci = key
        async with sem:
            return key, await verify_claim(extracted[ai][2].claims[ci], metered, searcher, today=today)

    outcomes: dict[tuple[int, int], VerifyOutcome] = dict(await asyncio.gather(*(verify(k) for k in chosen)))

    reports, usage = [], Usage()
    for ai, (log, opts, ex, risks) in enumerate(extracted):
        claims = [build_claim_report(c, risks[ci], outcomes.get((ai, ci))) for ci, c in enumerate(ex.claims)]
        reports.append(AnswerReport(answer=log["answer"], model=log["model"], mode="gateway", checked_at=datetime.now(UTC),
                                    verification_budget=budget, claims=claims, answer_score=answer_score([c.freshness_score for c in claims]),
                                    errors=list(ex.errors), bifrost_request_id=log["id"]))
    for o in outcomes.values():
        usage.tavily_calls += o.searches
        usage.tavily_credits += o.credits
        usage.tavily_cache_hits += o.cache_hits
    usage.model_calls, usage.model_cost_usd = metered.calls, round(metered.cost_usd, 6)
    usage.latency_ms = round((datetime.now(UTC) - started).total_seconds() * 1000, 1)

    rows = aggregate(logs, reports)
    rows, overall = add_estimates(rows, logs, pool, ts, stratum_of, sample, outcomes, extracted)
    if ledger is not None:
        for log, rep in zip(logs, reports):
            ledger.record(rep, model=log["model"], virtual_key=log["virtual_key"])
    hl = half_lives or {}
    summary = GatewaySummary(
        generated_at=datetime.now(UTC), window_start=started - timedelta(hours=hours), window_end=started,
        logs_scanned=scanned, sample_cap=cap, verification_budget=budget, rows=rows,
        half_lives={k.value: v[0] for k, v in hl.items()}, half_life_source={k.value: v[1] for k, v in hl.items()},
        usage=usage, errors=[e for r in reports for e in r.errors], random_share=random_share, estimate_overall=overall,
    )
    return summary, reports


def _outcome(o: VerifyOutcome | None) -> bool | None:
    if o is None or o.verdict is None:
        return None
    return {"changed": True, "current": False}.get(o.verdict.label.value)


def _est_fields(e) -> dict:
    return {"est_stale_rate": None if e.stale_rate is None else round(e.stale_rate, 4),
            "est_ci95": None if e.ci95 is None else (round(e.ci95[0], 4), round(e.ci95[1], 4)),
            "est_bounds_unverifiable": None if e.bound_low is None else (round(e.bound_low, 4), round(e.bound_high, 4)),
            "est_n_sampled": e.n_sampled}


def add_estimates(rows, logs, pool, ts, stratum_of, sample, outcomes, extracted):
    """Traffic-wide estimate per (model, key) and overall, from the random sample only."""
    def slice_key(i):
        lg = logs[pool[i][0]]
        return (lg["model"], lg["virtual_key"])
    sampled = {i: _outcome(outcomes.get((pool[i][0], pool[i][1]))) for i in sample}
    out = []
    for r in rows:
        members = [i for i in ts if slice_key(i) == (r.model, r.virtual_key)]
        e = estimate([stratum_of[i] for i in members], [(stratum_of[i], sampled[i]) for i in members if i in sampled])
        out.append(r.model_copy(update={**_est_fields(e), "time_sensitive_claims": len(members)}))
    e_all = estimate([stratum_of[i] for i in ts], [(stratum_of[i], y) for i, y in sampled.items()])
    overall = {**_est_fields(e_all), "time_sensitive_claims": len(ts)}
    return out, overall


def aggregate(logs: list[dict], reports: list[AnswerReport]) -> list[StaleRateRow]:
    acc: dict[tuple, dict] = defaultdict(lambda: {"seen": 0, "checked": 0, "found": 0, "verified": 0, "changed": 0, "scores": []})
    for log, rep in zip(logs, reports):
        a = acc[(log["model"], log["virtual_key"])]
        a["seen"] += 1
        a["found"] += len(rep.claims)
        verified = [c for c in rep.claims if c.verdict and c.verdict.label.value in ("current", "changed")]
        a["checked"] += any(c.searched for c in rep.claims)
        a["verified"] += len(verified)
        a["changed"] += sum(c.verdict.label.value == "changed" for c in verified)
        if rep.answer_score is not None:
            a["scores"].append(rep.answer_score)
    return [StaleRateRow(model=m, virtual_key=vk, answers_seen=a["seen"], answers_checked=a["checked"], claims_found=a["found"],
                         claims_verified=a["verified"], claims_changed=a["changed"],
                         stale_rate=round(a["changed"] / a["verified"], 4) if a["verified"] else None,
                         mean_answer_score=round(sum(a["scores"]) / len(a["scores"]), 1) if a["scores"] else None)
            for (m, vk), a in sorted(acc.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))]


async def main_async(args) -> None:
    s = load_settings()
    bf = BifrostClient(s)
    searcher = TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir))
    with Ledger(s.db_path) as ledger:
        names = [n for n in args.virtual_keys.split(",") if n]
        vks = (await bf.admin("GET", "/api/governance/virtual-keys")).json().get("virtual_keys") or [] if names else []
        vk_ids = [k["id"] for k in vks if k["name"] in names] or None
        if args.budget * args.random_share < 60:
            print(f"note: {round(args.budget * args.random_share)} random samples; intervals undercover below ~60")
        summary, reports = await audit(bf, bf, searcher, hours=args.hours, cap=args.sample_cap, budget=args.budget,
                                       half_lives=ledger.half_lives(), ledger=ledger, random_share=args.random_share,
                                       vk_ids=vk_ids)
        if args.refit:
            for row in ledger.refit():
                print("refit", row)
    await bf.aclose()
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(summary.model_dump_json(indent=2))
    print(json.dumps({"answers": len(reports), "rows": [r.model_dump() for r in summary.rows], "usage": summary.usage.model_dump()}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--sample-cap", type=int, default=50)
    ap.add_argument("--budget", type=int, default=60, help="claims verified per run, riskiest first")
    ap.add_argument("--random-share", type=float, default=0.3,
                    help="share of the budget for the stratified random sample behind the traffic-wide estimate; "
                         "aim for at least ~60 random samples (budget x share): below that the 95%% interval undercovers "
                         "(validation: 0.74 coverage at 18, 0.945 at 60; results/2026-11-13-estimator-validation)")
    ap.add_argument("--virtual-keys", default="", help="comma-separated virtual key names to audit (server-side log filter)")
    ap.add_argument("--refit", action="store_true")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
