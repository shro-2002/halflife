"""One pipeline for both modes: extract -> risk -> rank -> verify (budgeted) -> score -> report.

Ranking (J0.5 decision): the extractor's p_outdated_model orders the verification budget; the
half-life P(stale) is the fallback when the model gave no probability, and is always reported
(it drives cache TTL and re-scoring of aged cached answers without a model call).
"""

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from halflife.clients.bifrost import ChatModel
from halflife.clients.tavily import Searcher
from halflife.extract import extract_claims
from halflife.risk import answer_score, freshness_score, p_stale, recommended_ttl_days
from halflife.schemas import (
    PRIOR_HALF_LIFE_DAYS,
    AgeBasis,
    AnswerReport,
    Claim,
    ClaimReport,
    RiskScore,
    ScoreBasis,
    Usage,
    VerdictLabel,
    VolatilityClass,
)
from halflife.verify import VerifyOutcome, verify_claim

HalfLives = Mapping[VolatilityClass, tuple[float, Literal["prior_guess", "fitted"]]]
VERIFY_CONCURRENCY = 4


def prior_half_lives() -> dict[VolatilityClass, tuple[float, Literal["prior_guess", "fitted"]]]:
    return {cls: (h, "prior_guess") for cls, h in PRIOR_HALF_LIFE_DAYS.items()}


@dataclass(frozen=True)
class CheckOptions:
    as_of: date  # date the answer's information is current as of
    today: date
    age_basis: AgeBasis = AgeBasis.MODEL_CUTOFF
    budget: int | None = None  # max claims to search; None = every time-sensitive claim (check mode)
    mode: Literal["check", "gateway"] = "check"
    answer_model: str | None = None
    request_id: str | None = None
    epsilon: float = 0.05


class MeteredModel:
    """Wraps a ChatModel to count calls and sum estimated cost across extract and judge calls."""

    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner
        self.calls = 0
        self.cost_usd = 0.0

    async def chat(self, messages: list[dict[str, str]], **kwargs):  # noqa: ANN201 - mirrors ChatModel
        self.calls += 1
        result = await self._inner.chat(messages, **kwargs)
        self.cost_usd += result.cost_usd
        return result


def is_time_sensitive(claim: Claim) -> bool:
    # A dated past event ("became CEO in 2011") stays true; it does not decay.
    return claim.volatility_class is not VolatilityClass.TIMELESS and not claim.is_past_event


def assess_risk(claim: Claim, opts: CheckOptions, half_lives: HalfLives) -> RiskScore:
    if claim.explicit_date and claim.explicit_date <= opts.today:
        age, basis = (opts.today - claim.explicit_date).days, AgeBasis.EXPLICIT_DATE
    else:
        age, basis = max((opts.today - opts.as_of).days, 0), opts.age_basis
    h, source = (half_lives.get(claim.volatility_class) or (None, "prior_guess")) if is_time_sensitive(claim) else (None, "prior_guess")
    p = p_stale(age, h)
    model_p = claim.p_outdated_model if is_time_sensitive(claim) else 0.0
    use_model = model_p is not None
    return RiskScore(
        claim_id=claim.id, age_days=age, age_basis=basis, half_life_days=h, half_life_source=source,
        p_stale=round(p, 4), recommended_ttl_days=None if h is None else round(recommended_ttl_days(h, opts.epsilon), 2),
        rank_score=round(model_p if use_model else p, 4), rank_basis="model_p" if use_model else "half_life",
    )


def select_for_verification(claims: list[Claim], risks: list[RiskScore], budget: int | None) -> list[int]:
    # model_p and half-life p_stale are different scales: model-ranked claims go first, fallback after.
    eligible = [i for i, c in enumerate(claims) if is_time_sensitive(c)]
    eligible.sort(key=lambda i: (risks[i].rank_basis != "model_p", -risks[i].rank_score, i))
    return eligible if budget is None else eligible[: max(budget, 0)]


