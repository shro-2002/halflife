# J3 live detector evaluation — eval date 2026-11-12

Reproduce tables from saved results (no spend): `uv run python -m eval.run --offline` (`make eval`).
Live rerun: `uv run python -m eval.run` (needs Bifrost + keys; evidence is disk-cached per day).

**Protocol (fixed before running).** 108 labelled cases (eval/cases.jsonl, one annotator). Each case's
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

## Headline (run 2)

| Metric | Value | 95% CI (by source URL) |
|---|---|---|
| Precision (stale flagged correctly) | **0.854** (35 / 41) | [0.742, 0.950] |
| Recall (stale caught) | **0.921** (35 / 38) | [0.828, 1.000] |
| Unverifiable rate (time-sensitive cases) | 0.084 | |
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

## Budget curve (run 2): stale claims caught vs answers verified

| Ordering | caught @25% | caught @50% | caught @100% |
|---|---|---|---|
| Haiku outdated-probability (product default) | **0.462** [0.366, 0.574] | **0.842** [0.703, 0.938] | 0.921 |
| Half-life | 0.387 [0.276, 0.500] | 0.708 [0.586, 0.853] | 0.921 |
| Random (expected) | 0.233 | 0.460 | 0.921 |

Curve: `budget_curve.png`, data: `curves.json`. @100% equals recall (every case verified).

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
