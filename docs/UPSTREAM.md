# Proposal for Bifrost maintainers: freshness auditing of logged traffic, and content-aware cache TTL

*Built for the Geek Room Global AI Hackathon 2026. Filed as [maximhq/bifrost#10039](https://github.com/maximhq/bifrost/issues/10039). Related: #9748 (FreshGuard).*

The sections below follow Bifrost's feature-request issue form (Problem, Proposed solution, Alternatives, Area,
Additional context), so the issue body is this file without the title and the line above.

## Problem to solve

Operators running many apps behind one Bifrost gateway cannot answer: **how much of what this gateway served is
stale?** Half-Life is a working, Apache-2.0 companion service for stock Bifrost v2.5.1
([github.com/shro-2002/halflife](https://github.com/shro-2002/halflife)) that answers it out of band, using only public
extension points (logging API, governance, relays, cache headers, MCP gateway). It reads `GET /api/logs`, samples
recent answers, ranks their claims by risk, verifies the riskiest under a budget, and reports:

- an **estimated stale rate across the sampled answers**, from a stratified random sample that takes 30% of the
  verification budget;
- the **stale rate among verified claims per model and virtual key**. In our seeded demo these per-slice figures are
  confounded, not a model comparison: each slice received different questions and has 11–20 verified claims.

Two gaps in Bifrost made this harder than it needed to be (proposed solution, items 1 and 2).

**How it relates to #9748.** #9748 checks each answer **inline** with a Go plugin. Half-Life works **out of band** on
the logs. The approaches are complementary: an inline checker could use the same risk ranking to decide which answers
to check. Measured on 108 labelled cases, ranking by the extractor model's outdated-probability caught 0.831 of stale
claims when verifying half the claims (mean of two live runs), against 0.694 for random order among time-sensitive
claims (the fair baseline) and 0.474 for blind random. Full verification, post-fix run: precision 0.854, recall 0.921
([fair_baseline.json](https://github.com/shro-2002/halflife/blob/main/results/2026-11-12-detector/fair_baseline.json),
[summary.json](https://github.com/shro-2002/halflife/blob/main/results/2026-11-12-detector/summary.json); one
annotator, cases pre-screened to facts Tavily could retrieve). This issue does not repeat #9748's questions (plugin
placement, `plugin_metadata` on stream chunks, a shared plugin cache).

## Proposed solution

1. **An exclusion filter for log queries.** The audit filters by virtual key on the server with `virtual_key_ids`,
   which works when the keys to audit are known. Auditing all traffic *except* the auditor's own key is not possible
   on the server today: the auditor's extract and judge calls land in the same log, so Half-Life skips them on the
   client and scans up to 10× more rows than it samples. An `exclude_virtual_key_ids` parameter on `GET /api/logs`
   (same comma-separated format as `virtual_key_ids`) would remove the extra scan. We checked `dev`: the handler
   (`transports/bifrost-http/handlers/logging.go`) has inclusion filters only.
2. **Document `reasoning.effort: "none"` for Anthropic models.** It turns thinking off on Claude Haiku 5.5 through
   `/v1/chat/completions` (measured 288 → 5 output tokens on a yes/no probe), which matters for high-volume judge and
   extraction calls, and `core/providers/anthropic/chat.go` maps it to `thinking: {type: "disabled"}`. The live
   [reasoning docs](https://docs.getbifrost.ai/providers/reasoning) still give the Anthropic mapping as
   ``| `reasoning.effort` | `thinking.type` | Always mapped to `"enabled"` |`` and list Anthropic effort levels as
   "`enabled` only".
3. *(Optional, discussion)* A note in the caching docs that `x-bf-cache-ttl` can be computed by an external service
   from answer content, with Half-Life's proxy as a reference implementation (experimental: its fitted half-lives are
   not yet calibrated).

What we would contribute:

- A docs page, "Auditing served answers for staleness" (logging API + relay + budget pattern), with the integration.
- If (1) is welcome: the filter with tests, following `docs/contributing/raising-a-pr.mdx`.
- The doc fix for (2).
- The integration itself stays a separate repo unless you prefer it under a community-integrations list.

## Alternatives considered

- **Client-side filtering** (what Half-Life does now): works, but reads far more rows than the sample needs.
- **A dedicated logging store or second gateway for auditor calls**: isolates them, but adds deployment the operator
  should not need.
- **Inline checking (#9748)**: covers every answer at request time; out-of-band auditing trades coverage for cost and
  stays off the request path.

What already works on stock Bifrost v2.5.1 (no changes needed):

| Need | Bifrost feature used |
|---|---|
| Read served answers | `GET /api/logs?roots_only=true` + `GET /api/logs/{id}` (list view omits `output_message`) |
| Audit chosen keys only | `GET /api/logs?virtual_key_ids=...` |
| Join a request to its log | `x-bifrost-request-id` response header == log id |
| Govern verification spend | the auditor's own virtual key with a budget; Tavily behind a **relay** so search is priced and logged under that key |
| Per-request cache TTL | `x-bf-cache-key` + `x-bf-cache-ttl` |
| Expose checking to agents | MCP gateway (`POST /api/mcp/client`, VK `mcp_configs`) |
| Failover | `fallbacks` + `x-bifrost-routing-info-is-fallback` |

## Area(s)

Transports (HTTP), Docs

## Additional context

All figures come from recorded runs in the Half-Life repo
([results/](https://github.com/shro-2002/halflife/tree/main/results)). Limits we state plainly: 5.9 s median per full
check; the per-class half-life model gave no measurable lift over the fair baseline (0.712 vs 0.694 at half budget),
and neither it nor the model's outdated-probability is calibrated within 0.10 per class; the labelled set is 108 cases
from one annotator.
