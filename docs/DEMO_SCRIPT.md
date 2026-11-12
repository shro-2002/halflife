# Two-minute demo script

**Before recording** (once, off camera): `make demo` (starts stock Bifrost, sets up the relay and virtual key, seeds
~40 demo requests, runs the audit, starts the UI) with `HALFLIFE_DEMO_MODE=1` in `.env`. Open
http://localhost:8091 in a browser at 1440 px wide. Run the "Stale facts" example once off camera so its evidence is
cached (the recorded run is then fast and costs 0 credits). Keep a terminal with the Bifrost dashboard
(http://localhost:8088) in a second tab.

| Time | Click / show | Say (one sentence) |
|---|---|---|
| 0:00–0:12 | Title card, then the **Gateway audit** tab (opens by default). | "Bifrost tells you what every key cost; Half-Life tells you how much of what it served is no longer true." |
| 0:12–0:30 | Point at the stale-rate bar chart and table; hover the **DEMO TRAFFIC** badge. | "It reads Bifrost's own request logs, checks the riskiest claims under a budget, and reports stale rate per model and virtual key — here the older model is stale far more often." |
| 0:30–0:40 | Scroll to the half-life table; point at the **experimental** TTL label. | "Each kind of fact has a half-life, which also gives a cache TTL — we label that experimental because it isn't calibrated yet." |
| 0:40–0:48 | Click the **Check an answer** tab, then the **Stale facts** chip, then **Check**. | "Now one answer: a rate and a version that were true at the model's cutoff." |
| 0:48–1:05 | Show the two claim cards: **changed**, score 5, corrected value (Bank Rate → 4.0%, Node 20 → Node.js 26), the green evidence quote and source links; point at the separate "model reasoning" box. | "Each verdict rests on a verbatim quote that Tavily returned, checked in code, with the current value and sources." |
| 1:05–1:15 | Click the **Timeless facts** chip, then **Check**. Point at "Skipped — not time-sensitive. 0 searches, 0 Tavily credits". | "Timeless facts are skipped, so they cost nothing." |
| 1:15–1:27 | Tick **Simulate primary model outage**, click **Check** again; point at the **FAILOVER: served by claude-haiku-4-5** badge. | "If the primary model fails, Bifrost's fallback serves the check and the report says so." |
| 1:27–1:45 | Click the **Evidence** tab; point at the budget-curve chart and the caught@25/50% table. | "On 108 labelled cases, verifying half the answers caught 84% of stale claims, versus 46% in random order." |
| 1:45–1:55 | Point at the caption "Haiku's own outdated-probability ranks better than the half-life model". | "We measured our own idea honestly: the model's estimate ranks better than the half-life model, so it's the default." |
| 1:55–2:00 | Switch to the Bifrost dashboard tab (Logs / Relay Logs) showing the Tavily relay calls under the virtual key. | "Stock Bifrost, public APIs only — every model call and every search is governed and logged by the gateway." |

Numbers on screen come from `results/2026-11-12-detector`, `results/2026-11-12-gateway-audit` and live checks; the
Bank of England and Node values reflect the evidence retrieved on the day of recording.
