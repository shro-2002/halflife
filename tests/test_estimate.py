"""Traffic-wide stale-rate estimator: strata, allocation, weighting, bounds, interval. Offline."""

import random

import pytest

from halflife.gateway.estimate import estimate, strata_of, stratified_sample


def test_strata_are_equal_count_quantiles():
    st = strata_of([0.9, 0.1, 0.5, 0.3, 0.7, 0.2, 0.8, 0.4])
    assert sorted(st) == [0, 0, 1, 1, 2, 2, 3, 3]
    assert st[1] == 0 and st[0] == 3  # lowest score in stratum 0, highest in 3


def test_proportional_allocation_hits_every_stratum():
    scores = [i / 100 for i in range(100)]
    idx = stratified_sample(scores, 20, random.Random(1))
    st = strata_of(scores)
    assert len(idx) == 20 and len(set(idx)) == 20
    assert [sum(st[i] == j for i in idx) for j in range(4)] == [5, 5, 5, 5]


def test_weighting_by_stratum_share():
    pop = [0] * 90 + [3] * 10  # 90% low-risk, 10% high-risk
    sampled = [(0, False)] * 9 + [(0, True)] + [(3, True)] * 9 + [(3, False)]
    est = estimate(pop, sampled, random.Random(0), boot=200)
    assert est.stale_rate == pytest.approx(0.9 * 0.1 + 0.1 * 0.9)
    assert est.ci95[0] <= est.stale_rate <= est.ci95[1]


def test_unverifiable_reported_under_both_bounds():
    pop = [0] * 4
    sampled = [(0, True), (0, False), (0, None), (0, None)]
    est = estimate(pop, sampled, random.Random(0), boot=100)
    assert est.stale_rate == pytest.approx(0.5)
    assert est.bound_low == pytest.approx(0.25) and est.bound_high == pytest.approx(0.75)
    assert est.n_unverifiable == 2 and est.n_sampled == 4


def test_unbiased_on_synthetic_population():
    rng = random.Random(7)
    scores = [rng.random() for _ in range(2000)]
    labels = [rng.random() < 0.1 + 0.6 * s for s in scores]  # staleness rises with score
    st = strata_of(scores)
    truth = sum(labels) / len(labels)
    ests = []
    for r in range(150):
        idx = stratified_sample(scores, 80, random.Random(r))
        ests.append(estimate(st, [(st[i], labels[i]) for i in idx], random.Random(r), boot=1).stale_rate)
    assert abs(sum(ests) / len(ests) - truth) < 0.01


def test_empty_sample_gives_no_estimate():
    est = estimate([0, 1], [], random.Random(0), boot=10)
    assert est.stale_rate is None and est.ci95 is None
