"""Pipeline tests with fake model and search. No network."""

import json
from datetime import date

import pytest

from halflife.clients.fakes import FakeChat, FakeSearch
from halflife.clients.tavily import SearchError
from halflife.pipeline import CheckOptions, check_answer, rescore_aged
from halflife.schemas import ScoreBasis, VerdictLabel

TODAY = date(2026, 11, 12)
OPTS = CheckOptions(as_of=date(2026, 6, 30), today=TODAY)
ANSWER = "Python's latest release is 3.12. The ECB deposit rate is 4.00%. Water boils at 100 C."


def claims_json(p_python=0.9, p_ecb=0.4):
    return json.dumps([
        {"text": "Python's latest release is 3.12.", "span": "Python's latest release is 3.12.",
         "volatility_class": "software_version", "subject": "Python latest release",
         "authoritative_domain": "python.org", "p_outdated_model": p_python},
        {"text": "The ECB deposit rate is 4.00%.", "span": "The ECB deposit rate is 4.00%.",
         "volatility_class": "rate_or_statistic", "subject": "ECB deposit rate", "p_outdated_model": p_ecb},
        {"text": "Water boils at 100 C.", "span": "Water boils at 100 C.", "volatility_class": "timeless"},
    ])


PY_EVIDENCE = [{"url": "https://www.python.org/downloads/", "title": "Downloads",
                "content": "Download the latest release: Python 3.15.0 for Windows, macOS and Linux."}]


def judge(messages):
    text = messages[-1]["content"]
    if "Python" in text:
        return json.dumps({"label": "changed", "supports": [{"url": PY_EVIDENCE[0]["url"],
                           "quote": "Download the latest release: Python 3.15.0"}],
                           "current_value": "Python 3.15.0", "reasoning": "newer release listed"})
    return json.dumps({"label": "unverifiable", "supports": [], "current_value": None, "reasoning": "no data"})


def scripted(extract_output: str):
    first = {"done": False}

    def respond(messages):
        if not first["done"]:
            first["done"] = True
            return extract_output
        return judge(messages)
    return FakeChat(respond)


async def test_check_mode_verifies_every_time_sensitive_claim_and_skips_timeless():
    search = FakeSearch({"python": PY_EVIDENCE})
    report = await check_answer(ANSWER, model=scripted(claims_json()), searcher=search, opts=OPTS)
    by_text = {c.claim.text: c for c in report.claims}
    py = by_text["Python's latest release is 3.12."]
    assert py.verdict.label is VerdictLabel.CHANGED and py.freshness_score == 5
    assert py.risk.rank_basis == "model_p" and py.risk.rank_score == 0.9
    water = by_text["Water boils at 100 C."]
    assert water.searched is False and water.score_basis is ScoreBasis.NOT_TIME_SENSITIVE
    assert report.usage.model_calls >= 2 and report.answer_score is not None


async def test_budget_takes_highest_model_probability_first():
    search = FakeSearch({"python": PY_EVIDENCE})
    report = await check_answer(ANSWER, model=scripted(claims_json(p_python=0.2, p_ecb=0.8)), searcher=search,
                                opts=CheckOptions(as_of=OPTS.as_of, today=TODAY, budget=1))
    searched = [c.claim.text for c in report.claims if c.searched]
    assert searched == ["The ECB deposit rate is 4.00%."]
    estimated = [c for c in report.claims if c.score_basis is ScoreBasis.ESTIMATED]
    assert [c.claim.text for c in estimated] == ["Python's latest release is 3.12."]


async def test_falls_back_to_half_life_when_model_gives_no_probability():
    out = json.loads(claims_json())
    for c in out:
        c.pop("p_outdated_model", None)
    report = await check_answer(ANSWER, model=scripted(json.dumps(out)), searcher=FakeSearch(), opts=OPTS)
    ts = [c for c in report.claims if c.claim.volatility_class.value != "timeless"]
    assert all(c.risk.rank_basis == "half_life" and c.risk.rank_score == c.risk.p_stale for c in ts)


