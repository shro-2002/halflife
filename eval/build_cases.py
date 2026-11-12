"""Build and check the labelled live-test cases (eval/cases.jsonl).

Two modes:
  --search SPECS.json   run Tavily searches through the Bifrost relay (disk cache in front) and append
                        every returned result (query, params, url, content) to
                        eval/cases_sources/search_results.jsonl. Prints results and credits spent.
                        SPECS.json: [{"query": "...", "include_domains": ["..."]}, ...]
  --check               offline: validate every case in eval/cases.jsonl against the saved results.
                        Fails (exit 1) if any supporting_quote is not an exact substring of the saved
                        Tavily `content` for (query, source_url), or a field/class/label is invalid.

Usage:
  uv run python eval/build_cases.py --search eval/cases_sources/specs_batch1.json
  uv run python eval/build_cases.py --check
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from halflife.schemas import VolatilityClass  # noqa: E402

CASES = ROOT / "eval" / "cases.jsonl"
RESULTS = ROOT / "eval" / "cases_sources" / "search_results.jsonl"
DATE_CHECKED = "2026-11-12"
LABELS = {"stale", "current", "timeless"}
FIELDS = {"id", "claim", "volatility_class", "as_of", "label", "current_truth", "source_url",
          "supporting_quote", "query", "date_checked", "notes"}
CLASSES = {c.value for c in VolatilityClass}
SEARCH_CONCURRENCY = 4


async def run_searches(specs: list[dict]) -> int:
    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay, SearchError
    from halflife.config import load_settings

    settings = load_settings()
    bf = BifrostClient(settings)
    tavily = TavilyViaRelay(bf, settings.relay_name, DiskCache(settings.cache_dir))
    sem = asyncio.Semaphore(SEARCH_CONCURRENCY)

    async def one(spec: dict):
        params = {k: v for k, v in spec.items() if k != "query"}
        async with sem:
            try:
                return spec, await tavily.search(spec["query"], **params)
            except SearchError as err:
                return spec, err

    try:
        done = await asyncio.gather(*(one(s) for s in specs))
    finally:
        await bf.aclose()
    credits = 0
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS.open("a") as out:
        for spec, res in done:
            if isinstance(res, Exception):
                print(f"!! {spec['query']}: {res}")
                continue
            credits += res.credits
            print(f"\n=== {spec['query']}  (credits {res.credits}, cache {res.from_cache})")
            for r in res.results:
                row = {"query": spec["query"], "params": res.payload, "url": r.get("url", ""),
                       "title": r.get("title", ""), "content": r.get("content", ""),
                       "published_date": r.get("published_date"), "credits_for_query": res.credits}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"--- {row['url']}  {row['content'][:160]!r}")
    print(f"\ncredits this run: {credits}")
    return credits


def load_results() -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = {}
    for line in RESULTS.read_text().splitlines():
        row = json.loads(line)
        index.setdefault((row["query"], row["url"]), []).append(row["content"])
    return index


def load_payloads() -> dict[str, dict]:
    return {row["query"]: row["params"] for row in map(json.loads, RESULTS.read_text().splitlines())}


def cache_check(cases: list[dict]) -> tuple[int, int, list[str]]:
    """Re-check quotes against the live Tavily disk cache (.cache/tavily) when its entries exist.

    Returns (verified, cache_missing, failures). Missing entries (another machine, or a later UTC
    day) are not failures: the saved copy in eval/cases_sources/ is the reproducible record.
    """
    from halflife.clients.tavily import DiskCache
    from halflife.config import load_settings

    cache = DiskCache(load_settings().cache_dir)
    payloads = load_payloads()
    verified, missing, failures = 0, 0, []
    for case in cases:
        entry = cache.get(DiskCache.key(payloads[case["query"]], date.fromisoformat(DATE_CHECKED)))
        if entry is None:
            missing += 1
            continue
        contents = [r.get("content", "") for r in entry["results"] if r.get("url") == case["source_url"]]
        if any(case["supporting_quote"] in c for c in contents):
            verified += 1
        else:
            failures.append(case["id"])
    return verified, missing, failures


def case_errors(case: dict, index: dict[tuple[str, str], list[str]]) -> list[str]:
    errs = []
    missing = FIELDS - set(case) - {"notes"}
    if missing:
        errs.append(f"missing fields {sorted(missing)}")
    if set(case) - FIELDS:
        errs.append(f"unknown fields {sorted(set(case) - FIELDS)}")
    if case.get("volatility_class") not in CLASSES:
        errs.append(f"bad volatility_class {case.get('volatility_class')!r}")
    if case.get("label") not in LABELS:
        errs.append(f"bad label {case.get('label')!r}")
    if (case.get("label") == "timeless") != (case.get("volatility_class") == "timeless"):
        errs.append("label timeless <=> class timeless")
    if case.get("label") in {"stale", "current"} and not case.get("current_truth"):
        errs.append("time-sensitive case needs current_truth")
    if case.get("date_checked") != DATE_CHECKED:
        errs.append(f"date_checked must be {DATE_CHECKED}")
    try:
        if date.fromisoformat(case.get("as_of", "")) > date.fromisoformat(DATE_CHECKED):
            errs.append("as_of after date_checked")
    except ValueError:
        errs.append(f"bad as_of {case.get('as_of')!r}")
    contents = index.get((case.get("query"), case.get("source_url")))
    if contents is None:
        errs.append("no saved Tavily result for (query, source_url)")
    elif not case.get("supporting_quote") or not any(case["supporting_quote"] in c for c in contents):
        errs.append("supporting_quote not an exact substring of saved Tavily content")
    return errs


def check() -> int:
    index = load_results()
    cases = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    bad = 0
    ids = Counter(c.get("id") for c in cases)
    for dup in [i for i, n in ids.items() if n > 1]:
        print(f"FAIL duplicate id {dup}")
        bad += 1
    for case in cases:
        for err in case_errors(case, index):
            print(f"FAIL {case.get('id')}: {err}")
            bad += 1
    table = Counter((c["volatility_class"], c["label"]) for c in cases)
    print(f"{'class':<20}{'stale':>7}{'current':>9}{'timeless':>10}{'total':>7}")
    for cls in sorted(CLASSES):
        row = [table[(cls, lab)] for lab in ("stale", "current", "timeless")]
        print(f"{cls:<20}{row[0]:>7}{row[1]:>9}{row[2]:>10}{sum(row):>7}")
    labels = Counter(c["label"] for c in cases)
    print(f"{'total':<20}{labels['stale']:>7}{labels['current']:>9}{labels['timeless']:>10}{len(cases):>7}")
    verified, missing, failures = cache_check(cases)
    for cid in failures:
        print(f"FAIL {cid}: quote not in the Tavily disk-cache entry for (query, source_url)")
    bad += len(failures)
    print(f"\ndisk cache: {verified} verified, {missing} entries absent (saved copy used), {len(failures)} mismatches")
    print(f"{len(cases)} cases, {bad} problems -> {'FAIL' if bad else 'OK'}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", type=Path, help="JSON list of search specs to run")
    ap.add_argument("--check", action="store_true", help="validate eval/cases.jsonl offline")
    args = ap.parse_args()
    if args.search:
        asyncio.run(run_searches(json.loads(args.search.read_text())))
        return 0
    if args.check:
        return check()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
