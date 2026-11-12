"""J0.5 ordering test: does half-life ordering catch stale claims earlier than the alternatives?

    uv run python -m eval.ordering            # uses cached model ratings if present
    uv run python -m eval.ordering --no-model # skip the Haiku baseline (no spend)

Fit half-lives on the fit split (outcomes before 2024-11-12), evaluate on the test split
(changes after it). Methods rank claims by risk; the risk-coverage curve plots the share of
stale claims caught against the share of claims verified, in rank order.

Methods
  halflife     P(stale) = 1 - 2^(-age/h_class), h fitted per class (timeless = 0)
  class_only   fitted per-class rate, ignoring age (ties broken at random)
  age_only     age in days, ignoring class
  random       expected curve of a random order (averaged over shuffles)
  model_ts     Haiku's time-sensitivity rating of the claim text alone (0-10)
  model_p      Haiku's probability the claim is outdated today, given its as-of date
Model baselines run on a stratified sample of MODEL_SAMPLE test claims (spend cap); every
method is also reported on that same sample so the comparison is like for like.
"""

import argparse
import asyncio
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from halflife.fit import fit_half_life
from halflife.risk import p_stale
from halflife.schemas import PRIOR_HALF_LIFE_DAYS, VolatilityClass

from eval.histories import CUTOFF, DATA, TODAY

ROOT = DATA.parent.parent
OUT = ROOT / "results" / f"{date.today().isoformat()}-ordering"
MODEL_SAMPLE = 300
SEED = 7
SHUFFLES = 200
BOOTSTRAP = 1000
GRID = [i / 100 for i in range(101)]


def load_claims() -> list[dict]:
    return [json.loads(line) for line in (DATA / "claims.jsonl").read_text().splitlines()]


def fit_classes(fit: list[dict]) -> dict[str, dict]:
    by_class: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for c in fit:
        if c["volatility_class"] != "timeless":
            by_class[c["volatility_class"]].append((c["age_days"], c["label"] == "stale"))
    out = {}
    for cls, obs in by_class.items():
        prior = PRIOR_HALF_LIFE_DAYS[VolatilityClass(cls)]
        res = fit_half_life(obs, prior)
        out[cls] = {"prior_guess_days": prior, "fitted_days": round(res.half_life_days, 1),
                    "n": res.n, "n_changed": res.n_changed}
    return out


def curve(scores: list[float], stale: list[bool], rng: random.Random | None = None) -> list[float]:
    """Catch fraction at each verified fraction in GRID. Random tie-breaking if rng given."""
    n, total = len(scores), sum(stale)
    keys = [(s, rng.random() if rng else 0.0, -i) for i, s in enumerate(scores)]
    order = sorted(range(n), key=lambda i: keys[i], reverse=True)
    cum, caught = [0], 0
    for i in order:
        caught += stale[i]
        cum.append(caught)
    return [cum[round(g * n)] / total if total else 0.0 for g in GRID]


def auc(c: list[float]) -> float:
    return sum((c[i] + c[i + 1]) / 2 for i in range(len(c) - 1)) / (len(c) - 1)


