"use strict";

// Live API by default; `?fixtures=1` renders checked-in samples for offline demos.
const DATA_SOURCE = new URLSearchParams(location.search).has("fixtures") ? "fixture" : "api";

// Absolute paths: the page is served at "/" and at "/web/index.html".
const ENDPOINTS = {
  fixture: { check: "/fixtures/report.json", gateway: "/fixtures/gateway.json" },
  api: { check: "/v1/check", gateway: "/v1/gateway/summary" },
};
const HEALTH_URL = "/health";
const DETECTOR_DIR = "/results/2026-11-12-detector";
const ORDERING_DIR = "/results/2026-11-12-ordering";
const RESULTS = {
  detectorSummary: `${DETECTOR_DIR}/summary.json`,
  detectorCurves: `${DETECTOR_DIR}/curves.json`,
  orderingSummary: `${ORDERING_DIR}/summary.json`,
  orderingCurves: `${ORDERING_DIR}/curves.json`,
  orderingHeadline: `${ORDERING_DIR}/headline.json`,
};

const TTL_EPSILON = 0.05;
const TABS = ["gateway", "check", "evidence"];
const DEMO_KEY_PREFIX = "demo-";

const EXAMPLES = {
  stale: "The Bank of Canada policy interest rate is 2.25%. Justin Trudeau is the Prime Minister of Canada.",
  timeless: "Water boils at 100 degrees Celsius at sea level, and the speed of light is about 299,792 km/s.",
  mixed: "Satya Nadella is the CEO of Microsoft. A Netflix Standard plan costs $15.49 per month.",
};

const SCORE_BASIS = {
  verified_current_authoritative: "Verified current, authoritative source",
  verified_current_single_source: "Verified current, single source",
  changed: "Changed: evidence states a newer value",
  unverified: "Searched, not confirmed (capped at 50)",
  estimated: "Estimated from P(stale), not searched (over budget)",
  not_time_sensitive: "Not time-sensitive: no score",
};
const RANK_BASIS = {
  model_p: "model's P(outdated)",
  half_life: "half-life model (fallback)",
};
const METHODS = {
  model_p: "Model P(outdated)",
  halflife: "Half-life model",
  half_life: "Half-life model",
  model_ts: "Model time-sensitivity",
  class_only: "Class only",
  age_only: "Age only",
  random: "Random",
  oracle_upper_bound: "Oracle (upper bound)",
};
const METHOD_STYLE = {
  model_p: { color: "--accent", width: 3 },
  halflife: { color: "--info", width: 3 },
  half_life: { color: "--info", width: 3 },
  model_ts: { color: "--warn", width: 2 },
  class_only: { color: "--ok", width: 2 },
  age_only: { color: "--neutral", width: 2 },
  random: { color: "--ink-2", width: 1.5, dash: [4, 4] },
  oracle_upper_bound: { color: "--ok", width: 1.5, dash: [2, 3] },
};

const charts = {};
const loaded = {};
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- DOM helpers (never innerHTML: answers and evidence are untrusted) ----------

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") Object.assign(el.style, value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function safeLink(url, label) {
  let parsed = null;
  try { parsed = new URL(url, location.origin); } catch (_) { parsed = null; }
  if (!parsed || !["http:", "https:"].includes(parsed.protocol)) return h("span", { class: "muted" }, label || String(url));
  return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer" }, label || parsed.href);
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return String(url); }
}

function stateBox(kind, title, ...lines) {
  return h("div", { class: `state ${kind}`, role: kind === "error" ? "alert" : null },
    h("h3", null, title), ...lines.map((line) => (line instanceof Node ? line : h("p", null, line))));
}

// Traffic-wide estimate from the stratified random sample: "12.3% [5.0–20.1%]", unverifiable bounds on hover.
function estText(e) {
  if (!e || e.est_stale_rate === null || e.est_stale_rate === undefined) return "not estimated";
  const ci = e.est_ci95 ? ` [${fmt.pct(e.est_ci95[0], 0)}–${fmt.pct(e.est_ci95[1], 0)}]` : "";
  const b = e.est_bounds_unverifiable ? `; unverifiable as current/stale: ${fmt.pct(e.est_bounds_unverifiable[0], 0)}–${fmt.pct(e.est_bounds_unverifiable[1], 0)}` : "";
  return h("span", { title: `n sampled = ${e.est_n_sampled}${b}` }, `${fmt.pct(e.est_stale_rate, 1)}${ci}`, e.est_n_sampled < 60 ? h("span", { class: "muted" }, ` (n=${e.est_n_sampled}, wide)`) : null);
}

function errorList(title, errors) {
  if (!errors || !errors.length) return null;
  return h("div", { class: "errors" }, h("p", null, h("strong", null, title)),
    h("ul", null, errors.map((e) => h("li", null, String(e)))));
}

