"""J0.5: build a time-travel dataset from dated public histories. No Tavily.

    uv run python -m eval.histories            # fetch (cached in data/histories/raw/) and build

Sources
  office_holder      Wikidata: heads of government (P6), heads of state (P35) of sovereign states,
                     CEOs (P169) of listed companies; start/end qualifiers P580/P582.
  software_version   PyPI JSON API and npm registry release times.
  rate_or_statistic  BIS central bank policy rates (WS_CBPOL, monthly, end of period).
  timeless           Wikidata atomic numbers (P1086) and birth dates (P569) of historical people.

For each entity, a `series` is a list of (start_date, value). A claim states the value true at an
as-of date; its label compares that value with the value at the reference date.

Time split (entity-disjoint):
  fit  entities: reference = CUTOFF (2024-11-12), as-of = CUTOFF - age, age in [7, 1825] days.
  test entities: reference = TODAY  (2026-11-12), as-of = TODAY - age,  age in [7, 730] days,
                 so every as-of date is after CUTOFF: test outcomes are changes after the cutoff.
"""

import csv
import hashlib
import io
import json
import math
import random
import time
from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

import os

import httpx
from packaging.version import InvalidVersion, Version

from halflife.config import ROOT  # also loads .env

DATA = ROOT / "data" / "histories"
RAW = DATA / "raw"
TODAY = date(2026, 11, 12)
CUTOFF = date(2024, 11, 12)
# Wikimedia requires contact info in the User-Agent: https://w.wiki/4wJS
UA = {"User-Agent": f"HalfLife/0.1 (+{os.environ.get('HALFLIFE_CONTACT_URL', '')}) python-httpx"}
SEED = 20261112

PYPI = ["requests", "numpy", "pandas", "django", "flask", "fastapi", "pydantic", "sqlalchemy", "pytest",
        "scipy", "matplotlib", "boto3", "urllib3", "setuptools", "pip", "black", "ruff", "httpx", "celery",
        "scikit-learn", "torch", "transformers", "openai", "anthropic", "langchain", "polars", "pyarrow",
        "jinja2", "click", "rich", "uvicorn", "mypy", "poetry", "numba", "pillow", "cryptography",
        "aiohttp", "redis", "psycopg2-binary", "alembic"]
NPM = ["react", "vue", "next", "express", "typescript", "webpack", "vite", "eslint", "prettier", "lodash",
       "axios", "jest", "svelte", "@angular/core", "tailwindcss", "zod", "prisma", "electron", "node-fetch",
       "mongoose", "socket.io", "esbuild", "rollup", "three", "d3", "moment", "dayjs", "commander",
       "chalk", "nodemon"]
BIS_AREAS = ["US", "GB", "XM", "JP", "CA", "AU", "NZ", "CH", "SE", "NO", "IN", "BR", "MX", "ZA", "KR",
             "CN", "RU", "TR", "PL", "CZ", "HU", "CL", "CO", "PE", "ID", "MY", "TH", "PH", "IL", "SA",
             "DK", "IS", "RO", "AR", "HK"]
AREA_NAMES = {"US": "US Federal Reserve", "GB": "Bank of England", "XM": "European Central Bank",
              "JP": "Bank of Japan", "CA": "Bank of Canada", "AU": "Reserve Bank of Australia",
              "NZ": "Reserve Bank of New Zealand", "CH": "Swiss National Bank", "SE": "Sveriges Riksbank",
              "NO": "Norges Bank", "IN": "Reserve Bank of India", "BR": "Central Bank of Brazil",
              "MX": "Bank of Mexico", "ZA": "South African Reserve Bank", "KR": "Bank of Korea",
              "CN": "People's Bank of China", "RU": "Bank of Russia", "TR": "Central Bank of Turkey",
              "PL": "National Bank of Poland", "CZ": "Czech National Bank", "HU": "Hungarian National Bank",
              "CL": "Central Bank of Chile", "CO": "Bank of the Republic (Colombia)",
              "PE": "Central Reserve Bank of Peru", "ID": "Bank Indonesia", "MY": "Bank Negara Malaysia",
              "TH": "Bank of Thailand", "PH": "Bangko Sentral ng Pilipinas", "IL": "Bank of Israel",
              "SA": "Saudi Central Bank", "DK": "Danmarks Nationalbank", "IS": "Central Bank of Iceland",
              "RO": "National Bank of Romania", "AR": "Central Bank of Argentina",
              "HK": "Hong Kong Monetary Authority"}


@dataclass
class Series:
    entity_id: str
    volatility_class: str
    template: str  # format with {value}
    source: str
    points: list[tuple[str, str]]  # (iso start date, value), sorted

    def value_at(self, t: date) -> str | None:
        starts = [p[0] for p in self.points]
        i = bisect_right(starts, t.isoformat())
        return self.points[i - 1][1] if i else None


