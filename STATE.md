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
- J0.5 gate: awaiting user decision on the model_p result. Then fan-out W1–W6, V1–V3, GATE 2, M1, J2, J3, J4, J5, V4, GATE 3, J6.
- Item 4: measure cost/latency per check on 10 answers before J3, record here.
- Item 7: read #9748 thread before UPSTREAM.md.

## Spend
- Model: $0.0092 (current VK) + $0.00007 (pre-reset VK) ≈ $0.0093 / $10. Tavily: 5 / 1000 credits by own count (4 spike searches + 1 relay test); Tavily /usage endpoint reported 0 at 20:57 IST.