async def test_both_searches_failing_stays_valid_and_scores_unverified():
    boom = SearchError("relay down")
    search = FakeSearch({"python": boom, "ecb": boom})
    report = await check_answer(ANSWER, model=scripted(claims_json()), searcher=search, opts=OPTS)
    for c in report.claims:
        if c.claim.volatility_class.value != "timeless":
            assert c.verdict is None and c.errors
            assert c.score_basis in (ScoreBasis.UNVERIFIED, ScoreBasis.ESTIMATED)


async def test_past_event_is_not_time_sensitive():
    answer = "Tim Cook became CEO of Apple in 2011."
    out = json.dumps([{"text": answer, "span": answer, "volatility_class": "office_holder",
                       "is_past_event": True, "explicit_date": "2011-08-24", "p_outdated_model": 0.0}])
    report = await check_answer(answer, model=scripted(out), searcher=FakeSearch(), opts=OPTS)
    (c,) = report.claims
    assert c.searched is False and c.score_basis is ScoreBasis.NOT_TIME_SENSITIVE and c.risk.p_stale == 0


async def test_malformed_extraction_fails_open():
    report = await check_answer(ANSWER, model=FakeChat(["not json at all"]), searcher=FakeSearch(), opts=OPTS)
    assert report.claims == [] and report.errors and report.answer_score is None


async def test_rescore_aged_lowers_estimated_scores_without_calls():
    search = FakeSearch({"python": PY_EVIDENCE})
    report = await check_answer(ANSWER, model=scripted(claims_json(p_python=0.2, p_ecb=0.8)), searcher=search,
                                opts=CheckOptions(as_of=OPTS.as_of, today=TODAY, budget=1))
    later = rescore_aged(report, today=date(2027, 6, 1))
    before = {c.claim.id: c.freshness_score for c in report.claims if c.score_basis is ScoreBasis.ESTIMATED}
    after = {c.claim.id: c.freshness_score for c in later.claims if c.claim.id in before}
    assert before and all(after[k] < before[k] for k in before)


@pytest.mark.live
async def test_live_check_through_bifrost_and_tavily():
    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay
    from halflife.config import load_settings
    s = load_settings()
    bf = BifrostClient(s)
    report = await check_answer("The Bank of England base rate is 5.25%.", model=bf,
                                searcher=TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir)),
                                opts=CheckOptions(as_of=s.model_cutoff, today=TODAY))
    await bf.aclose()
    assert report.claims and report.claims[0].searched


def test_api_requires_key_when_configured_and_rate_limits(monkeypatch):
    from fastapi.testclient import TestClient

    import halflife.api as api
    monkeypatch.setenv("HALFLIFE_API_KEY", "k-test")
    monkeypatch.setattr(api, "RATE_LIMIT_PER_MIN", 2)
    api._hits.clear()
    api._fails.clear()

    async def fake_check(answer, **_):
        from halflife.schemas import AnswerReport
        return AnswerReport.model_validate_json(open("tests/fixtures/report.json").read())
    monkeypatch.setattr(api, "check_answer", fake_check)
    with TestClient(api.app) as client:
        assert client.post("/v1/check", json={"answer": "x"}).status_code == 401
        ok = {"x-halflife-key": "k-test"}
        assert client.post("/v1/check", json={"answer": "x"}, headers=ok).status_code == 200
        assert client.post("/v1/check", json={"answer": "x"}, headers=ok).status_code == 200
        assert client.post("/v1/check", json={"answer": "x"}, headers=ok).status_code == 429
        for _ in range(api.FAILED_AUTH_PER_MIN):
            client.post("/v1/check", json={"answer": "x"}, headers={"x-halflife-key": "wrong"})
        assert client.post("/v1/check", json={"answer": "x"}, headers={"x-halflife-key": "wrong"}).status_code == 429
