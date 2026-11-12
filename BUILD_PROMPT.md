# Half-Life: end-to-end build prompt (task-graph edition)

Use: open Claude Code (Opus 5.5) in an empty git repo, save this file as `BUILD_PROMPT.md`, put `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` in `.env`, then say: "Read BUILD_PROMPT.md and run the graph from J0."

<situation>
I am a solo developer entering the Geek Room Global AI Hackathon 2026 (HackCulture). Prototype submissions close 15 Nov 2026 at 23:59 IST; judging is 29 Nov. You are the lead agent and will build the whole project, from an empty repo to a submission-ready one, by running the task graph below.

Judges score innovation, technical execution, problem and potential impact, use of AI, user experience, and scalability and potential. Engineers from Maxim AI (Bifrost) and Tavily are likely among them, so a wrong claim about either product or a number that cannot be reproduced costs more than a missing feature.

I work in Python, SQL and PostgreSQL and have an analytics background. I do not write Go. Use the stock Bifrost binary and its public extension points; do not build a Go plugin or a custom Bifrost.
</situation>

<official_requirements>
All submissions must meaningfully integrate both Tavily and Bifrost and show what each contributes. This project answers two statements with one integrated product.

Problem Statement 06, Tavily: Build a Stale-Answer Detector for AI Applications. Goal: accept an LLM-generated answer, detect potentially stale factual claims, re-verify them with live sources, and give a freshness score for each relevant claim.

* T1 Claim identification: find the time-sensitive factual statements in an AI-generated response.
* T2 Freshness detection: flag claims that could be outdated, including pricing, API versions, laws and leadership.
* T3 Live verification: re-check flagged claims against current web sources.
* T4 Freshness scoring: a freshness score for each relevant claim, based on the evidence.

Expected outcome: users can see which claims are outdated and which are supported by current sources.

Problem Statement 04, Bifrost contributor track: Build a Feature the Open-Source Gateway Is Missing. Goal: extend Bifrost with a practical feature that solves a real operational or developer problem and could be contributed upstream.

* B1 Real operator problem: name a meaningful missing capability and solve it end to end.
* B2 Public extension points: build on supported interfaces such as plugins, logging APIs, routing rules, or the MCP gateway.
* B3 Reproducible integration: works with a standard Bifrost installation, with clear setup instructions.
* B4 Contribution quality: tests, documentation, and a repository prepared for a potential upstream pull request.

The statement also says to check existing functionality before choosing a contribution.

Hackathon rules that bind the build: the core project is created during 1 to 15 Nov; AI tool use is disclosed in the submission; third-party code and data are used within their licences; one submission per team. A submission needs a working project or demo, source repository, project description, the problem being solved, technologies used, how AI is used, and a demo video if required.
</official_requirements>

<product>
Name: Half-Life. One line: "Facts decay. Half-Life tells an AI gateway which answers to re-check, and when."

The operator problem (B1). Bifrost reports cost, latency and errors for every virtual key, but nothing about whether what it served is still true. Checking every answer against the web costs two extra model calls, a search and several seconds, so nobody runs it on production traffic. The gateway's cache also uses one TTL for every answer, whether the question was the capital of France or the latest Python release.

The idea. Treat staleness as survival analysis.

1. Each time-sensitive claim gets a volatility class: software version, price, rate or statistic, office holder, law or regulation, product spec, or timeless.
2. Each class has a half-life h in days. For information that is `age` days old, P(stale) = 1 - 2^(-age/h). `age` is days since the answering model's knowledge cutoff for a fresh answer, days since cache write for a cached answer, or days since an explicit date in the claim.
3. Claims are verified with Tavily in order of P(stale), up to a verification budget.
4. Each outcome (changed or unchanged, at what age) goes into a fact ledger, and half-lives are re-fitted from it.
5. The same half-life gives a recommended cache TTL: the time at which P(stale) reaches a tolerance epsilon.

Fitting. Outcomes are interval-censored: we only know whether the fact changed within `age`. Per class, likelihood is the product of (1 - exp(-lambda*age)) over changed claims and exp(-lambda*age) over unchanged ones. Fit lambda by one-dimensional MAP with a Gamma prior centred on the class prior; h = ln(2)/lambda. Starting priors are my guesses and must be labelled as guesses everywhere: software version 120 d, price 240 d, rate or statistic 150 d, office holder 900 d, law or regulation 700 d, product spec 300 d.

Freshness score (T4), 0 to 100, shown per claim with its basis:

