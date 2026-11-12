"""T3 verify_claim: offline with FakeChat/FakeSearch, plus one live test (deselected by default)."""

import asyncio
import json
from datetime import UTC, date, datetime
from typing import Any

import pytest

from halflife.clients.fakes import FakeChat, FakeSearch
from halflife.clients.tavily import SearchError, SearchResult
from halflife.schemas import Claim, VerdictLabel, VolatilityClass
from halflife.verify import verify_claim

TODAY = date(2026, 11, 12)
PY_DOC = {"url": "https://www.python.org/downloads/", "title": "Downloads",
          "content": "The latest  stable release is Python 3.14.1, released in October 2026.",
          "published_date": "2026-10-15"}
BLOG_DOC = {"url": "https://blog.example.com/python", "title": "Blog",
            "content": "Python 3.14 is now the current stable version of the language."}
NEWS_DOC = {"url": "https://news.other.org/py", "title": "News",
            "content": "Developers can download Python 3.14.1, the newest stable release."}


def claim(domain: str | None = "python.org", cls: VolatilityClass = VolatilityClass.SOFTWARE_VERSION) -> Claim:
    return Claim(id="c1", text="The latest stable Python version is 3.12.", span="3.12", volatility_class=cls,
                 subject="Python", authoritative_domain=domain)


def judge(label: str, supports: list[dict[str, str]], value: str | None = None) -> str:
    return json.dumps({"label": label, "supports": supports, "current_value": value, "reasoning": "because"})


def search_by_domain(open_web: list[dict[str, Any]], auth: list[dict[str, Any]] | None = None) -> "RoutedSearch":
    return RoutedSearch(open_web, auth or [])


class RoutedSearch:
    """Returns different results for the open-web and the domain-restricted search."""

    def __init__(self, open_web: Any, auth: Any) -> None:
        self.open_web, self.auth = open_web, auth
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def search(self, query: str, **params: Any) -> SearchResult:
        self.queries.append((query, params))
        out = self.auth if "include_domains" in params else self.open_web
        if isinstance(out, Exception):
            raise out
        if isinstance(out, float):
            await asyncio.sleep(out)
            out = []
        return SearchResult({"query": query, **params}, out, False, 1, 1.0)


async def run(chat_script: list[Any], searcher: Any, c: Claim | None = None, **kw: Any):
    model = FakeChat(chat_script)
    return await verify_claim(c or claim(), model, searcher, today=TODAY, **kw), model


async def test_verbatim_quote_with_whitespace_and_case_drift_is_verified():
    quote = "the latest stable release is python 3.14.1"  # source has a double space and capitals
    out, _ = await run([judge("changed", [{"url": PY_DOC["url"], "quote": quote}], "3.14.1")],
                       search_by_domain([BLOG_DOC], [PY_DOC]))
    assert out.verdict.label is VerdictLabel.CHANGED
    assert out.verdict.quote_verified and out.verdict.supporting_url == PY_DOC["url"]
    assert out.verdict.current_value == "3.14.1"
    assert out.verdict.reasoning == "because" and out.errors == []


async def test_paraphrased_quote_is_dropped_and_label_becomes_unverifiable():
    out, _ = await run([judge("current", [{"url": PY_DOC["url"], "quote": "Python 3.12 is the newest release"}])],
                       search_by_domain([], [PY_DOC]))
    assert out.verdict.label is VerdictLabel.UNVERIFIABLE
    assert not out.verdict.quote_verified and out.verdict.supporting_quote is None
    assert not out.strong_support


async def test_fabricated_url_is_dropped_even_with_real_quote_text():
    real_text = "The latest  stable release is Python 3.14.1"
    supports = [{"url": "https://made-up.example/x", "quote": real_text},
                {"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"}]
    out, _ = await run([judge("changed", supports, "3.14")], search_by_domain([BLOG_DOC], [PY_DOC]))
    assert out.verdict.source_urls == [BLOG_DOC["url"]]
    assert "https://made-up.example/x" not in out.verdict.source_urls


