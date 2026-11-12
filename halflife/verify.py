"""Verify ONE claim against Tavily evidence (requirement T3).

Two searches in parallel (open web with a recency filter, plus the claim's authoritative domain
when known), then one judge call. Ground rule 2 is enforced here in code, not trusted to the
model: every supporting quote must be a verbatim (whitespace/case-normalised) substring of the
evidence content Tavily returned for that URL, or it is dropped. Fails open: never raises.
"""

import asyncio
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

from halflife.clients.bifrost import ChatModel, ModelError
from halflife.clients.tavily import Searcher, SearchResult
from halflife.schemas import Claim, Evidence, Verdict, VerdictLabel, VolatilityClass

JUDGE_MAX_TOKENS = 1500
SEARCH_SHARE = 0.6  # fraction of timeout_s the parallel searches may use; the judge gets the rest
MIN_QUOTE_CHARS = 8  # shorter "quotes" match almost anything
MAX_QUERY_CHARS = 380  # Tavily rejects queries over 400 chars
OPEN_WEB_PARAMS: dict[str, Any] = {
    "topic": "general",
    "time_range": "year",
    "search_depth": "basic",
    "max_results": 5,
    "include_published_date": True,
}
_PUNCT = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})

JUDGE_SYSTEM = """You check whether a factual claim is still true today, using ONLY the evidence given.
Reply with one JSON object and nothing else:
{"label": "current" | "changed" | "unverifiable",
 "supports": [{"url": "<evidence url>", "quote": "<exact text copied from that evidence>"}],
 "current_value": "<just the new value, e.g. 3.15 or a name, only if label is changed, else null>",
 "reasoning": "<two sentences at most>"}
Rules: copy quotes character for character from the evidence content (no paraphrase, no ellipses).
"current" = evidence states the claim still holds; "changed" = evidence states a different current
value; otherwise "unverifiable". Do not use your own knowledge."""


@dataclass(frozen=True)
class VerifyOutcome:
    evidence: list[Evidence]
    verdict: Verdict | None  # None only if no search succeeded
    strong_support: bool  # CURRENT backed by an authoritative source or two independent domains
    errors: list[str] = field(default_factory=list)
    searches: int = 0
    credits: int = 0
    cache_hits: int = 0
    model_calls: int = 0


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_PUNCT)
    return " ".join(text.lower().split())


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _on_domain(url: str, domain: str | None) -> bool:
    if not domain:
        return False
    host, want = _domain(url), domain.lower().removeprefix("www.")
    return host == want or host.endswith("." + want)


def build_query(claim: Claim, today: date) -> str:
    base = f"{claim.subject}: {claim.text}" if claim.subject else claim.text
    return f"{base[:MAX_QUERY_CHARS]} (as of {today.year})"


def _to_evidence(result: SearchResult, query: str, *, authoritative: bool, domain: str | None) -> list[Evidence]:
    now = datetime.now(UTC)
    out = []
    for r in result.results:
        url, content = r.get("url"), r.get("content")
        if not url or not content:
            continue
        out.append(Evidence(
            url=url, title=r.get("title") or "", content=content, published_date=r.get("published_date"),
            query=query, is_authoritative=authoritative or _on_domain(url, domain), retrieved_at=now,
        ))
    return out


def _dedupe(items: list[Evidence]) -> list[Evidence]:
    """First occurrence wins, except an authoritative copy replaces a non-authoritative one."""
    by_url: dict[str, Evidence] = {}
    for ev in items:
        if ev.url not in by_url or (ev.is_authoritative and not by_url[ev.url].is_authoritative):
            by_url[ev.url] = ev
    return list(by_url.values())


async def _search_all(claim: Claim, searcher: Searcher, query: str, timeout: float) -> tuple[list, list[str]]:
    jobs: list[tuple[str, bool, dict[str, Any]]] = [("open-web", False, dict(OPEN_WEB_PARAMS))]
    if claim.authoritative_domain:
        jobs.append(("authoritative", True, {**OPEN_WEB_PARAMS, "include_domains": [claim.authoritative_domain]}))

    async def one(params: dict[str, Any]) -> SearchResult:
        return await asyncio.wait_for(searcher.search(query, **params), timeout)

    raw = await asyncio.gather(*(one(p) for _, _, p in jobs), return_exceptions=True)
    done, errors = [], []
    for (name, authoritative, _), res in zip(jobs, raw, strict=True):
        if isinstance(res, SearchResult):
            done.append((res, authoritative))
        elif isinstance(res, TimeoutError):
            errors.append(f"search {name}: timed out after {timeout:.1f}s")
        else:  # SearchError or anything else the searcher raised: fail open
            errors.append(f"search {name}: {res}")
    return done, errors