# ---------- fetching (raw responses cached on disk) ----------

def _cached_get(name: str, url: str, params: dict | None = None, accept: str = "application/json") -> str:
    path = RAW / name
    if path.exists():
        return path.read_text()
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        resp = httpx.get(url, params=params, headers={**UA, "Accept": accept}, timeout=120)
        if resp.status_code == 200:
            path.write_text(resp.text)
            return resp.text
        time.sleep(2 ** attempt * 3)
    raise RuntimeError(f"fetch failed {resp.status_code}: {url}")


def _sparql(name: str, query: str) -> list[dict]:
    text = _cached_get(name, "https://query.wikidata.org/sparql", {"query": query},
                       accept="application/sparql-results+json")
    return json.loads(text)["results"]["bindings"]


ROLE_QUERY = """
SELECT ?org ?orgLabel ?h ?hLabel ?s ?e WHERE {{
  {scope}
  ?org p:{prop} ?st. ?st ps:{prop} ?h; pq:P580 ?s.
  OPTIONAL {{ ?st pq:P582 ?e }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def office_series() -> list[Series]:
    roles = [
        ("P6", "head_of_government", "?org wdt:P31 wd:Q3624078.",
         "The head of government of {org} is {{value}}."),
        ("P35", "head_of_state", "?org wdt:P31 wd:Q3624078.", "The head of state of {org} is {{value}}."),
        ("P169", "ceo", "?org wdt:P414 ?ex. ?org wdt:P2139 ?rev.", "The CEO of {org} is {{value}}."),
    ]
    out = []
    for prop, role, scope, tmpl in roles:
        rows = _sparql(f"wikidata_{role}.json", ROLE_QUERY.format(scope=scope, prop=prop))
        by_org: dict[str, dict] = {}
        for r in rows:
            org = r["org"]["value"].rsplit("/", 1)[-1]
            label = r["orgLabel"]["value"]
            holder = r["hLabel"]["value"]
            if holder.startswith("Q") and holder[1:].isdigit():
                continue  # no English label
            s = r["s"]["value"][:10]
            e = r.get("e", {}).get("value", "")[:10] or None
            by_org.setdefault(org, {"label": label, "terms": set()})["terms"].add((s, e, holder))
        for org, info in by_org.items():
            terms = sorted((t for t in info["terms"] if t[0][:1] in "12"), key=lambda t: (t[0], t[2]))
            if len(terms) < 2:
                continue
            points = _term_points(terms)
            out.append(Series(f"{role}:{org}", "office_holder", tmpl.format(org=info["label"]),
                              f"https://www.wikidata.org/wiki/{org}#{prop}", _dedupe(points)))
    return out


NO_HOLDER = "(no holder recorded)"


def _term_points(terms: list[tuple[str, str | None, str]]) -> list[tuple[str, str]]:
    """Holder at each boundary = latest-starting term still open (end null or after the date).

    A term that ended with no successor recorded yields NO_HOLDER, so "X is CEO" made during
    X's term is labelled stale once the term ends, even if Wikidata lacks the successor.
    """
    bounds = sorted({s for s, _, _ in terms} | {e for _, e, _ in terms if e and e[:1] in "12"})
    points = []
    for d in bounds:
        open_terms = [(s, h) for s, e, h in terms if s <= d and (e is None or e > d)]
        points.append((d, max(open_terms)[1] if open_terms else NO_HOLDER))
    return points


def _dedupe(points: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for d, v in sorted(points):
        if out and out[-1][1] == v:
            continue
        if out and out[-1][0] == d:
            out[-1] = (d, v)
            continue
        out.append((d, v))
    return out


def _version_points(releases: dict[str, str]) -> list[tuple[str, str]]:
    """releases: version -> first upload date. Value at t = highest stable version released by t."""
    parsed = []
    for v, d in releases.items():
        try:
            pv = Version(v)
        except InvalidVersion:
            continue
        if pv.is_prerelease or pv.is_devrelease:
            continue
        parsed.append((d, pv, v))
    parsed.sort()
    points, best = [], None
    for d, pv, v in parsed:
        if best is None or pv > best:
            best = pv
            points.append((d, v))
    return _dedupe(points)


def version_series() -> list[Series]:
    out = []
    for pkg in PYPI:
        data = json.loads(_cached_get(f"pypi_{pkg}.json", f"https://pypi.org/pypi/{pkg}/json"))
        rel = {v: min(f["upload_time"][:10] for f in files) for v, files in data["releases"].items() if files}
        out.append(Series(f"pypi:{pkg}", "software_version", f"The latest stable release of the Python package {pkg} is {{value}}.",
                          f"https://pypi.org/project/{pkg}/#history", _version_points(rel)))
    for pkg in NPM:
        safe = pkg.replace("/", "__")
        data = json.loads(_cached_get(f"npm_{safe}.json", f"https://registry.npmjs.org/{pkg}"))
        rel = {v: t[:10] for v, t in data.get("time", {}).items() if v not in ("created", "modified")}
        out.append(Series(f"npm:{pkg}", "software_version", f"The latest stable release of the npm package {pkg} is {{value}}.",
                          f"https://www.npmjs.com/package/{pkg}?activeTab=versions", _version_points(rel)))
    return out


def rate_series() -> list[Series]:
    out = []
    for area in BIS_AREAS:
        text = _cached_get(f"bis_{area}.csv", f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.{area}",
                           {"format": "csv"}, accept="text/csv")
        points = []
        for row in csv.DictReader(io.StringIO(text)):
            if not row.get("OBS_VALUE"):
                continue
            # Monthly end-of-period value: treat as in force from the first day of the month.
            points.append((f"{row['TIME_PERIOD']}-01", f"{float(row['OBS_VALUE']):.2f}%"))
        if points:
            out.append(Series(f"rate:{area}", "rate_or_statistic",
                              f"The {AREA_NAMES.get(area, area)} policy rate is {{value}}.",
                              f"https://data.bis.org/topics/CBPOL (WS_CBPOL M.{area})", _dedupe(points)))
    return out


def timeless_series() -> list[Series]:
    out = []
    rows = _sparql("wikidata_elements.json", """
