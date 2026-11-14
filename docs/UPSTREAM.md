# Proposal for Bifrost maintainers: freshness auditing of logged traffic, and content-aware cache TTL

*Draft issue, not yet filed. Prepared 2026-11-12. Related: #9748 (FreshGuard).*

## Summary

Half-Life is a working, Apache-2.0 companion service for stock Bifrost that answers an operator question Bifrost
cannot answer today: **how much of what this gateway served is stale, per model and virtual key?** It uses only
public Bifrost extension points (logging API, governance, relays, cache headers, MCP gateway). This issue asks
whether you would accept it as a documented integration, and proposes two small, optional additions that would make
it — and tools like it — simpler. It does not repeat #9748's questions (plugin placement, `plugin_metadata` on stream
chunks, a shared plugin cache).

## How it relates to #9748

#9748 checks each answer **inline** with a Go plugin. Half-Life works **out of band**: it reads `GET /api/logs`,
samples recent answers, ranks claims by risk, verifies only the riskiest under a budget, and aggregates stale rate by
`(model, virtual_key)`. The approaches are complementary: an inline checker could use the same risk ranking to decide
which answers to check. Measured on 108 labelled cases, ranking by the extractor model's outdated-probability caught
0.831 of stale claims when verifying half the claims (mean of two live runs), against 0.694 for random order among
time-sensitive claims (the fair baseline) and 0.474 for blind random; full verification, post-fix run: precision
0.854, recall 0.921 (repo `results/2026-11-12-detector/fair_baseline.json` and `summary.json`; one annotator, cases
pre-screened to facts Tavily could retrieve).

## What already works on stock Bifrost v2.5.1 (no changes needed)

| Need | Bifrost feature used |
|---|---|
| Read served answers | `GET /api/logs?roots_only=true` + `GET /api/logs/{id}` (list view omits `output_message`) |
| Join a request to its log | `x-bifrost-request-id` response header == log id |
| Govern verification spend | the auditor's own virtual key with a budget; Tavily behind a **relay** so search is priced and logged under that key |
| Per-request cache TTL | `x-bf-cache-key` + `x-bf-cache-ttl` |
| Expose checking to agents | MCP gateway (`POST /api/mcp/client`, VK `mcp_configs`) |
| Failover | `fallbacks` + `x-bifrost-routing-info-is-fallback` |

## Proposed additions (small, optional)

1. **Exclude a virtual key (or label) from log queries.** `GET /api/logs` supports `virtual_key_ids` inclusion only.
   An auditor's own model calls land in the same log and must be filtered client-side, which forces scanning far more
   rows than the sample needs. A `exclude_virtual_key_ids` (or a filter on `x-bf-lh-*` log labels) would fix it.
2. **Document `reasoning.effort: "none"` for Anthropic models.** It turns thinking off on Claude Haiku 5.5 through
   `/v1/chat/completions` (measured 288 → 5 output tokens on a yes/no probe), which matters for high-volume judge and
   extraction calls, but the reasoning docs describe Anthropic effort as always-thinking.
3. *(Optional, discussion)* A documented note in the caching docs that `x-bf-cache-ttl` can be computed by an external
   service from answer content, with Half-Life's proxy as a reference implementation (marked experimental: its fitted
   half-lives are not yet calibrated).

## What we would contribute

- Docs page: "Auditing served answers for staleness" (logging API + relay + budget pattern), with the integration.
- If (1) is welcome: the filter implementation with tests, following `CONTRIBUTING` in the Bifrost repo.
- The integration itself stays a separate repo unless you prefer it under a community-integrations list.

## Evidence and limits

All figures come from recorded runs in the Half-Life repo (`results/`). Limits we state plainly: 5.9 s median per full
check; the per-class half-life model ranks worse than the model's own outdated-probability, and neither is calibrated
within 0.10 per class; the labelled set is 108 cases from one annotator.
