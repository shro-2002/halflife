"""Tests for halflife.fit (MAP half-life from interval-censored outcomes)."""

import math
import random
import statistics

import pytest

from halflife.fit import fit_half_life

N_OBS = 200
SEEDS = range(20)
MAX_MEDIAN_REL_ERROR = 0.15
PRIOR_FACTORS = (0.5, 2.0)  # prior deliberately off by 2x either way


def synth(true_h: float, n: int, seed: int) -> list[tuple[float, bool]]:
    """Ages log-uniform in [h/4, 4h]; changed ~ Bernoulli(1 - 2^(-age/h))."""
    rng = random.Random(seed)
    obs = []
    for _ in range(n):
        age = math.exp(rng.uniform(math.log(true_h / 4), math.log(4 * true_h)))
        obs.append((age, rng.random() < 1 - 2 ** (-age / true_h)))
    return obs


@pytest.mark.parametrize("prior_factor", PRIOR_FACTORS)
@pytest.mark.parametrize("true_h", [30.0, 120.0, 900.0])
def test_recovers_known_half_life_at_n200(true_h, prior_factor):
    errors = [
        abs(fit_half_life(synth(true_h, N_OBS, seed), true_h * prior_factor).half_life_days / true_h - 1)
        for seed in SEEDS
    ]
    median, worst = statistics.median(errors), max(errors)
    print(f"h={true_h} prior={prior_factor}x median_rel_err={median:.3f} max={worst:.3f}")
    assert median < MAX_MEDIAN_REL_ERROR


def test_zero_data_returns_prior():
    fit = fit_half_life([], prior_half_life_days=120.0)
    assert fit.half_life_days == pytest.approx(120.0, rel=1e-3)
    assert (fit.n, fit.n_changed) == (0, 0)


def test_all_unchanged_pushes_half_life_up():
    assert fit_half_life([(100.0, False)] * 30, 120.0).half_life_days > 120.0


def test_all_changed_pushes_half_life_down():
    assert fit_half_life([(100.0, True)] * 30, 120.0).half_life_days < 120.0


def test_invariant_to_observation_order():
    obs = synth(120.0, N_OBS, seed=7)
    shuffled = obs[:]
    random.Random(1).shuffle(shuffled)
    assert fit_half_life(shuffled, 150.0).half_life_days == pytest.approx(
        fit_half_life(obs, 150.0).half_life_days, rel=1e-6)


def test_non_positive_ages_ignored():
    obs = synth(120.0, 50, seed=3)
    noisy = obs + [(0.0, True), (-5.0, False), (-1.0, True)]
    with_noise, clean = fit_half_life(noisy, 150.0), fit_half_life(obs, 150.0)
    assert with_noise.n == clean.n == len(obs)
    assert with_noise.half_life_days == pytest.approx(clean.half_life_days, rel=1e-6)
