# STATE

## Found
- Bifrost transport v2.5.1 (`npx -y @maximhq/bifrost --transport-version v2.5.1`), port from `BIFROST_PORT` (8088 here; 8080 held by another local process). docs/SPIKE.md.
- `/api/*` needs admin auth in v2.x → `governance.auth_config` with `env.` refs; creds only in `.env`. Inference auth = VK only.
- Logs: log id == `x-bifrost-request-id`; list view omits `output_message`, `GET /api/logs/{id}` has it. Writes async (~1 s).
- Cache: `x-bf-cache-key`/`x-bf-cache-ttl` work (direct hit 1–2 ms) but need a Redis vector store.
- Relay `tavily` → `/relay/tavily/search`; calls appear in `GET /api/relay-logs` under `halflife-dev` (status, latency, cost $0). Repeat queries served from disk cache: 0 credits, no relay row.
- Reasoning: Haiku 5.5 defaults to `medium` effort with adaptive thinking (Anthropic effort docs). `thinking:{type:disabled}` allowed at ≤high effort. Through Bifrost's OpenAI endpoint `reasoning_effort:"none"` → 5 output tokens vs 288 default on a yes/no probe; `"low"` barely helps (282). Default for extract/judge: `"none"`; quality to be checked on 10 answers.
- J0.5 (results/2026-11-12-ordering): half-life ordering beats random/age/class (AUC 0.856 vs 0.502/0.642/0.812, all CIs exclude 0) but **loses to Haiku's own P(outdated) given the as-of date** (0.826 vs 0.782 on n=300, CI [-0.064,-0.023]); holds after model cutoff too. Fitted h: version 83 d, rate 55 d, office 1627 d.
- Headline (n=300): Haiku-with-date caught@10/25/50 = 0.357 [0.303,0.429] / 0.748 [0.670,0.836] / 0.980 [0.946,1.0]; half-life 0.298 / 0.655 / 0.917. results/2026-11-12-ordering/headline.json.
- Calibration: 24-month window refit does not improve (worst class error 0.267 both) -> full fit kept; neither half-life nor Haiku within 0.10 on all classes -> **cache TTL ships labelled experimental**. calibration.json.
- First live end-to-end check (pipeline draft): Node 20 LTS -> changed, BoE 5.25% -> changed (3.75%, verified quote), timeless skipped. 3 model calls, 4 credits, 7.0 s, **$0.0015 per check** (token estimate == sum of Bifrost log costs; judge prompts 4-5k input tokens). VK current_usage lags >3 s after calls.
- Item 4 done (results/2026-11-12-checks10): 10 answers, **$0.0011 and 2.8 credits per check, median 5.9 s** (max 9.3), reasoning effort none; token estimate == VK delta. Haiku 4.5 fallback accepts reasoning.effort none but answered a prime check wrong without reasoning (weaker fallback).
- V2 fixed: documented `max_completion_tokens` + `reasoning.effort`, provider then key on setup, no time_range on official-site search, logs `roots_only` + paging, routing-info headers, Tavily `include_usage` for actual credits, spike VK relay grant. Disk-cache key now includes include_usage (old entries not reused).
- V3: 0/30 wrong (Wilson 95% 0–11.4%); s-au-super weak (original ATO URL 403). Systemic risks: ~18 stale cases' quotes show only the current value (former value from notes); approximate stale as_of dates; 52/83 time-sensitive cases share 26 URLs (pairs) so per-case CIs are too narrow; product_spec only 5 cases; single annotator. GATE 2 hand-check list: eval/GATE2_HANDCHECK.md.
- J3 done (results/2026-11-12-detector): run 2 precision 0.854 [0.742,0.950], recall 0.921 [0.828,1.0] (CIs by URL); budget @25/50%: model 0.462/0.842, half-life 0.387/0.708, random 0.233/0.460. Run 1 found bug (numeric value equality), fixed, rerun once; no prompt change. Cost/answer (cold, run 1): $0.00058, 1.31 credits, 4.3 s mean.
- J2 (a)(b) done: audit + seed; live e2e (10 questions) stale rate matches reports (2nd attempt; 1st failed because internal J3 logs crowded the newest-rows scan -> read ids directly). Audit of 50 demo answers: stale rate 0.27–0.78 per (model, key); $0.055, 88 credits.
- J2 (c) proxy (experimental, cache profile on :8089 + Redis): question class -> TTL from half-life, x-bf-cache-key/ttl to Bifrost, 2nd identical request = Bifrost direct cache hit, background report joined by x-bifrost-request-id. (d) MCP tool `check_freshness` (mcp 2.3.0 MCPServer, :8092) registered in Bifrost MCP gateway, healthy, callable via /v1/mcp/tool/execute after VK mcp_configs grant. J2 done.
- Failover demo: /v1/check simulate_primary_down (needs HALFLIFE_DEMO_MODE=1) -> Bifrost falls back to claude-haiku-4-5; Usage.models_used/fallback_used. MCP tool granted to demo keys only (granting halflife-dev made Bifrost inject the tool into internal calls -> internal calls now send x-bf-mcp-include-clients with a non-matching name).
- J5 (in progress): README, UPSTREAM, CONTRIBUTING, SUBMISSION, LICENSE (Apache-2.0), CI (actions pinned by SHA), Dockerfile (node 24.22.1, uv 0.11.21, forwarded IPs default 127.0.0.1), make demo. DEMO_SCRIPT done. Docker image builds and smoke-runs (health ok, UI 200). J4 done: UI live by default, Gateway/Check/Evidence, demo path verified in browser by worker (3 live checks). Ledger seeded with J0.5 fit via `ledger import-fit` in make setup.
- M1 done: real answers end to end through Bifrost + Tavily return valid AnswerReports.
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