SELECT ?el ?elLabel ?n WHERE { ?el wdt:P31 wd:Q11344; wdt:P1086 ?n.
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }""")
    for r in rows:
        q = r["el"]["value"].rsplit("/", 1)[-1]
        out.append(Series(f"element:{q}", "timeless", f"The atomic number of {r['elLabel']['value']} is {{value}}.",
                          f"https://www.wikidata.org/wiki/{q}", [("0001-01-01", r["n"]["value"])]))
    rows = _sparql("wikidata_births.json", """
SELECT ?p ?pLabel ?b WHERE { ?p wdt:P31 wd:Q5; wdt:P166 wd:Q7191; wdt:P569 ?b; wdt:P570 ?d.
 SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } LIMIT 300""")
    seen = set()
    for r in rows:
        q = r["p"]["value"].rsplit("/", 1)[-1]
        if q in seen or not r["b"]["value"][:1].isdigit():
            continue
        seen.add(q)
        out.append(Series(f"birth:{q}", "timeless", f"{r['pLabel']['value']} was born on {{value}}.",
                          f"https://www.wikidata.org/wiki/{q}", [("0001-01-01", r["b"]["value"][:10])]))
    return out


# ---------- claims ----------

SAMPLES_PER_ENTITY = {"office_holder": 3, "software_version": 4, "rate_or_statistic": 4, "timeless": 2}


def _split(entity_id: str) -> str:
    return "fit" if int(hashlib.sha256(entity_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def build_claims(series: list[Series]) -> list[dict]:
    rng = random.Random(SEED)
    claims = []
    for s in series:
        split = _split(s.entity_id)
        ref, max_age = (CUTOFF, 1825) if split == "fit" else (TODAY, 730)
        ref_value = s.value_at(ref)
        if ref_value is None:
            continue
        for k in range(SAMPLES_PER_ENTITY[s.volatility_class]):
            age = round(math.exp(rng.uniform(math.log(7), math.log(max_age))))
            asof = ref - timedelta(days=age)
            value = s.value_at(asof)
            if value is None or value == NO_HOLDER:
                continue  # nothing to claim on that date
            claims.append({
                "id": f"{s.entity_id}#{k}", "entity_id": s.entity_id, "split": split,
                "volatility_class": s.volatility_class, "text": s.template.format(value=value),
                "asof": asof.isoformat(), "reference_date": ref.isoformat(), "age_days": age,
                "value_then": value, "value_at_reference": ref_value,
                "label": "current" if value == ref_value else "stale", "source": s.source,
            })
    return claims


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    series = office_series() + version_series() + rate_series() + timeless_series()
    (DATA / "series.jsonl").write_text("".join(json.dumps(asdict(s)) + "\n" for s in series))
    claims = build_claims(series)
    (DATA / "claims.jsonl").write_text("".join(json.dumps(c) + "\n" for c in claims))
    from collections import Counter
    print("series:", Counter(s.volatility_class for s in series))
    print("claims:", Counter((c["split"], c["volatility_class"], c["label"]) for c in claims))


if __name__ == "__main__":
    main()
