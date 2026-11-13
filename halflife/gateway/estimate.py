"""Traffic-wide stale-rate estimate from a stratified random sample of claims.

The top-risk slice tells you where stale claims are, but not how many there are overall. A random sample does:
claims are split into STRATA equal-count strata by rank score (quantiles), a sample is drawn from each stratum in
proportion to its size, and the stale rate over ALL time-sensitive claims is the stratum-share-weighted mean of the
per-stratum stale rates in the sample. Uncertainty: bootstrap, resampling within strata.

Unverifiable sampled claims are not dropped: the estimate is reported under both bounds (all current = low,
all stale = high); the point estimate uses verified claims only.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass

STRATA = 4
BOOT = 1000


def strata_of(scores: Sequence[float], k: int = STRATA) -> list[int]:
    """Stratum index (0 = lowest risk) per claim, by rank-score quantile; ties broken by position."""
    order = sorted(range(len(scores)), key=lambda i: (scores[i], i))
    out = [0] * len(scores)
    for rank, i in enumerate(order):
        out[i] = min(rank * k // max(len(scores), 1), k - 1)
    return out


def stratified_sample(scores: Sequence[float], n: int, rng: random.Random, k: int = STRATA) -> list[int]:
    """Proportional allocation across strata (largest remainder), uniform within each stratum."""
    st = strata_of(scores, k)
    members = [[i for i, s in enumerate(st) if s == j] for j in range(k)]
    n = min(n, len(scores))
    quotas = [n * len(m) / len(scores) for m in members] if scores else [0] * k
    alloc = [int(q) for q in quotas]
    for j in sorted(range(k), key=lambda j: quotas[j] - alloc[j], reverse=True)[: n - sum(alloc)]:
        alloc[j] += 1
    return sorted(i for j in range(k) for i in rng.sample(members[j], min(alloc[j], len(members[j]))))


@dataclass(frozen=True)
class Estimate:
    stale_rate: float | None  # point estimate from verified sampled claims
    ci95: tuple[float, float] | None
    bound_low: float | None  # unverifiable counted as current
    bound_high: float | None  # unverifiable counted as stale
    n_sampled: int
    n_unverifiable: int


def _weighted(by_stratum: dict[int, list[float]], weights: dict[int, float]) -> float | None:
    used = {j: v for j, v in by_stratum.items() if v}
    if not used:
        return None
    total_w = sum(weights[j] for j in used)  # strata with no usable sample: renormalise over the rest
    return sum(weights[j] * (sum(v) / len(v)) for j, v in used.items()) / total_w


def estimate(population_strata: Sequence[int], sampled: Sequence[tuple[int, bool | None]],
             rng: random.Random | None = None, boot: int = BOOT) -> Estimate:
    """population_strata: stratum of every time-sensitive claim in the population (gives the weights).
    sampled: (stratum, outcome) for each sampled claim; outcome True = stale, False = current, None = unverifiable."""
    rng = rng or random.Random(0)
    weights = {j: population_strata.count(j) / len(population_strata) for j in set(population_strata)} if population_strata else {}
    groups: dict[int, list[bool | None]] = {}
    for j, y in sampled:
        groups.setdefault(j, []).append(y)

    def point(gs: dict[int, list[bool | None]], fill: bool | None) -> float | None:
        conv = {j: [float(y if y is not None else fill) for y in ys if y is not None or fill is not None] for j, ys in gs.items()}
        return _weighted(conv, weights)

    p = point(groups, None)
    ci = None
    if p is not None:
        draws = []
        for _ in range(boot):
            g2 = {j: [rng.choice(ys) for _ in ys] for j, ys in groups.items()}
            v = point(g2, None)
            if v is not None:
                draws.append(v)
        draws.sort()
        ci = (draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1])
    return Estimate(p, ci, point(groups, False), point(groups, True), len(sampled),
                    sum(1 for _, y in sampled if y is None))