def averaged_curve(scores: list[float], stale: list[bool], reps: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    curves = [curve(scores, stale, rng) for _ in range(reps)]
    return [statistics.fmean(col) for col in zip(*curves)]


def method_scores(claims: list[dict], hl: dict[str, dict], ratings: dict[str, dict]) -> dict[str, list[float]]:
    def h(cls: str) -> float | None:
        return None if cls == "timeless" else hl[cls]["fitted_days"]
    out = {
        "halflife": [p_stale(c["age_days"], h(c["volatility_class"])) for c in claims],
        "class_only": [0.0 if h(c["volatility_class"]) is None else math.log(2) / h(c["volatility_class"]) for c in claims],
        "age_only": [float(c["age_days"]) for c in claims],
        "random": [0.0] * len(claims),
    }
    if ratings and all(c["id"] in ratings for c in claims):
        out["model_ts"] = [ratings[c["id"]]["time_sensitivity"] for c in claims]
        out["model_p"] = [ratings[c["id"]]["p_outdated"] for c in claims]
    return out


def evaluate(claims: list[dict], scores: dict[str, list[float]]) -> dict[str, dict]:
    stale = [c["label"] == "stale" for c in claims]
    res = {}
    for name, s in scores.items():
        tied = name in ("random", "class_only", "model_ts", "model_p")
        c = averaged_curve(s, stale, SHUFFLES if tied else 1, SEED)
        res[name] = {"curve": c, "auc": round(auc(c), 4),
                     "catch_at_10": round(c[10], 3), "catch_at_25": round(c[25], 3), "catch_at_50": round(c[50], 3)}
    return res


def bootstrap_auc_diff(claims: list[dict], scores: dict[str, list[float]], base: str = "halflife") -> dict[str, list[float]]:
    """95% CI of AUC(base) - AUC(other), resampling claims. Ties broken by a fixed random draw."""
    rng = random.Random(SEED + 1)
    stale = [c["label"] == "stale" for c in claims]
    n = len(claims)
    diffs: dict[str, list[float]] = defaultdict(list)
    for _ in range(BOOTSTRAP):
        idx = [rng.randrange(n) for _ in range(n)]
        st = [stale[i] for i in idx]
        if not any(st):
            continue
        a_base = auc(curve([scores[base][i] for i in idx], st, rng))
        for name, s in scores.items():
            if name != base:
                diffs[name].append(a_base - auc(curve([s[i] for i in idx], st, rng)))
    out = {}
    for name, d in diffs.items():
        d.sort()
        out[name] = [round(d[int(0.025 * len(d))], 4), round(statistics.fmean(d), 4), round(d[int(0.975 * len(d)) - 1], 4)]
    return out


def stratified_sample(test: list[dict], k: int) -> list[dict]:
    rng = random.Random(SEED)
    by_class: dict[str, list[dict]] = defaultdict(list)
    for c in test:
        by_class[c["volatility_class"]].append(c)
    per = k // len(by_class)
    sample = []
    for cls in sorted(by_class):
        pool = by_class[cls][:]
        rng.shuffle(pool)
        sample += pool[:per]
    rest = [c for c in test if c not in sample]
    rng.shuffle(rest)
    return sample + rest[: k - len(sample)]


RATING_PROMPT = """You rate how likely a factual claim is to be out of date.

Claim: "{text}"
The claim was accurate as of {asof}. Today is {today}.

Return only JSON: {{"time_sensitivity": <integer 0-10, how quickly facts of this kind change in general, judged from the claim text alone>, "p_outdated": <number 0-1, probability the claim is no longer accurate today>}}"""


async def rate_with_model(sample: list[dict], cache_path: Path) -> tuple[dict[str, dict], dict]:
    from halflife.clients.bifrost import BifrostClient, ModelError
    from halflife.config import load_settings

    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [c for c in sample if c["id"] not in cache]
    bf = BifrostClient(load_settings())
    sem = asyncio.Semaphore(8)
    spend = {"calls": 0, "cost_usd": 0.0, "failures": 0}
    before = await bf.vk_spend_usd() if todo else 0.0

    async def one(c: dict) -> None:
        prompt = RATING_PROMPT.format(text=c["text"], asof=c["asof"], today=c["reference_date"])
        async with sem:
            try:
                r = await bf.chat([{"role": "user", "content": prompt}], max_tokens=200)
            except ModelError:
                spend["failures"] += 1
                return
        spend["calls"] += 1
        m = re.search(r"\{.*\}", r.text, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
            cache[c["id"]] = {"time_sensitivity": float(d["time_sensitivity"]), "p_outdated": float(d["p_outdated"])}
        except (ValueError, KeyError, TypeError):
            spend["failures"] += 1

    await asyncio.gather(*(one(c) for c in todo))
    if todo:
        await asyncio.sleep(3)  # budget usage is updated asynchronously after each call
        spend["cost_usd"] = round(await bf.vk_spend_usd() - before, 6)
    await bf.aclose()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=1))
    return cache, spend