- J0.5 gate decision (user): extractor returns `p_outdated_model` in the same call; that is the default verification ordering (`RiskScore.rank_basis = model_p`). Half-life kept for cache TTL, re-scoring aged cached answers without a model call, and fallback when the model call fails. No more ranking experiments (no stacking, no per-entity fits; per-entity = README future work).
- Positioning (README/UPSTREAM/SUBMISSION): lead with (a) traffic audit stale rate per model and VK, (b) budgeted verification with the measured curve, (c) decay-based cache TTL. State plainly the model's rating ranks better; ordering data covers 4 classes only (no prices, laws).
- Calibration rule: refit on last 24 months before cutoff; keep the better-calibrated fit; if neither within ~0.10 per class, TTL ships "experimental" with the reason in README.

- V1 (correctness) fixed in M1: fail-open on any extract/verify exception, authority by URL on a validated domain only, model_p claims ranked before half-life fallbacks, estimated/unverified scores use the ranking probability, rescore_aged chain-safe, refit ignores age<=0, whole-token current_value that must differ from the claim, quote relevance + min 12 chars + untrusted-evidence judge prompt, guards on non-positive half-lives. Not fixed: #10 silent span dedupe (minor), #11 ledger dupes without request id (moot: only the audit writes the ledger). tests/test_regressions.py.
- Security fixes: /v1/check optional key + separate per-IP windows for allowed requests and failed auth, idle windows evicted; ad-hoc checks not recorded in the ledger.

## Fan-out ownership (one writer per file; workers never commit, lead merges)
| Node | Files it may write |
|---|---|
| W1 extract | halflife/extract.py, tests/test_extract.py |
| W2 risk tests | tests/test_risk.py (risk.py is lead-owned, read-only) |
| W3 verify | halflife/verify.py, tests/test_verify.py |
| W4 ledger + fit tests | halflife/ledger.py, tests/test_fit.py, tests/test_ledger.py (fit.py lead-owned, read-only) |
| W5 cases | eval/cases.jsonl, eval/README.md, eval/build_cases.py |
| W6 UI shell | web/index.html, web/app.js, web/style.css |
| Lead | everything else (schemas, clients, risk.py, fit.py, results/, STATE.md) |

## Remains
- GATE 3: awaiting user go for push/deploy/upstream issue. Done: A case fixes, J3, J2 (a-d), J4, J5, V4 (2 rounds: quickstart 133 s, all numbers traceable after fixes). No cuts applied. Earlier: fan-out W1–W6, V1–V3, GATE 2, M1, J2, J3, J4, J5, V4, GATE 3, J6.
- Item 4: measure cost/latency per check on 10 answers before J3, record here.
- Item 7: #9748 thread read 2026-11-12 21:03 IST: no maintainer reply, only a CodeRabbit bot comment (links merged relay PR #9170). Its asks: plugin location, `plugin_metadata` on stream chunks, shared plugin cache. UPSTREAM.md must not repeat those; re-read before writing.
- M1 notes from W3: verbatim-but-weak quote can still count as strong support (UN photo caption on un.org) -> judge prompt must require the quote to state the fact; carry VerifyOutcome.strong_support into the 95/80 score; when both searches fail, searched=True with verdict None -> score as unverified. current_value prompt changed to value-only (untested live).
- M1 security fixes (review on 56f7694): validate `authoritative_domain` (hostname chars, >=1 dot, not a bare/public suffix) before using include_domains or the authoritative flag; count source independence by registrable domain, not host.
- W6 done: UI renders from fixtures; switch `DATA_SOURCE` to "api" in web/app.js at J4; J3 results path assumed `results/j3-live/summary.json`.
- M1 notes from W1: treat `is_past_event` claims as non-decaying in the half-life fallback; year-only dates stored as YYYY-01-01 (no precision field).

## Spend
- Model: $0.245 / $10 measured 22:20 IST (halflife-dev $0.233, demo keys $0.011, cache-profile gateway $0.001). Tavily: ~430 / 1000 by own count (Tavily /usage reports 152 at 22:20 IST; its counter lags) (154 to Gate 2 + ~5 recheck + 141 J3 run1 + 33 J3 run2 + 88 audit + ~10 e2e/proxy/MCP); Tavily /usage endpoint reported 0 at 20:57 IST.
