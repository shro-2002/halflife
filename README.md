# Half-Life

**Facts decay. Half-Life tells an AI gateway which answers to re-check, and when.**

Half-Life sits beside a stock [Bifrost](https://github.com/maximhq/bifrost) gateway. It reads the traffic Bifrost
already logs, finds time-sensitive claims in the answers (prices, versions, office holders, rates, laws), verifies
the riskiest ones against live web sources through [Tavily](https://tavily.com), and reports a stale rate per model
and virtual key. It also checks any single answer on demand, and (experimentally) sets a cache TTL per request.

## 1. The operator problem

Bifrost tells an operator what every virtual key cost, how long it took and whether it errored. It says nothing about
whether what it served is still true. A model with a June 2026 knowledge cutoff will confidently state a policy
rate or a "latest version" that changed in October. Checking every answer against the web costs extra model calls,
searches and seconds, so nobody does it on production traffic. And Bifrost's cache uses one TTL for every answer,
whether the question was the capital of France or the latest Python release.

## 2. What Half-Life adds

1. **Traffic audit (lead feature).** Reads recent requests from Bifrost's logging API, verifies the riskiest claims
   under a budget, and stores **stale rate by model and virtual key** in a fact ledger
   (`halflife/gateway/audit.py`). On 50 answers of **seeded demo traffic** through stock Bifrost, the stale rate
   among verified claims ranged from 0.27 to 0.78 per (model, key) slice, with 29.7% of found claims verified
   ([results](results/2026-11-12-gateway-audit/README.md)).

   **How stale rate is computed.** For each (model, virtual key): *stale rate among verified claims* = claims with a
   `changed` verdict ÷ claims verified, where "verified" means the verdict was `current` or `changed` (unverifiable
   claims are excluded). The audit verifies only the riskiest claims, ranked across the whole run, up to a verification
   budget — so this is **not** a stale rate over all traffic. The *verified share* (claims verified ÷ claims found) is
   reported beside it.
2. **Budgeted verification with a measured curve.** Claims are ranked by the extractor model's own probability that
   the claim is outdated, so a budget is spent where staleness is likely. On 108 labelled cases, verifying the top
   50% of answers caught **0.788** of stale claims on average over five runs (range 0.724–0.842; random order 0.441)
   ([results](results/2026-11-12-detector/README.md)).
3. **Decay-based cache TTL (experimental).** Each volatility class has a fitted half-life; the recommended TTL is the
   time until P(stale) reaches 5%. A proxy puts that TTL on each request with Bifrost's own `x-bf-cache-ttl`
   header (`halflife/gateway/proxy.py`). **Experimental:** the half-lives are not calibrated (see Limits).

Plus a check API and UI (`POST /v1/check`), and a `check_freshness` MCP tool registered in Bifrost's MCP gateway.

## 3. Quickstart (stock Bifrost, base profile, no Redis)

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 18+ (for `npx`), an Anthropic API key and a
Tavily API key (free tier: 1,000 credits/month).

```bash
git clone <this repo> halflife && cd halflife
cp .env.example .env    # fill ANTHROPIC_API_KEY, TAVILY_API_KEY, BIFROST_ADMIN_USERNAME/PASSWORD, BIFROST_SETUP_TOKEN
                        # (HALFLIFE_CONTACT_URL only for the eval scripts: Wikidata wants a contact URL)
uv sync
make bifrost            # stock Bifrost v2.5.1 via npx on :8088 (BIFROST_PORT), admin auth from .env
make setup              # Anthropic provider, Tavily relay, virtual key "halflife-dev" ($10 budget), fitted half-lives
make api                # Half-Life API + UI on http://localhost:8091 (stays in the foreground; use a
                        # second terminal, or `make api-bg`). Other port: make api PORT_API=<port>
```

Check one answer:

```bash
curl -s localhost:8091/v1/check -H 'Content-Type: application/json' \
  -d '{"answer": "The Bank of England base rate is 5.25%."}' | python3 -m json.tool
```

Audit gateway traffic (seed demo traffic first if your gateway has none):

```bash
uv run python -m halflife.gateway.seed     # ~40 demo requests on two demo keys and two models
uv run python -m halflife.gateway.audit    # writes data/gateway_summary.json; shown in the UI's Gateway tab
```

`make demo` does all of the above in one command. `make test` runs the offline suite (no keys needed).

Optional pieces:
- **Cache-TTL proxy (needs Redis):** `docker compose up -d redis`, then `BIFROST_PORT=8089 scripts/bifrost.sh cache`,
  `BIFROST_PORT=8089 make setup`, `BIFROST_PORT=8089 uv run uvicorn halflife.gateway.proxy:app --port 8093`.
  Bifrost's cache plugin needs a vector store even in exact-match mode; only this proxy needs Redis.
- **MCP tool:** `uv run python -m halflife.gateway.mcp_server --register` serves `check_freshness` and adds it to
  Bifrost's MCP gateway, granted to the demo keys.

## 4. Requirements map

| Requirement | Where |
|---|---|
| **T1** Claim identification | `halflife/extract.py` (one Haiku call; spans must be exact substrings; tense kept: dated past events do not decay) |
| **T2** Freshness detection (pricing, API versions, laws, leadership) | `halflife/extract.py` volatility classes + `p_outdated_model`; `halflife/risk.py` half-life P(stale) |
| **T3** Live verification | `halflife/verify.py` (two parallel Tavily searches via the Bifrost relay; judge must quote evidence verbatim, checked in code) |
| **T4** Freshness score per claim | `halflife/risk.py::freshness_score` (95 / 80 / 5 / unverified ≤ 50 / estimated; timeless unscored) |
| **B1** Real operator problem | stale rate per model and virtual key: `halflife/gateway/audit.py`; TTL proxy: `halflife/gateway/proxy.py` |
| **B2** Public extension points | logging API (`GET /api/logs`, `/api/logs/{id}`), governance (virtual keys, budgets, relay and MCP grants), Relays, cache headers, MCP gateway — no Go plugin, no fork |
| **B3** Reproducible on standard Bifrost | `scripts/bifrost.sh` (stock `npx @maximhq/bifrost`), `make setup`, `scripts/spike.sh`, `Dockerfile` |
| **B4** Contribution quality | 146 offline tests + live tests (`make test`), CI (`.github/workflows/ci.yml`), `docs/UPSTREAM.md`, `CONTRIBUTING.md`, Apache-2.0 |

## 5. What Bifrost contributes, what Tavily contributes

**Bifrost** is the platform: it routes every model call (Anthropic provider, `claude-haiku-5-5` with automatic
fallback to `claude-haiku-4-5`), enforces the virtual key's $10 budget, logs every request (which is what the audit
reads), caches with per-request TTLs (which the proxy sets), hosts the Tavily credential behind a **relay** so search
calls are governed and logged under the same virtual key, and serves `check_freshness` through its MCP gateway.

**Tavily** is the evidence: every verdict rests only on text Tavily returned, via an open-web search with a recency
filter and a domain-restricted search on the official site when one is known. 1 credit per basic search.

## 6. Results

All numbers come from files under `results/`; each folder has a README with the protocol and a reproduce command.

**Live detector, 108 labelled cases** (eval date 2026-11-12), mean over five runs with the range beside it —
[variance.json](results/2026-11-12-detector/variance.json), [results README](results/2026-11-12-detector/README.md)

| Metric | Mean of 5 runs | Range | One run's 95% CI (run 2, by source URL) |
|---|---|---|---|
| Precision | **0.863** | 0.841–0.889 | [0.742, 0.950] |
| Recall | **0.884** | 0.816–0.974 | [0.828, 1.000] |
| Timeless cases flagged | 0 of 25 in every run | | |

Recall varies because the extractor phrases each claim slightly differently on every run, so the search query and the retrieved evidence change; in the three cached-evidence runs, queries never seen before could not be searched and count as unverifiable, so their recall is a lower bound.

| Budget ordering | stale caught @25% (mean, range) | @50% (mean, range) |
|---|---|---|
| Haiku outdated-probability (default) | 0.438 (0.406–0.477) | 0.788 (0.724–0.842) |
| Half-life | 0.365 (0.338–0.387) | 0.681 (0.646–0.715) |
| Random | 0.224 (0.207–0.246) | 0.441 (0.406–0.487) |

**The model's own estimate ranks better than the half-life model.** On the time-travel ordering dataset
([results/2026-11-12-ordering](results/2026-11-12-ordering/README.md)), 300-claim sample:

| Ordering | AUC | caught @10% | @25% | @50% |
|---|---|---|---|---|
| Haiku P(outdated), given as-of date | 0.826 | 0.357 [0.303, 0.429] | 0.748 [0.670, 0.836] | 0.980 |
| Half-life (fitted per class) | 0.782 | 0.298 [0.238, 0.356] | 0.655 [0.556, 0.750] | 0.917 |
| Class only / age only / random | 0.696 / 0.606 / 0.499 | | | |

The gap holds on claims dated after the model's knowledge cutoff (0.827 vs 0.773), so it is not leakage. Half-life
ordering beats random, age-only and class-only (all 95% CIs exclude zero), which is why it stays as the fallback and
as the basis for TTL — but the product ranks by the model.

**Cost per check** ([results/2026-11-12-checks10](results/2026-11-12-checks10/README.md)): 10 multi-claim answers,
$0.0011 and 2.8 Tavily credits per check, median latency 5.9 s (max 9.3 s), `reasoning: none` on Haiku 5.5.

## 7. Limits

- **Latency:** 5.9 s median per full check (extract + search + judge). The audit runs offline on logged traffic;
  the proxy returns the answer first and checks in the background.
- **Calibration is off, so the TTL is experimental.** Predicted vs observed stale rates miss by up to 0.27 per class;
  a 24-month refit did not help, and Haiku's probability is not calibrated either
  ([calibration.json](results/2026-11-12-ordering/calibration.json)). Exponential decay per class is a simplification;
  the starting priors were guesses.
- **Data:** the ordering dataset covers four classes only (office holder, software version, policy rate, timeless) —
  prices and laws are not in it. The labelled set is 108 cases from one annotator; several classes are too thin to
  read alone (product spec 5, rates 12, prices 13, software versions 14). Stale cases' as-of dates are approximate,
  and 22 of 38 stale cases take the former value from annotator notes.
- **Search index lag:** a verdict is only as fresh as Tavily's copy of a page (one missed stale case: the Bank of
  England page still showed the old rate days after a change).
