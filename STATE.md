# STATE

## Found
- Bifrost transport v2.5.1 (`npx -y @maximhq/bifrost --transport-version v2.5.1`), port from `BIFROST_PORT` (8088 here; 8080 held by another local process). docs/SPIKE.md.
- `/api/*` needs admin auth in v2.x → `governance.auth_config` with `env.` refs; creds only in `.env`. Inference auth = VK only.
- Logs: log id == `x-bifrost-request-id`; list view omits `output_message`, `GET /api/logs/{id}` has it. Writes async (~1 s).
- Cache: `x-bf-cache-key`/`x-bf-cache-ttl` work (direct hit 1–2 ms) but need a Redis vector store.
- Relay `tavily` → `/relay/tavily/search`; calls appear in `GET /api/relay-logs` under `halflife-dev` (status, latency, cost $0). Repeat queries served from disk cache: 0 credits, no relay row.
- Reasoning: Haiku 5.5 defaults to `medium` effort with adaptive thinking (Anthropic effort docs). `thinking:{type:disabled}` allowed at ≤high effort. Through Bifrost's OpenAI endpoint `reasoning_effort:"none"` → 5 output tokens vs 288 default on a yes/no probe; `"low"` barely helps (282). Default for extract/judge: `"none"`; quality to be checked on 10 answers.
- J0.5 (results/2026-11-12-ordering): half-life ordering beats random/age/class (AUC 0.856 vs 0.502/0.642/0.812, all CIs exclude 0) but **loses to Haiku's own P(outdated) given the as-of date** (0.826 vs 0.782 on n=300, CI [-0.064,-0.023]); holds after model cutoff too. Fitted h: version 83 d, rate 55 d, office 1627 d.
- Bifrost chat responses carry no cost; spend = VK budget `current_usage` delta (`vk_spend_usd`).
- Wikidata needs contact URL in User-Agent: `HALFLIFE_CONTACT_URL` (set to user's GitHub profile).
- **Overlap:** maximhq/bifrost#9748 "FreshGuard" (inline Go plugin, Tavily relay, verdicts).

## Decided
- Two Bifrost profiles: `bifrost/base` (no Redis; check mode, audit) and `bifrost/cache` (Redis; TTL proxy only). docker-compose.yml provides Redis.
- Tavily always via Bifrost relay, disk cache (payload + UTC date) in front; relay priced $0 (free tier) so search does not eat the $10 model budget.
- Fallback model: `anthropic/claude-haiku-4-5` (no second-provider key supplied).
- J0.5 added by user before fan-out. Lead writes `halflife/risk.py` and `halflife/fit.py` in J0.5 (needed by the ordering test); W2/W4 become test-hardening workers on those files.
- W5 shrinks to ~100 live cases and may reuse J0.5 data.
- Audit: cap sample per run, semaphore on log-detail calls (BifrostClient log_concurrency=4).

## Remains
- J0.5 gate: awaiting user decision on the model_p result. Then fan-out W1–W6, V1–V3, GATE 2, M1, J2, J3, J4, J5, V4, GATE 3, J6.
- Item 4: measure cost/latency per check on 10 answers before J3, record here.
- Item 7: read #9748 thread before UPSTREAM.md.

## Spend
- Model: $0.0092 (current VK) + $0.00007 (pre-reset VK) ≈ $0.0093 / $10. Tavily: 6 / 1000 credits.
