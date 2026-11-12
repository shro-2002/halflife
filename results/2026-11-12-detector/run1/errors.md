# Detector errors — eval date 2026-11-12

Confusion (rows = label, columns = detector outcome; a case is flagged if any claim is `changed`):

| label | changed | current | unverifiable | not searched |
|---|---|---|---|---|
| stale | 37 | 1 | 0 | 0 |
| current | 7 | 26 | 3 | 9 |
| timeless | 0 | 0 | 0 | 25 |

Precision 0.841, recall 0.974 on 83 time-sensitive cases.

## 8 wrong verdicts (missed stale = FN incl. unverifiable/not searched; flagged non-stale = FP)

### `s-boe-rate` — FN (missed stale) — rate_or_statistic
- Claim: The Bank of England's Bank Rate is 3.75%.
- Labelled truth: 4% (raised, published 5 Nov 2026) (source: https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate)
- Outcome: **current**
- Extracted: "The Bank of England's Bank Rate is 3.75%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.5
  - Verdict current; quote: "voted by a majority of 6–3 to maintain Bank Rate at 3.75%" (https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026); value: None
  - Model reasoning: The most recent evidence, the Bank of England's September 2026 minutes, states Bank Rate was maintained at 3.75%. No evidence dated after that shows a different value, so the claim still holds as of today, 2026-11-12.
  - Evidence: https://getsmartsaver.co.uk/bank-of-england-july-2026-rate-decision — "The Bank of England’s Bank Rate is currently 3.75 per cent, held at the June 2026 meeting, and the next decision lands at noon on 30 July 2026. The most likely outcome is another h"
  - Evidence: https://advaithhomes.co.uk/news/bank-of-england-interest-rate-held-at-3-75-september-2026 — "The Bank of England has kept Bank Rate unchanged at 3.75% following its latest Monetary Policy Committee meeting, with the decision published on 17 September 2026. The Monetary Pol"
  - Evidence: https://cambridgecurrencies.com/next-bank-of-england-interest-rate-decision-date — "•

9–13 minutes

Direct answer: The Bank of England held Bank Rate at 3.75% on Thursday 17 September 2026 in a 6–3 vote, with three members voting for a rise to 4%. The current UK"

