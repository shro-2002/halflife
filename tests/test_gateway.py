"""Gateway audit tests. Offline unit tests plus one live end-to-end done-check (marked live)."""

import json
from datetime import UTC, datetime

import pytest

from halflife.gateway.audit import aggregate, parse_log
from halflife.schemas import AnswerReport

FIXTURE = AnswerReport.model_validate_json(open("tests/fixtures/report.json").read())


def test_parse_log_reads_question_and_answer_from_detail_row():
    row = {"id": "r1", "provider": "anthropic", "model": "claude-haiku-5-5", "virtual_key_name": "demo-a",
           "timestamp": "2026-11-12T10:00:00Z",
           "input_history": [{"role": "system", "content": "be brief"}, {"role": "user", "content": "Latest Python?"}],
           "output_message": {"role": "assistant", "content": "Python 3.12."}}
    p = parse_log(row)
    assert (p["model"], p["question"], p["answer"], p["virtual_key"]) == ("anthropic/claude-haiku-5-5", "Latest Python?", "Python 3.12.", "demo-a")


def test_parse_log_skips_rows_without_answer_text():
    assert parse_log({"id": "r", "output_message": {"content": None}, "input_history": []}) is None


def test_aggregate_counts_only_current_and_changed_as_verified():
    logs = [{"model": "m1", "virtual_key": "k1"}, {"model": "m1", "virtual_key": "k1"}, {"model": "m2", "virtual_key": None}]
    rows = aggregate(logs, [FIXTURE, FIXTURE, FIXTURE])
    by = {(r.model, r.virtual_key): r for r in rows}
    # fixture: 1 changed, 2 current, 1 unverifiable, 1 estimated, 1 timeless
    assert by[("m1", "k1")].claims_verified == 6 and by[("m1", "k1")].claims_changed == 2
    assert by[("m1", "k1")].stale_rate == pytest.approx(2 / 6, abs=1e-4)
    assert by[("m2", None)].answers_seen == 1


@pytest.mark.live
async def test_live_ten_questions_audit_matches_per_answer_reports(tmp_path):
    """Done-check for J2: ten questions through real Bifrost, audit them, stored stale rate == reports."""
    import asyncio

    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay
    from halflife.config import load_settings
    from halflife.gateway.audit import audit
    from halflife.gateway.seed import QUESTIONS, seed
    from halflife.ledger import Ledger

    picks = [QUESTIONS[i] for i in (0, 2, 4, 5, 8, 12, 20, 22, 31, 33)]  # 8 time-sensitive, 2 timeless
    sent = await seed(len(picks), picks)
    ids = {r["request_id"] for r in sent if r["status"] == 200}
    assert len(ids) == 10
    await asyncio.sleep(3)  # Bifrost writes logs asynchronously
    s = load_settings()
    bf = BifrostClient(s)
    with Ledger(tmp_path / "ledger.sqlite") as ledger:
        summary, reports = await audit(bf, bf, TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir)), hours=1,
                                       cap=10, budget=100, request_ids=ids, half_lives=ledger.half_lives(), ledger=ledger)
        stored = ledger.stale_rates()
    await bf.aclose()
    assert len(reports) == 10
    from_reports = {}
    for rep in reports:
        verified = [c for c in rep.claims if c.verdict and c.verdict.label.value in ("current", "changed")]
        key = rep.model
        v, ch = from_reports.get(key, (0, 0))
        from_reports[key] = (v + len(verified), ch + sum(c.verdict.label.value == "changed" for c in verified))
    by_model: dict[str, tuple[int, int]] = {}
    for row in stored:
        v, ch = by_model.get(row["model"], (0, 0))
        by_model[row["model"]] = (v + row["verified"], ch + row["changed"])
    assert by_model == from_reports
    summary_by_model = {}
    for r in summary.rows:
        v, ch = summary_by_model.get(r.model, (0, 0))
        summary_by_model[r.model] = (v + r.claims_verified, ch + r.claims_changed)
    assert summary_by_model == from_reports
    (tmp_path / "e2e.json").write_text(json.dumps({"checked_at": datetime.now(UTC).isoformat(), "by_model": from_reports}))


def test_proxy_ttl_follows_half_life_and_bounds():
    from halflife.gateway.proxy import MAX_TTL_S, MIN_TTL_S, cache_key, ttl_seconds
    from halflife.schemas import VolatilityClass as V
    hl = {V.SOFTWARE_VERSION: (120.0, "prior_guess"), V.OFFICE_HOLDER: (900.0, "prior_guess"), V.PRICE: (0.0001, "fitted")}
    assert ttl_seconds(V.TIMELESS, hl) == MAX_TTL_S
    assert ttl_seconds(V.SOFTWARE_VERSION, hl) < ttl_seconds(V.OFFICE_HOLDER, hl)
    assert ttl_seconds(V.SOFTWARE_VERSION, hl) == int(-120 * __import__("math").log2(0.95) * 86400)
    assert ttl_seconds(V.PRICE, hl) == MIN_TTL_S
    body = {"model": "m", "messages": [{"role": "user", "content": "q"}]}
    a = cache_key(body, "sk-bf-a")
    assert a == cache_key(dict(body), "sk-bf-a") and a.startswith("halflife:")
    assert a != cache_key(body, "sk-bf-b")  # no cross-tenant sharing
    assert a != cache_key({**body, "temperature": 0.9}, "sk-bf-a")  # generation params are part of the key


def test_add_estimates_uses_only_the_random_sample_per_slice():
    from types import SimpleNamespace as NS

    from halflife.gateway.audit import add_estimates
    from halflife.schemas import StaleRateRow, VerdictLabel
    logs = [{"model": "m1", "virtual_key": "k1"}, {"model": "m2", "virtual_key": "k2"}]
    pool = [(0, 0, None, None), (0, 1, None, None), (1, 0, None, None), (1, 1, None, None)]
    ts = [0, 1, 2, 3]
    stratum_of = {0: 0, 1: 3, 2: 0, 3: 3}
    out = lambda lab: NS(verdict=NS(label=VerdictLabel(lab)))
    outcomes = {(0, 0): out("changed"), (0, 1): out("current"), (1, 0): out("current"), (1, 1): out("unverifiable")}
    rows = [StaleRateRow(model="m1", virtual_key="k1", answers_seen=1, answers_checked=1, claims_found=2, claims_verified=2,
                         claims_changed=1, stale_rate=0.5),
            StaleRateRow(model="m2", virtual_key="k2", answers_seen=1, answers_checked=1, claims_found=2, claims_verified=1,
                         claims_changed=0, stale_rate=0.0)]
    new, overall = add_estimates(rows, logs, pool, ts, stratum_of, [0, 1, 2, 3], outcomes, None)
    assert new[0].est_stale_rate == 0.5 and new[0].est_n_sampled == 2 and new[0].time_sensitive_claims == 2
    assert new[1].est_stale_rate == 0.0 and new[1].est_bounds_unverifiable == (0.0, 0.5)
    assert overall["time_sensitive_claims"] == 4 and overall["est_n_sampled"] == 4
