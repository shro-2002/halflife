# Detector errors — eval date 2026-11-12

Confusion (rows = label, columns = detector outcome; a case is flagged if any claim is `changed`):

| label | changed | current | unverifiable | not searched |
|---|---|---|---|---|
| stale | 32 | 1 | 5 | 0 |
| current | 5 | 21 | 9 | 10 |
| timeless | 0 | 0 | 0 | 25 |

Precision 0.865, recall 0.842 on 83 time-sensitive cases.

## 11 wrong verdicts (missed stale = FN incl. unverifiable/not searched; flagged non-stale = FP)

### `s-boe-rate` — FN (missed stale) — rate_or_statistic
- Claim: The Bank of England's Bank Rate is 3.75%.
- Labelled truth: 4% (raised, published 5 Nov 2026) (source: https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate)
- Outcome: **current**
- Extracted: "The Bank of England's Bank Rate is 3.75%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.5
  - Verdict current; quote: "At its meeting ending on 16 September 2026, the Monetary Policy Committee (MPC) voted by a majority of 6–3 to maintain Bank Rate at 3.75%." (https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026); value: None
  - Model reasoning: The official Bank of England September 2026 minutes state Bank Rate was maintained at 3.75%, and the official explainer page also gives 3.75% as the current rate. The only later-dated source, the globebids.co.uk page, is non-official and reports the same 3.75% level.
  - Evidence: https://getsmartsaver.co.uk/bank-of-england-july-2026-rate-decision — "The Bank of England’s Bank Rate is currently 3.75 per cent, held at the June 2026 meeting, and the next decision lands at noon on 30 July 2026. The most likely outcome is another h"
  - Evidence: https://advaithhomes.co.uk/news/bank-of-england-interest-rate-held-at-3-75-september-2026 — "The Bank of England has kept Bank Rate unchanged at 3.75% following its latest Monetary Policy Committee meeting, with the decision published on 17 September 2026. The Monetary Pol"
  - Evidence: https://cambridgecurrencies.com/next-bank-of-england-interest-rate-decision-date — "•

9–13 minutes

Direct answer: The Bank of England held Bank Rate at 3.75% on Thursday 17 September 2026 in a 6–3 vote, with three members voting for a rise to 4%. The current UK"

