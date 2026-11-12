"""Property and example tests for halflife.risk (pure functions, no I/O)."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from halflife.risk import answer_score, budget_order, freshness_score, p_stale, recommended_ttl_days
from halflife.schemas import ScoreBasis, VerdictLabel, VolatilityClass

settings.register_profile("fast", max_examples=150, deadline=None)
settings.load_profile("fast")

ages = st.floats(min_value=0, max_value=1e6, allow_nan=False)
half_lives = st.floats(min_value=1e-3, max_value=1e5, allow_nan=False)
probs = st.floats(min_value=0, max_value=1, allow_nan=False)
epsilons = st.floats(min_value=1e-6, max_value=1 - 1e-6, allow_nan=False)
ROUND_TOL = 0.05 + 1e-9  # outputs are rounded to 1 decimal
TIME_SENSITIVE = [c for c in VolatilityClass if c is not VolatilityClass.TIMELESS]


# --- p_stale -------------------------------------------------------------------------------


@given(st.floats(min_value=-1e6, max_value=1e12, allow_nan=False), half_lives)
def test_p_stale_in_unit_interval_and_finite(age, h):
    p = p_stale(age, h)
    assert not math.isnan(p)
    assert 0.0 <= p <= 1.0


@given(ages, ages, half_lives)
def test_p_stale_non_decreasing_in_age(a, b, h):
    lo, hi = sorted((a, b))
    assert p_stale(lo, h) <= p_stale(hi, h)


@given(st.floats(min_value=1e-3, max_value=1e6, allow_nan=False), half_lives, half_lives)
def test_p_stale_non_increasing_in_half_life(age, h1, h2):
    short, long_ = sorted((h1, h2))
    assert p_stale(age, short) >= p_stale(age, long_)


@given(half_lives)
def test_p_stale_is_half_at_one_half_life(h):
    assert p_stale(h, h) == pytest.approx(0.5)


@given(st.floats(min_value=-1e6, max_value=0, allow_nan=False), half_lives)
def test_p_stale_zero_for_non_positive_age(age, h):
    assert p_stale(age, h) == 0.0


@given(st.floats(min_value=-1e6, max_value=1e12, allow_nan=False))
def test_p_stale_zero_for_timeless(age):
    assert p_stale(age, None) == 0.0


def test_p_stale_examples():
    assert p_stale(240, 120) == pytest.approx(0.75)
    assert p_stale(1e300, 1.0) == 1.0


# --- recommended_ttl_days ------------------------------------------------------------------


@given(half_lives, half_lives, epsilons)
def test_ttl_monotone_in_half_life(h1, h2, eps):
    short, long_ = sorted((h1, h2))
    assert recommended_ttl_days(short, eps) <= recommended_ttl_days(long_, eps)


@given(half_lives, epsilons, epsilons)
def test_ttl_grows_with_epsilon(h, e1, e2):
    lo, hi = sorted((e1, e2))
    assert recommended_ttl_days(h, lo) <= recommended_ttl_days(h, hi)


@given(half_lives, epsilons)
def test_ttl_round_trips_through_p_stale(h, eps):
    ttl = recommended_ttl_days(h, eps)
    assert ttl > 0
    assert p_stale(ttl, h) == pytest.approx(eps, rel=1e-6, abs=1e-12)


def test_ttl_default_epsilon_example():
    # 5% of a 120-day half-life: -120*log2(0.95) ~= 8.88 days
    assert recommended_ttl_days(120.0) == pytest.approx(8.880, abs=1e-3)


def test_ttl_none_for_timeless():
    assert recommended_ttl_days(None) is None
    assert recommended_ttl_days(None, 0.2) is None


@pytest.mark.parametrize("eps", [0.0, 1.0, -0.1, 1.5])
def test_ttl_rejects_epsilon_outside_open_unit_interval(eps):
    with pytest.raises(ValueError):
        recommended_ttl_days(100.0, eps)


# --- budget_order --------------------------------------------------------------------------

p_lists = st.lists(st.sampled_from([0.0, 0.1, 0.3, 0.3, 0.7, 1.0]) | probs, max_size=20)
budgets = st.none() | st.integers(min_value=-5, max_value=25)


@given(p_lists, budgets)
def test_budget_order_properties(ps, budget):
    order = budget_order(ps, budget)
    positive = [i for i, p in enumerate(ps) if p > 0]
    assert len(order) == len(set(order))
    assert all(ps[i] > 0 for i in order)  # zero-risk never selected
    cap = len(positive) if budget is None else max(min(budget, len(positive)), 0)
    assert len(order) == cap
    # highest first, ties broken by lower index (stable)
    assert order == sorted(order, key=lambda i: (-ps[i], i))
    # selected set is a top-k: nothing left out beats anything selected
    left_out = set(positive) - set(order)
    if order and left_out:
        assert min(ps[i] for i in order) >= max(ps[i] for i in left_out)


def test_budget_order_examples():
    ps = [0.2, 0.0, 0.9, 0.2, 0.5]
    assert budget_order(ps, None) == [2, 4, 0, 3]
    assert budget_order(ps, 2) == [2, 4]
    assert budget_order(ps, 3) == [2, 4, 0]
    assert budget_order(ps, 0) == []
    assert budget_order(ps, -1) == []
    assert budget_order([0.0, 0.0], None) == []
    assert budget_order([], 5) == []


# --- freshness_score -----------------------------------------------------------------------


@given(st.booleans(), st.sampled_from([None, *VerdictLabel]), probs, st.booleans())
def test_timeless_never_scored(searched, verdict, p, auth):
    score, basis = freshness_score(
        volatility_class=VolatilityClass.TIMELESS, searched=searched, verdict=verdict, p=p,
        authoritative_or_two_sources=auth,
    )
    assert (score, basis) == (None, ScoreBasis.NOT_TIME_SENSITIVE)


@given(st.sampled_from(TIME_SENSITIVE), st.sampled_from([None, *VerdictLabel]), probs)
def test_not_searched_is_estimated(cls, verdict, p):
    # Verdict is ignored when not searched (a verdict requires a search).
    score, basis = freshness_score(volatility_class=cls, searched=False, verdict=verdict, p=p)
    assert basis is ScoreBasis.ESTIMATED
    assert score == pytest.approx(100 * (1 - p), abs=ROUND_TOL)


@given(st.sampled_from(TIME_SENSITIVE), probs, st.booleans())
def test_changed_scores_five(cls, p, auth):
    assert freshness_score(
        volatility_class=cls, searched=True, verdict=VerdictLabel.CHANGED, p=p,
        authoritative_or_two_sources=auth,
    ) == (5.0, ScoreBasis.CHANGED)


@given(st.sampled_from(TIME_SENSITIVE), probs)
def test_current_scores_by_source_strength(cls, p):
    common = dict(volatility_class=cls, searched=True, verdict=VerdictLabel.CURRENT, p=p)
    assert freshness_score(**common, authoritative_or_two_sources=True) == (95.0, ScoreBasis.VERIFIED_AUTHORITATIVE)
    assert freshness_score(**common, authoritative_or_two_sources=False) == (80.0, ScoreBasis.VERIFIED_SINGLE)


@given(st.sampled_from(TIME_SENSITIVE), st.sampled_from([None, VerdictLabel.UNVERIFIABLE]), probs, st.booleans())
def test_searched_but_unverified_is_capped_at_50(cls, verdict, p, auth):
    score, basis = freshness_score(
        volatility_class=cls, searched=True, verdict=verdict, p=p, authoritative_or_two_sources=auth,
    )
    assert basis is ScoreBasis.UNVERIFIED
    assert score <= 50.0
    assert score == pytest.approx(min(50.0, 100 * (1 - p)), abs=ROUND_TOL)


@given(st.sampled_from(list(VolatilityClass)), st.booleans(), st.sampled_from([None, *VerdictLabel]), probs, st.booleans())
def test_scores_always_within_0_100(cls, searched, verdict, p, auth):
    score, _ = freshness_score(
        volatility_class=cls, searched=searched, verdict=verdict, p=p, authoritative_or_two_sources=auth,
    )
    assert score is None or 0.0 <= score <= 100.0


def test_freshness_score_examples():
    sv = VolatilityClass.SOFTWARE_VERSION
    assert freshness_score(volatility_class=sv, searched=False, verdict=None, p=0.25) == (75.0, ScoreBasis.ESTIMATED)
    assert freshness_score(volatility_class=sv, searched=True, verdict=None, p=0.25) == (50.0, ScoreBasis.UNVERIFIED)
    assert freshness_score(
        volatility_class=sv, searched=True, verdict=VerdictLabel.UNVERIFIABLE, p=0.8
    ) == (20.0, ScoreBasis.UNVERIFIED)


# --- answer_score --------------------------------------------------------------------------


@given(st.lists(st.none() | st.floats(min_value=0, max_value=100, allow_nan=False), max_size=15))
def test_answer_score_is_mean_of_non_none(scores):
    vals = [s for s in scores if s is not None]
    result = answer_score(scores)
    if not vals:
        assert result is None
    else:
        assert result == pytest.approx(sum(vals) / len(vals), abs=ROUND_TOL)
        assert min(vals) - ROUND_TOL <= result <= max(vals) + ROUND_TOL


def test_answer_score_examples():
    assert answer_score([]) is None
    assert answer_score([None, None]) is None
    assert answer_score([95.0, None, 5.0]) == 50.0
    assert answer_score([80.0]) == 80.0
