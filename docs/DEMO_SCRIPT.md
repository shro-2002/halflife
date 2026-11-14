# Two-minute demo script

**Before recording** (once, off camera): `make demo` (starts stock Bifrost, sets up the relay and virtual key, seeds
~40 demo requests, runs the audit (use `--budget 120 --random-share 0.5 --virtual-keys demo-support-bot,demo-docs-assistant` for the estimate on screen), starts the UI) with `HALFLIFE_DEMO_MODE=1` in `.env`. Open
http://localhost:8091 in a browser at 1440 px wide. Run the "Stale facts" example once off camera so its evidence is
cached (the recorded run is then fast and costs 0 credits). Keep a terminal with the Bifrost dashboard
(http://localhost:8088) in a second tab.

| Time | Click / show | Say (one sentence) |
|---|---|---|
| 0:00–0:08 | Title card, then the **Check an answer** tab. | "Bifrost tells you what every key cost; Half-Life tells you whether what it served is still true." |
| 0:08–0:28 | Click the **Stale facts** chip, then **Check**. Show the two claim cards: **changed**, score 5, corrected value (Bank of Canada 2.25% → 2.5%, Justin Trudeau → Mark Carney), the green evidence quote and source links; point at the separate "model reasoning" box. | "Each verdict rests on a verbatim quote that Tavily returned, checked in code, with the current value and sources; no quote, no verdict." |
| 0:28–0:38 | Click the **Timeless facts** chip, then **Check**. Point at "Skipped — not time-sensitive. 0 searches, 0 Tavily credits". | "Timeless facts are skipped, so they cost nothing." |
| 0:38–0:50 | Tick **Simulate primary model outage**, click **Check** again; point at the **FAILOVER: served by claude-haiku-4-5** badge. | "If the primary model fails, Bifrost's fallback serves the check and the report says so." |
| 0:50–1:12 | Click the **Gateway audit** tab; point at **Estimated stale rate across the sampled answers** (47.7%, CI 37–59%) and the **DEMO TRAFFIC** badge, then the "budget did not bind" note. | "The same check runs over answers Bifrost already logged; this number describes our seeded question list, hand-picked and mostly time-sensitive, not anyone's real traffic, and here the budget covered almost every claim." |
| 1:12–1:22 | Point at the bar chart and its **confounded** caption. | "Per-model and per-key bars show the pipeline working; each slice got different questions, so they are not a model comparison." |
| 1:22–1:42 | Click the **Evidence** tab; point at the budget-curve chart, then the note above the tables (mean of live runs 1–2). The budget table below it shows run 2 alone (84% / 68% / 46%). | "On 108 labelled cases, verifying half the claims caught 83% of the stale ones risk-ranked, against 69% random among time-sensitive claims and 47% blind random: about 14 points from the ranking." |
| 1:42–1:52 | Point at the lift table: the half-life intervals span zero. | "We measured our own idea honestly: the half-life model adds no measurable lift over that baseline, so the model's estimate is the default." |
| 1:52–2:00 | Switch to the Bifrost dashboard tab (Logs / Relay Logs) showing the Tavily relay calls under the virtual key. | "Stock Bifrost, public APIs only — every model call and every search is governed and logged by the gateway." |

Numbers on screen come from `results/2026-11-12-detector` (note above the tables: `fair_baseline.json` and `variance.json`; tables: run 2 `summary.json`), `results/2026-11-13-gateway-audit` and live checks; the
Bank of England and Node values reflect the evidence retrieved on the day of recording.
