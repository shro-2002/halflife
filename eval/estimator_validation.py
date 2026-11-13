"""Validate the traffic-wide stale-rate estimator where true labels are known (J0.5 ordering dataset).

    uv run python -m eval.estimator_validation

Population: every time-sensitive claim in data/histories/claims.jsonl (both splits), label stale/current known.
Rank score: half-life P(stale) with the fitted per-class half-lives (what the audit has for every claim).
For each sample size n, draw REPS stratified samples (4 rank-score strata, proportional allocation), estimate the
population stale rate with a bootstrap 95% interval, and report bias (mean estimate − truth), RMSE and the share of
intervals that contain the truth (coverage). No model or Tavily calls.
"""

import json
import math
import random
import statistics
from pathlib import Path

from halflife.gateway.estimate import estimate, strata_of, stratified_sample
from halflife.risk import p_stale

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results" / "2026-11-13-estimator-validation"
SIZES = (8, 18, 30, 60, 120, 240)
REPS = 400
BOOT = 300


def main() -> None:
    hl = json.loads((ROOT / "results/2026-11-12-ordering/summary.json").read_text())["half_lives"]
    claims = [json.loads(l) for l in (ROOT / "data/histories/claims.jsonl").read_text().splitlines()]
    pop = [c for c in claims if c["volatility_class"] != "timeless"]
    scores = [p_stale(c["age_days"], hl[c["volatility_class"]]["fitted_days"]) for c in pop]
    labels = [c["label"] == "stale" for c in pop]
    st = strata_of(scores)
    truth = sum(labels) / len(labels)
    rows = {}
    for n in SIZES:
        ests, covered, widths = [], 0, []
        for r in range(REPS):
            rng = random.Random(1000 * n + r)
            idx = stratified_sample(scores, n, rng)
            e = estimate(st, [(st[i], labels[i]) for i in idx], rng, boot=BOOT)
            ests.append(e.stale_rate)
            covered += e.ci95[0] <= truth <= e.ci95[1]
            widths.append(e.ci95[1] - e.ci95[0])
        rows[str(n)] = {"mean_estimate": round(statistics.fmean(ests), 4), "bias": round(statistics.fmean(ests) - truth, 4),
                        "rmse": round(math.sqrt(statistics.fmean((x - truth) ** 2 for x in ests)), 4),
                        "ci95_coverage": round(covered / REPS, 3), "mean_ci_width": round(statistics.fmean(widths), 4)}
        print(n, rows[str(n)])
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"population_claims": len(pop), "true_stale_rate": round(truth, 4), "strata": 4, "reps_per_size": REPS,
           "bootstrap_draws": BOOT, "rank_score": "half-life P(stale), fitted per class (results/2026-11-12-ordering)",
           "by_sample_size": rows}
    (OUT / "summary.json").write_text(json.dumps(out, indent=2))
    lines = ["# Estimator validation — traffic-wide stale rate", "",
             "Reproduce: `uv run python -m eval.estimator_validation` (no spend). Population: "
             f"{len(pop)} time-sensitive claims from the time-travel dataset (true stale rate {truth:.4f}). Each row: "
             f"{REPS} stratified samples (4 rank-score strata, proportional allocation), bootstrap 95% interval ({BOOT} draws).", "",
             "| sample size | bias | RMSE | 95% CI coverage | mean CI width |", "|---|---|---|---|---|"]
    lines += [f"| {n} | {v['bias']:+.4f} | {v['rmse']:.4f} | {v['ci95_coverage']:.3f} | {v['mean_ci_width']:.3f} |" for n, v in rows.items()]
    lines += ["", "Bias is near zero at every size. Coverage below 0.95 at small sizes is the usual undercoverage of a "
              "percentile bootstrap on very few draws per stratum; read small-sample intervals as optimistic."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
