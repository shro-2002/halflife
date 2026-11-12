"""Pure risk functions: P(stale), budget ordering, recommended TTL, freshness score.

Model: facts in a volatility class change as a Poisson process with rate lambda = ln2 / h.
P(stale | age) = 1 - 2^(-age/h). Timeless facts never decay.
"""

import math
from collections.abc import Sequence

from halflife.schemas import ScoreBasis, VerdictLabel, VolatilityClass

DEFAULT_EPSILON = 0.05  # tolerated probability that a cached answer is stale


def p_stale(age_days: float, half_life_days: float | None) -> float:
    if half_life_days is None or not age_days > 0:  # also catches NaN
        return 0.0
    if not half_life_days > 0:
        raise ValueError(f"half-life must be positive, got {half_life_days}")
    return 1.0 - 2.0 ** (-age_days / half_life_days)


def recommended_ttl_days(half_life_days: float | None, epsilon: float = DEFAULT_EPSILON) -> float | None:
    """Time until P(stale) reaches epsilon: t = -h * log2(1 - epsilon). None = never expires."""
    if half_life_days is None:
        return None
    if not 0 < epsilon < 1:
        raise ValueError("epsilon must be in (0, 1)")
    return -half_life_days * math.log2(1.0 - epsilon)


def budget_order(p_stales: Sequence[float], budget: int | None) -> list[int]:
    """Indices to verify: highest P(stale) first, zero-risk (timeless) never, at most `budget`."""
    ranked = sorted((i for i, p in enumerate(p_stales) if p > 0), key=lambda i: (-p_stales[i], i))
    return ranked if budget is None else ranked[: max(budget, 0)]


def freshness_score(
    *,
    volatility_class: VolatilityClass,
    searched: bool,
    verdict: VerdictLabel | None,
    p: float,
    authoritative_or_two_sources: bool = False,
) -> tuple[float | None, ScoreBasis]:
    """Score table from the build prompt (T4)."""
    if volatility_class is VolatilityClass.TIMELESS:
        return None, ScoreBasis.NOT_TIME_SENSITIVE
    if not searched:
        return round(100 * (1 - p), 1), ScoreBasis.ESTIMATED
    if verdict is VerdictLabel.CHANGED:
        return 5.0, ScoreBasis.CHANGED
    if verdict is VerdictLabel.CURRENT:
        if authoritative_or_two_sources:
            return 95.0, ScoreBasis.VERIFIED_AUTHORITATIVE
        return 80.0, ScoreBasis.VERIFIED_SINGLE
    return min(50.0, round(100 * (1 - p), 1)), ScoreBasis.UNVERIFIED


def answer_score(scores: Sequence[float | None]) -> float | None:
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals), 1) if vals else None
