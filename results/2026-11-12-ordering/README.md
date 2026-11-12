# J0.5 ordering test — 2026-11-12

Reproduce: `uv run python -m eval.histories && uv run python -m eval.ordering` (model ratings are cached in
`model_ratings.json`; a rerun spends nothing). Data: `data/histories/claims.jsonl`, built from Wikidata,
PyPI, npm and BIS policy rates. No Tavily calls.

## Setup
- Fit split: entities hashed to "fit"; as-of dates 7–1825 days before the **cutoff 2024-11-12**; labels
  compare with the value on the cutoff. Test split: other entities; as-of dates 7–730 days before
  **2026-11-12**, so every test outcome is a change after the cutoff. Asserted: no entity in both splits.
- Classes covered: office holder, software version, policy rate, timeless controls. **Price, law and
  product-spec classes are not in this dataset** (no free dated history source used).
- Half-lives fitted by MAP (Gamma prior, shape 2) on the fit split. Priors were guesses.

## Fitted half-lives (fit split)

| Class | Prior guess | Fitted | n | changed |
|---|---|---|---|---|
| software_version | 120 d | 83.2 d | 130 | 82 |
| rate_or_statistic | 150 d | 55.2 d | 64 | 44 |
| office_holder | 900 d | 1626.9 d | 675 | 72 |

## Risk-coverage, test split, all 1048 claims (198 stale)

| Method | AUC | caught @10% | @25% | @50% |
|---|---|---|---|---|
| halflife | **0.856** | 0.515 | 0.788 | 0.988 |
| class_only | 0.812 | 0.292 | 0.852 | 0.914 |
| age_only | 0.642 | 0.224 | 0.436 | 0.727 |
| random | 0.502 | 0.101 | 0.251 | 0.501 |

AUC(halflife) − AUC(other), bootstrap 95% CI: class_only [0.022, 0.068], age_only [0.182, 0.250], random [0.312, 0.401].

## Same, on the stratified model sample (n = 300, 84 stale), with Claude Haiku 5.5 baselines

| Method | AUC | caught @10% | @25% | @50% |
|---|---|---|---|---|
| model_p (Haiku: P(outdated) given claim + as-of date) | **0.826** | 0.36 | 0.75 | 0.98 |
| halflife | 0.782 | 0.30 | 0.66 | 0.92 |
| model_ts (Haiku: time-sensitivity of claim text only) | 0.760 | 0.28 | 0.53 | 0.96 |
| class_only | 0.696 | 0.12 | 0.31 | 0.98 |
| age_only | 0.606 | 0.18 | 0.38 | 0.68 |
| random | 0.499 | 0.10 | 0.25 | 0.50 |

AUC(halflife) − AUC(other), 95% CI: model_p **[−0.064, −0.023]** (half-life is worse), model_ts [−0.012, 0.054]
(no clear difference), class_only [0.055, 0.118], age_only [0.135, 0.217], random [0.217, 0.347].

**Leakage check.** Haiku 5.5's reliable knowledge cutoff is June 2026. On sample claims with as-of ≥ 2026-07-01
(n = 185, 41 stale) the model still leads: model_p 0.827 vs halflife 0.773, CI [−0.094, −0.021]. So the gap is
not explained by the model already knowing the answer.

**Post-hoc (not pre-registered):** rank-averaging halflife with model_p gives 0.810, below model_p alone
(CI [−0.028, −0.004]). `posthoc_combination.json`.

## Headline (300-claim model sample, 84 stale) — `headline.json`

Share of stale claims caught when verifying the top k% of claims. Point estimate (ties averaged over 200
shuffles) with bootstrap 95% CI (1000 resamples). Reproduce: `uv run python -m eval.calibration`.

| Ordering | caught @10% | caught @25% | caught @50% |
|---|---|---|---|
| Haiku outdated-probability, given as-of date (**product default**) | **0.357** [0.303, 0.429] | **0.748** [0.670, 0.836] | **0.980** [0.946, 1.000] |
| Half-life (fitted per class) | 0.298 [0.238, 0.356] | 0.655 [0.556, 0.750] | 0.917 [0.850, 0.975] |
| Random (expected) | 0.10 | 0.25 | 0.50 |

## Calibration on test (mean predicted P(stale) vs observed stale rate)

| Class | n | observed | predicted | median age |
|---|---|---|---|---|
| office_holder | 670 | 0.039 | 0.058 | 64.5 d |
| rate_or_statistic | 76 | 0.342 | 0.609 | 77.5 d |
| software_version | 148 | 0.764 | 0.515 | 75 d |
| timeless | 154 | 0.000 | 0.000 | 85.5 d |

Rates were fitted on 2019–2024 outcomes (incl. the 2022–23 hiking cycle) and changed less often after the
cutoff; versions changed faster. A single exponential per class drifts with regime.

## Recalibration attempt (time-boxed, `calibration.json`)
Refit on a rolling window: fit-split outcomes with as-of dates in the 24 months before the cutoff.
Half-lives: software_version 83.2 d (unchanged), rate_or_statistic 55.2 d (unchanged), office_holder 2259 d
(was 1627). Version and rate fits do not move because the outcomes dropped by the window are long-age changes,
which carry almost no likelihood information. Worst per-class |predicted − observed| on the test split:
0.267 for both fits, so the **full fit is kept**.

| Class (test) | observed | half-life predicted | Haiku p_outdated (sample, n=75 per class) |
|---|---|---|---|
| office_holder | 0.039 | 0.058 ✓ | 0.156 (obs 0.027) ✗ |
| rate_or_statistic | 0.342 | 0.609 ✗ | 0.580 (obs 0.347) ✗ |
| software_version | 0.764 | 0.515 ✗ | 0.768 (obs 0.747) ✓ |
| timeless | 0.000 | 0.000 ✓ | 0.011 ✓ |

✓ = within 0.10. Neither the half-life fits nor Haiku's probability are within 0.10 on every class, so the
decay-based cache TTL ships **labelled experimental**.

## Cost
Model ratings: 300 Haiku 5.5 calls, `reasoning_effort: none`, **$0.0088** measured as the delta of the virtual
key's budget usage (`halflife-dev`). The run's own counter printed $0.00 because Bifrost chat responses carry no
cost field; fixed (`BifrostClient.vk_spend_usd`) after this run.

## Limits
Hand-built from public histories; Wikidata office data has gaps (e.g. US head of state not matched by the
sovereign-state filter; holders without English labels become "no holder recorded"). Rates are BIS monthly
end-of-period values. Label = exact string match of the value then vs at reference.
