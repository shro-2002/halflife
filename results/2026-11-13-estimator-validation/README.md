# Estimator validation — traffic-wide stale rate

Reproduce: `uv run python -m eval.estimator_validation` (no spend). Population: 1763 time-sensitive claims from the time-travel dataset (true stale rate 0.2059). Each row: 400 stratified samples (4 rank-score strata, proportional allocation), bootstrap 95% interval (300 draws).

| sample size | bias | RMSE | 95% CI coverage | mean CI width |
|---|---|---|---|---|
| 8 | -0.0008 | 0.1138 | 0.465 | 0.187 |
| 18 | -0.0032 | 0.0786 | 0.740 | 0.224 |
| 30 | +0.0041 | 0.0597 | 0.890 | 0.199 |
| 60 | +0.0006 | 0.0401 | 0.945 | 0.150 |
| 120 | +0.0013 | 0.0286 | 0.945 | 0.109 |
| 240 | +0.0005 | 0.0184 | 0.970 | 0.078 |

Bias is near zero at every size. Coverage below 0.95 at small sizes is the usual undercoverage of a percentile bootstrap on very few draws per stratum; read small-sample intervals as optimistic.
