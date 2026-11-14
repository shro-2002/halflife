# J3 live detector evaluation — eval date 2026-11-12

Reproduce tables from saved results (no spend): `uv run python -m eval.run --offline` (`make eval`).
Live rerun: `uv run python -m eval.run` (needs Bifrost + keys; evidence is disk-cached per day).

**Protocol (fixed before running).** 108 labelled cases (eval/cases.jsonl, one annotator; a case was kept only if
a Tavily result states its current truth verbatim, so recall is measured on facts Tavily can retrieve). Each case's
claim is the answer; as_of = runtime model's knowledge cutoff (2026-06-30) for every case so the as-of
date cannot leak the label; today = 2026-11-12. Check mode: every time-sensitive claim found is
verified. Predicted stale = any claim gets `changed`; `unverifiable` = not flagged. CIs: 1000 bootstrap
resamples of **source URLs** (82 URLs; stale/current pairs share URLs), not cases.

## Runs
- **Run 1** (`run1/`): found one code bug — a `changed` verdict whose "new" value equalled the claimed
  value numerically (2.50% vs 2.5%) was not downgraded (`c-boc-rate`). Fixed in `halflife/verify.py`
  (numeric normalisation), regression test added. **No prompt was changed.**
- **Run 2** (this folder, headline): full rerun once after the fix. Model outputs are not deterministic;
  run 1 → run 2 differences on other cases are run-to-run variation.

## Variance across five runs (`variance.json`)

| Run | search | precision | recall | uncached queries |
|---|---|---|---|---|
| 1 | live, cold cache (before bug fix) | 0.841 | 0.974 | 0 |
| 2 | live, warm cache | 0.854 | 0.921 | 0 |
| 3 | cached evidence only | 0.861 | 0.816 | 17 |
| 4 | cached evidence only | 0.868 | 0.868 | 11 |
| 5 | cached evidence only | 0.889 | 0.842 | 16 |

**Detector headline = run 2, after the bug fix** (detail below): precision **0.854** [0.742, 0.950], recall **0.921**
[0.828, 1.000]. Run 1 (before the fix) is shown separately: precision 0.841 [0.733, 0.944], recall 0.974 [0.912, 1.000].

**Budget orderings, mean of live runs 1–2** (`fair_baseline.json`, `uv run python -m eval.fair_baseline`): caught@50%
of claims — model **0.831**, half-life 0.712, random among time-sensitive cases (fair baseline) **0.694**, blind random
0.474; caught@25%: 0.470 / 0.383 / 0.348 / 0.239. The fair baseline orders the cases the extractor marked
time-sensitive at random and the rest last, because the product never searches timeless claims or dated past events.
Lift over it, run 1 / run 2 (95% CI, paired bootstrap of source URLs): model @50% +0.109 [0.022, 0.197] / +0.167
[0.055, 0.232], @25% +0.121 [0.032, 0.224] / +0.123 [0.031, 0.222]; half-life @50% +0.003 [−0.067, 0.065] / +0.033
[−0.027, 0.095], @25% +0.023 [−0.071, 0.097] / +0.048 [−0.033, 0.130]. **The half-life ordering's intervals all span
zero: no measurable lift over the fair baseline.**

**Cached-evidence-only runs 3–5 = precision stability check**, not averaged with the live runs: precision 0.873
(0.861–0.889). Their recall, 0.842 (0.816–0.868), is a **lower bound**: the extractor phrases each claim slightly
differently on every run, so search queries change, and in these runs a query never seen before could not be
searched and counted as unverifiable. Runs 3–5 made 0 Tavily calls. All values: `variance.json`.

**Run 6 (2026-11-13, judge evidence order):** the judge prompt now prefers official-domain evidence, then the newest
publication date, when sources disagree (evidence is also listed in that order). Rerun once from the eval date's
cached evidence (`run6-judge-order/`, `HALFLIFE_CACHE_DATE=2026-11-12`, 0 Tavily credits): precision 0.865 (cached-only
runs 3–5: 0.861–0.889), recall 0.842 (lower bound) — no precision drop.

## Run 2 in detail

| Metric | Value | 95% CI (by source URL) |
|---|---|---|
| Precision (stale flagged correctly) | **0.854** (35 / 41) | [0.742, 0.950] |
| Recall (stale caught) | **0.921** (35 / 38) | [0.828, 1.000] |
| Unverifiable rate (time-sensitive cases) | 0.084 | |
| Current cases flagged as changed | 0.133 (6 / 45; 6 / 36 searched = 0.167) | [0.047, 0.234] |
| Timeless cases flagged / searched | 0 / 0 of 25 | |