def build_claim_report(claim: Claim, risk: RiskScore, outcome: VerifyOutcome | None) -> ClaimReport:
    searched = outcome is not None and outcome.searches > 0
    verdict = outcome.verdict if outcome else None
    score, basis = freshness_score(
        volatility_class=VolatilityClass.TIMELESS if not is_time_sensitive(claim) else claim.volatility_class,
        searched=searched, verdict=verdict.label if verdict else None,
        # Same signal that ranked the claim: model probability when present, else half-life.
        p=risk.rank_score, authoritative_or_two_sources=bool(outcome and outcome.strong_support),
    )
    return ClaimReport(
        claim=claim, risk=risk, searched=searched, evidence=outcome.evidence if outcome else [],
        verdict=verdict if searched else None, freshness_score=score, score_basis=basis,
        errors=list(outcome.errors) if outcome else [],
    )


async def check_answer(answer: str, *, model: ChatModel, searcher: Searcher, opts: CheckOptions,
                       half_lives: HalfLives | None = None) -> AnswerReport:
    started = time.perf_counter()
    half_lives = half_lives or prior_half_lives()
    usage = Usage()
    model = MeteredModel(model)
    extracted = await extract_claims(answer, model, as_of=opts.as_of, today=opts.today)
    claims = extracted.claims
    risks = [assess_risk(c, opts, half_lives) for c in claims]
    chosen = select_for_verification(claims, risks, opts.budget)

    sem = asyncio.Semaphore(VERIFY_CONCURRENCY)

    async def run(i: int) -> tuple[int, VerifyOutcome]:
        async with sem:
            return i, await verify_claim(claims[i], model, searcher, today=opts.today)

    outcomes: dict[int, VerifyOutcome] = dict(await asyncio.gather(*(run(i) for i in chosen)))  # verify never raises
    for o in outcomes.values():
        usage.tavily_calls += o.searches
        usage.tavily_credits += o.credits
        usage.tavily_cache_hits += o.cache_hits
    usage.model_calls = model.calls  # counts attempts, including failed ones

    reports = [build_claim_report(c, r, outcomes.get(i)) for i, (c, r) in enumerate(zip(claims, risks))]
    usage.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    usage.model_cost_usd = round(model.cost_usd, 6)  # estimated from tokens at list price
    return AnswerReport(
        answer=answer, model=opts.answer_model, mode=opts.mode, checked_at=datetime.now(UTC),
        verification_budget=opts.budget, claims=reports, answer_score=answer_score([r.freshness_score for r in reports]),
        usage=usage, errors=list(extracted.errors), bifrost_request_id=opts.request_id,
    )


def rescore_aged(report: AnswerReport, *, today: date, half_lives: HalfLives | None = None) -> AnswerReport:
    """Re-score a cached answer as it ages, with no model or search call (half-life only).

    Verified verdicts keep their score; estimated/unverified claims are recomputed at the new age.
    """
    half_lives = half_lives or prior_half_lives()
    delta = (today - report.checked_at.date()).days
    out = []
    for cr in report.claims:
        if cr.score_basis in (ScoreBasis.ESTIMATED, ScoreBasis.UNVERIFIED) and cr.risk.half_life_days:
            age = cr.risk.age_days + max(delta, 0)
            p = p_stale(age, cr.risk.half_life_days)
            score, basis = freshness_score(volatility_class=cr.claim.volatility_class, searched=cr.searched,
                                           verdict=cr.verdict.label if cr.verdict else None, p=p)
            risk = cr.risk.model_copy(update={"age_days": age, "p_stale": round(p, 4)})
            cr = cr.model_copy(update={"risk": risk, "freshness_score": score, "score_basis": basis})
        out.append(cr)
    checked_at = datetime.combine(today, report.checked_at.timetz()) if delta > 0 else report.checked_at
    return report.model_copy(update={"claims": out, "checked_at": checked_at,
                                     "answer_score": answer_score([c.freshness_score for c in out])})


__all__ = ["CheckOptions", "check_answer", "rescore_aged", "assess_risk", "select_for_verification",
           "prior_half_lives", "VerdictLabel"]
