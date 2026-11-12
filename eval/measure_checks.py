"""Measure real cost and latency per check on 10 answers (item 4), through Bifrost + Tavily relay.

    uv run python -m eval.measure_checks

Writes results/<date>-checks10/{reports.jsonl,summary.json}. Spend: ~10 extract calls, one judge call
per time-sensitive claim, two searches per claim with an official domain (one otherwise).
"""

import asyncio
import json
import statistics
from datetime import date
from pathlib import Path

from halflife.clients.bifrost import BifrostClient
from halflife.clients.tavily import DiskCache, TavilyViaRelay
from halflife.config import ROOT, load_settings
from halflife.pipeline import CheckOptions, check_answer

ANSWERS = [
    "The latest LTS release of Node.js is Node 20, and npm 10 ships with it.",
    "The Bank of England base rate is 5.25%, the highest level since 2008.",
    "Satya Nadella is the CEO of Microsoft and Sundar Pichai is the CEO of Google.",
    "A Netflix Standard plan costs $15.49 per month in the United States.",
    "The EU AI Act's obligations for high-risk AI systems apply from August 2026.",
    "Python 3.12 is the newest stable Python release; Python 3.8 reached end of life in 2024.",
    "The US federal minimum wage is $7.25 per hour.",
    "Water boils at 100 degrees Celsius at sea level, and the speed of light is about 299,792 km/s.",
    "The iPhone 16 Pro has a 6.3-inch display and starts at $999.",
    "Jerome Powell is the Chair of the US Federal Reserve, and the federal funds target range is 5.25% to 5.50%.",
]


async def main() -> None:
    s = load_settings()
    bf = BifrostClient(s)
    searcher = TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir))
    out_dir = ROOT / "results" / f"{date.today().isoformat()}-checks10"
    out_dir.mkdir(parents=True, exist_ok=True)
    before = await bf.vk_spend_usd()
    reports = []
    for answer in ANSWERS:  # sequential, so latency is per check, not contended
        r = await check_answer(answer, model=bf, searcher=searcher,
                               opts=CheckOptions(as_of=s.model_cutoff, today=date.today(), answer_model=s.model))
        reports.append(r)
        verdicts = [(c.claim.volatility_class.value, c.verdict.label.value if c.verdict else c.score_basis.value,
                     c.freshness_score) for c in r.claims]
        print(f"{r.usage.latency_ms/1000:5.1f}s ${r.usage.model_cost_usd:.5f} cr={r.usage.tavily_credits} {verdicts}")
    await asyncio.sleep(20)  # VK usage updates asynchronously
    after = await bf.vk_spend_usd()
    await bf.aclose()
    lat = [r.usage.latency_ms / 1000 for r in reports]
    summary = {
        "n_answers": len(reports), "model": s.model, "reasoning_effort": "none",
        "claims_total": sum(len(r.claims) for r in reports),
        "claims_searched": sum(c.searched for r in reports for c in r.claims),
        "verdicts": {lab: sum(1 for r in reports for c in r.claims if c.verdict and c.verdict.label.value == lab)
                     for lab in ("current", "changed", "unverifiable")},
        "model_cost_usd_token_estimate": round(sum(r.usage.model_cost_usd for r in reports), 6),
        "model_cost_usd_vk_delta": round(after - before, 6),
        "cost_per_check_usd": round((after - before) / len(reports), 6),
        "tavily_credits": sum(r.usage.tavily_credits for r in reports),
        "credits_per_check": round(sum(r.usage.tavily_credits for r in reports) / len(reports), 2),
        "latency_s": {"mean": round(statistics.fmean(lat), 2), "median": round(statistics.median(lat), 2),
                      "max": round(max(lat), 2)},
        "errors": [e for r in reports for e in r.errors + [x for c in r.claims for x in c.errors]],
    }
    (out_dir / "reports.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in reports))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