Run 1 for comparison: precision 0.841 [0.733, 0.944], recall 0.974 [0.912, 1.000].

Confusion (run 2; rows = label, columns = outcome):

| label | changed | current | unverifiable | not searched |
|---|---|---|---|---|
| stale (38) | 35 | 1 | 2 | 0 |
| current (45) | 6 | 25 | 5 | 9 |
| timeless (25) | 0 | 0 | 0 | 25 |

"not searched" current cases are dated past events the extractor correctly marked as non-decaying
(e.g. a release date), counted as not flagged.

## Budget curve (run 2): stale claims caught vs claims verified

| Ordering | caught @25% | caught @50% | caught @100% |
|---|---|---|---|
| Haiku outdated-probability (product default) | **0.462** [0.366, 0.574] | **0.842** [0.703, 0.938] | 0.921 |
| Half-life | 0.387 [0.276, 0.500] | 0.708 [0.586, 0.853] | 0.921 |
| Random among time-sensitive cases (fair baseline, expected) | 0.339 | 0.675 | 0.921 |
| Blind random (expected) | 0.233 | 0.460 | 0.921 |

Curve: `budget_curve.png`, data: `curves.json`. @100% equals recall (every case verified), which is why every curve
tops out at 0.92. Lift over the fair baseline (run 2): model +0.123 @25%, +0.167 @50%; half-life +0.048, +0.033 with
intervals spanning zero (`summary.json` → `lift_over_random_time_sensitive`).

**Measurement bias.** The detector flags 13% of current cases as changed (17% of those it searched). Estimates built
on its labels read high when the true stale rate is low: with recall 0.92, traffic that is truly 5% stale would read
about 17–20%. These current cases are hard by design (each paired with a stale twin), so the rate on real traffic may
be lower; it is not measured.

## Cost and latency per answer

Run 1 had a cold evidence cache, so it shows real search cost; run 2 reused cached evidence.

| Budget (model ordering) | model $ / answer | Tavily credits / answer | latency mean / median |
|---|---|---|---|
| 25% (run 1) | $0.000306 | 0.48 | 2.37 s / 1.36 s |
| 50% (run 1) | $0.000470 | 0.98 | 3.55 s / 3.36 s |
| 100% (run 1) | $0.000579 | 1.31 | 4.31 s / 4.89 s |
| 100% (run 2, warm cache) | $0.000582 | 0.31 | 2.82 s / 2.66 s |

Totals: run 1 $0.0626 and 141 credits (token cost; virtual-key delta $0.0626); run 2 $0.0628 (token
cost; its key delta also includes a concurrent gateway audit) and 33 credits. Single-claim answers, so
cost per answer here is lower than the multi-claim answers in `results/2026-11-12-checks10`.

## Per class (run 2)

| Class | n time-sensitive | precision | recall | readable? |
|---|---|---|---|---|
| law_or_regulation | 21 | 0.90 | 0.90 | yes |
| office_holder | 18 | 0.875 | 0.875 | yes |
| software_version | 14 | 0.78 | 1.00 | thin (< 15) |
| price | 13 | 1.00 | 1.00 | **too thin** |
| rate_or_statistic | 12 | 1.00 | 0.80 | **too thin** |
| product_spec | 5 | 0.50 | 1.00 | **too thin** |
| timeless | 25 | 0 flagged | — | — |

## Errors (`errors.md`: confusion + every wrong verdict with its evidence)
- **Stale index:** `s-boe-rate` — Tavily returned the Bank of England page still saying 3.75%; the rate
  was raised on 5 Nov 2026. A search index can lag a change by days.
- **Judgment errors (judge over-reads evidence):** `c-ecb-president` (announced departure treated as
  done), `c-iphone17pro-chip` and `c-newest-iphone` (iPhone 18 Pro / foldable evidence applied to the
  17 Pro or "flagship"), `c-ubuntu-lts` (point release read as a new release).
- **Label disputed, not changed:** `c-django` — evidence includes Django 6.1.3 release notes, so the
  case may have changed after labelling; `c-au-super` — from 1 July 2026 the guarantee is computed on
  "qualifying earnings", so the claim's "ordinary time earnings" may be outdated. Labels are frozen at
  Gate 2 and were not edited; these count as false positives above.
- **Unverifiable on stale:** `s-401k`, `s-lu-grandduke` (no quote survived the verbatim check).
