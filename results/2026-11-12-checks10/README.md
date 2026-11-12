# 10-answer cost and latency measurement — 2026-11-12

Reproduce: `uv run python -m eval.measure_checks` (live: spends model calls and Tavily credits; evidence
cached on disk per day). Check mode, every time-sensitive claim verified, `anthropic/claude-haiku-5-5`
with `reasoning: {effort: "none"}`, Tavily basic search through the Bifrost relay, run sequentially.

| Metric | Value |
|---|---|
| Answers | 10 (17 claims; 14 searched; 3 timeless skipped) |
| Model cost, total | $0.010955 (virtual-key budget delta); token estimate $0.010954 |
| **Model cost per check** | **$0.0011** |
| Tavily credits | 28 (**2.8 per check**) |
| Latency per check | mean 6.06 s, median 5.87 s, max 9.31 s |
| Verdicts | 10 changed, 4 current, 0 unverifiable |
| Errors | none |

Per-answer reports: `reports.jsonl`. These are not labelled eval cases; the verdicts were spot-checked by
hand against sources retrieved in W5 (Fed chair, EU AI Act high-risk date, US minimum wage, Microsoft CEO)
and looked right. Accuracy is measured in J3 on the labelled set, not here.