async def test_changed_value_absent_from_verified_quotes_is_nulled():
    supports = [{"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"}]
    out, _ = await run([judge("changed", supports, "3.15")], search_by_domain([BLOG_DOC]))
    assert out.verdict.label is VerdictLabel.CHANGED
    assert out.verdict.current_value is None


async def test_current_value_is_dropped_for_non_changed_labels():
    supports = [{"url": PY_DOC["url"], "quote": "stable release is Python 3.14.1"}]
    out, _ = await run([judge("current", supports, "3.14.1")], search_by_domain([], [PY_DOC]))
    assert out.verdict.current_value is None


async def test_authoritative_support_gives_strong_support():
    supports = [{"url": PY_DOC["url"], "quote": "stable release is Python 3.14.1"}]
    out, _ = await run([judge("current", supports)], search_by_domain([BLOG_DOC], [PY_DOC]))
    assert out.verdict.label is VerdictLabel.CURRENT and out.strong_support
    assert next(e for e in out.evidence if e.url == PY_DOC["url"]).is_authoritative


async def test_two_independent_domains_give_strong_support():
    supports = [{"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"},
                {"url": NEWS_DOC["url"], "quote": "download Python 3.14.1, the newest stable release"}]
    out, _ = await run([judge("current", supports)], search_by_domain([BLOG_DOC, NEWS_DOC]), claim(domain=None))
    assert out.strong_support


async def test_one_non_authoritative_source_is_not_strong():
    supports = [{"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"}]
    out, _ = await run([judge("current", supports)], search_by_domain([BLOG_DOC]), claim(domain=None))
    assert out.verdict.label is VerdictLabel.CURRENT and not out.strong_support


async def test_one_search_errors_other_succeeds():
    supports = [{"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"}]
    out, _ = await run([judge("changed", supports, "3.14")],
                       search_by_domain([BLOG_DOC], SearchError("relay 502")))
    assert out.verdict.label is VerdictLabel.CHANGED
    assert any("authoritative" in e and "relay 502" in e for e in out.errors)
    assert out.searches == 2 and out.credits == 1


async def test_both_searches_fail_gives_no_verdict_and_no_model_call():
    out, model = await run([], search_by_domain(SearchError("down"), SearchError("down")))
    assert out.verdict is None and len(out.errors) == 2
    assert out.model_calls == 0 and model.calls == []


async def test_search_timeout_is_recorded_and_other_search_used():
    supports = [{"url": PY_DOC["url"], "quote": "stable release is Python 3.14.1"}]
    out, _ = await run([judge("current", supports)], search_by_domain(5.0, [PY_DOC]), timeout_s=0.5)
    assert any("open-web" in e and "timed out" in e for e in out.errors)
    assert out.verdict.label is VerdictLabel.CURRENT


@pytest.mark.parametrize("reply", ["not json at all", '{"label": "probably", "supports": []}', "[1, 2]"])
async def test_unusable_judge_output_gives_unverifiable_with_error(reply):
    out, _ = await run([reply], search_by_domain([BLOG_DOC]))
    assert out.verdict.label is VerdictLabel.UNVERIFIABLE
    assert any(e.startswith("judge:") for e in out.errors) and out.model_calls == 1


async def test_judge_model_error_gives_unverifiable():
    from halflife.clients.bifrost import ModelError

    out, _ = await run([ModelError("bifrost 503")], search_by_domain([BLOG_DOC]))
    assert out.verdict.label is VerdictLabel.UNVERIFIABLE
    assert any("bifrost 503" in e for e in out.errors)


async def test_judge_reply_in_code_fence_is_parsed():
    supports = [{"url": BLOG_DOC["url"], "quote": "Python 3.14 is now the current stable version"}]
    out, _ = await run(["```json\n" + judge("current", supports) + "\n```"], search_by_domain([BLOG_DOC]))
    assert out.verdict.label is VerdictLabel.CURRENT


