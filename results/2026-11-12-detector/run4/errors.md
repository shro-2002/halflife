# Detector errors — eval date 2026-11-12

Confusion (rows = label, columns = detector outcome; a case is flagged if any claim is `changed`):

| label | changed | current | unverifiable | not searched |
|---|---|---|---|---|
| stale | 33 | 1 | 4 | 0 |
| current | 5 | 26 | 5 | 9 |
| timeless | 0 | 0 | 0 | 25 |

Precision 0.868, recall 0.868 on 83 time-sensitive cases.

## 10 wrong verdicts (missed stale = FN incl. unverifiable/not searched; flagged non-stale = FP)

### `s-boe-rate` — FN (missed stale) — rate_or_statistic
- Claim: The Bank of England's Bank Rate is 3.75%.
- Labelled truth: 4% (raised, published 5 Nov 2026) (source: https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate)
- Outcome: **current**
- Extracted: "The Bank of England's Bank Rate is 3.75%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.5
  - Verdict current; quote: "voted by a majority of 6–3 to maintain Bank Rate at 3.75%" (https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026); value: None
  - Model reasoning: The most authoritative source, the Bank of England's September 2026 summary, confirms Bank Rate was maintained at 3.75%, and the latest evidence is from September 2026 with nothing later showing a change. Since today is 2026-11-12, the November 5 decision would be the next check, but no evidence rep
  - Evidence: https://getsmartsaver.co.uk/bank-of-england-july-2026-rate-decision — "The Bank of England’s Bank Rate is currently 3.75 per cent, held at the June 2026 meeting, and the next decision lands at noon on 30 July 2026. The most likely outcome is another h"
  - Evidence: https://advaithhomes.co.uk/news/bank-of-england-interest-rate-held-at-3-75-september-2026 — "The Bank of England has kept Bank Rate unchanged at 3.75% following its latest Monetary Policy Committee meeting, with the decision published on 17 September 2026. The Monetary Pol"
  - Evidence: https://cambridgecurrencies.com/next-bank-of-england-interest-rate-decision-date — "•

9–13 minutes

Direct answer: The Bank of England held Bank Rate at 3.75% on Thursday 17 September 2026 in a 6–3 vote, with three members voting for a rise to 4%. The current UK"