- **Judge errors:** the judge can over-read evidence (an announced resignation treated as done); every verdict ships
  its verbatim quote and URL so it can be audited. See [errors.md](results/2026-11-12-detector/errors.md).
- **Rate limiter is per process** (in-memory). Behind several replicas, use a shared store. Setting `HALFLIFE_API_KEY`
  protects programmatic callers, but the bundled UI does not send a key; a public UI relies on the rate limit.
- Demo audit numbers describe seeded demo traffic, not production.

**Future work:** per-entity half-lives (a package or office, not a whole class). The model wins today because it
knows within-class differences — a fast-moving package versus a slow one, an unstable government versus a stable one
— that a single per-class half-life cannot express.

## 8. Existing functionality (checked 2026-11-12)

- **Bifrost** has exact-match and semantic caching with per-request TTL (`x-bf-cache-ttl`), but nothing computes the
  TTL from content. It has no freshness scoring or claim verification.
- **[maximhq/bifrost#9748](https://github.com/maximhq/bifrost/issues/9748)** ("FreshGuard", opened 8 Nov 2026) proposes
  a Go plugin that checks answers inline as they pass through Bifrost, using Tavily via a relay. Half-Life differs:
  it needs no plugin or custom build (stock binary, public APIs only); it audits logged traffic offline and reports
  stale rate per model and virtual key; it spends a verification budget on the riskiest claims with a measured
  risk-coverage curve; and it ties cache TTL to fitted decay. The two are complementary: an inline checker could use
  Half-Life's ranking to decide which answers to check. See [docs/UPSTREAM.md](docs/UPSTREAM.md).

## 9. AI usage disclosure

- **Built with Claude Code** (Claude Opus 5.5) as the lead agent, with Claude subagents for parallel workers and
  independent verifiers; every design decision and gate was approved by the human author.
- **Inside the product:** Claude Haiku 5.5 (via Bifrost) extracts claims, rates how likely each is outdated, and judges
  claims against Tavily evidence; Claude Haiku 4.5 is the automatic fallback. Verdicts are constrained in code to
  verbatim quotes from retrieved evidence.

Licence: Apache-2.0 (same as Bifrost). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md).