* verified current, backed by an authoritative source or two independent ones: 95
* verified current, one source: 80
* changed: 5, shown with the current value and sources
* searched but unverifiable: 100*(1 - P(stale)), capped at 50, labelled "unverified"
* not searched because it is under budget: 100*(1 - P(stale)), labelled "estimated"
* timeless claims are listed as not time-sensitive and get no score

The answer-level score is the mean over scored claims.

Two modes, one pipeline:

* Check mode (PS06): one answer in, every flagged claim verified, full report out.
* Gateway mode (PS04): reads real traffic from Bifrost's logging API, verifies only the riskiest slice under a budget, reports stale rate by model and virtual key, and sets a per-request cache TTL from the predicted half-life.
</product>

<ground_rules>
1. Verify before coding. My notes on Bifrost come from reading other people's repos, not from testing. J0 confirms each one against https://docs.getbifrost.ai/llms.txt and https://docs.tavily.com. If a mechanism does not exist, record it in STATE.md and use the nearest real one. Never invent an API. Unverified notes: start with `npx -y @maximhq/bifrost` on port 8080; models are `provider/model`; virtual keys go in `x-bf-vk`; the request body accepts `fallbacks`; management APIs under `/api/*` cover logs, governance, MCP and cache; caching is opt-in per request with `x-bf-cache-key` and `x-bf-cache-ttl`, and has an exact-match mode that needs no embedding provider.
2. Evidence only. A verdict rests only on text Tavily returned. The judge quotes its supporting span; code checks the quote is in the retrieved text, otherwise the verdict is `unverifiable`. Cited URLs not in the results are dropped. A corrected value appears only when the evidence states it.
3. Measured numbers only. Every figure in the README, interface and submission comes from a recorded run under `results/`. Where a run has not happened, write "not yet measured". Half-lives are fitted on the fit split and reported on the test split.
4. Fail open. A failed search, bad model output or timeout never breaks the user's answer; the report says what failed.
5. Zero spend beyond my credits. Runtime model: the cheapest current Claude Haiku through Bifrost's Anthropic provider (confirm the model ID in Anthropic's docs), with a free-tier model from a second provider as fallback if I supply a key, otherwise a second Claude model. Hard budget on the Bifrost virtual key: $10 for the whole build. Cache every Tavily response on disk by query and date; the free tier is 1,000 credits a month, basic search costs 1. Print model spend and Tavily credits used at the end of each eval run and keep a running total in STATE.md. Stop and tell me if either passes 70 percent.
6. Secrets live in `.env`, which is git-ignored from the first commit. Commit `.env.example`. Never print a key.
7. Stack: Python 3.11+, FastAPI, httpx, SQLite, scipy, pytest. Interface: one static page served by FastAPI, plain HTML and JS with a CDN chart library, no build step.
</ground_rules>

<graph_method>
This build follows task-graph rules. They are part of the instructions, not background.

* A node is one job. An edge exists only where a job reads another job's result. Nothing else is ordered; nodes with no edge between them run in parallel.
* Split only work whose pieces never read each other's results. Everything that needs the full picture stays with you, the lead, in one context.
* Verification happens in a separate context from the work it checks, and each verifier asks a different question.
* You own every merge. Workers never integrate each other's output.
* I approve only where a mistake is expensive to undo. There are three such gates; do not ask me for approval anywhere else.
* Guardrails: at most 4 subagents at once and 12 in total; every fix-and-reverify loop stops after 2 rounds and escalates to me with the evidence; one writer per file, as listed in each node; the routing is this file, so do not re-plan the graph, only fill the jobs. If a node proves impossible, record why in STATE.md and stop.

State. Keep `STATE.md` at the repo root and update it at the end of every node: Found (confirmed facts, with doc links), Decided (choices and why), Remains (open nodes), Spend (dollars and Tavily credits). Every subagent brief starts by pointing at STATE.md and `halflife/schemas.py`, because a subagent sees nothing of this conversation. Each brief also states the goal, the files it may write, what done looks like, and what to return: a short report that separates what it ran and observed from what it assumes.
</graph_method>

<task_graph>

```
J0 spike ── GATE 1 ── J1 contracts ──┬─ W1 extract ──┐
                                     ├─ W2 risk ─────┤
                                     ├─ W3 verify ───┤
                                     ├─ W4 ledger ───┼─ V1 V2 V3 ── M1 merge ── J2 gateway ──┐
                                     ├─ W5 cases ────┤      (GATE 2 on W5)                    ├─ J4 interface ── J5 package ── V4 ── GATE 3 ── J6 release
                                     └─ W6 ui shell ─┘                  M1 ── J3 evaluation ──┘
```

