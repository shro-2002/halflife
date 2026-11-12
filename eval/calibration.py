"""Headline catch rates with CIs, and calibration of half-life fits vs Haiku's probability.

    uv run python -m eval.calibration

Reads the J0.5 dataset and cached model ratings; no model or Tavily calls.
1. Headline: caught@10/25/50% on the 300-claim model sample for model_p and halflife,
   bootstrap 95% CIs (resampling claims; ties broken by a random draw per resample).
2. Calibration: half-lives fitted on (a) all fit-split outcomes (J0.5 baseline) and (b) a rolling
   window — fit outcomes whose as-of date is in the 24 months before the cutoff. On the test split,
   per class: mean predicted P(stale) vs observed stale rate. Haiku's p_outdated is compared on the
   300-claim sample (the only claims it rated). Within 0.10 absolute per class = calibrated.
"""

import json
import random
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from halflife.fit import fit_half_life
from halflife.risk import p_stale
from halflife.schemas import PRIOR_HALF_LIFE_DAYS, VolatilityClass

from eval.histories import CUTOFF
from eval.ordering import BOOTSTRAP, SEED, SHUFFLES, averaged_curve, curve, fit_classes, load_claims, method_scores, stratified_sample, MODEL_SAMPLE

RESULTS = Path(__file__).resolve().parent.parent / "results" / "2026-11-12-ordering"
WINDOW_DAYS = 730
TOLERANCE = 0.10
KS = (10, 25, 50)


def bootstrap_catch(claims: list[dict], scores: list[float]) -> dict[str, list[float]]:
    rng = random.Random(SEED + 2)
    stale = [c["label"] == "stale" for c in claims]
    n = len(claims)
    point = averaged_curve(scores, stale, SHUFFLES, SEED)  # same tie handling as the J0.5 table
    draws = defaultdict(list)
    for _ in range(BOOTSTRAP):
        idx = [rng.randrange(n) for _ in range(n)]
        st = [stale[i] for i in idx]
        if not any(st):
            continue
        c = curve([scores[i] for i in idx], st, rng)
        for k in KS:
            draws[k].append(c[k])
    out = {}
    for k in KS:
        d = sorted(draws[k])
        out[f"caught_at_{k}"] = [round(d[int(0.025 * len(d))], 3), round(point[k], 3), round(d[int(0.975 * len(d)) - 1], 3)]
    return out


def fit_window(fit: list[dict]) -> dict[str, dict]:
    start = CUTOFF - timedelta(days=WINDOW_DAYS)
    by_class: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for c in fit:
        if c["volatility_class"] != "timeless" and date.fromisoformat(c["asof"]) >= start:
            by_class[c["volatility_class"]].append((c["age_days"], c["label"] == "stale"))
    out = {}
    for cls, obs in by_class.items():
        prior = PRIOR_HALF_LIFE_DAYS[VolatilityClass(cls)]
        r = fit_half_life(obs, prior)
        out[cls] = {"prior_guess_days": prior, "fitted_days": round(r.half_life_days, 1), "n": r.n, "n_changed": r.n_changed}
    return out


def calib_rows(claims: list[dict], predict) -> dict[str, dict]:
    rows = {}
    for cls in sorted({c["volatility_class"] for c in claims}):
        cs = [c for c in claims if c["volatility_class"] == cls]
        obs = sum(c["label"] == "stale" for c in cs) / len(cs)
        pred = statistics.fmean(predict(c) for c in cs)
        rows[cls] = {"n": len(cs), "observed": round(obs, 3), "predicted": round(pred, 3),
                     "abs_error": round(abs(pred - obs), 3), "within_0_10": abs(pred - obs) <= TOLERANCE}
    return rows


def main() -> None:
    claims = load_claims()
    fit = [c for c in claims if c["split"] == "fit"]
    test = [c for c in claims if c["split"] == "test"]
    ratings = json.loads((RESULTS / "model_ratings.json").read_text())
    full_hl, win_hl = fit_classes(fit), fit_window(fit)

    sample = [c for c in stratified_sample(test, MODEL_SAMPLE) if c["id"] in ratings]
    scores = method_scores(sample, full_hl, ratings)
    headline = {"n": len(sample), "n_stale": sum(c["label"] == "stale" for c in sample),
                "model_p": bootstrap_catch(sample, scores["model_p"]),
                "halflife": bootstrap_catch(sample, scores["halflife"]),
                "format": "[ci_low, point, ci_high], fraction of stale claims caught when verifying the top k% of claims"}

    def hl_pred(table):
        return lambda c: p_stale(c["age_days"], None if c["volatility_class"] == "timeless" else table[c["volatility_class"]]["fitted_days"])

    calibration = {
        "half_lives_full": full_hl, "half_lives_window_24m": win_hl,
        "test_full__halflife_full": calib_rows(test, hl_pred(full_hl)),
        "test_full__halflife_window_24m": calib_rows(test, hl_pred(win_hl)),
        "sample__halflife_full": calib_rows(sample, hl_pred(full_hl)),
        "sample__halflife_window_24m": calib_rows(sample, hl_pred(win_hl)),
        "sample__model_p": calib_rows(sample, lambda c: ratings[c["id"]]["p_outdated"]),
    }
    def worst(rows):  # time-sensitive classes only; timeless is 0 vs 0 by construction
        return max(r["abs_error"] for k, r in rows.items() if k != "timeless")
    calibration["max_abs_error_time_sensitive"] = {k: worst(v) for k, v in calibration.items() if k.startswith(("test_", "sample_"))}
    keep = "window_24m" if worst(calibration["test_full__halflife_window_24m"]) < worst(calibration["test_full__halflife_full"]) else "full"
    calibration["kept_half_life_fit"] = keep
    kept_rows = calibration[f"test_full__halflife_{keep}"]
    calibration["ttl_status"] = "calibrated" if all(r["within_0_10"] for r in kept_rows.values()) else "experimental"

    (RESULTS / "headline.json").write_text(json.dumps(headline, indent=2))
    (RESULTS / "calibration.json").write_text(json.dumps(calibration, indent=2))
    print(json.dumps({"headline": headline, "max_abs_error": calibration["max_abs_error_time_sensitive"],
                      "window_half_lives": win_hl, "kept": keep, "ttl_status": calibration["ttl_status"],
                      "test_full_kept": kept_rows, "sample_model_p": calibration["sample__model_p"]}, indent=1))


if __name__ == "__main__":
    main()
