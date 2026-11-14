# Estimator validation — stratified stale-rate estimate

Reproduce: `uv run python -m eval.estimator_validation` (no spend). Population: 1763 time-sensitive claims from the time-travel dataset (true stale rate 0.2059). Each row: 400 stratified samples (4 rank-score strata, proportional allocation), bootstrap 95% interval (300 draws).

**What this tests: interval coverage by sample size.** Read the audit's 95% interval as reliable from about 60 random samples; below that it is too narrow.

| sample size | 95% CI coverage | mean CI width | RMSE | bias |
|---|---|---|---|---|
| 8 | 0.465 | 0.187 | 0.1138 | -0.0008 |
| 18 | 0.740 | 0.224 | 0.0786 | -0.0032 |
| 30 | 0.890 | 0.199 | 0.0597 | +0.0041 |
| 60 | 0.945 | 0.150 | 0.0401 | +0.0006 |
| 120 | 0.945 | 0.109 | 0.0286 | +0.0013 |
| 240 | 0.970 | 0.078 | 0.0184 | +0.0005 |

Coverage below 0.95 at small sizes is the usual undercoverage of a percentile bootstrap on very few draws per stratum; read small-sample intervals as optimistic.

Bias: a proportionally allocated stratified mean is unbiased by construction, so the near-zero bias column checks the implementation, not a finding. It says nothing about measurement bias: in the audit, labels come from the detector, which flags some current claims as changed (results/2026-11-12-detector).