const isNil = (x) => x === null || x === undefined;
const fmt = {
  pct: (x, d = 0) => (isNil(x) ? "—" : `${(x * 100).toFixed(d)}%`),
  num: (x, d = 0) => (isNil(x) ? "—" : Number(x).toFixed(d)),
  usd: (x) => (isNil(x) ? "—" : `$${Number(x).toFixed(4)}`),
  ms: (x) => (!x ? "—" : x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${Math.round(x)} ms`),
  days: (x) => (isNil(x) ? "—" : `${Number(x).toFixed(x < 10 ? 1 : 0)} d`),
  ci: (ci) => (Array.isArray(ci) && ci.length === 2 ? `[${fmt.pct(ci[0])}, ${fmt.pct(ci[1])}]` : ""),
  when: (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso ?? "—") : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
  },
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const stat = (label, value, note) => h("div", { class: "stat" }, h("dt", null, label), h("dd", null, value),
  note ? h("dd", { class: "stat-note" }, note) : null);

// ---------- data access ----------

class FetchError extends Error {
  constructor(message, { status = null, code = null, network = false } = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.network = network;
  }
}

function detailOf(body) {
  const detail = body && body.detail;
  if (!detail) return {};
  if (typeof detail === "string") return { message: detail };
  if (Array.isArray(detail)) return { code: "VALIDATION_ERROR", message: detail.map((d) => d.msg || String(d)).join("; ") };
  return { code: detail.code || null, message: detail.message || null };
}

async function getJSON(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    throw new FetchError(`Could not reach ${url} (${err.message}).`, { network: true });
  }
  let body = null;
  try { body = await res.json(); } catch (_) { body = null; }
  if (!res.ok) {
    const { code, message } = detailOf(body);
    throw new FetchError(message || `${url} returned HTTP ${res.status}.`, { status: res.status, code });
  }
  if (body === null) throw new FetchError(`${url} did not return valid JSON.`);
  return body;
}

function runCheck({ answer, asOf, budget, simulateDown }) {
  if (DATA_SOURCE === "fixture") return getJSON(ENDPOINTS.fixture.check);
  const body = { answer, simulate_primary_down: simulateDown };
  if (asOf) body.as_of = asOf;
  if (budget !== null) body.budget = budget;
  return getJSON(ENDPOINTS.api.check, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------- header status ----------

async function loadHealth() {
  const pill = document.getElementById("health-pill");
  try {
    const health = await getJSON(HEALTH_URL);
    const bifrost = health && health.checks ? health.checks.bifrost : null;
    const ok = bifrost === "ok";
    pill.textContent = ok ? "Bifrost ok" : "Bifrost unreachable";
    pill.title = ok ? "Gateway answered /health" : String(bifrost || "no status");
    pill.className = `pill ${ok ? "ok" : "bad"}`;
  } catch (err) {
    pill.textContent = "API unreachable";
    pill.title = err.message;
    pill.className = "pill bad";
  }
}

// ---------- tabs ----------

function selectTab(name, { focus = false } = {}) {
  const active = TABS.includes(name) ? name : TABS[0];
  for (const tab of TABS) {
    const isActive = tab === active;
    const button = document.getElementById(`tab-${tab}`);
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
    document.getElementById(`panel-${tab}`).hidden = !isActive;
  }
  if (focus) document.getElementById(`tab-${active}`).focus();
  if (location.hash.slice(1) !== active) history.replaceState(null, "", `${location.search}#${active}`);
  if (active === "gateway" && !loaded.gateway) loadGateway();
  if (active === "evidence" && !loaded.evidence) loadEvidence();
}

function initTabs() {
  const list = document.querySelector('[role="tablist"]');
  list.addEventListener("click", (e) => {
    const tab = e.target.closest('[role="tab"]');
    if (tab) selectTab(tab.id.replace("tab-", ""));
  });
  list.addEventListener("keydown", (e) => {
    const current = TABS.indexOf(document.activeElement.id.replace("tab-", ""));
    if (current < 0) return;
    const moves = { ArrowRight: 1, ArrowLeft: -1, Home: -current, End: TABS.length - 1 - current };
    if (!(e.key in moves)) return;
    e.preventDefault();
    selectTab(TABS[(current + moves[e.key] + TABS.length) % TABS.length], { focus: true });
  });
  window.addEventListener("hashchange", () => selectTab(location.hash.slice(1)));
  selectTab(location.hash.slice(1));
}

// ---------- Check view ----------

function verdictInfo(report) {
  if (report.verdict) return { key: report.verdict.label, text: report.verdict.label };
  if (report.score_basis === "not_time_sensitive") return { key: "not-time-sensitive", text: "skipped: not time-sensitive" };
  return { key: "not-searched", text: "not searched" };
}

function markClass(info) {
  return ["changed", "current", "unverifiable"].includes(info.key) ? `v-${info.key}` : "v-other";
}

function annotatedAnswer(answer, claims) {
  const ranges = [];
  claims.forEach((report, i) => {
    const span = report.claim && report.claim.span;
    if (!span) return;
    let start = answer.indexOf(span);
    // skip occurrences already taken by an earlier claim with the same span
    while (start >= 0 && ranges.some((r) => start < r.end && start + span.length > r.start)) {
      start = answer.indexOf(span, start + 1);
    }
    if (start >= 0) ranges.push({ start, end: start + span.length, index: i, info: verdictInfo(report) });
  });
  ranges.sort((a, b) => a.start - b.start);

  const block = h("p", { class: "answer-text" });
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue;
    block.append(answer.slice(cursor, r.start));
    block.append(h("mark", { class: markClass(r.info), title: `Claim ${r.index + 1}: ${r.info.text}` },
      answer.slice(r.start, r.end), h("sup", null, String(r.index + 1))));
    cursor = r.end;
  }
  block.append(answer.slice(cursor));
  return { block, unmatched: claims.length - ranges.length };
}

function legend() {
  const item = (cssName, text) => h("li", null,
    h("span", { class: "sw", "aria-hidden": "true", style: { background: `var(${cssName})` } }), text);
  return h("ul", { class: "legend", "aria-label": "Highlight legend" },
    item("--mark-changed", "changed"), item("--mark-current", "current"), item("--mark-unverifiable", "unverifiable"),
    item("--mark-other", "not searched / not time-sensitive"));
}

function servedByBadges(usage) {
  const models = Array.isArray(usage.models_used) ? usage.models_used : [];
  const badges = [];
  if (usage.fallback_used) {
    badges.push(h("span", { class: "badge failover" }, `FAILOVER: served by ${models.join(", ") || "fallback model"}`));
  }
  return h("div", { class: "served-by" },
    h("span", { class: "kicker" }, "Models that served this check"),
    h("div", { class: "badges" }, ...badges,
      models.length ? models.map((m) => h("span", { class: "badge class" }, m)) : h("span", { class: "muted" }, "not reported")));
}

function searchSpendNote(report) {
  const usage = report.usage || {};
  const claims = report.claims || [];
  if ((usage.tavily_calls || 0) > 0 || usage.tavily_credits > 0) return null;
  const allTimeless = claims.length > 0 && claims.every((c) => c.score_basis === "not_time_sensitive");
  const why = allTimeless || !claims.length ? "not time-sensitive" : "no claim needed a search within the budget";
  return h("div", { class: "skip-note", role: "status" },
    h("strong", null, `Skipped — ${why}.`),
    ` 0 searches, ${fmt.num(usage.tavily_credits || 0)} Tavily credits. Only the extraction call ran.`);
}

