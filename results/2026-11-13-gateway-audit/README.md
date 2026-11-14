# Gateway audit with an estimated stale rate — 2026-11-13 (seeded demo traffic)

`summary.json` = `uv run python -m halflife.gateway.audit --hours 30 --sample-cap 50 --budget 120 --random-share 0.5
--virtual-keys demo-support-bot,demo-docs-assistant`. Same 50 seeded **demo** answers as `results/2026-11-12-gateway-audit`
(2 demo keys × 2 models); claims were re-extracted, so counts differ from that run.

**What the traffic is.** 40 hand-picked questions from `halflife/gateway/seed.py` (28 about time-sensitive facts, 12
timeless) plus 10 more picked from that list by the J2 end-to-end test (8 time-sensitive, 2 timeless;
36 time-sensitive and 14 timeless questions in all), alternating between `claude-haiku-5-5` (knowledge
cutoff June 2026) and `claude-haiku-4-5` (cutoff February 2025), with no retrieval. Every number below is a property
of that question list, not of any real gateway's traffic.

**Population.** The audit reads the newest 50 answers in the window (not a random draw of all traffic). 177 claims
were extracted; 75 are time-sensitive, the other 102 are timeless facts or dated past events, which cannot go stale and
are never verified. The 75 are the one population for both verification and the estimate.

**Estimated stale rate across the sampled answers: 0.477, 95% CI [0.369, 0.590]**; with the unverifiable sampled
claims counted all current / all stale: 0.428–0.528. The interval covers claim-level sampling error only. Claims
cluster within answers and the bootstrap resamples claims, not answers, so the interval does not cover that
clustering, nor the choice of the newest 50 answers, nor detector error: labels come from the detector (post-fix
live run: precision 0.854, recall 0.921; it flags 13% of current claims as changed, which pushes low true stale rates
up). 60 of 75 claims were sampled, so the bootstrap without a finite-population correction is conservative for these
75 claims.

**The budget did not bind.** Budget 120 claims (60 to the riskiest claims, 60 to a stratified random sample in 4
rank-score strata) against 75 time-sensitive claims: 60 of 75 were sampled at random and 63 of 75 (84%) got a
current or changed verdict, the rest were unverifiable. The top-risk figure, stale among verified 0.508 (32 changed
of 63 verified), is close to the estimate because the two sets nearly coincide. This run shows the pipeline, not a
budgeted sample.

**Per-slice figures are confounded, not a model comparison.** Keys and models received different questions (the seed
alternates them by question index), and each (model, key) slice has 11–20 verified claims and 11–18 random samples
(`summary.json`). The slices do not show which model or key serves more stale content.

Cost: 125 Tavily credits (136 calls, 11 cache hits), $0.063 model (token estimate).
