# Gateway audit on demo traffic — 2026-11-12

`summary.json` is a copy of `data/gateway_summary.json` written by
`uv run python -m halflife.gateway.audit --hours 3 --sample-cap 50 --budget 60`.

Traffic: **DEMO** — 50 answers seeded by `python -m halflife.gateway.seed` (40) and the J2 end-to-end test (10)
through stock Bifrost on two demo virtual keys (`demo-support-bot`, `demo-docs-assistant`) and two models
(`claude-haiku-5-5`, knowledge cutoff Jun 2026; `claude-haiku-4-5`, cutoff Feb 2025). Questions were chosen to
mix time-sensitive and timeless topics, so these stale rates describe this demo mix, not production traffic.

**How stale rate is computed.** For each (model, virtual key): *stale rate among verified claims* = claims with a
`changed` verdict ÷ claims verified, where "verified" means the verdict was `current` or `changed` (unverifiable
claims are excluded). The audit verifies only the riskiest claims, ranked across the whole run, up to a verification
budget — so this is **not** a stale rate over all traffic. The *verified share* (claims verified ÷ claims found) is
reported beside it.

| model | virtual key | answers | claims found | verified | verified share | changed | stale among verified |
|---|---|---|---|---|---|---|---|
| claude-haiku-4-5 | demo-docs-assistant | 12 | 36 | 12 | 0.333 | 7 | 0.583 |
| claude-haiku-4-5 | demo-support-bot | 12 | 43 | 15 | 0.349 | 11 | 0.733 |
| claude-haiku-5-5 | demo-docs-assistant | 13 | 47 | 15 | 0.319 | 4 | 0.267 |
| claude-haiku-5-5 | demo-support-bot | 13 | 46 | 9 | 0.196 | 7 | 0.778 |
| **all (seeded demo traffic)** | | 50 | 172 | 51 | 0.297 | 29 | 0.569 |

Per-row figures are confounded, not a model comparison: keys and models received different questions (the seed
alternates them by question index) and each row has 9–15 verified claims.

Run cost: 110 model calls, $0.0546 (token estimate), 88 Tavily credits (26 cache hits), 95.6 s wall time for 50
answers with 51 claims verified (verification budget 60). The J2 done-check (`tests/test_gateway.py`, live) confirms the stored
ledger stale rate equals the per-answer reports for 10 fresh requests.

This audit ran before the ledger was seeded with fitted half-lives, so `summary.json` lists every class as
`prior_guess`. Stale rates come from verdicts and are unaffected; only ranking fallbacks and TTLs use half-lives.