function summaryStrip(report) {
  const usage = report.usage || {};
  const score = report.answer_score;
  const claims = report.claims || [];
  const budget = isNil(report.verification_budget) ? "" : ` / budget ${report.verification_budget}`;
  return h("div", { class: "summary" },
    h("div", { class: "score-plate" },
      h("div", { class: "kicker" }, "Answer freshness"),
      h("div", { class: "big" }, isNil(score) ? "—" : fmt.num(score)),
      h("div", { class: "of" }, isNil(score) ? "no time-sensitive claims scored" : "of 100, mean of scored claims")),
    h("dl", { class: "stats" },
      stat("Claims", String(claims.length)),
      stat("Searched", `${claims.filter((c) => c.searched).length}${budget}`),
      stat("Model calls", fmt.num(usage.model_calls)),
      stat("Model cost", fmt.usd(usage.model_cost_usd), "estimated from tokens at list price"),
      stat("Tavily searches", fmt.num(usage.tavily_calls)),
      stat("Tavily credits", fmt.num(usage.tavily_credits)),
      stat("Cache hits", fmt.num(usage.tavily_cache_hits)),
      stat("Latency", fmt.ms(usage.latency_ms))));
}

function decayBar(risk) {
  const p = Math.min(1, Math.max(0, Number(risk.p_stale) || 0));
  const fill = h("span", { style: { width: `${p * 100}%` } });
  if (p > 0) fill.style.setProperty("--full", `${100 / p}%`);
  const hl = isNil(risk.half_life_days)
    ? "no half-life (timeless)"
    : `h = ${fmt.days(risk.half_life_days)} (${risk.half_life_source === "fitted" ? "fitted" : "prior guess"}), age ${fmt.days(risk.age_days)} via ${String(risk.age_basis || "").replace(/_/g, " ")}`;
  return h("div", { class: "metric" },
    h("span", { class: "kicker" }, "P(stale), half-life model"),
    h("div", { class: "decay", role: "img", "aria-label": `P(stale) ${fmt.pct(p)}` }, fill),
    h("div", { class: "decay-caption" }, `${fmt.pct(p)} · ${hl}`));
}

function freshnessBlock(report) {
  const score = report.freshness_score;
  let tone = "none";
  if (!isNil(score)) tone = score >= 80 ? "hi" : score >= 40 ? "mid" : "lo";
  return h("div", { class: "metric" },
    h("span", { class: "kicker" }, "Freshness score"),
    h("div", { class: "fresh" },
      h("span", { class: `num ${tone}` }, isNil(score) ? "no score" : fmt.num(score)),
      h("span", { class: "basis" }, SCORE_BASIS[report.score_basis] || report.score_basis || "")));
}

function evidenceBlock(report) {
  const verdict = report.verdict;
  const items = report.evidence || [];
  if (!items.length && !(verdict && verdict.supporting_quote)) {
    if (!report.searched) return null;
    return h("div", { class: "evidence" }, h("span", { class: "kicker" }, "Evidence"),
      h("p", { class: "muted" }, "Search returned no usable results."));
  }
  const box = h("div", { class: "evidence", "aria-label": "Search evidence" }, h("span", { class: "kicker" }, "Evidence (verbatim from search)"));
  if (verdict && verdict.supporting_quote) {
    box.append(h("blockquote", null, verdict.supporting_quote));
    box.append(h("div", { class: "ev-meta" },
      h("span", { class: `flag ${verdict.quote_verified ? "qv" : "qx"}` }, verdict.quote_verified ? "quote found in evidence" : "quote not verified"),
      " ", verdict.supporting_url ? safeLink(verdict.supporting_url, domainOf(verdict.supporting_url)) : null));
  }
  if (items.length) {
    box.append(h("ul", { class: "ev-list" }, items.map((ev) => h("li", { class: "ev-item" },
      h("div", { class: "ev-meta" },
        h("span", { class: "domain" }, domainOf(ev.url)),
        h("span", { class: `flag ${ev.is_authoritative ? "auth" : "nonauth"}` }, ev.is_authoritative ? "authoritative" : "not authoritative"),
        ev.published_date ? h("span", { class: "muted" }, `published ${ev.published_date}`) : null),
      ev.content ? h("p", { class: "snippet" }, ev.content) : null,
      h("div", null, safeLink(ev.url)),
      ev.query ? h("div", { class: "muted" }, `query: ${ev.query}`) : null))));
  }
  return box;
}

function claimCard(report, index) {
  const claim = report.claim || {};
  const risk = report.risk || {};
  const info = verdictInfo(report);
  const verdict = report.verdict;
  const sources = verdict && verdict.source_urls ? verdict.source_urls : [];
  const timeless = report.score_basis === "not_time_sensitive";

  return h("li", { class: `claim${timeless ? " claim-skipped" : ""}`, id: `claim-${claim.id || index}`, "aria-label": `Claim ${index + 1}` },
    h("div", { class: "claim-head" },
      h("span", { class: "claim-num", "aria-hidden": "true" }, String(index + 1)),
      h("div", { style: { flex: "1", minWidth: "0" } },
        h("h3", { class: "claim-text" }, claim.text || claim.span || "(claim text missing)"),
        h("div", { class: "badges" },
          h("span", { class: "badge class" }, String(claim.volatility_class || "unknown class").replace(/_/g, " ")),
          h("span", { class: `badge ${info.key}` }, info.text),
          claim.is_past_event ? h("span", { class: "badge class" }, "past event") : null,
          claim.explicit_date ? h("span", { class: "badge class" }, `as of ${claim.explicit_date}`) : null))),
    timeless
      ? h("p", { class: "hint" }, "Skipped — not time-sensitive. No search, no credits, no score.")
      : h("div", { class: "claim-grid" },
        decayBar(risk),
        freshnessBlock(report),
        h("div", { class: "metric" },
          h("span", { class: "kicker" }, "Verification rank"),
          h("div", { class: "decay-caption" },
            `rank score ${fmt.num(risk.rank_score, 2)} · from ${RANK_BASIS[risk.rank_basis] || risk.rank_basis || "unknown"}`,
            isNil(claim.p_outdated_model) ? "" : ` · model P(outdated) ${fmt.pct(claim.p_outdated_model)}`)),
        h("div", { class: "metric" },
          h("span", { class: "kicker" }, "Cache TTL (5% stale risk, experimental)"),
          h("div", { class: "decay-caption" }, isNil(risk.recommended_ttl_days) ? "none (does not decay)" : fmt.days(risk.recommended_ttl_days)))),
    verdict && verdict.label === "changed" && verdict.current_value
      ? h("div", { class: "correction" }, h("span", { class: "kicker" }, "Current value, per evidence"),
        h("p", null, h("s", null, claim.span || claim.text || ""), " → ", h("strong", null, verdict.current_value)))
      : null,
    evidenceBlock(report),
    verdict && verdict.reasoning
      ? h("div", { class: "reasoning" }, h("span", { class: "kicker" }, "model reasoning (not evidence)"), h("p", null, verdict.reasoning))
      : null,
    sources.length ? h("div", { class: "sources" }, h("span", { class: "kicker" }, "Sources"),
      h("ul", null, sources.map((u) => h("li", null, safeLink(u, domainOf(u)))))) : null,
    errorList("What failed (check continued without it):", report.errors));
}

