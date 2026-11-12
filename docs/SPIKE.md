# J0 Spike: what Bifrost and Tavily actually provide

Checked 2026-11-12 against Bifrost transport **v2.5.1** (launcher `@maximhq/bifrost` 1.6.3) and the live docs.
`scripts/spike.sh` reproduces every call. Status: **doc** = confirmed in docs, **live** = observed on a local run,
**pending** = needs `ANTHROPIC_API_KEY` / `TAVILY_API_KEY` in `.env`.

## Mechanisms

| # | Mechanism (note from build prompt) | Status | Evidence / substitute |
|---|---|---|---|
| 1 | Start with `npx -y @maximhq/bifrost` on port 8080 | **live** (port changed) | Boots v2.5.1. Port 8080 was taken by another local process, so Half-Life uses **8088** (`-port 8088`, `BIFROST_URL`). [Setting up](https://docs.getbifrost.ai/quickstart/gateway/setting-up.md) |
| 2 | Management APIs under `/api/*` open by default | **live: not as noted** | v2.x returns 403 until admin auth is configured; first account needs a setup token. Substitute: `governance.auth_config` in `bifrost/config.json` with `env.` refs, Basic auth on `/api/*`, `disable_auth_on_inference: true` so inference is governed by VK only. [Setting up auth](https://docs.getbifrost.ai/quickstart/gateway/setting-up-auth.md), [config.json governance](https://docs.getbifrost.ai/deployment-guides/config-json/governance.md) |
| 3 | Models are `provider/model` | doc | Quickstart uses `openai/gpt-4o-mini`. Runtime model: `anthropic/claude-haiku-5-5` (cheapest current Haiku, from $0.10 / $0.50 per MTok; reliable knowledge cutoff Jun 2026, per Anthropic models overview). |
| 4 | Add Anthropic provider | doc, pending | `POST /api/providers/{provider}/keys`, value `env.ANTHROPIC_API_KEY`. [Create a key](https://docs.getbifrost.ai/api-reference/providers/create-a-key-for-a-provider.md) |
| 5 | Virtual keys in `x-bf-vk`, with budget | doc, **live (API reachable)** | `POST /api/governance/virtual-keys` with `budgets: [{max_limit, reset_duration}]` (array since v1.5.0). Also accepted: `Authorization: Bearer sk-bf-*`. [Virtual keys](https://docs.getbifrost.ai/features/governance/virtual-keys.md) |
| 6 | Body accepts `fallbacks` | doc | [Retries & fallbacks](https://docs.getbifrost.ai/features/retries-and-fallbacks.md); response headers report which provider served it. [Response headers](https://docs.getbifrost.ai/providers/response-headers.md) |
| 7 | Logging API | doc, pending | `GET /api/logs` with filters `providers, models, status, virtual_key_ids, ...`; rows carry `provider, model, timestamp, latency, cost, virtual_key_id/name, input_history, output_message, cache_debug`. [Get logs](https://docs.getbifrost.ai/api-reference/logging/get-logs.md) |
| 8 | Cache opt-in with `x-bf-cache-key` + `x-bf-cache-ttl` | doc, **live (plugin active)** | Both headers exist; TTL accepts duration or seconds. Plugin `semantic_cache` in **direct-only mode** (`dimension: 1`, no provider) needs no embeddings, **but does need a vector store**: Redis Stack container (`redis/redis-stack-server:7.4.0-v3`) added. Entries are scoped per VK automatically. Tool-call responses not cached by default. [Semantic caching](https://docs.getbifrost.ai/features/semantic-caching.md) |
| 9 | MCP gateway | doc | `POST /api/mcp/client` with `connection_type: http|sse|stdio`. Fits J2(c). [Add MCP client](https://docs.getbifrost.ai/api-reference/mcp/add-mcp-client.md) |
| 10 | **Relays (new, not in notes)** | doc | `/relay/<name>/<path>` puts a non-LLM API (e.g. Tavily search) behind Bifrost: stored credential, VK access, per-call pricing, budgets, Relay Logs. Lets Tavily spend sit in the same budget as model spend. [Relays](https://docs.getbifrost.ai/relays/overview.md) |
| 11 | Tavily search | doc, pending | `POST https://api.tavily.com/search`, Bearer key. `basic` = 1 credit, `advanced` = 2. Recency: `time_range` / `start_date` / `end_date`; `include_domains` (+ `include_domains_mode`); `include_published_date`; a max cached-copy age in hours (0 = live fetch). Free: 1,000 credits/month. [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search.md), [Credits](https://docs.tavily.com/documentation/api-credits.md) |

Licence: Bifrost is Apache-2.0 (API spec header) — Half-Life will match.

## Live run (2026-11-12, `scripts/spike.sh`, 7/7 pass)

| Step | Observed |
|---|---|
| Provider | Chat worked with `ANTHROPIC_API_KEY` exported to Bifrost's environment; `GET /api/providers/anthropic` returned 200 before any add call, and the log row carries a `selected_key`. The script's add-provider path (`POST /api/providers`) was not exercised. |
| Virtual key | `halflife-dev` created, `budgets[0].max_limit = 10`; `current_usage` increments per call (6.79e-05 after three spike runs). |
| Chat | `anthropic/claude-haiku-5-5` via `x-bf-vk` → "pong". **Haiku 5.5 spends output tokens on reasoning**: with `max_tokens: 30` a "2+2" probe returned `content: null`, `finish_reason: length`. Use generous `max_tokens`. |
| Logs | Writes are async (~1 s). **Log id == `x-bifrost-request-id` response header.** List view (`GET /api/logs`) omits `output_message`; `GET /api/logs/{id}` returns it with `input_history`, `cost`, `token_usage`, `virtual_key_name`. Cache hits log `cost: null`. |
| Cache | Second identical request with `x-bf-cache-key` + `x-bf-cache-ttl: 120`: `X-Bifrost-Cache-Hit: true`, `X-Bifrost-Cache-Hit-Type: direct`, 1–2 ms; same data in `extra_fields.cache_debug`. |
| Tavily | `POST /search`, `basic`, `time_range: year`, 3 results. Response had no `usage` field; credits counted by our own ledger (1 per basic call). |

## Existing-functionality check

* Bifrost docs: no freshness scoring, no claim verification, no content-aware cache TTL. Cache TTL is per plugin config or per request header (`x-bf-cache-ttl`) set by the caller; nothing computes it.
* Bifrost issues: **open issue [maximhq/bifrost#9748](https://github.com/maximhq/bifrost/issues/9748)** (filed 2026-11-08 by `sidharth-cs`): "FreshGuard", a Go plugin that inline-checks answers (claim extraction through Bifrost, Tavily via a Bifrost relay, supported/changed/unverifiable verdicts, 60-min claim cache, 37-case eval). Repo created 2026-11-06, Apache-2.0. **This overlaps T1–T3 directly** and is likely another entry in this hackathon.
* Not in #9748 and not in Bifrost: per-class half-lives fitted from outcomes, budgeted risk ordering of what to verify, recommended cache TTL from predicted decay, offline audit of logged traffic with stale rate per model and VK.

## Feasibility of gateway mode

Feasible with stock Bifrost: audit reads `GET /api/logs`; proxy sets `x-bf-cache-key` + `x-bf-cache-ttl` per request; MCP tool registers via `/api/mcp/client`; Tavily can go through a relay. Costs over design: Redis container and admin auth setup.