def _judge_messages(claim: Claim, evidence: list[Evidence], today: date) -> list[dict[str, str]]:
    blocks = "\n\n".join(
        f"[{i}] url: {ev.url}\npublished: {ev.published_date or 'unknown'}\ncontent: {ev.content}"
        for i, ev in enumerate(evidence, 1)
    )
    user = f"Today is {today.isoformat()}.\nClaim: {claim.text}\n\nEvidence:\n{blocks}"
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def _parse_judge(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("judge returned no JSON object")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("judge JSON is not an object")
    return data


def _verified_supports(supports: Any, evidence: list[Evidence]) -> list[tuple[str, str]]:
    """Keep (url, quote) pairs whose URL is in the evidence and whose quote is in that URL's content."""
    content = {ev.url: _norm(ev.content) for ev in evidence}
    kept = []
    for s in supports if isinstance(supports, list) else []:
        if not isinstance(s, dict):
            continue
        url, quote = s.get("url"), s.get("quote")
        if not isinstance(url, str) or not isinstance(quote, str) or url not in content:
            continue
        q = _norm(quote).strip(" \"'")
        if len(q) >= MIN_QUOTE_CHARS and q in content[url]:
            kept.append((url, quote.strip()))
    return kept


def _verdict_from_judge(claim: Claim, data: dict[str, Any], evidence: list[Evidence]) -> Verdict:
    label = VerdictLabel(str(data.get("label", "")).strip().lower())  # ValueError on unknown label
    supports = _verified_supports(data.get("supports"), evidence)
    if label is not VerdictLabel.UNVERIFIABLE and not supports:
        label = VerdictLabel.UNVERIFIABLE
    value = data.get("current_value")
    keep_value = (
        label is VerdictLabel.CHANGED and isinstance(value, str) and value.strip()
        and any(_norm(value) in _norm(q) for _, q in supports)
    )
    return Verdict(
        claim_id=claim.id,
        label=label,
        supporting_quote=supports[0][1] if supports else None,
        supporting_url=supports[0][0] if supports else None,
        current_value=value.strip() if keep_value else None,
        source_urls=list(dict.fromkeys(u for u, _ in supports)),
        reasoning=str(data.get("reasoning") or ""),
        quote_verified=bool(supports),
    )


def _unverifiable(claim: Claim, reason: str) -> Verdict:
    return Verdict(claim_id=claim.id, label=VerdictLabel.UNVERIFIABLE, reasoning=reason)


def _is_strong(verdict: Verdict, evidence: list[Evidence]) -> bool:
    if verdict.label is not VerdictLabel.CURRENT or not verdict.quote_verified:
        return False
    by_url = {ev.url: ev for ev in evidence}
    backing = [by_url[u] for u in verdict.source_urls if u in by_url]
    return any(ev.is_authoritative for ev in backing) or len({_domain(ev.url) for ev in backing}) >= 2


async def _judge(claim: Claim, evidence: list[Evidence], model: ChatModel, today: date,
                 timeout: float) -> tuple[Verdict, str | None]:
    try:
        result = await asyncio.wait_for(
            model.chat(_judge_messages(claim, evidence, today), max_tokens=JUDGE_MAX_TOKENS), timeout)
        return _verdict_from_judge(claim, _parse_judge(result.text), evidence), None
    except TimeoutError:
        err = f"judge: timed out after {timeout:.1f}s"
    except ModelError as e:
        err = f"judge: {e}"
    except (ValueError, TypeError) as e:  # json.JSONDecodeError is a ValueError; so is an unknown label
        err = f"judge: unusable output ({e})"
    except Exception as e:  # noqa: BLE001 - fail open: a verify call never raises
        err = f"judge: {type(e).__name__}: {e}"
    return _unverifiable(claim, err), err


async def verify_claim(claim: Claim, model: ChatModel, searcher: Searcher, *, today: date,
                       timeout_s: float = 25.0) -> VerifyOutcome:
    if claim.volatility_class is VolatilityClass.TIMELESS:
        return VerifyOutcome(evidence=[], verdict=None, strong_support=False)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    query = build_query(claim, today)
    done, errors = await _search_all(claim, searcher, query, timeout_s * SEARCH_SHARE)
    searches = 2 if claim.authoritative_domain else 1
    credits = sum(r.credits for r, _ in done)
    cache_hits = sum(r.from_cache for r, _ in done)
    evidence = _dedupe([ev for r, auth in done for ev in _to_evidence(
        r, query, authoritative=auth, domain=claim.authoritative_domain)])
    counts = {"searches": searches, "credits": credits, "cache_hits": cache_hits}
    if not done:
        return VerifyOutcome(evidence=[], verdict=None, strong_support=False, errors=errors, **counts)
    if not evidence:
        verdict = _unverifiable(claim, "searches returned no evidence")
        return VerifyOutcome(evidence=[], verdict=verdict, strong_support=False, errors=errors, **counts)
    verdict, err = await _judge(claim, evidence, model, today, max(deadline - loop.time(), 0.1))
    errors += [err] if err else []
    return VerifyOutcome(evidence=evidence, verdict=verdict, strong_support=_is_strong(verdict, evidence),
                         errors=errors, model_calls=1, **counts)
