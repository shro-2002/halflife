"""J1 contract tests: schemas, fixture, clients against mocked HTTP. No network."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from halflife.clients.bifrost import BifrostClient, ModelError
from halflife.clients.fakes import FakeChat, FakeSearch
from halflife.clients.tavily import DiskCache, SearchError, TavilyViaRelay
from halflife.config import load_settings
from halflife.schemas import (
    AgeBasis,
    AnswerReport,
    Claim,
    ClaimReport,
    RiskScore,
    ScoreBasis,
    VerdictLabel,
    VolatilityClass,
)

FIXTURE = Path(__file__).parent / "fixtures" / "report.json"
BASE = "http://bifrost.test"


@pytest.fixture
def settings(tmp_path):
    s = load_settings()
    return replace(s, bifrost_url=BASE, virtual_key="sk-bf-test", admin_user="u", admin_password="p",
                   fallback_models=("anthropic/claude-haiku-4-5",), cache_dir=tmp_path / "tavily")


def test_fixture_validates_and_covers_every_verdict_and_basis():
    report = AnswerReport.model_validate_json(FIXTURE.read_text())
    labels = {c.verdict.label for c in report.claims if c.verdict}
    bases = {c.score_basis for c in report.claims}
    assert labels == set(VerdictLabel)
    assert bases == set(ScoreBasis)
    scored = [c.freshness_score for c in report.claims if c.freshness_score is not None]
    assert report.answer_score == pytest.approx(sum(scored) / len(scored), abs=0.1)


def _risk():
    return RiskScore(claim_id="x", age_days=1, age_basis=AgeBasis.MODEL_CUTOFF, half_life_days=None,
                     half_life_source="prior_guess", p_stale=0.0)


def test_timeless_claim_cannot_carry_a_score():
    claim = Claim(id="x", text="t", span="t", volatility_class=VolatilityClass.TIMELESS)
    with pytest.raises(ValidationError):
        ClaimReport(claim=claim, risk=_risk(), searched=False, freshness_score=50,
                    score_basis=ScoreBasis.NOT_TIME_SENSITIVE)


def test_verdict_requires_search():
    report = json.loads(FIXTURE.read_text())
    report["claims"][0]["searched"] = False
    with pytest.raises(ValidationError):
        AnswerReport.model_validate(report)


@respx.mock
async def test_chat_sends_vk_fallbacks_and_disables_reasoning(settings):
    route = respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(
        200, headers={"x-bifrost-request-id": "req-1", "x-bifrost-provider": "anthropic"},
        json={"choices": [{"message": {"content": "pong"}}], "usage": {"cost": {"total_cost": 4.1e-06}}}))
    bf = BifrostClient(settings)
    result = await bf.chat([{"role": "user", "content": "ping"}])
    await bf.aclose()
    sent = json.loads(route.calls[0].request.content)
    assert route.calls[0].request.headers["x-bf-vk"] == "sk-bf-test"
    assert sent["reasoning_effort"] == "none"
    assert sent["fallbacks"] == ["anthropic/claude-haiku-4-5"]
    assert (result.text, result.request_id, result.cost_usd) == ("pong", "req-1", 4.1e-06)


@respx.mock
async def test_chat_empty_completion_raises(settings):
    respx.post(f"{BASE}/v1/chat/completions").mock(return_value=httpx.Response(
        200, json={"choices": [{"message": {"content": None}, "finish_reason": "length"}]}))
    bf = BifrostClient(settings)
    with pytest.raises(ModelError, match="length"):
        await bf.chat([{"role": "user", "content": "x"}])
    await bf.aclose()


@respx.mock
async def test_search_hits_relay_once_then_disk_cache(settings):
    route = respx.post(f"{BASE}/relay/tavily/search").mock(return_value=httpx.Response(
        200, json={"results": [{"url": "https://python.org", "content": "Python 3.14"}]}))
    bf = BifrostClient(settings)
    tavily = TavilyViaRelay(bf, "tavily", DiskCache(settings.cache_dir))
    first = await tavily.search("python latest", time_range="year")
    second = await tavily.search("python latest", time_range="year")
    await bf.aclose()
    assert route.call_count == 1
    assert (first.from_cache, first.credits) == (False, 1)
    assert (second.from_cache, second.credits) == (True, 0)


async def test_offline_search_never_calls_relay(settings):
    tavily = TavilyViaRelay(BifrostClient(settings), "tavily", DiskCache(settings.cache_dir), offline=True)
    with pytest.raises(SearchError, match="offline"):
        await tavily.search("uncached query")


def test_disk_cache_key_depends_on_day():
    payload = {"query": "q"}
    a = DiskCache.key(payload, datetime(2026, 11, 12, tzinfo=UTC).date())
    b = DiskCache.key(payload, datetime(2026, 11, 13, tzinfo=UTC).date())
    assert a != b


async def test_fakes_are_scriptable():
    chat = FakeChat(["one", ModelError("boom")])
    assert (await chat.chat([{"role": "user", "content": "a"}])).text == "one"
    with pytest.raises(ModelError):
        await chat.chat([{"role": "user", "content": "b"}])
    search = FakeSearch({"python": [{"url": "u", "content": "c"}]})
    assert (await search.search("Python version")).results == [{"url": "u", "content": "c"}]
    assert (await search.search("other")).results == []
