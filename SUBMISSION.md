# Submission — Geek Room Global AI Hackathon 2026 (HackCulture)

**Project:** Half-Life
**Tracks:** Problem Statement 06 (Tavily: Stale-Answer Detector) and Problem Statement 04 (Bifrost: a feature the
open-source gateway is missing), as one integrated product.
**Repository:** https://github.com/shro-2002/halflife
**Demo video:** https://youtu.be/0BJx83UlPSU
**Upstream issue:** [maximhq/bifrost#10039](https://github.com/maximhq/bifrost/issues/10039), a feature request for an
exclusion filter on log queries and a reasoning-docs fix (proposal text: `docs/UPSTREAM.md`).

## Project description

Half-Life tells an AI gateway which answers to re-check, and when. It runs beside a stock Bifrost gateway, reads the
traffic Bifrost already logs, finds time-sensitive claims in the answers (prices, software versions, office holders,
rates, laws), verifies the riskiest ones against live web sources with Tavily, and reports a freshness score per claim
and a stale rate per model and virtual key. It also checks any answer on demand (API, UI and an MCP tool inside
Bifrost's MCP gateway), estimates the stale rate across the sampled answers from a stratified random sample of their
claims (interval coverage validated on 1,763 labelled claims), and experimentally sets a cache TTL per request from
fitted fact half-lives.

## The problem being solved

Gateways report cost, latency and errors, but not whether what they served is still true. Models answer from a fixed
knowledge cutoff and state outdated prices, versions and office holders confidently. Verifying every answer costs
extra model calls, searches and seconds, so nobody does it on production traffic; and gateway caches use one TTL for
every answer regardless of how fast the facts in it decay. Half-Life gives operators a stale-rate metric per model and
key from logged traffic, spends a verification budget where staleness is likely, and grounds every verdict in a
verbatim quote from a retrieved source. Measured on 108 labelled cases (mean of the two live runs): verifying half
the claims caught 83% of the stale ones risk-ranked, against 69% in random order among time-sensitive claims (the
fair baseline, since timeless claims are never searched) and 47% in blind random order; the lift over the fair
baseline is about 14 points, and the half-life ordering shows no measurable lift over it.

## Technologies used

- **Bifrost** (stock v2.5.1 via `npx @maximhq/bifrost`): model routing with fallback, virtual keys and budgets, the
  logging API (audit source), a Relay that puts Tavily behind the gateway, per-request cache TTL headers, the MCP gateway.
- **Tavily** Search API (basic depth, recency filter, official-domain search) — the only source of evidence.
- **Anthropic Claude Haiku 5.5** (runtime model, through Bifrost), Claude Haiku 4.5 as fallback.
- Python 3.11+, FastAPI, httpx, Pydantic, SciPy (MAP half-life fit), SQLite (fact ledger), MCP Python SDK; plain
  HTML/JS UI with Chart.js; Redis Stack (optional, only for the experimental cache-TTL proxy); Docker; GitHub Actions.
- Data for the ordering study: Wikidata, PyPI, npm and BIS policy-rate histories.

## How AI is used (inside the product)

- Claude Haiku 5.5 extracts time-sensitive claims from an answer (exact spans, volatility class, tense-aware) and, in the
  same call, estimates the probability each claim is outdated; that probability orders the verification budget.
- For each verified claim, Haiku acts as a judge over Tavily evidence only; code accepts a verdict only if its quote
  appears verbatim in the retrieved text, and a corrected value only if the evidence states it.
- Survival analysis (a per-class half-life fitted by MAP from verification outcomes) provides the fallback ranking,
  re-scores cached answers as they age without a model call, and drives the experimental cache TTL.
- Measured honestly: the model's own outdated-probability ranks stale claims better than the half-life model (AUC
  0.826 vs 0.782), so it is the default; calibration is not yet good enough, so the TTL is labelled experimental.

## AI tools used to build it

- **Claude Code (Claude Opus 5.5)** as the lead agent for the whole build: documentation checks, code, tests,
  evaluation and packaging, following a task graph with three human approval gates.
- **Claude subagents** (spawned from Claude Code) for parallel workers (extractor, verifier, ledger, labelled cases, UI)
  and independent verifiers (correctness, API currency against live docs, source re-checks, fresh-eyes quickstart).
- Automated security review and Semgrep findings raised during the build were fixed and are recorded in the git history.
- **ElevenLabs** for the demo video narration (voice Matilda, `eleven_multilingual_v2`), generated from the author's
  approved script and edited into a real screen recording of the running app in replay mode (no live checks, no
  Tavily credits spent).
- All judgment calls (scope, positioning, label approval, release) were made by the human author.

## Key results (all from `results/`)

Labelled set: 108 cases, one annotator, pre-screened to facts a Tavily result states verbatim.

| What | Number | File |
|---|---|---|
| Detector, post-fix live run 2 (headline) | precision 0.854 [0.742, 0.950], recall 0.921 [0.828, 1.000] (95% CI by source URL) | results/2026-11-12-detector/summary.json |
| Detector, pre-fix live run 1 (separate) | precision 0.841 [0.733, 0.944], recall 0.974 [0.912, 1.000]; cached-only stability runs: precision 0.873, recall ≥ 0.816 (lower bound) | results/2026-11-12-detector/run1, variance.json |
| Current claims flagged as changed (run 2) | 6 of 45 = 13% [5%, 23%]: low true stale rates read high (truly 5% stale reads about 17–20%) | results/2026-11-12-detector/summary.json |
| Stale caught at 50% of claims verified, live runs 1–2: model / random among time-sensitive (fair) / blind random | 0.831 / 0.694 / 0.474 | results/2026-11-12-detector/fair_baseline.json |
| Lift over the fair baseline at 50%, run 1 / run 2 | model +0.109 [0.022, 0.197] / +0.167 [0.055, 0.232]; half-life +0.003 [−0.067, 0.065] / +0.033 [−0.027, 0.095] (spans zero) | results/2026-11-12-detector/fair_baseline.json |
| Ordering AUC (300 claims): model / half-life / random | 0.826 / 0.782 / 0.499 | results/2026-11-12-ordering |
| Estimator interval coverage (1,763 labelled claims) | 95% CI coverage 0.74 at 18, 0.89 at 30, 0.945 at 60 samples; unbiased by construction (simulated abs bias ≤ 0.004) | results/2026-11-13-estimator-validation |
| Cost per check (10 answers) | $0.0011 model cost + 2.8 Tavily credits (≈ $0.022 at $0.008/credit pay-as-you-go, Tavily docs 2026-11-14) ≈ $0.024; median 5.9 s | results/2026-11-12-checks10 |
| Gateway audit, seeded demo traffic | estimated stale rate across the sampled answers 0.477 [0.369, 0.590]: a property of the seeded question list (hand-picked, mostly time-sensitive, half sent to a model with a Feb 2025 cutoff); budget 120 did not bind on 75 claims; per-slice bars confounded (different questions per slice, 11–20 verified claims each) | results/2026-11-13-gateway-audit |
