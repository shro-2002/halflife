# Gateway audit on demo traffic — 2026-11-12

`summary.json` is a copy of `data/gateway_summary.json` written by
`uv run python -m halflife.gateway.audit --hours 3 --sample-cap 50 --budget 60`.

Traffic: **DEMO** — 50 answers seeded by `python -m halflife.gateway.seed` (40) and the J2 end-to-end test (10)
through stock Bifrost on two demo virtual keys (`demo-support-bot`, `demo-docs-assistant`) and two models
(`claude-haiku-5-5`, knowledge cutoff Jun 2026; `claude-haiku-4-5`, cutoff Feb 2025). Questions were chosen to
mix time-sensitive and timeless topics, so these stale rates describe this demo mix, not production traffic.

| model | virtual key | answers | claims verified | changed | stale rate |
|---|---|---|---|---|---|
| claude-haiku-4-5 | demo-docs-assistant | 12 | 12 | 7 | 0.583 |
| claude-haiku-4-5 | demo-support-bot | 12 | 15 | 11 | 0.733 |
| claude-haiku-5-5 | demo-docs-assistant | 13 | 15 | 4 | 0.267 |
| claude-haiku-5-5 | demo-support-bot | 13 | 9 | 7 | 0.778 |

Run cost: 110 model calls, $0.0546 (token estimate), 88 Tavily credits (26 cache hits), 95.6 s wall time for 50
answers with 60 claims verified (budget). The J2 done-check (`tests/test_gateway.py`, live) confirms the stored
ledger stale rate equals the per-answer reports for 10 fresh requests.
