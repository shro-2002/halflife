"""J3: live detector evaluation on the labelled cases (eval/cases.jsonl).

    uv run python -m eval.run            # live: Bifrost + Tavily relay; writes results/<date>-detector/raw.jsonl
    uv run python -m eval.run --offline  # recompute every table from raw.jsonl (no model calls, no credits)

Protocol (fixed before running):
- Each case's claim is the answer. as_of = the runtime model's knowledge cutoff (2026-06-30) for every
  case, so the as-of date cannot leak the label; today = frozen eval date 2026-11-12.
- Check mode: every time-sensitive claim the extractor finds is verified. A case is predicted stale if
  any of its claims gets a `changed` verdict. `unverifiable` counts as "not flagged".
- Budget curves are computed from the full-verification results: verifying the top k% of cases in a
  given order catches the stale cases among them that the detector flagged.
- Confidence intervals: bootstrap resampling source URLs (clusters), not cases, because stale/current
  pairs share a URL.
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from halflife.config import ROOT, load_settings
from halflife.risk import p_stale

EVAL_DATE = date(2026, 11, 12)
CASES = ROOT / "eval" / "cases.jsonl"
OUT = ROOT / "results" / f"{EVAL_DATE.isoformat()}-detector"
HALF_LIVES = ROOT / "results" / "2026-11-12-ordering" / "summary.json"
GRID = [i / 100 for i in range(101)]
BOOT = 1000
SEED = 11
THIN = 15  # fewer time-sensitive cases than this: per-class numbers are too thin to read


# ---------------------------------------------------------------- live run

class Meter:
    def __init__(self, inner) -> None:
        self.inner, self.cost, self.calls = inner, 0.0, 0

    async def chat(self, messages, **kw):
        self.calls += 1
        r = await self.inner.chat(messages, **kw)
        self.cost += r.cost_usd
        return r


async def run_case(case: dict, bf, searcher, cutoff: date) -> dict:
    from halflife.extract import extract_claims
    from halflife.pipeline import CheckOptions, assess_risk, is_time_sensitive, prior_half_lives
    from halflife.verify import verify_claim

    m = Meter(bf)
    t0 = time.perf_counter()
    ex = await extract_claims(case["claim"], m, as_of=cutoff, today=EVAL_DATE)
    extract = {"cost": m.cost, "latency_s": time.perf_counter() - t0, "errors": ex.errors}
    opts = CheckOptions(as_of=cutoff, today=EVAL_DATE)
    claims = []
    for c in ex.claims:
        risk = assess_risk(c, opts, prior_half_lives())
        row = {"claim": c.model_dump(mode="json"), "risk": risk.model_dump(mode="json"), "time_sensitive": is_time_sensitive(c)}
        if is_time_sensitive(c):
            vm = Meter(bf)
            t1 = time.perf_counter()
            o = await verify_claim(c, vm, searcher, today=EVAL_DATE)
            row.update(verdict=o.verdict.model_dump(mode="json") if o.verdict else None, strong=o.strong_support,
                       evidence=[e.model_dump(mode="json") for e in o.evidence], errors=o.errors,
                       credits=o.credits, searches=o.searches, cost=vm.cost, latency_s=time.perf_counter() - t1)
        claims.append(row)
    return {"id": case["id"], "extract": extract, "claims": claims}


CACHED_ONLY = False  # --cached-evidence-only: never call Tavily; a cache miss -> search error -> unverifiable


async def live() -> None:
    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay

    s = load_settings()
    bf = BifrostClient(s)
    searcher = TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir), offline=CACHED_ONLY)
    cases = [json.loads(l) for l in CASES.read_text().splitlines()]
    OUT.mkdir(parents=True, exist_ok=True)
    raw_path = OUT / "raw.jsonl"
    done = {json.loads(l)["id"] for l in raw_path.read_text().splitlines()} if raw_path.exists() else set()
    todo = [c for c in cases if c["id"] not in done]
    sem = asyncio.Semaphore(4)
    before = await bf.vk_spend_usd()

    async def one(c):
        async with sem:
            r = await run_case(c, bf, searcher, s.model_cutoff)
        with raw_path.open("a") as f:  # append as we go: a crash keeps finished cases
            f.write(json.dumps(r) + "\n")
        print("done", c["id"], flush=True)

    await asyncio.gather(*(one(c) for c in todo))
    await asyncio.sleep(20)
    spend = {"vk_delta_usd": round(await bf.vk_spend_usd() - before, 6), "cases_run": len(todo)}
    (OUT / "live_spend.json").write_text(json.dumps(spend, indent=2))
    await bf.aclose()


# ---------------------------------------------------------------- metrics (offline)

def load_joined() -> list[dict]:
    cases = {c["id"]: c for c in map(json.loads, CASES.read_text().splitlines())}
    rows = []
    for r in map(json.loads, (OUT / "raw.jsonl").read_text().splitlines()):
        c = cases[r["id"]]
        ts = [x for x in r["claims"] if x["time_sensitive"]]
        verdicts = [x["verdict"]["label"] if x.get("verdict") else "no_verdict" for x in ts]
        outcome = ("changed" if "changed" in verdicts else "current" if "current" in verdicts
                   else "unverifiable" if verdicts else "not_searched")
        rows.append({
            **c, "outcome": outcome, "flagged": outcome == "changed",
            "model_p": max([x["claim"].get("p_outdated_model") or 0.0 for x in ts] or [0.0]),
            "hl_class": max(ts, key=lambda x: x["risk"]["p_stale"])["claim"]["volatility_class"] if ts else "timeless",
            "extract_cost": r["extract"]["cost"], "extract_latency": r["extract"]["latency_s"],
            "verify_cost": sum(x.get("cost", 0) for x in ts), "verify_latency": sum(x.get("latency_s", 0) for x in ts),
            "credits": sum(x.get("credits", 0) for x in ts), "claims_raw": r["claims"],
        })
    return rows


def half_life_scores(rows: list[dict]) -> list[float]:
    fitted = json.loads(HALF_LIVES.read_text())["half_lives"]
    from halflife.schemas import PRIOR_HALF_LIFE_DAYS, VolatilityClass
    age = (EVAL_DATE - load_settings().model_cutoff).days
    out = []
    for r in rows:
        cls = r["hl_class"]
        h = None if cls == "timeless" else (fitted.get(cls, {}).get("fitted_days") or PRIOR_HALF_LIFE_DAYS[VolatilityClass(cls)])
        out.append(p_stale(age, h))
    return out


def detector(rows: list[dict]) -> dict:
    ts = [r for r in rows if r["label"] != "timeless"]
    tp = sum(r["label"] == "stale" and r["flagged"] for r in ts)
    fp = sum(r["label"] == "current" and r["flagged"] for r in ts)
    fn = sum(r["label"] == "stale" and not r["flagged"] for r in ts)
    tn = sum(r["label"] == "current" and not r["flagged"] for r in ts)
    tl = [r for r in rows if r["label"] == "timeless"]
    return {"n_time_sensitive": len(ts), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
            "unverifiable_rate": sum(r["outcome"] == "unverifiable" for r in ts) / len(ts) if ts else None,
            "timeless_n": len(tl), "timeless_flagged": sum(r["flagged"] for r in tl),
            "timeless_searched": sum(r["outcome"] != "not_searched" for r in tl)}


def budget_curve(rows: list[dict], scores: list[float], rng: random.Random | None) -> list[float]:
    n, total = len(rows), sum(r["label"] == "stale" for r in rows)
    keys = [(s, rng.random() if rng else 0.0) for s in scores]
    order = sorted(range(n), key=lambda i: keys[i], reverse=True)
    cum, caught = [0], 0
    for i in order:
        caught += rows[i]["label"] == "stale" and rows[i]["flagged"]
        cum.append(caught)
    return [cum[round(g * n)] / total if total else 0.0 for g in GRID]


def avg_curve(rows, scores, reps, seed):
    rng = random.Random(seed)
    cs = [budget_curve(rows, scores, rng) for _ in range(reps)]
    return [statistics.fmean(col) for col in zip(*cs)]


def costs_at(rows: list[dict], scores: list[float], frac: float) -> dict:
    n = len(rows)
    chosen = set(sorted(range(n), key=lambda i: -scores[i])[: round(frac * n)])
    cost = sum(r["extract_cost"] + (r["verify_cost"] if i in chosen else 0) for i, r in enumerate(rows)) / n
    cred = sum(r["credits"] if i in chosen else 0 for i, r in enumerate(rows)) / n
    lat = [r["extract_latency"] + (r["verify_latency"] if i in chosen else 0) for i, r in enumerate(rows)]
    return {"model_cost_usd_per_answer": round(cost, 6), "tavily_credits_per_answer": round(cred, 2),
            "latency_s_per_answer_mean": round(statistics.fmean(lat), 2),
            "latency_s_per_answer_median": round(statistics.median(lat), 2)}


def cluster_boot(rows: list[dict], stat) -> list[float]:
    """95% CI of stat(rows) resampling source URLs with replacement."""
    by_url = defaultdict(list)
    for r in rows:
        by_url[r["source_url"]].append(r)
    urls, rng, vals = list(by_url), random.Random(SEED), []
    for _ in range(BOOT):
        sample = [r for u in (rng.choice(urls) for _ in urls) for r in by_url[u]]
        v = stat(sample)
        if v is not None:
            vals.append(v)
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals)) - 1], 3)] if vals else [None, None]


def errors_md(rows: list[dict], conf: dict, det: dict) -> str:
    lines = ["# Detector errors — eval date 2026-11-12", "",
             "Confusion (rows = label, columns = detector outcome; a case is flagged if any claim is `changed`):", "",
             "| label | changed | current | unverifiable | not searched |", "|---|---|---|---|---|"]
    for lab in ("stale", "current", "timeless"):
        lines.append(f"| {lab} | " + " | ".join(str(conf.get(lab, {}).get(o, 0)) for o in ("changed", "current", "unverifiable", "not_searched")) + " |")
    lines += ["", f"Precision {det['precision']:.3f}, recall {det['recall']:.3f} on {det['n_time_sensitive']} time-sensitive cases.", ""]
    wrong = [r for r in rows if (r["label"] == "stale" and not r["flagged"]) or (r["label"] != "stale" and r["flagged"])]
    lines.append(f"## {len(wrong)} wrong verdicts (missed stale = FN incl. unverifiable/not searched; flagged non-stale = FP)\n")
    for r in wrong:
        kind = "FN (missed stale)" if r["label"] == "stale" else "FP (flagged non-stale)"
        lines += [f"### `{r['id']}` — {kind} — {r['volatility_class']}", f"- Claim: {r['claim']}",
                  f"- Labelled truth: {r.get('current_truth')} (source: {r['source_url']})", f"- Outcome: **{r['outcome']}**"]
        for x in r["claims_raw"]:
            v = x.get("verdict")
            lines.append(f"- Extracted: \"{x['claim']['text']}\" [{x['claim']['volatility_class']}], time-sensitive={x['time_sensitive']}, p_outdated_model={x['claim'].get('p_outdated_model')}")
            if v:
                lines.append(f"  - Verdict {v['label']}; quote: \"{(v.get('supporting_quote') or '')[:200]}\" ({v.get('supporting_url')}); value: {v.get('current_value')}")
                lines.append(f"  - Model reasoning: {v.get('reasoning', '')[:300]}")
            for e in (x.get("evidence") or [])[:3]:
                lines.append(f"  - Evidence: {e['url']} — \"{e['content'][:180].strip()}\"")
            if x.get("errors"):
                lines.append(f"  - Errors: {x['errors']}")
        lines.append("")
    return "\n".join(lines)


def offline() -> dict:
    rows = load_joined()
    det = detector(rows)
    conf = defaultdict(Counter)
    for r in rows:
        conf[r["label"]][r["outcome"]] += 1
    model_s, hl_s = [r["model_p"] for r in rows], half_life_scores(rows)
    curves = {"model_p": avg_curve(rows, model_s, 200, SEED), "half_life": avg_curve(rows, hl_s, 200, SEED),
              "random": avg_curve(rows, [0.0] * len(rows), 200, SEED)}
    n_stale = sum(r["label"] == "stale" for r in rows)
    curves["oracle_upper_bound"] = [min(1.0, g * len(rows) / n_stale) * det["recall"] for g in GRID]

    def catch(order_key, k):
        def f(sample):
            sc = [r["model_p"] for r in sample] if order_key == "model_p" else half_life_scores(sample)
            return avg_curve(sample, sc, 5, SEED)[k] if any(r["label"] == "stale" for r in sample) else None
        return f

    budget = {}
    for name, sc in (("model_p", model_s), ("half_life", hl_s)):
        budget[name] = {f"caught_at_{k}": {"point": round(curves[name][k], 3), "ci95_by_url": cluster_boot(rows, catch(name, k))}
                        for k in (25, 50, 100)}
    budget["random"] = {f"caught_at_{k}": {"point": round(curves["random"][k], 3)} for k in (25, 50, 100)}
    cost = {f"{k}%": costs_at(rows, model_s, k / 100) for k in (25, 50, 100)}

    per_class = {}
    for cls in sorted({r["volatility_class"] for r in rows}):
        rs = [r for r in rows if r["volatility_class"] == cls]
        d = detector(rs)
        n_ts = d["n_time_sensitive"]
        per_class[cls] = {**{k: d[k] for k in ("n_time_sensitive", "tp", "fp", "fn", "tn", "precision", "recall")},
                          "too_thin_to_read": cls != "timeless" and n_ts < THIN} if cls != "timeless" else \
                         {"n": d["timeless_n"], "flagged": d["timeless_flagged"], "searched": d["timeless_searched"]}

    summary = {
        "eval_date": EVAL_DATE.isoformat(), "n_cases": len(rows), "n_stale": n_stale,
        "detector": {**det, "precision_ci95_by_url": cluster_boot(rows, lambda s: detector(s)["precision"]),
                     "recall_ci95_by_url": cluster_boot(rows, lambda s: detector(s)["recall"]),
                     "n_source_urls": len({r["source_url"] for r in rows})},
        "confusion": {k: dict(v) for k, v in conf.items()},
        "budget": budget, "cost_latency_by_budget_model_order": cost, "per_class": per_class,
        "half_lives_used": "J0.5 fitted (results/2026-11-12-ordering) where available, else prior guesses",
    }
    spend_path = OUT / "live_spend.json"
    if spend_path.exists():
        summary["live_spend"] = json.loads(spend_path.read_text())
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    (OUT / "curves.json").write_text(json.dumps({"grid": GRID, **curves}))
    (OUT / "errors.md").write_text(errors_md(rows, conf, det))
    plot(curves, OUT / "budget_curve.png")
    return summary


def plot(curves: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    style = {"model_p": ("#1d4ed8", 2.4, "-"), "half_life": ("#c2410c", 2.0, "-"), "random": ("#6b7280", 1.4, "--"),
             "oracle_upper_bound": ("#9ca3af", 1.0, ":")}
    for name, c in curves.items():
        col, lw, ls = style[name]
        ax.plot([g * 100 for g in GRID], [v * 100 for v in c], color=col, lw=lw, ls=ls, label=name)
    ax.set_xlabel("claims verified (%)")
    ax.set_ylabel("stale claims caught (%)")
    ax.set_title("Live detector, 108 labelled cases (eval date 2026-11-12)", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="recompute from raw.jsonl; no spend")
    ap.add_argument("--out", type=Path, default=None, help="results folder (default results/<eval date>-detector)")
    ap.add_argument("--cached-evidence-only", action="store_true", help="live model calls, no Tavily calls")
    args = ap.parse_args()
    global OUT, CACHED_ONLY
    if args.out:
        OUT = args.out
    CACHED_ONLY = args.cached_evidence_only
    if not args.offline:
        asyncio.run(live())
    s = offline()
    print(json.dumps({k: s[k] for k in ("detector", "confusion", "budget", "cost_latency_by_budget_model_order")}, indent=1))


if __name__ == "__main__":
    main()
