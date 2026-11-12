"""Claim extraction (T1/T2): one model call per answer, validated in code, fail open.

The same call returns p_outdated_model, the default verification ranking signal (J0.5).
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from halflife.clients.bifrost import ChatModel, ModelError
from halflife.schemas import Claim, VolatilityClass

MAX_CLAIMS = 20
# Haiku 5.5 counts reasoning toward output tokens; 20 claims of JSON is ~2k tokens.
MAX_TOKENS = 2500
_CLASSES = {c.value for c in VolatilityClass}

SYSTEM_PROMPT = """You extract factual claims from an AI assistant's answer so they can be checked for staleness.

Return JSON only: a list (possibly empty) of objects with exactly these fields:
- "text": the claim restated as a standalone sentence (resolve pronouns).
- "span": an EXACT, verbatim substring of the answer the claim came from. Copy characters exactly; do not paraphrase.
- "volatility_class": one of
  "software_version" (latest/current versions, API versions, release status, deprecations),
  "price" (prices, fees, subscription costs, pricing tiers),
  "rate_or_statistic" (interest/exchange/tax rates, populations, rankings, counts, market shares),
  "office_holder" (who currently holds a role: CEO, president, minister, maintainer),
  "law_or_regulation" (laws, regulations, limits, legal status, policies in force),
  "product_spec" (product features, specs, limits, availability, model line-ups),
  "timeless" (facts that do not change: physics, maths, definitions, settled history).
- "explicit_date": ISO date (YYYY-MM-DD) if the claim states its own as-of or event date, else null. Year only -> YYYY-01-01.
- "is_past_event": true if the claim reports a dated past event ("became CEO in 2021", "was released in March 2023") rather than a current state. Keep the tense of the answer: a dated past event is NOT a claim about who or what is current.
- "subject": the entity the claim is about (short, good for a web search), or null.
- "authoritative_domain": the official website for checking it if obvious (e.g. "python.org"), else null.
- "p_outdated_model": the probability the claim is no longer accurate today ({today}), given it was accurate as of {as_of}. A number from 0 to 1. Use 0 for timeless claims.

Rules: one fact per claim. Skip opinions, advice, instructions, hedges and questions; they are not claims.
If nothing in the answer is a factual claim, return []."""


@dataclass(frozen=True)
class ExtractResult:
    claims: list[Claim]
    errors: list[str] = field(default_factory=list)
    model_calls: int = 0
    request_id: str | None = None


def build_messages(answer: str, *, as_of: date, today: date) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT.format(as_of=as_of.isoformat(), today=today.isoformat())
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Answer to analyse:\n<answer>\n{answer}\n</answer>\nReturn the JSON list only."},
    ]


async def extract_claims(answer: str, model: ChatModel, *, as_of: date, today: date) -> ExtractResult:
    if not answer.strip():
        return ExtractResult(claims=[])
    try:
        result = await model.chat(build_messages(answer, as_of=as_of, today=today), max_tokens=MAX_TOKENS)
    except ModelError as err:
        return ExtractResult(claims=[], errors=[f"extract: model error: {err}"], model_calls=1)
    items = parse_json_list(result.text)
    if items is None:
        return ExtractResult(claims=[], errors=[f"extract: malformed JSON: {result.text[:120]!r}"],
                             model_calls=1, request_id=result.request_id)
    claims, errors = validate_items(items, answer)
    return ExtractResult(claims=claims, errors=errors, model_calls=1, request_id=result.request_id)


def parse_json_list(text: str) -> list[Any] | None:
    """First JSON list (or {"claims": [...]}) in text; tolerates ``` fences and leading prose."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[\[{]", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("claims"), list):
            return value["claims"]
    return None


def validate_items(items: list[Any], answer: str) -> tuple[list[Claim], list[str]]:
    claims: list[Claim] = []
    errors: list[str] = []
    seen_spans: set[str] = set()
    for i, item in enumerate(items):
        if len(claims) >= MAX_CLAIMS:
            errors.append(f"extract: capped at {MAX_CLAIMS} claims, dropped {len(items) - i} more")
            break
        claim_or_error = _to_claim(item, answer, claim_id=f"c{len(claims) + 1}")
        if isinstance(claim_or_error, str):
            errors.append(f"extract: item {i}: {claim_or_error}")
            continue
        if claim_or_error.span in seen_spans:
            continue
        seen_spans.add(claim_or_error.span)
        claims.append(claim_or_error)
    return claims, errors


def _to_claim(item: Any, answer: str, *, claim_id: str) -> Claim | str:
    if not isinstance(item, dict):
        return "not an object"
    span = _locate_span(item.get("span"), answer)
    if span is None:
        return f"span not in answer: {str(item.get('span'))[:80]!r}"
    vclass = item.get("volatility_class")
    if vclass not in _CLASSES:
        return f"unknown volatility_class {vclass!r}"
    text = item.get("text")
    text = text.strip() if isinstance(text, str) and text.strip() else span
    p = 0.0 if vclass == VolatilityClass.TIMELESS.value else _probability(item.get("p_outdated_model"))
    try:
        return Claim(
            id=claim_id,
            text=text,
            span=span,
            volatility_class=vclass,
            explicit_date=_iso_date(item.get("explicit_date")),
            is_past_event=item.get("is_past_event") is True,
            subject=_opt_str(item.get("subject")),
            authoritative_domain=_opt_str(item.get("authoritative_domain")),
            p_outdated_model=p,
        )
    except ValidationError as err:
        return f"invalid claim: {err.errors()[0]['msg']}"


def _locate_span(span: Any, answer: str) -> str | None:
    """Exact substring, else a whitespace-normalised match mapped back to the answer's own text."""
    if not isinstance(span, str) or not span.strip():
        return None
    span = span.strip()
    if span in answer:
        return span
    pattern = r"\s+".join(re.escape(tok) for tok in span.split())
    match = re.search(pattern, answer)
    return match.group(0) if match else None


def _probability(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if p != p:  # NaN
        return None
    return min(1.0, max(0.0, p))


def _iso_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"\d{4}", value):
        value += "-01-01"
    elif re.fullmatch(r"\d{4}-\d{2}", value):
        value += "-01"
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _opt_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
