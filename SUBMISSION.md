# Submission — Geek Room Global AI Hackathon 2026 (HackCulture)

**Project:** Half-Life
**Tracks:** Problem Statement 06 (Tavily: Stale-Answer Detector) and Problem Statement 04 (Bifrost: a feature the
open-source gateway is missing), as one integrated product.
**Repository:** <GitHub URL — filled at release>
**Demo video:** <URL — recorded by the author>

## Project description

Half-Life tells an AI gateway which answers to re-check, and when. It runs beside a stock Bifrost gateway, reads the
traffic Bifrost already logs, finds time-sensitive claims in the answers (prices, software versions, office holders,
rates, laws), verifies the riskiest ones against live web sources with Tavily, and reports a freshness score per claim
and a stale rate per model and virtual key. It also checks any answer on demand (API, UI and an MCP tool inside
Bifrost's MCP gateway), and experimentally sets a cache TTL per request from fitted fact half-lives.

## The problem being solved

Gateways report cost, latency and errors, but not whether what they served is still true. Models answer from a fixed
knowledge cutoff and state outdated prices, versions and office holders confidently. Verifying every answer costs
extra model calls, searches and seconds, so nobody does it on production traffic; and gateway caches use one TTL for
every answer regardless of how fast the facts in it decay. Half-Life gives operators a stale-rate metric per model and
key from logged traffic, spends a verification budget where staleness is likely (measured: verifying half the answers
caught 0.842 of stale claims, versus 0.460 for random order, on 108 labelled cases), and grounds every verdict in a
verbatim quote from a retrieved source.

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
- All judgment calls (scope, positioning, label approval, release) were made by the human author.

## Key results (all from `results/`)

| What | Number | File |
|---|---|---|
| Detector precision / recall (108 cases) | 0.854 [0.742, 0.950] / 0.921 [0.828, 1.000] | results/2026-11-12-detector |
| Stale caught at 50% verified: model ordering / half-life / random | 0.842 / 0.708 / 0.460 | results/2026-11-12-detector |
| Ordering AUC (300 claims): model / half-life / random | 0.826 / 0.782 / 0.499 | results/2026-11-12-ordering |
| Cost per check (10 answers) | $0.0011, 2.8 Tavily credits, median 5.9 s | results/2026-11-12-checks10 |
| Demo audit (50 answers, 2 keys × 2 models) | stale rate 0.27–0.78 per slice | results/2026-11-12-gateway-audit |