### `s-ss-wage-base` — FN (missed stale) — law_or_regulation
- Claim: The maximum earnings subject to Social Security tax is $176,100.
- Labelled truth: $184,500 for 2026 ($192,300 set for 2027) (source: https://www.ssa.gov/oact/cola/cbb.html)
- Outcome: **unverifiable**
- Extracted: "The maximum earnings subject to Social Security tax is $176,100." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.6
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `s-401k` — FN (missed stale) — law_or_regulation
- Claim: The annual 401(k) employee elective deferral limit is $23,500.
- Labelled truth: $24,500 for 2026 (source: https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500)
- Outcome: **unverifiable**
- Extracted: "The annual 401(k) employee elective deferral limit is $23,500." [law_or_regulation], time-sensitive=True, p_outdated_model=0.35
  - Verdict unverifiable; quote: "" (None); value: None
  - Model reasoning: judge: unusable output (Expecting ',' delimiter: line 1 column 482 (char 481))
  - Evidence: https://www.empower.com/the-currency/work/401k-contribution-limits — "For 2026, the employee 401(k) elective deferral limit is $24,500 (up from $23,500 in 2025). Catch-up contributions are generally capped at $8,000 for people age 50 or older, while"
  - Evidence: https://roistreet.com/learn/what-is-the-401k-elective-deferral-limit — "The regular 2026 employee elective-deferral ceiling is $24,500.(#source-1)(#source-2)(#source-3)
 Traditional pre-tax and designated Roth 401(k) deferrals share that one basic limi"
  - Evidence: https://blog.surgentcpe.com/401k-planning-2026-contribution-limits-rules — "### SIMPLE 401(k)

Available to employers with 100 or fewer employees who received at least $5,000 in compensation in the prior year. The elective deferral limit for SIMPLE 401(k)"
  - Errors: ["judge: unusable output (Expecting ',' delimiter: line 1 column 482 (char 481))"]

### `s-us-cpi` — FN (missed stale) — rate_or_statistic
- Claim: US consumer prices are up 3.4% over the past year.
- Labelled truth: 3.7% for the 12 months ending September 2026 (latest published 12-month figure; BLS published no year-over-year rate for October 2026) (source: https://www.bls.gov/news.release/pdf/cpi.pdf)
- Outcome: **unverifiable**
- Extracted: "US consumer prices are up 3.4% over the past year." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.9
  - Verdict unverifiable; quote: "" (None); value: None
  - Model reasoning: The claim's 3.4% figure is still the headline value, as the August 2026 CPI was reported at 3.4% year-over-year, but the claim's wording is tied to the past year as of an earlier period. The strictly official source (BLS) gives 3.4% for the 12 months ended July 2026, and the non-official TD source c
  - Evidence: https://www.bls.gov/opub/ted/2026/consumer-prices-up-3-4-over-the-year-in-july-2026.htm — "August 14, 2026

Over the 12 months ended July 2026, the Consumer Price Index for All Urban Consumers increased 3.4 percent, after rising 3.5 percent for the year ending in June. P"
  - Evidence: https://economics.td.com/us-cpi — "## Thomas Feltmate, Director & Senior Economist | 416-944-5730

Date Published: September 11, 2026

   Category:
   U.S.
   Data Commentary

Share:

## Core inflation heats up in A"
  - Evidence: https://www.haver.com/articles/u-s-consumer-price-inflation-steady-in-august-at-3-4-y-y — "Haver Analytics

Haver Analytics

 Economy in Brief
 Viewpoints
 Contact Us

USA| Sep 11 2026

# U.S. Consumer Price Inflation Steady in August at 3.4% Y/Y

by:Winnie Tapasanun

|i"

### `s-jp-ctax` — FN (missed stale) — law_or_regulation
- Claim: Japan's standard consumption tax rate is 8%.
- Labelled truth: 10% (since 1 October 2019; 8% reduced rate for food) (source: https://www.eu-japan.eu/taxes-accounting/consumption-taxes)
- Outcome: **unverifiable**
- Extracted: "Japan's standard consumption tax rate is 8%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.1
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `s-sbux-ceo` — FN (missed stale) — office_holder
- Claim: Laxman Narasimhan is the CEO of Starbucks.
- Labelled truth: Brian Niccol (since September 2024) (source: https://investor.starbucks.com/governance/board-of-directors/person-details/default.aspx?ItemId=5490d108-aad0-46c9-bd96-e53e863b3bc2)
- Outcome: **unverifiable**
- Extracted: "Laxman Narasimhan is the CEO of Starbucks." [office_holder], time-sensitive=True, p_outdated_model=0.3
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `c-au-super` — FP (flagged non-stale) — law_or_regulation
- Claim: The Australian superannuation guarantee rate is 12% of ordinary time earnings.
- Labelled truth: 12% (source: https://www.ato.gov.au/businesses-and-organisations/super-for-employers/quarterly-super-to-30-june-2026/how-much-super-to-pay)
- Outcome: **changed**
- Extracted: "The Australian superannuation guarantee rate is 12% of ordinary time earnings." [law_or_regulation], time-sensitive=True, p_outdated_model=0.1
  - Verdict changed; quote: "The super guarantee amount is calculated as 12% of qualifying earnings." (https://www.ato.gov.au/businesses-and-organisations/super-for-employers/about-payday-super); value: 12% of qualifying earnings
  - Model reasoning: The claim's rate of 12% still holds, but since 1 July 2026 the official ATO guidance calculates super guarantee as 12% of qualifying earnings rather than ordinary time earnings. The base the claim names is therefore outdated.
  - Evidence: https://www.teamed.global/country-hiring-guides/australia/tax-and-payroll — "| Contribution type | Rate | Ceiling | Who pays |
 ---  --- |
| Superannuation Guarantee | 12% | AUD 270,830 a year per employee (2026-27 maximum contribution base) | Employer, on"
  - Evidence: https://www.australianretirementtrust.com.au/learn/superannuation/super-guarantee-rate-increase — "Before 1 July 2026, that amount was calculated as 12% of your ordinary time earnings (OTE).

From 1 July 2026 onwards, your employer will calculate your SG amount as 12% of your ‘q"
  - Evidence: https://smcaustralia.com/superannuation-basics-and-history/super-guarantee-rates-a-history — "| 1 July 2024 – 30 June 2025 | 11.5% | Albanese (Labor) | Nearing 12%, higher contributions hope to improve outcomes, especially for younger workers and lower-income earners. |
| 1"

### `c-ofgem-cap` — FP (flagged non-stale) — price
- Claim: Ofgem's energy price cap for a typical dual-fuel household paying by direct debit is £1,723 a year.
- Labelled truth: £1,723 (1 Oct - 31 Dec 2026) (source: https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026)
- Outcome: **changed**
- Extracted: "Ofgem's energy price cap for a typical dual-fuel household paying by direct debit is £1,723 a year." [price], time-sensitive=True, p_outdated_model=0.9
  - Verdict changed; quote: "From 1 October to 31 December 2026, the price cap will be £1,723 per year." (https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/energy-price-cap-unit-rates-and-standing-charges); value: None
  - Model reasoning: The claim gives £1,723 as the current cap, which matches the latest official Ofgem figure for 1 October to 31 December 2026. Today is 12 November 2026, so that period is still in force and the claim is consistent with it, though the verdict is labelled 'changed' per the evidence and the cap is set q
  - Evidence: https://www.bluettipower.co.uk/blogs/basic-knowledge/energy-bills-price-cap — "As of 8 September 2026, the current Ofgem cap period runs from 1 July to 30 September 2026. For a typical dual-fuel household paying by Direct Debit, the headline annualised figure"
  - Evidence: https://www.ofgem.gov.uk/press-release/energy-price-cap-will-rise-4-october-2026 — "The current price cap for a typical household paying by direct debit for gas and electricity is £1,663. Based on the energy use of a typical domestic household, from October, the p"
  - Evidence: https://www.ofgem.gov.uk/news/changes-energy-price-cap-between-1-april-and-30-june-2026 — "Every 3 months we review and set a level for how much an energy supplier can charge for each unit of energy and daily standing charge, under the price cap.

From 1 April to 30 June"

### `c-go` — FP (flagged non-stale) — software_version
- Claim: The latest major Go release is Go 1.27, released in August 2026.
- Labelled truth: Go 1.27 (source: https://go.dev/doc/go1.27)
- Outcome: **changed**
- Extracted: "The latest major Go release is Go 1.27, released in August 2026." [software_version], time-sensitive=True, p_outdated_model=0.45
  - Verdict changed; quote: "go1.27.0 (released 2026-08-19)" (https://go.dev/doc/devel/release); value: None
  - Model reasoning: The claim that Go 1.27 is the latest major release and was released in August 2026 is still true: the official release page confirms go1.27.0 was released 2026-08-19 and no newer major version appears. However, the claim's wording is about the major release, and the most recent official release list
  - Evidence: https://go.dev/blog/go1.27 — "# The Go Blog

# Go 1.27 is released

Nicholas Husin, on behalf of the Go team  
 19 August 2026

Today the Go team is pleased to release Go 1.27. You can find its binary archives"
  - Evidence: https://devblogs.microsoft.com/go/go-1-27-0-1-microsoft-build-now-available — "August 20th, 2026

heart1 reaction

# Go 1.27.0-1 Microsoft build now available

Davis Goodin

Senior Software Engineer

A new release of the Microsoft build of Go is now available"
  - Evidence: https://safeguard.sh/resources/blog/how-long-is-a-go-version-supported — "3 min read

A Go major release is supported until two newer major releases are out, which works out to about a year. With Go 1.27 released on 19 August 2026, Go 1.26 and 1.27 are t"

### `c-django` — FP (flagged non-stale) — software_version
- Claim: The latest Django release is 6.1.2.
- Labelled truth: 6.1.2 (source: https://www.djangoproject.com/download)
- Outcome: **changed**
- Extracted: "The latest Django release is 6.1.2." [software_version], time-sensitive=True, p_outdated_model=0.6
  - Verdict changed; quote: "Django 6.1.3 fixes five security issues with severity “low”, one security issue with severity “moderate”, and several bugs in 6.1.2." (https://docs.djangoproject.com/en/6.1/releases/6.1.3); value: 6.1.3
  - Model reasoning: The official Django 6.1.3 release notes, published November 3, 2026, show a newer 6.1 release than 6.1.2. The official forum also lists the 6.1.3 security release, so the claim that 6.1.2 is the latest is no longer true.
  - Evidence: https://django.readthedocs.io/en/stable/releases/1.4.17.html — "Title: Django 1.4.17 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 1.4.17 release notes¶. Django 1.4"
  - Evidence: https://django.readthedocs.io/en/stable/releases/4.1.8.html — "Title: Django 4.1.8 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 4.1.8 release notes¶. Django 4.1.8"
  - Evidence: https://django.readthedocs.io/en/stable/releases/5.1.2.html — "Title: Django 5.1.2 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 5.1.2 release notes¶. Django 5.1.2"

### `c-newest-iphone` — FP (flagged non-stale) — product_spec
- Claim: Apple's newest flagship iPhones are the iPhone 18 Pro and iPhone 18 Pro Max, launched in September 2026.
- Labelled truth: iPhone 18 Pro / Pro Max (source: https://www.macrumors.com/roundup/iphone-18)
- Outcome: **changed**
- Extracted: "Apple's newest flagship iPhones are the iPhone 18 Pro and iPhone 18 Pro Max." [product_spec], time-sensitive=True, p_outdated_model=0.6
  - Verdict changed; quote: "iPhone Duo
New" (https://www.apple.com/iphone-18-pro/specs); value: iPhone Duo
  - Model reasoning: Official Apple pages list the iPhone Duo as the newest model, marked "New" above the iPhone 18 Pro lineup. MacRumors describes the iPhone 18 Pro models as the latest flagships, but that source is not official and is older than the Apple pages.
  - Evidence: https://www.macrumors.com/2026/09/12/iphone-18-pro-available-to-pre-order — "The ‌iPhone 18 Pro‌ and ‌iPhone 18 Pro‌ Max are Apple's latest flagship iPhones, featuring a new variable aperture Main camera, a faster A20 Pro chip, improved vapor chamber coolin"
  - Evidence: https://www.youtube.com/watch?v=Q3zwkxqh1t0 — "Posted: 2026-09-09
iPhone 18 Pro is Apple’s most powerful iPhone yet. It features the A20 Pro chip, which has exceptional AI capabilities and is cooled by a next-generation vapor c"
  - Evidence: https://www.apple.com/uk/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max — "CUPERTINO, CALIFORNIA Apple today announced iPhone 18 Pro and iPhone 18 Pro Max, delivering the most advanced pro camera system in an iPhone, and huge leaps in battery life and per"
- Extracted: "The iPhone 18 Pro and iPhone 18 Pro Max were launched in September 2026." [timeless], time-sensitive=False, p_outdated_model=0.0