### `c-boc-rate` — FP (flagged non-stale) — rate_or_statistic
- Claim: The Bank of Canada's policy interest rate is 2.5%.
- Labelled truth: 2.5% (source: https://www.bankofcanada.ca)
- Outcome: **changed**
- Extracted: "The Bank of Canada's policy interest rate is 2.5%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.5
  - Verdict changed; quote: "Policy interest rate

2.50%

Oct 28, 2026" (https://www.bankofcanada.ca); value: 2.50%
  - Model reasoning: The Bank of Canada raised its policy rate to 2.5% on October 28, 2026, so the 2.5% claim is off by a stated 2.50% versus 2.5%, and the rate is 2.50% per the bank's own site. The claim states 2.5%, which matches the new value, so the claim itself is essentially the current rate.
  - Evidence: https://www.nesto.ca/mortgage-basics/bank-of-canada-interest-rate-schedule — "The Bank of Canada (BoC) raised its policy interest rate by 25 basis points to 2.50% on October 28, its first increase since July 2023. The move ended a run of seven consecutive ho"
  - Evidence: https://www.nesto.ca/mortgage-basics/bank-of-canada-interest-rate-schedule#main — "The Bank of Canada (BoC) raised its policy interest rate by 25 basis points to 2.50% on October 28, its first increase since July 2023. The move ended a run of seven consecutive ho"
  - Evidence: https://www.nesto.ca/mortgage-basics/bank-of-canada-interest-rate-schedule#h-where-to-find-the-bank-of-canada-s-monetary-policy-reports — "Skip to content

Bank of Canada Maintains the Policy Rate at 2.25%

View Impact

nesto.ca

1-866-686-0544

Get a quote

Login

1-866-686-0544

Get a quote

New mortgage

Renewal /"

### `c-au-super` — FP (flagged non-stale) — law_or_regulation
- Claim: The Australian superannuation guarantee rate is 12% of ordinary time earnings.
- Labelled truth: 12% (source: https://www.ato.gov.au/businesses-and-organisations/super-for-employers/quarterly-super-to-30-june-2026/how-much-super-to-pay)
- Outcome: **changed**
- Extracted: "The Australian superannuation guarantee rate is 12% of ordinary time earnings." [law_or_regulation], time-sensitive=True, p_outdated_model=0.1
  - Verdict changed; quote: "From 1 July 2026 onwards, your employer will calculate your SG amount as 12% of your ‘qualifying earnings.'" (https://www.australianretirementtrust.com.au/learn/superannuation/super-guarantee-rate-increase); value: None
  - Model reasoning: The rate itself is still 12%, but since 1 July 2026 the base is qualifying earnings rather than ordinary time earnings, so the claim's 'of ordinary time earnings' no longer describes the current calculation. The ATO page explicitly states the calculation is now on qualifying earnings.
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
- Extracted: "Christine Lagarde is the President of the European Central Bank." [office_holder], time-sensitive=True, p_outdated_model=0.25
  - Verdict changed; quote: "European Central Bank President Christine Lagarde today informed the Governing Council and the President of the European Council António Costa that she will step down from her position on 7 February 2" (https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr261029~abbb6dc64b.en.html); value: None
  - Model reasoning: As of 2026-11-12 the evidence states Lagarde announced on 29 October 2026 that she will step down as ECB President on 7 February 2027, so she still holds the post but the claim's present-tense framing is superseded by a scheduled departure. The label is 'changed' because the evidence describes a dif
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

### `c-go` — FP (flagged non-stale) — software_version
- Claim: The latest major Go release is Go 1.27, released in August 2026.
- Labelled truth: Go 1.27 (source: https://go.dev/doc/go1.27)
- Outcome: **changed**
- Extracted: "The latest major Go release is Go 1.27." [software_version], time-sensitive=True, p_outdated_model=0.5
  - Verdict changed; quote: "| 1.27 | 2 months and 2 weeks ago (19 Aug 2026) | Yes | 1.27.3 (19 Oct 2026) |" (https://endoflife.date/go); value: None
  - Model reasoning: The claim names Go 1.27 as the latest major release, and the evidence shows Go 1.27 is still the newest major version (released 2026-08-19), so it still holds. The evidence does not indicate a changed major version, though it does show newer patch releases, which the claim does not address.
  - Evidence: https://go.dev/blog/go1.27 — "# The Go Blog

# Go 1.27 is released

Nicholas Husin, on behalf of the Go team  
 19 August 2026

Today the Go team is pleased to release Go 1.27. You can find its binary archives"
  - Evidence: https://endoflife.date/go — "| Release | Released | Supported | Latest |
 ---  --- |
| 1.27 | 2 months and 2 weeks ago (19 Aug 2026) | Yes | 1.27.3 (19 Oct 2026) |
| 1.26 | 8 months ago (10 Feb 2026) | Yes | 1"
  - Evidence: https://gosuda.org/blog/posts/go-1-27-or-how-i-learned-to-stop-worrying-and-love-generic-methods-za800e454 — "GoSuda

# Go 1.27, or How I Learned to Stop Worrying and Love Generic Methods

By iwanhae views ...

Go 1.27 lands in August 2026, and for once the language itself changed. Not "we"
- Extracted: "Go 1.27 was released in August 2026." [software_version], time-sensitive=False, p_outdated_model=0.02

### `c-django` — FP (flagged non-stale) — software_version
- Claim: The latest Django release is 6.1.2.
- Labelled truth: 6.1.2 (source: https://www.djangoproject.com/download)
- Outcome: **changed**
- Extracted: "The latest Django release is 6.1.2." [software_version], time-sensitive=True, p_outdated_model=0.85
  - Verdict changed; quote: "Django 6.1.3 fixes five security issues with severity “low”, one security issue with severity “moderate”, and several bugs in 6.1.2." (https://docs.djangoproject.com/en/6.1/releases/6.1.3); value: 6.1.3
  - Model reasoning: The evidence shows Django 6.1.3 was released on November 3, 2026, after 6.1.2 (October 6, 2026), so 6.1.2 is no longer the latest release. The latest version named in the evidence is 6.1.3.
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
  - Model reasoning: The claim describes the iPhone 17 Pro as using the A19 Pro, which was true at launch. The MacRumors evidence states that Apple's successor iPhone 18 Pro is built around the A20 Pro, and the CNET evidence says the iPhone Air uses the A19 Pro, the same chip as the iPhone 17 Pro, but does not state the
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
  - Verdict changed; quote: "iPhone Duo brings a foldable screen for people who want more room to work, watch, browse, or multitask." (https://www.t-mobile.com/dialed-in/devices/iphone-18-series-specs-features); value: iPhone Duo
  - Model reasoning: The evidence describes the iPhone Duo as Apple's first foldable iPhone, part of the 2026 lineup alongside the iPhone 18 Pro models. Sources present the iPhone 18 Pro and Pro Max as the Pro lineup, but the newest flagship in the evidence is the foldable iPhone Duo, so the claim no longer holds.
  - Evidence: https://www.macrumors.com/2026/09/12/iphone-18-pro-available-to-pre-order — "The ‌iPhone 18 Pro‌ and ‌iPhone 18 Pro‌ Max are Apple's latest flagship iPhones, featuring a new variable aperture Main camera, a faster A20 Pro chip, improved vapor chamber coolin"
  - Evidence: https://www.youtube.com/watch?v=Q3zwkxqh1t0 — "Posted: 2026-09-09
iPhone 18 Pro is Apple’s most powerful iPhone yet. It features the A20 Pro chip, which has exceptional AI capabilities and is cooled by a next-generation vapor c"
  - Evidence: https://www.apple.com/uk/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max — "CUPERTINO, CALIFORNIA Apple today announced iPhone 18 Pro and iPhone 18 Pro Max, delivering the most advanced pro camera system in an iPhone, and huge leaps in battery life and per"
- Extracted: "The iPhone 18 Pro and iPhone 18 Pro Max were launched in September 2026." [product_spec], time-sensitive=False, p_outdated_model=0.05