J0 Spike. Lead. Reads: nothing. Writes: `docs/SPIKE.md`, `scripts/spike.sh`, STATE.md. Read the docs per ground rule 1. Start stock Bifrost, add the Anthropic provider, create a virtual key with a budget, make one chat completion through it, read that request back from the logging API, send one request with the cache headers and observe a hit, and run one Tavily search. Also do the existing-functionality check: search Bifrost's docs and open issues for anything that already does freshness scoring or content-aware cache TTL. Done when: `scripts/spike.sh` reproduces every call, and SPIKE.md marks each mechanism confirmed (with link) or unavailable (with substitute).

GATE 1. Show me SPIKE.md in ten lines: what is confirmed, what is not, what overlaps with existing Bifrost features, and whether gateway mode is still feasible as designed. Wait for my go. This is the last cheap moment to change direction.

J1 Contracts. Lead. Reads: J0. Writes: `halflife/schemas.py`, `halflife/clients/` (Bifrost and Tavily clients, disk cache, fakes for tests), `tests/fixtures/report.json`, `Makefile`, `pyproject.toml`, `.gitignore`, `.env.example`. Define the typed records every other node shares: Claim (text, exact span, class, explicit date), RiskScore, Evidence, Verdict, ClaimReport, AnswerReport. Write one realistic fixture report covering every verdict type. `make dev` starts Bifrost and the API together. Done when: offline `pytest` passes with fake model and fake search, and the fixture validates against the schema.

Fan-out. Six workers run in parallel as subagents. None reads another's output; each reads only J1.

W1 Extract. Writes: `halflife/extract.py`, `tests/test_extract.py`. One model call returning claims as JSON. Each span must be a substring of the answer or the claim is discarded. Keep tense: "became CEO in 2021" is a dated past event, not a current claim. Classes must cover pricing, API or software versions, laws and leadership (T1, T2). Done when: tests pass on 15 hand-written answers, two of them with nothing time-sensitive.

W2 Risk. Writes: `halflife/risk.py`, `tests/test_risk.py`. Pure functions: P(stale), budget ordering, recommended TTL from epsilon, the freshness score table above. Done when: property tests pass (monotonic in age, timeless scores zero risk, TTL shrinks with half-life).

W3 Verify. Writes: `halflife/verify.py`, `tests/test_verify.py`. For one claim: two Tavily searches in parallel (open web with a recency filter, and the authoritative domain when the extractor names one), then one judge call under ground rule 2 (T3). Done when: tests cover the quote check, URL filtering, timeout and malformed-output paths.

W4 Ledger. Writes: `halflife/ledger.py`, `halflife/fit.py`, `tests/test_fit.py`. SQLite tables for claims, verifications and class parameters; the MAP fit; a command that re-fits and prints old against new half-lives. Done when: on synthetic data with a known half-life the fit recovers it within 15 percent at n=200.

W5 Cases. Writes: `eval/cases.jsonl`, `eval/README.md`. At least 120 single-claim cases: about 45 stale, 45 current, 30 timeless, across every class, including about 30 finance and regulation cases (policy rates, tax rates, payment limits, fees). Each has claim, class, as-of date, label, current truth, a source URL actually retrieved through Tavily, the supporting quote, and the date checked. No case without a retrieved source. Done when: the file validates and every case has a quote found in its cached source text.

W6 Interface shell. Writes: `web/index.html`, `web/app.js`, `web/style.css`. Built against `tests/fixtures/report.json` only. Three views. Check: paste an answer, see each claim with class, a decay bar for P(stale), verdict, freshness score with its basis, corrected value and source links, with evidence visually separate from the model's reasoning. Gateway: stale rate by model and virtual key, budget used, half-lives learned. Evidence: risk-coverage curve and summary table from `results/`. Done when: all three views render from fixtures with no console errors and show a clear state when data is missing.

Verification. Three fresh subagents, each given the worker outputs and one question. They report findings; they do not edit. V1 Is it correct? Run the tests, read W1 to W4 for logic errors, and try to break the quote check and the fit with adversarial inputs. V2 Is it current? Compare every Bifrost and Tavily call in `halflife/clients/` and W3 against the live docs and SPIKE.md; list any endpoint, header or field that does not match. V3 Is the source real? Sample 30 cases from W5 at random, re-fetch each source, and confirm the quote supports the stated truth and the label. Report the error rate.

GATE 2. Show me V3's error rate and 20 random cases to hand-check. Wait for my go. Every number we publish rests on these labels, so nothing is evaluated before I approve them. If V3 finds more than 10 percent wrong, W5 is redone once before you ask me.