def plot(results: dict[str, dict], title: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    style = {"halflife": ("#c2410c", 2.6, "-"), "random": ("#6b7280", 1.4, "--")}
    for name, r in results.items():
        color, lw, ls = style.get(name, (None, 1.6, "-"))
        ax.plot([g * 100 for g in GRID], [v * 100 for v in r["curve"]], label=f"{name} (AUC {r['auc']:.3f})",
                color=color, lw=lw, ls=ls)
    ax.set_xlabel("claims verified (%)")
    ax.set_ylabel("stale claims caught (%)")
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-model", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    claims = load_claims()
    fit = [c for c in claims if c["split"] == "fit"]
    test = [c for c in claims if c["split"] == "test"]
    assert not {c["entity_id"] for c in fit} & {c["entity_id"] for c in test}, "entity leak across splits"
    assert all(date.fromisoformat(c["asof"]) >= CUTOFF for c in test), "test as-of before cutoff"

    hl = fit_classes(fit)
    full = evaluate(test, method_scores(test, hl, {}))
    full_ci = bootstrap_auc_diff(test, method_scores(test, hl, {}))

    sample = stratified_sample(test, MODEL_SAMPLE)
    ratings, spend = ({}, {"calls": 0, "cost_usd": 0.0, "failures": 0})
    if not args.no_model:
        ratings, spend = asyncio.run(rate_with_model(sample, OUT / "model_ratings.json"))
    rated = [c for c in sample if c["id"] in ratings]
    sample_scores = method_scores(rated, hl, ratings)
    on_sample = evaluate(rated, sample_scores) if rated else {}
    sample_ci = bootstrap_auc_diff(rated, sample_scores) if rated else {}

    calib = {}
    for cls in sorted({c["volatility_class"] for c in test}):
        cs = [c for c in test if c["volatility_class"] == cls]
        h = None if cls == "timeless" else hl[cls]["fitted_days"]
        calib[cls] = {"n": len(cs), "observed_stale_rate": round(sum(c["label"] == "stale" for c in cs) / len(cs), 3),
                      "mean_predicted_p_stale": round(statistics.fmean(p_stale(c["age_days"], h) for c in cs), 3),
                      "median_age_days": statistics.median(c["age_days"] for c in cs)}

    summary = {
        "generated": date.today().isoformat(), "cutoff": CUTOFF.isoformat(), "today": TODAY.isoformat(),
        "counts": {"fit": Counter(f"{c['volatility_class']}:{c['label']}" for c in fit),
                   "test": Counter(f"{c['volatility_class']}:{c['label']}" for c in test),
                   "model_sample": len(sample), "model_rated": len(rated)},
        "half_lives": hl,
        "test_full": {k: {kk: vv for kk, vv in v.items() if kk != "curve"} for k, v in full.items()},
        "test_full_auc_diff_ci95_halflife_minus": full_ci,
        "test_sample": {k: {kk: vv for kk, vv in v.items() if kk != "curve"} for k, v in on_sample.items()},
        "test_sample_auc_diff_ci95_halflife_minus": sample_ci,
        "calibration_test": calib,
        "model_spend_this_run": spend,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    (OUT / "curves.json").write_text(json.dumps({"grid": GRID, "test_full": {k: v["curve"] for k, v in full.items()},
                                                 "test_sample": {k: v["curve"] for k, v in on_sample.items()}}))
    plot(full, f"Test split, all {len(test)} claims (changes after {CUTOFF})", OUT / "curve_full.png")
    if on_sample:
        plot(on_sample, f"Test split, model sample n={len(rated)}", OUT / "curve_sample.png")
    print(json.dumps({k: summary[k] for k in ("half_lives", "test_full", "test_full_auc_diff_ci95_halflife_minus",
                                              "test_sample", "test_sample_auc_diff_ci95_halflife_minus",
                                              "calibration_test", "model_spend_this_run")}, indent=1))


if __name__ == "__main__":
    main()