function renderReport(report, typedAnswer) {
  const out = document.getElementById("check-out");
  if (!report || typeof report !== "object" || !Array.isArray(report.claims)) {
    out.replaceChildren(stateBox("error", "Report is malformed", "The response did not contain a claims list."));
    return;
  }
  const notes = [];
  if (report.recorded) {
    notes.push(h("div", { class: "demo-banner", role: "note" }, h("span", { class: "badge" }, "RECORDED"),
      ` Replay mode: this is a saved report recorded on ${fmt.when(report.checked_at)}, not a live check. Type your own answer for a live check (daily cap applies).`));
  }
  if (DATA_SOURCE === "fixture" && typedAnswer && typedAnswer.trim() !== String(report.answer || "").trim()) {
    notes.push(stateBox("", "Fixture mode", "Showing the sample report, not a check of the text you typed. Remove ?fixtures=1 from the URL to check live."));
  }
  const { block, unmatched } = annotatedAnswer(report.answer || "", report.claims);
  out.replaceChildren(...[...notes,
    searchSpendNote(report),
    summaryStrip(report),
    servedByBadges(report.usage || {}),
    errorList("Errors for the whole check:", report.errors),
    h("h2", null, "The answer, annotated"),
    block, legend(),
    unmatched ? h("p", { class: "hint" }, `${unmatched} claim span(s) not found verbatim in the answer.`) : null,
    h("h2", null, "Claims"),
    h("p", { class: "section-note" }, `Checked ${fmt.when(report.checked_at)}. Claims are searched in order of rank score until the budget runs out.`),
    report.claims.length
      ? h("ol", { class: "claims" }, report.claims.map(claimCard))
      : stateBox("", "No claims found", "The extractor found no factual claims in this answer.")].filter(Boolean));
}

function checkErrorBox(err) {
  if (err.status === 401) return stateBox("error", "Not authorised (401)", err.message, "This server requires an x-halflife-key; the UI does not send one.");
  if (err.status === 429) return stateBox("error", "Limit reached (429)", err.message);
  if (err.status === 502) return stateBox("error", "Check failed upstream (502)", `The pipeline raised ${err.message}. Bifrost or a model call may be down; try again.`);
  if (err.network) return stateBox("error", "Server unreachable", err.message, "Is the API running on this host?");
  return stateBox("error", `Check failed${err.status ? ` (${err.status})` : ""}`, err.message);
}

function loadingBox() {
  const seconds = h("span", null, "0");
  const box = stateBox("loading", "Checking…",
    h("p", null, "Extracting claims, ranking them, searching the riskiest. ", seconds, " s elapsed (a live check takes about 3–10 s)."));
  const started = Date.now();
  const timer = setInterval(() => { seconds.textContent = String(Math.floor((Date.now() - started) / 1000)); }, 250);
  return { box, stop: () => clearInterval(timer) };
}

function initCheck() {
  const form = document.getElementById("check-form");
  const input = document.getElementById("answer-input");
  const button = document.getElementById("check-btn");
  const out = document.getElementById("check-out");
  document.getElementById("check-hint").textContent = DATA_SOURCE === "fixture"
    ? "Fixture mode: Check loads the sample report (tests/fixtures/report.json)."
    : "Posts to /v1/check. Budget = max claims searched with Tavily; empty = all time-sensitive claims.";
  out.replaceChildren(stateBox("", "Nothing checked yet", "Pick an example or paste an answer, then press Check."));

  form.querySelectorAll("[data-example]").forEach((chip) => chip.addEventListener("click", () => {
    input.value = EXAMPLES[chip.dataset.example];
    input.focus();
  }));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (button.disabled) return;
    const answer = input.value;
    if (DATA_SOURCE === "api" && !answer.trim()) {
      out.replaceChildren(stateBox("error", "No answer to check", "Paste an answer or pick an example first."));
      return;
    }
    const rawBudget = document.getElementById("budget-input").value;
    const budget = rawBudget === "" ? null : Math.min(20, Math.max(0, Math.floor(Number(rawBudget))));
    const loading = loadingBox();
    button.disabled = true;
    button.textContent = "Checking…";
    out.replaceChildren(loading.box);
    try {
      const report = await runCheck({
        answer,
        asOf: document.getElementById("asof-input").value,
        budget,
        simulateDown: document.getElementById("failover-input").checked,
      });
      if (!answer.trim() && report && report.answer) input.value = report.answer;
      renderReport(report, answer);
    } catch (err) {
      out.replaceChildren(checkErrorBox(err));
    } finally {
      loading.stop();
      button.disabled = false;
      button.textContent = "Check";
    }
  });
}

// ---------- charts ----------

function baseChartOptions(yLabel, xLabel) {
  const ink = cssVar("--ink-2");
  const grid = cssVar("--rule");
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: prefersReducedMotion ? false : { duration: 400 },
    plugins: { legend: { labels: { color: ink, boxWidth: 14, font: { family: "system-ui" } } } },
    scales: {
      x: { ticks: { color: ink }, grid: { color: grid }, title: { display: !!xLabel, text: xLabel, color: ink } },
      y: { ticks: { color: ink }, grid: { color: grid }, title: { display: !!yLabel, text: yLabel, color: ink } },
    },
  };
}

function chartSlot(id, label) {
  return h("div", { class: "chart-box" }, h("canvas", { id, role: "img", "aria-label": label }));
}

