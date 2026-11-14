"""Budget orderings against the fair baseline, both live detector runs (no spend).

    uv run python -m eval.fair_baseline

Recomputes run 1 (results/2026-11-12-detector/run1, before the numeric-equality fix) and run 2 (the headline
folder) from their raw.jsonl with eval.run, then writes fair_baseline.json: caught@25/50% for the model order,
the half-life order, random among time-sensitive cases (fair baseline: the product never searches timeless
claims or dated past events) and blind random, plus each order's lift over the fair baseline with a paired
bootstrap 95% CI by source URL, per run and as the mean of the two runs.
"""

import json
import statistics

from eval import run

DETECTOR = run.OUT
ORDERS = ("model_p", "half_life", "random_time_sensitive", "random")


def main() -> None:
    runs = {}
    for name, folder in (("run1", DETECTOR / "run1"), ("run2", DETECTOR)):
        run.OUT = folder
        s = run.offline()
        runs[name] = {
            "caught": {o: {k: s["budget"][o][f"caught_at_{k}"]["point"] for k in (25, 50)} for o in ORDERS},
            "lift_over_random_time_sensitive": {o: s["lift_over_random_time_sensitive"][o] for o in ("model_p", "half_life")},
        }
    mean = {o: {k: round(statistics.fmean(runs[r]["caught"][o][k] for r in runs), 3) for k in (25, 50)} for o in ORDERS}
    lift = {o: {k: round(mean[o][k] - mean["random_time_sensitive"][k], 3) for k in (25, 50)} for o in ("model_p", "half_life")}
    out = {"note": __doc__.split("\n\n", 2)[2].strip(), "runs": runs,
           "mean_of_live_runs_1_2": {"caught": mean, "lift_over_random_time_sensitive": lift}}
    (DETECTOR / "fair_baseline.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["mean_of_live_runs_1_2"], indent=1))
    for r in runs:
        print(r, json.dumps(runs[r]["lift_over_random_time_sensitive"]))


if __name__ == "__main__":
    main()