M1 Merge. Lead. Reads: W1 to W4, V1, V2. Writes: `halflife/pipeline.py`, `halflife/api.py`, `tests/test_pipeline.py`. Fix what V1 and V2 found, then assemble extract, risk, verify and ledger into one pipeline with `POST /v1/check`. Check mode verifies every flagged claim. Done when: one real answer runs end to end through real Bifrost and Tavily and returns a valid AnswerReport.

J2 and J3 both read M1 and not each other; run J3's long eval in the background while you build J2.

J2 Gateway mode. Lead. Reads: M1. Writes: `halflife/gateway/audit.py`, `halflife/gateway/proxy.py`, `halflife/gateway/mcp_server.py`, `tests/test_gateway.py`. (a) Audit job: pull recent requests from Bifrost's logging API, score them, verify the riskiest slice under a budget, store stale rate by model and virtual key. (b) Pass-through proxy for chat completions that forwards to Bifrost, adds the cache key and predicted TTL, and attaches the freshness report without delaying the answer. (c) A `check_freshness` tool exposed as an MCP server and registered in Bifrost's MCP gateway. Done when: an end-to-end test against local Bifrost sends ten mixed questions through the proxy, runs the audit, and the stored stale rate matches the per-answer reports. If time is short, cut (c) first, then (b); never (a).

J3 Evaluation. Lead. Reads: M1, W5 after Gate 2. Writes: `eval/run.py`, `results/<date>/`. Split cases 50/50 into fit and test. Fit half-lives on the fit split. On the test split report: detector precision and recall with everything verified; the risk-coverage curve (share of stale claims caught against share of claims verified) for Half-Life ordering, random ordering, and the model's own time-sensitivity rating; model cost, Tavily credits and latency per answer at 25, 50 and 100 percent verification. Done when: `make eval` regenerates the table and curve from cached evidence with no new credits. If Half-Life ordering does not beat random on the test split, write that down plainly in `results/` and STATE.md and carry on: the product then leads with check mode and the gateway audit, and the README reports the negative result.

J4 Interface wiring. Lead. Reads: W6, J2, J3. Writes: `web/` (ownership passes from W6 to you). Connect the three views to the live API and to `results/`. Done when: the demo path works in a browser: one stale answer caught with sources, one timeless answer skipped at no cost, the curve, the gateway view, and failover when the primary model is disabled.

J5 Package. Lead. Reads: everything. Writes: `README.md`, `docs/UPSTREAM.md`, `CONTRIBUTING.md`, `LICENSE`, `.github/workflows/ci.yml`, `Dockerfile`, `SUBMISSION.md`, `docs/DEMO_SCRIPT.md`. README: the problem; a table mapping T1 to T4 and B1 to B4 to the code that satisfies each; what Bifrost contributes and what Tavily contributes; an "existing functionality" section from J0; architecture diagram in Mermaid; quickstart from a clean clone on a standard Bifrost install; results with honest limits (small hand-labelled set, exponential decay is a simplification, priors were guesses, latency depends on the provider); AI-usage disclosure (built with Claude Code; Claude Haiku runs inside the product). UPSTREAM.md: the proposal as it would be filed with Bifrost's maintainers. Licence matching Bifrost's. CI runs the offline tests. Dockerfile runs the API and the Bifrost binary together with a per-minute cap for a public demo. SUBMISSION.md: the fields the form needs. DEMO_SCRIPT.md: a two-minute recording script following J4's demo path.

V4 Fresh-eyes check. One fresh subagent, given only the repo. It clones to a temp directory, follows the quickstart exactly, and reports where it got stuck, plus every README number it could not trace to a file in `results/`. Done when: quickstart reaches a working check in under five minutes and every number traces. Fix and re-check, two rounds at most.

GATE 3. Show me the final status, total spend, and the exact commands you will run. Wait for my go before anything leaves my machine: `git push`, deployment, or filing the upstream issue.

J6 Release. Lead. Reads: Gate 3. Push to my GitHub repo, deploy the container to a free tier if I approve it, and give me the links for the submission form. Recording the video and submitting the form are mine.
</task_graph>

<if_time_runs_short>
Order of cuts, decided now so you do not have to ask: J2(c), J2(b), the finance slice of W5 (keep 90 cases), deployment. Never cut J3, the requirements table, or V4. By Sunday 15 Nov, 14:00 IST the graph should be at J5 at the latest; if it is not, apply the cuts and tell me which.
</if_time_runs_short>

<reporting>
After each node, three lines: what now works, what the done-check showed (the command and its result), what runs next. At a gate, the summary described in that gate, then stop. If something fails and you could not fix it within the loop cap, show me the error and the doc line it contradicts rather than working around it.
</reporting>