function drawChart(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  if (typeof window.Chart !== "function") {
    canvas.parentElement.replaceChildren(h("p", { class: "chart-fallback" }, "Chart library did not load (offline?). The table carries the same numbers."));
    return;
  }
  if (charts[id]) charts[id].destroy();
  charts[id] = new window.Chart(canvas, config);
}

function curveChartOptions(xLabel) {
  const options = baseChartOptions("Stale claims caught (%)", xLabel);
  options.scales.y.min = 0;
  options.scales.y.max = 100;
  options.scales.x.ticks.maxTicksLimit = 11;
  options.interaction = { mode: "index", intersect: false };
  options.plugins.tooltip = { callbacks: { title: (items) => `verify top ${items[0].label}%`, label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(0)}% caught` } };
  return options;
}

function curveDatasets(set, order) {
  return order.filter((m) => Array.isArray(set[m])).map((m) => {
    const style = METHOD_STYLE[m];
    const color = cssVar(style.color);
    return {
      label: METHODS[m], data: set[m].map((y) => y * 100), borderColor: color, backgroundColor: color,
      borderWidth: style.width, borderDash: style.dash || [], pointRadius: 0, tension: 0,
    };
  });
}

function table(caption, headers, rows) {
  return h("div", { class: "table-wrap" }, h("table", null,
    h("caption", null, caption),
    h("thead", null, h("tr", null, headers.map((col) => h("th", { scope: "col", class: col.num ? "num" : null }, col.label)))),
    h("tbody", null, rows)));
}

// ---------- Gateway view ----------

function ttlDays(halfLife) {
  return -halfLife * Math.log2(1 - TTL_EPSILON);
}

const isDemoKey = (key) => typeof key === "string" && key.startsWith(DEMO_KEY_PREFIX);
const demoBadge = () => h("span", { class: "badge demo" }, "DEMO TRAFFIC");

function staleRateRow(r) {
  return h("tr", null,
    h("th", { scope: "row" }, r.model),
    h("td", null, r.virtual_key || h("span", { class: "muted" }, "none"), isDemoKey(r.virtual_key) ? [" ", demoBadge()] : null),
    h("td", { class: "num" }, fmt.num(r.answers_seen)), h("td", { class: "num" }, fmt.num(r.answers_checked)),
    h("td", { class: "num" }, fmt.num(r.claims_found)), h("td", { class: "num" }, fmt.num(r.claims_verified)),
    h("td", { class: "num" }, fmt.num(r.claims_changed)),
    h("td", { class: "num" }, estText(r)),
    h("td", { class: "num" }, r.claims_found ? fmt.pct(r.claims_verified / r.claims_found, 1) : "—"),
    h("td", { class: "num" }, isNil(r.stale_rate) ? h("span", { class: "muted" }, "— nothing verified") : fmt.pct(r.stale_rate, 1)),
    h("td", { class: "num" }, fmt.num(r.mean_answer_score, 1)));
}

function halfLifeTable(summary) {
  const sourceOf = summary.half_life_source || {};
  const hlRows = Object.entries(summary.half_lives || {}).sort((a, b) => a[1] - b[1]);
  if (!hlRows.length) return stateBox("", "No half-lives reported", "The summary did not include half-life values.");
  const source = (cls) => {
    if (sourceOf[cls] === "fitted") return h("span", { class: "src-fitted" }, "fitted");
    return h("span", { class: "src-prior" }, sourceOf[cls] === "prior_guess" ? "prior guess" : "unknown");
  };
  return table(`Half-lives in use and cache TTL at ε = ${TTL_EPSILON} (TTL = −h · log₂(1 − ε))`,
    [{ label: "Class" }, { label: "Half-life", num: true }, { label: "Source" }, { label: "TTL (experimental)", num: true }],
    [...hlRows.map(([cls, hl]) => h("tr", null,
      h("th", { scope: "row" }, cls.replace(/_/g, " ")), h("td", { class: "num" }, fmt.days(hl)),
      h("td", null, source(cls)), h("td", { class: "num" }, fmt.days(ttlDays(hl))))),
    h("tr", null, h("th", { scope: "row" }, "timeless"), h("td", { class: "num muted" }, "—"), h("td", { class: "muted" }, "never decays"), h("td", { class: "num muted" }, "no expiry"))]);
}

function drawGatewayChart(charted) {
  if (!charted.length) return;
  const options = baseChartOptions(null, "Stale among verified (%)");
  options.indexAxis = "y";
  options.plugins.legend.display = false;
  options.scales.x.min = 0;
  options.scales.x.max = 100;
  options.plugins.tooltip = { callbacks: { label: (ctx) => `${ctx.parsed.x.toFixed(1)}% of verified claims changed` } };
  drawChart("gateway-chart", {
    type: "bar",
    data: {
      labels: charted.map((r) => [r.model.replace(/^anthropic\//, ""), `${r.virtual_key || "no key"}${isDemoKey(r.virtual_key) ? " (DEMO)" : ""}`]),
      datasets: [{ label: "Stale rate among verified claims", data: charted.map((r) => r.stale_rate * 100), backgroundColor: cssVar("--accent"), borderRadius: 2, maxBarThickness: 40 }],
    },
    options,
  });
}

function renderGateway(summary) {
  const out = document.getElementById("gateway-out");
  const rows = Array.isArray(summary.rows) ? summary.rows : [];
  const usage = summary.usage || {};
  const sum = (field) => rows.reduce((t, r) => t + (r[field] || 0), 0);
  const verified = sum("claims_verified");
  const changed = sum("claims_changed");
  const allDemo = rows.length > 0 && rows.every((r) => isDemoKey(r.virtual_key));
  const charted = rows.filter((r) => !isNil(r.stale_rate));

  out.replaceChildren(...[
    h("h2", null, "Stale rate among verified claims, by model and virtual key"),
    h("p", { class: "section-note" }, "Half-Life samples answers from Bifrost's own logs, extracts the time-sensitive claims, and verifies them with Tavily. Stale rate among verified claims = claims whose current value changed ÷ claims verified (verdict current or changed; unverifiable excluded). Only the riskiest claims, up to the verification budget, are verified, so this is not a stale rate over all traffic; the verified share is shown beside it."),
    summary.recorded ? h("div", { class: "demo-banner", role: "note" }, h("span", { class: "badge" }, "RECORDED"),
      ` Replay mode: the saved audit from ${fmt.when(summary.generated_at)}, not a live audit.`) : null,
    allDemo ? h("div", { class: "demo-banner", role: "note" }, demoBadge(),
      " Every row below comes from seeded demo virtual keys (demo-*), not real user traffic.") : null,
    h("div", { class: "meta-row" },
      h("span", null, `window ${fmt.when(summary.window_start)} → ${fmt.when(summary.window_end)}`),
      h("span", null, `generated ${fmt.when(summary.generated_at)}`)),
    h("dl", { class: "stats", style: { marginTop: "14px" } },
      stat("Estimated stale rate, all time-sensitive claims", estText(summary.estimate_overall)),
      stat("Stale among verified (top-risk slice)", verified ? fmt.pct(changed / verified, 1) : "—"),
      stat("Share of claims verified", sum("claims_found") ? fmt.pct(verified / sum("claims_found"), 1) : "—"),
      stat("Logs scanned", fmt.num(summary.logs_scanned)),
      stat("Answers seen", fmt.num(sum("answers_seen"))),
      stat("Answers checked", fmt.num(sum("answers_checked"))),
      stat("Claims verified", fmt.num(verified)),
      stat("Claims changed", fmt.num(changed)),
      stat("Sample cap", fmt.num(summary.sample_cap), "answers per audit run"),
      stat("Verification budget", fmt.num(summary.verification_budget), "claims searched per run")),
    rows.length ? chartSlot("gateway-chart", "Bar chart of stale rate by model and virtual key") : stateBox("", "No traffic in this window", "The audit found no gateway logs to sample."),
    charted.length < rows.length ? h("p", { class: "hint" }, `${rows.length - charted.length} slice(s) not charted: nothing verified there.`) : null,
    (summary.errors || []).length ? h("details", { class: "audit-errors" },
      h("summary", null, `Audit errors (${summary.errors.length}) — failures recorded, not hidden`),
      errorList("", summary.errors)) : null,
    rows.length ? table("Stale rate per model and virtual key",
      ["Model", "Virtual key", "Answers seen", "Checked", "Claims found", "Verified", "Changed", "Estimated stale (95% CI)", "Verified share", "Stale among verified", "Mean score"]
        .map((label, i) => ({ label, num: i >= 2 })),
      rows.map(staleRateRow)) : null,
    h("h3", { style: { marginTop: "18px" } }, "Cost of this audit"),
    h("dl", { class: "stats" },
      stat("Model calls", fmt.num(usage.model_calls)),
      stat("Model cost", fmt.usd(usage.model_cost_usd), "estimated from tokens at list price"),
      stat("Tavily searches", fmt.num(usage.tavily_calls)),
      stat("Tavily credits", fmt.num(usage.tavily_credits)),
      stat("Cache hits", fmt.num(usage.tavily_cache_hits)),
      stat("Wall time", fmt.ms(usage.latency_ms))),
    h("h2", null, "Half-lives and cache TTLs"),
    h("p", { class: "ttl-warning" }, h("strong", null, "TTL: experimental"), " — half-lives are not calibrated, see Evidence."),
    h("p", { class: "section-note" }, "A cached answer stays under 5% chance of staleness for TTL days. Prior guesses are placeholders until fitted values replace them."),
    halfLifeTable(summary)].filter(Boolean));
  drawGatewayChart(charted);
}

function noAuditBox() {
  return h("div", { class: "state" },
    h("h3", null, "No gateway audit yet"),
    h("p", null, "The audit reads Bifrost's request logs. Seed some demo traffic, then run one audit:"),
    h("pre", { class: "cmd" }, "uv run python -m halflife.gateway.seed\nuv run python -m halflife.gateway.audit"),
    h("p", null, "Then reopen this tab."));
}

async function loadGateway() {
  loaded.gateway = true;
  const out = document.getElementById("gateway-out");
  out.replaceChildren(stateBox("loading", "Loading gateway summary…"));
  try {
    const summary = await getJSON(ENDPOINTS[DATA_SOURCE].gateway);
    renderGateway(summary);
  } catch (err) {
    loaded.gateway = false;
    if (err.status === 404) out.replaceChildren(noAuditBox());
    else out.replaceChildren(stateBox("error", "Gateway summary failed to load", err.message));
  }
}

// ---------- Evidence view: (A) live detector ----------

const ciCell = (point, ci) => h("td", { class: "num" }, fmt.pct(point), ci ? h("span", { class: "ci" }, ` ${fmt.ci(ci)}`) : null);

function confusionTable(confusion) {
  const cols = ["changed", "current", "unverifiable", "not_searched"];
  const truths = Object.keys(confusion);
  return table("Confusion: labelled truth (rows) against detector outcome (columns)",
    [{ label: "Truth" }, ...cols.map((c) => ({ label: c.replace(/_/g, " "), num: true }))],
    truths.map((t) => h("tr", null, h("th", { scope: "row" }, t),
      cols.map((c) => h("td", { class: "num" }, fmt.num(confusion[t][c] || 0))))));
}

function budgetTable(budget) {
  const methods = ["model_p", "half_life", "random"].filter((m) => budget[m]);
  const ks = ["caught_at_25", "caught_at_50", "caught_at_100"];
  return table("Stale claims caught when verifying the top 25 / 50 / 100% of claims (95% CI by source URL)",
    [{ label: "Ordering" }, { label: "@25%", num: true }, { label: "@50%", num: true }, { label: "@100%", num: true }],
    methods.map((m) => h("tr", { class: m === "model_p" ? "best" : null }, h("th", { scope: "row" }, METHODS[m]),
      ks.map((k) => (budget[m][k] ? ciCell(budget[m][k].point, budget[m][k].ci95_by_url) : h("td", { class: "num" }, "—"))))));
}

function costTable(costs) {
  return table("Cost and latency per answer by verification budget (model ordering)",
    [{ label: "Budget" }, { label: "Model cost", num: true }, { label: "Tavily credits", num: true }, { label: "Latency mean", num: true }, { label: "Latency median", num: true }],
    Object.entries(costs).map(([k, v]) => h("tr", null, h("th", { scope: "row" }, k),
      h("td", { class: "num" }, `$${Number(v.model_cost_usd_per_answer).toFixed(6)}`),
      h("td", { class: "num" }, fmt.num(v.tavily_credits_per_answer, 2)),
      h("td", { class: "num" }, `${fmt.num(v.latency_s_per_answer_mean, 2)} s`),
      h("td", { class: "num" }, `${fmt.num(v.latency_s_per_answer_median, 2)} s`))));
}

function perClassTable(perClass) {
  return table("Per class (precision and recall on time-sensitive cases)",
    [{ label: "Class" }, { label: "n", num: true }, { label: "TP", num: true }, { label: "FP", num: true }, { label: "FN", num: true }, { label: "Precision", num: true }, { label: "Recall", num: true }, { label: "Read?" }],
    Object.entries(perClass).map(([cls, v]) => {
      if (isNil(v.n_time_sensitive)) {
        return h("tr", null, h("th", { scope: "row" }, cls.replace(/_/g, " ")), h("td", { class: "num" }, fmt.num(v.n)),
          h("td", { colspan: "5", class: "muted" }, `${fmt.num(v.flagged)} flagged, ${fmt.num(v.searched)} searched`), h("td", null, "control"));
      }
      return h("tr", null, h("th", { scope: "row" }, cls.replace(/_/g, " ")), h("td", { class: "num" }, fmt.num(v.n_time_sensitive)),
        h("td", { class: "num" }, fmt.num(v.tp)), h("td", { class: "num" }, fmt.num(v.fp)), h("td", { class: "num" }, fmt.num(v.fn)),
        h("td", { class: "num" }, fmt.pct(v.precision)), h("td", { class: "num" }, fmt.pct(v.recall)),
        h("td", null, v.too_thin_to_read ? h("span", { class: "badge thin" }, "too thin to read") : "ok"));
    }));
}

function detectorSection(summary, curves) {
  if (!summary) return stateBox("error", "Live detector results failed to load", `${RESULTS.detectorSummary} did not load.`);
  const det = summary.detector || {};
  return h("section", { "aria-labelledby": "det-h" },
    h("h2", { id: "det-h" }, `Live detector (${summary.n_cases} labelled cases)`),
    h("p", { class: "section-note" }, `${summary.n_cases} hand-labelled answers (${summary.n_stale} stale) run end to end through Bifrost and Tavily on ${summary.eval_date}. CIs are bootstrapped by source URL because many cases share a URL.`),
    h("dl", { class: "stats" },
      stat("Precision", fmt.pct(det.precision, 1), `95% CI ${fmt.ci(det.precision_ci95_by_url)}`),
      stat("Recall", fmt.pct(det.recall, 1), `95% CI ${fmt.ci(det.recall_ci95_by_url)}`),
      stat("Unverifiable", fmt.pct(det.unverifiable_rate, 1)),
      stat("Timeless searched", `${fmt.num(det.timeless_searched)} / ${fmt.num(det.timeless_n)}`)),
    summary.confusion ? confusionTable(summary.confusion) : null,
    h("h3", { style: { marginTop: "18px" } }, "Budget curve"),
    curves ? chartSlot("detector-chart", "Line chart of stale claims caught against claims verified, for model, half-life, random and oracle orderings") : stateBox("error", "Curve unavailable", `${RESULTS.detectorCurves} did not load.`),
    h("div", { class: "caption-box" }, h("p", null, "Haiku's own outdated-probability ranks better than the half-life model; it is the product default."), h("p", null, `Labelled set: ${summary.n_cases} cases, one annotator; eval date ${summary.eval_date}. CIs resample source URLs.`)),
    summary.budget ? budgetTable(summary.budget) : null,
    summary.cost_latency_by_budget_model_order ? costTable(summary.cost_latency_by_budget_model_order) : null,
    summary.per_class ? perClassTable(summary.per_class) : null,
    h("p", { class: "hint" }, "Details: ", safeLink(`${DETECTOR_DIR}/errors.md`, "errors.md"), " · ", safeLink(`${DETECTOR_DIR}/README.md`, "README.md")));
}

function drawDetectorChart(curves) {
  if (!curves) return;
  const grid = (curves.grid || []).map((x) => Math.round(x * 100));
  drawChart("detector-chart", {
    type: "line",
    data: { labels: grid, datasets: curveDatasets(curves, ["model_p", "half_life", "random", "oracle_upper_bound"]) },
    options: curveChartOptions("Claims verified, riskiest first (%)"),
  });
}

// ---------- Evidence view: (B) ordering test ----------

function orderingTable(summary, split) {
  const entries = Object.entries(summary[split] || {}).sort((a, b) => b[1].auc - a[1].auc);
  const best = entries.length ? entries[0][0] : null;
  return table("Area under the risk-coverage curve, and share of stale claims caught when verifying the top 10 / 25 / 50% of claims",
    [{ label: "Ranking" }, { label: "AUC", num: true }, { label: "Caught @10%", num: true }, { label: "@25%", num: true }, { label: "@50%", num: true }],
    entries.map(([m, v]) => h("tr", { class: m === best ? "best" : null },
      h("th", { scope: "row" }, METHODS[m] || m), h("td", { class: "num" }, fmt.num(v.auc, 3)),
      h("td", { class: "num" }, fmt.pct(v.catch_at_10)), h("td", { class: "num" }, fmt.pct(v.catch_at_25)), h("td", { class: "num" }, fmt.pct(v.catch_at_50)))));
}

function headlineTable(headline) {
  const ks = ["caught_at_10", "caught_at_25", "caught_at_50"];
  const cell = (triple) => (Array.isArray(triple) && triple.length === 3 ? ciCell(triple[1], [triple[0], triple[2]]) : h("td", { class: "num" }, "—"));
  return table(`Headline on the model sample (n = ${headline.n}, ${headline.n_stale} stale): caught @10 / 25 / 50% with 95% CIs`,
    [{ label: "Ordering" }, { label: "@10%", num: true }, { label: "@25%", num: true }, { label: "@50%", num: true }],
    ["model_p", "halflife"].filter((m) => headline[m]).map((m) => h("tr", { class: m === "model_p" ? "best" : null },
      h("th", { scope: "row" }, METHODS[m]), ks.map((k) => cell(headline[m][k])))));
}

function splitCounts(summary, split) {
  if (split === "test_sample") {
    const n = summary.counts && summary.counts.model_sample;
    return n ? `stratified sample, n = ${n}, rated by the model` : "stratified model sample";
  }
  const test = (summary.counts && summary.counts.test) || {};
  const n = Object.values(test).reduce((a, b) => a + b, 0);
  const stale = Object.entries(test).filter(([k]) => k.endsWith(":stale")).reduce((a, [, v]) => a + v, 0);
  return n ? `all test claims, n = ${n} (${stale} stale), no model baselines` : "all test claims";
}

function orderingSection(summary, curves, headline) {
  let split = "test_sample";
  const tableSlot = h("div");
  const countLine = h("p", { class: "hint" });
  const redraw = () => {
    tableSlot.replaceChildren(summary ? orderingTable(summary, split) : stateBox("error", "Summary table unavailable", "summary.json did not load."));
    countLine.textContent = summary ? splitCounts(summary, split) : "";
    if (!curves) return;
    const grid = (curves.grid || []).map((x) => Math.round(x * 100));
    drawChart("curve-chart", {
      type: "line",
      data: { labels: grid, datasets: curveDatasets(curves[split] || {}, ["model_p", "halflife", "model_ts", "class_only", "age_only", "random"]) },
      options: curveChartOptions("Claims verified, riskiest first (%)"),
    });
  };
  const radio = (value, label) => h("label", null,
    h("input", { type: "radio", name: "split", value, checked: value === split }), h("span", null, label));
  const picker = h("fieldset", { class: "segmented" },
    h("legend", { class: "visually-hidden" }, "Dataset"),
    radio("test_sample", "Model sample (n=300)"), radio("test_full", "Full test set"));
  picker.addEventListener("change", (e) => { split = e.target.value; redraw(); });

  const section = h("section", { "aria-labelledby": "ord-h" },
    h("h2", { id: "ord-h" }, "Ordering test (time-travel dataset)"),
    h("p", { class: "section-note" }, "Claims dated before a cutoff, outcomes after it. Verify claims from riskiest down; the curve shows what share of the truly stale ones are caught after verifying x% of all claims."),
    picker, countLine,
    curves ? chartSlot("curve-chart", "Line chart of stale claims caught against claims verified, one line per ranking method") : stateBox("error", "Curves unavailable", "curves.json did not load."),
    h("div", { class: "caption-box" },
      h("p", null, "Ordering dataset covers four classes (office holder, software version, policy rate, timeless); prices and laws are not in it.")),
    headline ? headlineTable(headline) : null,
    h("h3", { style: { marginTop: "18px" } }, "All rankings"),
    tableSlot,
    summary && summary.cutoff ? h("p", { class: "hint" }, `Half-lives fitted on outcomes before ${summary.cutoff}; every test outcome is a change after that date.`) : null);
  return { section, redraw };
}

async function loadEvidence() {
  loaded.evidence = true;
  const out = document.getElementById("evidence-out");
  out.replaceChildren(stateBox("loading", "Loading measured results…"));
  const keys = Object.keys(RESULTS);
  const settled = await Promise.allSettled(keys.map((k) => getJSON(RESULTS[k])));
  const data = Object.fromEntries(keys.map((k, i) => [k, settled[i].status === "fulfilled" ? settled[i].value : null]));
  if (keys.every((k) => !data[k])) {
    loaded.evidence = false;
    out.replaceChildren(stateBox("error", "No measured results found", settled[0].reason.message));
    return;
  }
  const ordering = orderingSection(data.orderingSummary, data.orderingCurves, data.orderingHeadline);
  out.replaceChildren(detectorSection(data.detectorSummary, data.detectorCurves), ordering.section);
  drawDetectorChart(data.detectorCurves);
  ordering.redraw();
}

// ---------- boot ----------

document.getElementById("source-flag").textContent = DATA_SOURCE === "fixture" ? "data: sample fixtures" : "data: live API";
loadHealth();
initCheck();
initTabs();


// Replay mode: show how many live checks remain today (public hosting).
(async () => {
  if (DATA_SOURCE !== "api") return;
  try {
    const r = await fetch("/v1/mode");
    if (!r.ok) return;
    const m = await r.json();
    if (!m.replay) return;
    const form = document.querySelector("#panel-check form") || document.getElementById("panel-check");
    if (!form) return;
    form.prepend(h("p", { class: "demo-banner", role: "note" }, h("span", { class: "badge" }, "REPLAY MODE"),
      ` Example answers return recorded reports. Live checks left today: ${m.live_checks_remaining_today} of ${m.live_checks_per_day}.`));
  } catch (_) { /* mode banner is optional */ }
})();

// Detector variance (five runs) next to the run-2 detail in the Evidence view.
(async () => {
  try {
    const r = await fetch("/results/2026-11-12-detector/variance.json");
    if (!r.ok) return;
    const data = await r.json();
    const v = data.headline_live_runs, c = data.stability_check_cached_only;
    const place = () => {
      const head = document.getElementById("det-h");
      if (!head || document.getElementById("det-variance")) return Boolean(head);
      const f = (x) => `${x.mean.toFixed(3)} (range ${x.min.toFixed(3)}–${x.max.toFixed(3)})`;
      const p = h("p", { class: "section-note", id: "det-variance" },
        `Headline, live-search runs 1–2 (run 1 predates the numeric-equality bug fix): precision ${f(v.precision)}, recall ${f(v.recall)}; ` +
        `stale caught @50% of claims verified: model ${v.caught_at_50.model_p.mean.toFixed(3)}, half-life ${v.caught_at_50.half_life.mean.toFixed(3)}, random ${v.caught_at_50.random.mean.toFixed(3)}. ` +
        `Cached-evidence-only runs 3–5 (stability check, not averaged in): precision ${f(c.precision)}; recall ${f(c.recall)} is a lower bound, since unseen queries could not be searched. ` +
        "Tables below: run 2.");
      head.after(p);
      return true;
    };
    if (!place()) new MutationObserver((_, obs) => { if (place()) obs.disconnect(); }).observe(document.body, { childList: true, subtree: true });
  } catch (_) { /* optional */ }
})();
