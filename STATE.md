# STATE

## Found
- Bifrost transport v2.5.1 via `npx -y @maximhq/bifrost`; runs on **port 8088** here (8080 held by another local process). See docs/SPIKE.md.
- `/api/*` needs admin auth in v2.x: configured via `governance.auth_config` in `bifrost/config.json`, creds in `.env` (generated locally). Inference auth = VK only.
- Cache: `x-bf-cache-key` + `x-bf-cache-ttl` real; direct-only mode needs Redis vector store (container `halflife-redis`).
- Logs: `GET /api/logs` returns provider/model/vk/cost/input_history/output_message.
- Relays exist: Tavily can run behind Bifrost (`/relay/<name>/...`).
- Runtime model `anthropic/claude-haiku-5-5`, knowledge cutoff Jun 2026.
- **Overlap:** maximhq/bifrost#9748 "FreshGuard" (inline Go plugin, Tavily relay, verdicts). Half-Life differs on half-lives, budgeted ordering, TTL, offline audit.

- Live spike 7/7 (docs/SPIKE.md "Live run"): log id == `x-bifrost-request-id`; full answer only via `GET /api/logs/{id}`; Haiku 5.5 needs generous `max_tokens` (reasoning tokens); VK budget usage tracked.

## Decided
- Port 8088 default, configurable via `BIFROST_URL`.
- Redis Stack 7.4.0-v3 container for cache vector store.

## Remains
- GATE 1 (awaiting user go), then J1…J6.

## Spend
- Model: $0.0000679 / $10 (VK current_usage). Tavily: 3 / 1000 credits.
