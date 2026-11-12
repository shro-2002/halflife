# Detector errors — eval date 2026-11-12

Confusion (rows = label, columns = detector outcome; a case is flagged if any claim is `changed`):

| label | changed | current | unverifiable | not searched |
|---|---|---|---|---|
| stale | 35 | 1 | 2 | 0 |
| current | 6 | 25 | 5 | 9 |
| timeless | 0 | 0 | 0 | 25 |

Precision 0.854, recall 0.921 on 83 time-sensitive cases.

## 9 wrong verdicts (missed stale = FN incl. unverifiable/not searched; flagged non-stale = FP)

### `s-boe-rate` — FN (missed stale) — rate_or_statistic
- Claim: The Bank of England's Bank Rate is 3.75%.
- Labelled truth: 4% (raised, published 5 Nov 2026) (source: https://www.bankofengland.co.uk/monetary-policy/the-interest-rate-bank-rate)
- Outcome: **current**
- Extracted: "The Bank of England's Bank Rate is 3.75%." [rate_or_statistic], time-sensitive=True, p_outdated_model=0.5
  - Verdict current; quote: "voted by a majority of 6–3 to maintain Bank Rate at 3.75%" (https://www.bankofengland.co.uk/monetary-policy-summary-and-minutes/2026/september-2026); value: None
  - Model reasoning: The Bank of England's September 2026 minutes state Bank Rate was maintained at 3.75%, and a later-dated secondary source confirms the current rate is 3.75%. No evidence shows a subsequent change, though the November 2026 decision is not yet covered by the evidence.
  - Evidence: https://getsmartsaver.co.uk/bank-of-england-july-2026-rate-decision — "The Bank of England’s Bank Rate is currently 3.75 per cent, held at the June 2026 meeting, and the next decision lands at noon on 30 July 2026. The most likely outcome is another h"
  - Evidence: https://advaithhomes.co.uk/news/bank-of-england-interest-rate-held-at-3-75-september-2026 — "The Bank of England has kept Bank Rate unchanged at 3.75% following its latest Monetary Policy Committee meeting, with the decision published on 17 September 2026. The Monetary Pol"
  - Evidence: https://cambridgecurrencies.com/next-bank-of-england-interest-rate-decision-date — "•

9–13 minutes

Direct answer: The Bank of England held Bank Rate at 3.75% on Thursday 17 September 2026 in a 6–3 vote, with three members voting for a rise to 4%. The current UK"

### `s-401k` — FN (missed stale) — law_or_regulation
- Claim: The annual 401(k) employee elective deferral limit is $23,500.
- Labelled truth: $24,500 for 2026 (source: https://www.irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500)
- Outcome: **unverifiable**
- Extracted: "The annual 401(k) employee elective deferral limit is $23,500." [law_or_regulation], time-sensitive=True, p_outdated_model=0.35
  - Verdict unverifiable; quote: "" (None); value: None
  - Model reasoning: The claim's $23,500 figure was the 2025 limit; the IRS states the 2026 limit is $24,500. Today's date falls in 2026, so the claim is outdated.
  - Evidence: https://www.empower.com/the-currency/work/401k-contribution-limits — "For 2026, the employee 401(k) elective deferral limit is $24,500 (up from $23,500 in 2025). Catch-up contributions are generally capped at $8,000 for people age 50 or older, while"
  - Evidence: https://roistreet.com/learn/what-is-the-401k-elective-deferral-limit — "The regular 2026 employee elective-deferral ceiling is $24,500.(#source-1)(#source-2)(#source-3)
 Traditional pre-tax and designated Roth 401(k) deferrals share that one basic limi"
  - Evidence: https://blog.surgentcpe.com/401k-planning-2026-contribution-limits-rules — "### SIMPLE 401(k)

Available to employers with 100 or fewer employees who received at least $5,000 in compensation in the prior year. The elective deferral limit for SIMPLE 401(k)"

### `s-lu-grandduke` — FN (missed stale) — office_holder
- Claim: Henri is the Grand Duke of Luxembourg.
- Labelled truth: Guillaume V (since 3 October 2025) (source: https://en.wikipedia.org/wiki/Guillaume_V_of_Luxembourg)
- Outcome: **unverifiable**
- Extracted: "Henri is the Grand Duke of Luxembourg." [office_holder], time-sensitive=True, p_outdated_model=0.03
  - Verdict unverifiable; quote: "" (None); value: None
  - Model reasoning: The evidence states Henri abdicated on 3 October 2025 in favour of his son Guillaume, who is now Grand Duke. Henri is therefore a former sovereign and no longer Grand Duke.
  - Evidence: https://en.wikipedia.org/wiki/Guillaume_V_of_Luxembourg — "| Guillaume in 2026 |
| Grand Duke of Luxembourg |
| Reign | 3 October 2025 – present |
| Enthronement | 3 October 2025 |
| Predecessor | Henri |
| Heir apparent | Charles "Prince"
  - Evidence: https://washington.mae.lu/en/actualites/2026/20260922-grand-duke-guillaume-addresses-the-un-general-assembly.html — "On 22 September 2026, HRH Grand Duke Guillaume delivered his first official address to the United Nations General Assembly since ascending to the throne in October 2025, following"
  - Evidence: https://linkedin.com/in/polhenrilebrun — "# Pol-henri Lebrun [...] ## Experience
- Head of Financial Operations Luxembourg at CBRE Investment Management (May 2026 to present)
- Principal at Henderson Park (Apr 2025 to May"

### `c-au-super` — FP (flagged non-stale) — law_or_regulation
- Claim: The Australian superannuation guarantee rate is 12% of ordinary time earnings.
- Labelled truth: 12% (source: https://www.ato.gov.au/businesses-and-organisations/super-for-employers/quarterly-super-to-30-june-2026/how-much-super-to-pay)
- Outcome: **changed**
- Extracted: "The Australian superannuation guarantee rate is 12% of ordinary time earnings." [law_or_regulation], time-sensitive=True, p_outdated_model=0.1
  - Verdict changed; quote: "From 1 July 2026 onwards, your employer will calculate your SG amount as 12% of your ‘qualifying earnings.'" (https://www.australianretirementtrust.com.au/learn/superannuation/super-guarantee-rate-increase); value: None
  - Model reasoning: The rate is still 12%, but since 1 July 2026 it applies to qualifying earnings rather than ordinary time earnings, which the claim names. The claim's base is therefore outdated.
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
  - Model reasoning: As of today (2026-11-12), the ECB's own 29 October 2026 release says Lagarde will step down on 7 February 2027, so she is still president now but the claim's ongoing status is changing. The claim as stated (she is ECB President) remains true until that date, but the evidence signals an impending cha
  - Evidence: https://linkedin.com/in/christine-lagarde-b45417137 — "# Christine Lagarde
President of the European Central Bank
Frankfurt, Hesse, Germany, DE  
2 connections, 3199503 followers [...] the first woman to hold that position<br><br> In F"
  - Evidence: https://www.instagram.com/reel/DfEwIBAIbJ5?hl=en — "on October 29, 2026. May be an image of one or more people, people studying, office and text.

Image 23: Photo by Christine Lagarde on October 27, 2026. May be an image of suit, di"
  - Evidence: https://www.ecb.europa.eu/press/pr/date/2026/html/ecb.pr261029~abbb6dc64b.en.html — "In-depth studies and expert analyses covering diverse topics and fields

# ECB President Lagarde to step down on 7 February 2027

29 October 2026

European Central Bank President C"

### `c-django` — FP (flagged non-stale) — software_version
- Claim: The latest Django release is 6.1.2.
- Labelled truth: 6.1.2 (source: https://www.djangoproject.com/download)
- Outcome: **changed**
- Extracted: "The latest Django release is 6.1.2." [software_version], time-sensitive=True, p_outdated_model=0.6
  - Verdict changed; quote: "Django 6.1.3 fixes five security issues with severity “low”, one security issue with severity “moderate”, and several bugs in 6.1.2." (https://docs.djangoproject.com/en/6.1/releases/6.1.3); value: 6.1.3
  - Model reasoning: A Django 6.1.3 release dated November 3, 2026 is documented, which is before today (2026-11-12), so 6.1.2 is no longer the latest release. The forum listing also shows security releases for 6.1.3 posted November 4, 2026.
  - Evidence: https://django.readthedocs.io/en/stable/releases/1.4.17.html — "Title: Django 1.4.17 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 1.4.17 release notes¶. Django 1.4"
  - Evidence: https://django.readthedocs.io/en/stable/releases/4.1.8.html — "Title: Django 4.1.8 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 4.1.8 release notes¶. Django 4.1.8"
  - Evidence: https://django.readthedocs.io/en/stable/releases/5.1.2.html — "Title: Django 5.1.2 release notes — Django 6.1.2 documentation
# Django 6.1.2 documentation. Home | Table of contents | Index | Modules. # Django 5.1.2 release notes¶. Django 5.1.2"

### `c-ubuntu-lts` — FP (flagged non-stale) — software_version
- Claim: The latest Ubuntu LTS release is Ubuntu 26.04 "Resolute Raccoon".
- Labelled truth: Ubuntu 26.04 LTS (source: https://discourse.ubuntu.com/t/ubuntu-26-04-1-lts-released/86808)
- Outcome: **changed**
- Extracted: "The latest Ubuntu LTS release is Ubuntu 26.04 "Resolute Raccoon"." [software_version], time-sensitive=True, p_outdated_model=0.1
  - Verdict changed; quote: "Ubuntu 26.04.1 LTS, codenamed “Resolute Raccoon”, is here." (https://discourse.ubuntu.com/t/ubuntu-26-04-1-lts-released/86808); value: Ubuntu 26.04.1 LTS
  - Model reasoning: The claim names Ubuntu 26.04 as the latest LTS, but the evidence shows a later point release, 26.04.1 LTS, published 27 Aug 2026 and still the same codename. Since the claim is about the release version and the evidence gives a newer version string, it is marked changed.
  - Evidence: https://canonical.com/blog/canonical-releases-ubuntu-26-04-lts-resolute-raccoon — "# Canonical releases Ubuntu 26.04 LTS Resolute Raccoon

Ubuntu 26.04 LTS   Ubuntu Desktop   Ubuntu Server

#### The 11th long-term supported release of Ubuntu delivers deep silicon"
  - Evidence: https://linuxcommunity.io/t/ubuntu-26-04-lts-resolute-raccoon-and-most-of-its-flavors-released-yesterday-23rd-april-2026/7057 — "The Ubuntu Studio team is pleased to announce Ubuntu Studio 26.04 LTS, code-named “Resolute Raccoon.” This marks Ubuntu Studio’s 38th release. This Long-Term Support (LTS) release"
  - Evidence: https://9to5linux.com/ubuntu-26-04-lts-resolute-raccoon-is-now-available-for-download — "Ubuntu maker Canonical released today Ubuntu 26.04 LTS (Resolute Raccoon) as the latest stable version of this popular distribution that features some of the latest GNU/Linux techn"

### `c-iphone17pro-chip` — FP (flagged non-stale) — product_spec
- Claim: The iPhone 17 Pro uses the A19 Pro chip.
- Labelled truth: A19 Pro (source: https://support.apple.com/en-us/125090)
- Outcome: **changed**
- Extracted: "The iPhone 17 Pro uses the A19 Pro chip." [product_spec], time-sensitive=True, p_outdated_model=0.05
  - Verdict changed; quote: "The new models are built around the A20 Pro chip" (https://www.macrumors.com/guide/iphone-17-pro-vs-18-pro); value: A20 Pro
  - Model reasoning: The claim that the iPhone 17 Pro uses the A19 Pro is historically accurate, but the claim is about current status and newer evidence says Apple has succeeded the iPhone 17 Pro with the iPhone 18 Pro built around the A20 Pro. The MacRumors item states the iPhone 17 Pro launched last September and the
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
- Extracted: "Apple's newest flagship iPhones are the iPhone 18 Pro and iPhone 18 Pro Max." [product_spec], time-sensitive=True, p_outdated_model=0.6
  - Verdict changed; quote: "The lineup includes iPhone 18 Pro, iPhone 18 Pro Max, and iPhone Duo - Apple's first foldable iPhone." (https://www.t-mobile.com/dialed-in/devices/iphone-18-series-specs-features); value: iPhone Duo
  - Model reasoning: The evidence shows Apple launched a third model, the foldable iPhone Duo, alongside the 18 Pro and 18 Pro Max, and describes the iPhone 18 Pro models as the 'Pro' family rather than the newest flagship. The claim that the 18 Pro and 18 Pro Max are the newest flagships is therefore superseded by the 
  - Evidence: https://www.macrumors.com/2026/09/12/iphone-18-pro-available-to-pre-order — "The ‌iPhone 18 Pro‌ and ‌iPhone 18 Pro‌ Max are Apple's latest flagship iPhones, featuring a new variable aperture Main camera, a faster A20 Pro chip, improved vapor chamber coolin"
  - Evidence: https://www.youtube.com/watch?v=Q3zwkxqh1t0 — "Posted: 2026-09-09
iPhone 18 Pro is Apple’s most powerful iPhone yet. It features the A20 Pro chip, which has exceptional AI capabilities and is cooled by a next-generation vapor c"
  - Evidence: https://www.apple.com/uk/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max — "CUPERTINO, CALIFORNIA Apple today announced iPhone 18 Pro and iPhone 18 Pro Max, delivering the most advanced pro camera system in an iPhone, and huge leaps in battery life and per"
- Extracted: "The iPhone 18 Pro and iPhone 18 Pro Max were launched in September 2026." [product_spec], time-sensitive=False, p_outdated_model=0.02
