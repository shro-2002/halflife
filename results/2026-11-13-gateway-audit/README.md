# Gateway audit with traffic-wide estimate — 2026-11-13 (seeded demo traffic)

`summary.json` = `uv run python -m halflife.gateway.audit --hours 30 --sample-cap 50 --budget 120 --random-share 0.5
--virtual-keys demo-support-bot,demo-docs-assistant`. Same 50 seeded **demo** answers as `results/2026-11-12-gateway-audit`
(2 demo keys × 2 models); claims were re-extracted, so counts differ from that run.

Budget 120 claims: 60 to the riskiest claims, 60 to a stratified random sample (4 rank-score strata) of all 75
time-sensitive claims found. **Traffic-wide estimate: 0.477, 95% CI [0.369, 0.590]**; with the unverifiable
sampled claims counted all current / all stale: 0.428–0.528. Top-risk figure: stale among verified 0.508 (32 changed of
63 verified). Counts: 177 claims extracted from the 50 answers; 75 of them are time-sensitive (the other 102 are
timeless facts or dated past events, which cannot go stale and are never verified); 63 of the 75 got a current or
changed verdict, the rest were unverifiable. The 75 are the one population for both verification and the estimate. The 95% interval covers sampling error only: labels come from the detector (live-run precision 0.847, recall 0.948), and the population is the time-sensitive claims the extractor found in the sampled answers. The random sample is 60 of 75 claims, so the bootstrap (no finite-population
correction) is conservative. Per-slice estimates (n = 11–18 each) are in `summary.json`; too few samples to read.
Cost: 125 Tavily credits (136 calls, 11 cache hits), $0.063 model (token estimate).
