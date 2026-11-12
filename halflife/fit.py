"""MAP fit of a per-class half-life from interval-censored outcomes.

Each observation is (age_days, changed): we only know whether the fact changed within `age`.
Exponential survival: P(changed by age) = 1 - exp(-lambda * age).
Log-likelihood = sum_changed log(1 - exp(-lambda a)) - lambda * sum_unchanged a.
Prior: lambda ~ Gamma(shape=k, rate=k / lambda0), mean lambda0 = ln2 / h_prior.
Half-life h = ln2 / lambda_MAP.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from scipy.optimize import minimize_scalar

LN2 = math.log(2.0)
DEFAULT_PRIOR_SHAPE = 2.0  # weak: about two pseudo-observations


@dataclass(frozen=True)
class FitResult:
    half_life_days: float
    lam: float
    n: int
    n_changed: int
    prior_half_life_days: float


def _neg_log_posterior(log_lam: float, ages_changed: list[float], sum_unchanged: float,
                       shape: float, rate: float) -> float:
    lam = math.exp(log_lam)
    ll = -lam * sum_unchanged
    for a in ages_changed:
        # log(1 - exp(-x)) computed stably
        ll += math.log(-math.expm1(-lam * a)) if lam * a > 0 else -1e9
    # Gamma log-density in lambda, plus log-Jacobian (+log_lam) for optimising over log lambda.
    lp = (shape - 1.0) * log_lam - rate * lam + log_lam
    return -(ll + lp)


def fit_half_life(observations: Iterable[tuple[float, bool]], prior_half_life_days: float,
                  prior_shape: float = DEFAULT_PRIOR_SHAPE) -> FitResult:
    if not prior_half_life_days > 0 or not prior_shape > 0:
        raise ValueError("prior half-life and shape must be positive")
    obs = [(float(a), bool(c)) for a, c in observations if a > 0 and math.isfinite(a)]
    lam0 = LN2 / prior_half_life_days
    rate = prior_shape / lam0
    ages_changed = [a for a, c in obs if c]
    sum_unchanged = sum(a for a, c in obs if not c)
    res = minimize_scalar(
        _neg_log_posterior,
        bounds=(math.log(lam0) - 12, math.log(lam0) + 12),
        args=(ages_changed, sum_unchanged, prior_shape, rate),
        method="bounded",
        options={"xatol": 1e-9},
    )
    lam = math.exp(res.x)
    return FitResult(LN2 / lam, lam, len(obs), len(ages_changed), prior_half_life_days)
