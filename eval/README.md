# Live detector test cases (`eval/cases.jsonl`)

108 single-claim cases, each one sentence the way an LLM might state it, labelled
`stale`, `current` or `timeless` against evidence retrieved on **2026-11-12** with Tavily
through the Bifrost relay (`/relay/tavily/search`, disk cache in front).

## Check

```bash
uv run python eval/build_cases.py --check
```

Offline. For every case it checks that:

- all fields are present, `volatility_class` is a `VolatilityClass` value, `label` is one of the
  three labels, `label == timeless` exactly when the class is `timeless`, stale/current cases
  have a `current_truth`, `as_of` is a date not after `date_checked`, ids are unique;
- `supporting_quote` is an **exact substring** of the Tavily `content` returned for
  (`query`, `source_url`), as saved in `eval/cases_sources/search_results.jsonl`;
- when the Tavily disk cache (`.cache/tavily`) still holds that day's entry, the quote is
  also found there. Absent entries (other machine, later UTC day) are reported, not failed.

Exit code 1 on any problem. Last run: `108 cases, 0 problems -> OK`, 108/108 also verified
against the disk cache.

## Fields

| Field | Meaning |
|---|---|
| `id` | `s-…` stale, `c-…` current, `t-…` timeless |
| `claim` | One sentence, as an LLM answer might state it |
| `volatility_class` | `software_version`, `price`, `rate_or_statistic`, `office_holder`, `law_or_regulation`, `product_spec`, `timeless` |
| `as_of` | Stale: a date the claim was last true. Current: the date the value took effect or was published (2026-11-12 when unknown). Timeless: 2026-11-12 |
| `label` | `stale` (was true, no longer), `current` (still true, or a correctly dated past event), `timeless` (never changes) |
| `current_truth` | The value true today as stated in the source; `null` for timeless |
| `source_url` | A URL returned by the Tavily search in `query` |
| `supporting_quote` | Verbatim span of that result's `content` that supports `current_truth` and the label |
| `query` | The Tavily query that returned `source_url` (params in the saved results file) |
| `date_checked` | 2026-11-12 |
| `notes` | Caveats, or `null` |

## Composition

| class | stale | current | timeless | total |
|---|---:|---:|---:|---:|
| law_or_regulation | 10 | 11 | 0 | 21 |
| office_holder | 8 | 10 | 0 | 18 |
| price | 6 | 7 | 0 | 13 |
| product_spec | 2 | 3 | 0 | 5 |
| rate_or_statistic | 5 | 7 | 0 | 12 |
| software_version | 7 | 7 | 0 | 14 |
| timeless | 0 | 0 | 25 | 25 |
| **total** | **38** | **45** | **25** | **108** |

Finance and regulation (policy rates, CPI, unemployment, tax rates and allowances, retirement
limits, minimum wages, estate tax, payment limits, EU AI Act and Instant Payments dates): 33
cases. Prices (subscriptions, postage, consoles, energy cap): 13. These cover the two classes
the J0.5 ordering dataset lacks (price, law).

Many stale/current cases come in pairs that share one source (e.g. "Bank Rate is 3.75%" stale,
"Bank Rate is 4%" current). That tests whether the detector tells a superseded value from the
current one on the same evidence; it also means the 83 time-sensitive cases are not 83
independent topics.

## How labels were decided

1. Queries were written per candidate topic, with `include_domains` set to the official site
   where one exists (federalreserve.gov, bankofengland.co.uk, ecb.europa.eu, bls.gov, irs.gov,
   ssa.gov, gov.uk, iras.gov.sg, ato.gov.au, nodejs.org, go.dev, nist.gov, …). Basic depth,
   5 results. Specs: `eval/cases_sources/specs_batch*.json`.
2. A label was assigned only when a returned snippet states the current value (or, for
   timeless cases, the fact) in so many words. **Stale**: the claim states a real former value
   and the quote states a different current value, usually naming the change ("increased to
   20% on 4 January 2011 (from 17.5%)"). **Current**: the quote states the claimed value as
   in force, or the claim is a dated past event. **Timeless**: constants, definitions and
   historical dates.
3. Values came from the evidence, not memory. Where the former value in a stale claim is not
   itself printed in the quote (e.g. Netflix $17.99, NLW £12.21, estate tax $13.99M), it is a
   known earlier value and the quote shows the current, different value; such cases say so in
   `notes` where relevant.

## Limits

- **"Current" means current in the evidence retrieved on 2026-11-12.** A value can change
  after that (RBI and other central banks meet again; Lagarde leaves 2027-02-07, Guterres
  2026-12-31; Django/Node patch releases). Re-run searches and re-label before reusing the set
  much later. Stale labels are more durable than current ones.
- **`as_of` for stale cases is a date the old value was true, often approximate** (chosen
  safely inside the period, e.g. the day before a change or a mid-period date when the change
  date was not in evidence). Use it for age, not as the exact date of change.
- Some sources are secondary: Wikipedia (timeless dates, UN SG, Luxembourg), Britannica,
  news sites (The Hindu, BBC, Yahoo Finance, CNET, MacRumors), a law firm (mhc.ie), stamps.com,
  and a trade magazine for H2O. Official sources were preferred and used for most rates,
  taxes, limits and versions.
- `s-macbook-air-chip`: evidence shows M4 superseded M3; it does not show whether a newer chip
  has since shipped, so `current_truth` reads "M4 or newer".
- Year of the BLS CPI release (September 2026) is inferred from the live release page, which
  does not state the year in the quoted span.
- Single annotator, no second labeller.

## Dropped candidates

| Candidate | Reason |
|---|---|
| Bank of Japan rate | only a Facebook post of a forecast |
| RBA cash rate (stale 4.35%) | release dates not in evidence; `as_of` unsupported |
| Kubernetes 1.36 stale | 1.37 release date not in evidence |
| France PM (Lecornu) | Wikipedia snippet with a January 2026 retrieval date; may be outdated |
| Disney CEO (D'Amaro) | evidence says "to become CEO at the upcoming annual meeting"; not confirmed in office |
| Apple CEO (Ternus) | only an Instagram post |
| Chile president (Kast) | only YouTube descriptions |
| Intel CEO (Lip-Bu Tan) | only YouTube/Instagram |
| UPI ₹1 lakh limit | payment-company blogs only |
| GDPR max fine | consultancy page only (official text not returned) |
| ECB deposit rate, stale | former value before the Sep 2026 hike not in evidence |
| Python "latest", Linux kernel, Java, NumPy | results did not state a current latest version |
| Euro cash 2002, Pythagoras, first iPhone 2007, Pluto 2006 | quote did not state the fact cleanly, or video/podcast source only |
| Spotify current price, UK Personal Allowance, standard deduction, React 19.3, pip 26.3 | kept the set near 100 (evidence was fine) |

## Files

- `cases.jsonl`: the cases.
- `build_cases.py`: `--search SPECS.json` runs searches through the relay and appends every
  result to `cases_sources/search_results.jsonl`; `--check` validates (above).
- `cases_sources/search_results.jsonl`: every Tavily result retrieved (505 rows from 101
  queries): query, request params, url, title, content, published_date.
- `cases_sources/specs_batch1-4.json`: the query specs.

Tavily cost: 101 basic searches = 101 credits (all cache misses, 0 repeats).