### `s-ss-wage-base` — FN (missed stale) — law_or_regulation
- Claim: The maximum earnings subject to Social Security tax is $176,100.
- Labelled truth: $184,500 for 2026 ($192,300 set for 2027) (source: https://www.ssa.gov/oact/cola/cbb.html)
- Outcome: **unverifiable**
- Extracted: "The maximum earnings subject to Social Security tax is $176,100." [law_or_regulation], time-sensitive=True, p_outdated_model=0.6
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `s-jp-ctax` — FN (missed stale) — law_or_regulation
- Claim: Japan's standard consumption tax rate is 8%.
- Labelled truth: 10% (since 1 October 2019; 8% reduced rate for food) (source: https://www.eu-japan.eu/taxes-accounting/consumption-taxes)
- Outcome: **unverifiable**
- Extracted: "Japan's standard consumption tax rate is 8%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.1
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `s-no-king` — FN (missed stale) — office_holder
- Claim: Harald V is the King of Norway.
- Labelled truth: Haakon VIII (since 28 August 2026) (source: https://www.britannica.com/biography/Haakon-VIII)
- Outcome: **unverifiable**
- Extracted: "Harald V is the King of Norway." [office_holder], time-sensitive=True, p_outdated_model=0.03
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `s-lu-grandduke` — FN (missed stale) — office_holder
- Claim: Henri is the Grand Duke of Luxembourg.
- Labelled truth: Guillaume V (since 3 October 2025) (source: https://en.wikipedia.org/wiki/Guillaume_V_of_Luxembourg)
- Outcome: **unverifiable**
- Extracted: "Henri is the Grand Duke of Luxembourg." [office_holder], time-sensitive=True, p_outdated_model=0.02
  - Errors: ['search open-web: offline mode: no cached evidence for this query', 'search authoritative: offline mode: no cached evidence for this query']

### `c-au-super` — FP (flagged non-stale) — law_or_regulation
- Claim: The Australian superannuation guarantee rate is 12% of ordinary time earnings.
- Labelled truth: 12% (source: https://www.ato.gov.au/businesses-and-organisations/super-for-employers/quarterly-super-to-30-june-2026/how-much-super-to-pay)
- Outcome: **changed**
- Extracted: "The Australian superannuation guarantee rate is 12% of ordinary time earnings." [law_or_regulation], time-sensitive=True, p_outdated_model=0.1
  - Verdict changed; quote: "From 1 July 2026 onwards, your employer will calculate your SG amount as 12% of your ‘qualifying earnings.'" (https://www.australianretirementtrust.com.au/learn/superannuation/super-guarantee-rate-increase); value: None
  - Model reasoning: The rate is still 12%, but since 1 July 2026 it applies to qualifying earnings rather than ordinary time earnings. The claim's base term is therefore outdated.
  - Evidence: https://www.teamed.global/country-hiring-guides/australia/tax-and-payroll — "| Contribution type | Rate | Ceiling | Who pays |
 ---  --- |
| Superannuation Guarantee | 12% | AUD 270,830 a year per employee (2026-27 maximum contribution base) | Employer, on"
  - Evidence: https://www.australianretirementtrust.com.au/learn/superannuation/super-guarantee-rate-increase — "Before 1 July 2026, that amount was calculated as 12% of your ordinary time earnings (OTE).

From 1 July 2026 onwards, your employer will calculate your SG amount as 12% of your ‘q"
  - Evidence: https://smcaustralia.com/superannuation-basics-and-history/super-guarantee-rates-a-history — "| 1 July 2024 – 30 June 2025 | 11.5% | Albanese (Labor) | Nearing 12%, higher contributions hope to improve outcomes, especially for younger workers and lower-income earners. |
| 1"

### `c-ecb-president` — FP (flagged non-stale) — office_holder
- Claim: Christine Lagarde is the President of the European Central Bank.
- Labelled truth: Christine Lagarde (to step down 7 Feb 2027) (source: https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr261029~abbb6dc64b.en.html)
- Outcome: **changed**
- Extracted: "Christine Lagarde is the President of the European Central Bank." [office_holder], time-sensitive=True, p_outdated_model=0.15
  - Verdict changed; quote: "European Central Bank President Christine Lagarde today informed the Governing Council and the President of the European Council António Costa that she will step down from her position on 7 February 2" (https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr261029~abbb6dc64b.en.html); value: None
  - Model reasoning: The ECB's own October 29, 2026 press release says Lagarde will step down on 7 February 2027, so she still holds the post today (2026-11-12) but the claim that she is president is no longer a lasting fact. The label is 'changed' because the evidence states a future departure and a pending successor r
  - Evidence: https://www.irishsun.com/news/279403687/christine-lagarde-resigns-as-european-central-bank-president — "Irish Sun Logo

Irish Sun Logo

 Facebook
 Twitter
 Google Plus
 RSS Feed

## Christine Lagarde resigns as European Central Bank President

ANI   
30 Oct 2026, 02:59 GMT+10

Christ"
  - Evidence: https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr261029~abbb6dc64b.en.html — "In-depth studies and expert analyses covering diverse topics and fields

# ECB President Lagarde to step down on 7 February 2027

29 October 2026

European Central Bank President C"
  - Evidence: https://www.aninews.in/news/world/europe/christine-lagarde-resigns-as-european-central-bank-president20261030025429 — "Frankfurt [Germany], October 30 (ANI): European Central Bank (ECB) President Christine Lagarde on Thursday informed the Governing Council and European Council President Antonio Cos"

### `c-django` — FP (flagged non-stale) — software_version
- Claim: The latest Django release is 6.1.2.
- Labelled truth: 6.1.2 (source: https://www.djangoproject.com/download)
- Outcome: **changed**
- Extracted: "The latest Django release is 6.1.2." [software_version], time-sensitive=True, p_outdated_model=0.85
  - Verdict changed; quote: "Django 6.1.3 fixes five security issues with severity “low”, one security issue with severity “moderate”, and several bugs in 6.1.2." (https://docs.djangoproject.com/en/6.1/releases/6.1.3); value: 6.1.3
  - Model reasoning: Evidence dated November 3, 2026 shows Django 6.1.3 released, which supersedes 6.1.2 as of today (2026-11-12). The forum listing also shows security releases 6.1.3, 6.0.10, and 5.2.19 published November 4, 2026.
  - Evidence: https://django.readthedocs.io/en/stable/releases/1.4.17.html — "Title: Django 1.4.17 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 1.4.17 release notes¶. Django 1.4"
  - Evidence: https://django.readthedocs.io/en/stable/releases/4.1.8.html — "Title: Django 4.1.8 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 4.1.8 release notes¶. Django 4.1.8"
  - Evidence: https://django.readthedocs.io/en/stable/releases/5.1.2.html — "Title: Django 5.1.2 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 5.1.2 release notes¶. Django 5.1.2"

### `c-iphone17pro-chip` — FP (flagged non-stale) — product_spec
- Claim: The iPhone 17 Pro uses the A19 Pro chip.
- Labelled truth: A19 Pro (source: https://support.apple.com/en-us/125090)
- Outcome: **changed**
- Extracted: "The iPhone 17 Pro uses the A19 Pro chip." [product_spec], time-sensitive=True, p_outdated_model=0.05
  - Verdict changed; quote: "The new models are built around the A20 Pro chip" (https://www.macrumors.com/guide/iphone-17-pro-vs-18-pro); value: A20 Pro
  - Model reasoning: The claim described the iPhone 17 Pro's chip, which the evidence confirms was the A19 Pro at launch. However, newer evidence states the successor iPhone 18 Pro now uses the A20 Pro, so the current flagship chip has changed.
  - Evidence: https://www.youtube.com/watch?v=TNhX1uR2vO8 — "### Description
680,757 views
Posted: 2026-08-20
iPhone 17 Pro features an innovative aluminum unibody design for the ultimate pro performance and battery life. Thanks to the power"
  - Evidence: https://smartish.com/blogs/news/new-iphone-17-pro — "The new iPhone 17 Pro drops September 19, 2025, with pre-orders starting September 12. Two sizes pack serious upgrades: 6.3-inch and 6.9-inch Pro Max variants both feature the A19"
  - Evidence: https://www.macrumors.com/guide/iphone-17-pro-vs-18-pro — "| ‌iPhone 17‌ Pro (2025) | ‌iPhone 18 Pro‌ (2026) |
| A19 Pro chip | A20 Pro chip |
| Built with TSMC's N3P process (3nm) | Built with TSMC's N2 process (2nm), Apple's first 2nm sm"

### `c-newest-iphone` — FP (flagged non-stale) — product_spec
- Claim: Apple's newest flagship iPhones are the iPhone 18 Pro and iPhone 18 Pro Max, launched in September 2026.
- Labelled truth: iPhone 18 Pro / Pro Max (source: https://www.macrumors.com/roundup/iphone-18)
- Outcome: **changed**
- Extracted: "Apple's newest flagship iPhones are the iPhone 18 Pro and iPhone 18 Pro Max." [product_spec], time-sensitive=True, p_outdated_model=0.5
  - Verdict changed; quote: "The lineup includes iPhone 18 Pro, iPhone 18 Pro Max, and iPhone Duo - Apple's first foldable iPhone." (https://www.t-mobile.com/dialed-in/devices/iphone-18-series-specs-features); value: iPhone Duo
  - Model reasoning: Multiple pieces of evidence describe iPhone Duo as Apple's first foldable iPhone launching in the same lineup, and Apple's own Oct 2026 spec page lists it as "New" above the iPhone 18 Pro. The claim that the iPhone 18 Pro and Pro Max are the newest flagships is therefore superseded by the iPhone Duo
  - Evidence: https://www.macrumors.com/2026/09/12/iphone-18-pro-available-to-pre-order — "The ‌iPhone 18 Pro‌ and ‌iPhone 18 Pro‌ Max are Apple's latest flagship iPhones, featuring a new variable aperture Main camera, a faster A20 Pro chip, improved vapor chamber coolin"
  - Evidence: https://www.youtube.com/watch?v=Q3zwkxqh1t0 — "Posted: 2026-09-09
iPhone 18 Pro is Apple’s most powerful iPhone yet. It features the A20 Pro chip, which has exceptional AI capabilities and is cooled by a next-generation vapor c"
  - Evidence: https://www.apple.com/uk/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max — "CUPERTINO, CALIFORNIA Apple today announced iPhone 18 Pro and iPhone 18 Pro Max, delivering the most advanced pro camera system in an iPhone, and huge leaps in battery life and per"
- Extracted: "The iPhone 18 Pro and iPhone 18 Pro Max were launched in September 2026." [timeless], time-sensitive=False, p_outdated_model=0.0