async def test_both_searches_issued_with_domain_filter_only_on_second():
    searcher = FakeSearch({"python": [BLOG_DOC]})
    await run([judge("unverifiable", [])], searcher)
    assert len(searcher.queries) == 2
    params = [p for _, p in searcher.queries]
    assert sum("include_domains" in p for p in params) == 1
    assert next(p for p in params if "include_domains" in p)["include_domains"] == ["python.org"]
    # Recency filter on the open web only; the official-site search has none (V2: prices/rates keep old dates).
    assert [p.get("time_range") for p in params] == ["year", None]
    assert all("2026" in q for q, _ in searcher.queries)


async def test_no_domain_issues_single_search_without_filter():
    searcher = FakeSearch({"python": [BLOG_DOC]})
    out, _ = await run([judge("unverifiable", [])], searcher, claim(domain=None))
    assert len(searcher.queries) == 1 and "include_domains" not in searcher.queries[0][1]
    assert out.searches == 1


async def test_searches_run_in_parallel():
    started = datetime.now(UTC)
    await verify_claim(claim(), FakeChat([judge("unverifiable", [])]), search_by_domain(0.3, 0.3), today=TODAY)
    assert (datetime.now(UTC) - started).total_seconds() < 0.55


async def test_duplicate_urls_are_merged_keeping_authoritative_copy():
    out, _ = await run([judge("unverifiable", [])], search_by_domain([PY_DOC, BLOG_DOC], [PY_DOC]))
    urls = [e.url for e in out.evidence]
    assert len(urls) == len(set(urls)) == 2
    assert next(e for e in out.evidence if e.url == PY_DOC["url"]).is_authoritative


async def test_empty_results_give_unverifiable_without_model_call():
    out, model = await run([], search_by_domain([], []))
    assert out.verdict.label is VerdictLabel.UNVERIFIABLE and model.calls == []


async def test_timeless_claim_is_not_searched():
    searcher = FakeSearch()
    out, model = await run([], searcher, claim(cls=VolatilityClass.TIMELESS))
    assert out.verdict is None and out.errors == [] and searcher.queries == [] and model.calls == []


@pytest.mark.live
async def test_live_two_claims_through_bifrost_and_tavily_relay():
    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay
    from halflife.config import load_settings

    settings = load_settings()
    bf = BifrostClient(settings)
    searcher = TavilyViaRelay(bf, settings.relay_name, DiskCache(settings.cache_dir))
    claims = [
        Claim(id="py", text="The latest stable Python release is Python 3.12.", span="3.12", subject="Python",
              volatility_class=VolatilityClass.SOFTWARE_VERSION, authoritative_domain="python.org"),
        Claim(id="un", text="The Secretary-General of the United Nations is António Guterres.", span="Guterres",
              subject="UN Secretary-General", volatility_class=VolatilityClass.OFFICE_HOLDER,
              authoritative_domain="un.org"),
    ]
    try:
        for c in claims:
            out = await verify_claim(c, bf, searcher, today=datetime.now(UTC).date(), timeout_s=60)
            v = out.verdict
            print(f"\n[{c.id}] label={v and v.label.value} strong={out.strong_support} value={v and v.current_value}"
                  f"\n  quote={v and v.supporting_quote!r}\n  url={v and v.supporting_url}"
                  f"\n  evidence={len(out.evidence)} searches={out.searches} credits={out.credits}"
                  f" cache_hits={out.cache_hits} model_calls={out.model_calls} errors={out.errors}"
                  f"\n  reasoning={v and v.reasoning}")
            assert v is not None
            if v.label is not VerdictLabel.UNVERIFIABLE:
                assert v.quote_verified and v.supporting_url in {e.url for e in out.evidence}
    finally:
        await bf.aclose()
