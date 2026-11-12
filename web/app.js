"use strict";

// "fixture" builds against checked-in sample files; "api" uses the FastAPI endpoints. Wiring = flip this.
const DATA_SOURCE = "fixture";

// Relative paths work both from /web/index.html (http.server at repo root) and from "/" (FastAPI).
const ENDPOINTS = {
  fixture: {
    check: "../tests/fixtures/report.json",
    gateway: "../tests/fixtures/gateway.json",
  },
  api: {
    check: "/v1/check",
    gateway: "/v1/gateway/summary",
  },
};
const RESULTS = {
  summary: "../results/2026-11-12-ordering/summary.json",
  curves: "../results/2026-11-12-ordering/curves.json",
  // ponytail: J3 output path is a guess until J3 lands; change here when it does.
  j3: "../results/j3-live/summary.json",
};

const TTL_EPSILON = 0.05;
const TABS = ["check", "gateway", "evidence"];

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
  model_ts: "Model time-sensitivity",
  class_only: "Class only",
  age_only: "Age only",
  random: "Random",
};
const METHOD_STYLE = {
  model_p: { color: "--accent", width: 3 },
  halflife: { color: "--info", width: 3 },
  model_ts: { color: "--warn", width: 2 },
  class_only: { color: "--ok", width: 2 },
  age_only: { color: "--neutral", width: 2 },
  random: { color: "--ink-2", width: 1.5, dash: [4, 4] },
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
  try { parsed = new URL(url); } catch (_) { parsed = null; }
  if (!parsed || !["http:", "https:"].includes(parsed.protocol)) return h("span", { class: "muted" }, label || String(url));
  return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer" }, label || parsed.href);
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return String(url); }
}

function stateBox(kind, title, ...lines) {
  return h("div", { class: `state ${kind}`, role: kind === "error" ? "alert" : null },
    h("h3", null, title), ...lines.map((line) => h("p", null, line)));
}

function errorList(title, errors) {
  if (!errors || !errors.length) return null;
  return h("div", { class: "errors" }, h("p", null, h("strong", null, title)),
    h("ul", null, errors.map((e) => h("li", null, String(e)))));
}

const fmt = {
  pct: (x, d = 0) => (x === null || x === undefined ? "—" : `${(x * 100).toFixed(d)}%`),
  num: (x, d = 0) => (x === null || x === undefined ? "—" : Number(x).toFixed(d)),
  usd: (x) => (x === null || x === undefined ? "—" : `$${Number(x).toFixed(4)}`),
  ms: (x) => (!x ? "—" : x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${Math.round(x)} ms`),
  days: (x) => (x === null || x === undefined ? "—" : `${Number(x).toFixed(x < 10 ? 1 : 0)} d`),
  when: (iso) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso ?? "—") : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
  },
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ---------- data access ----------

class FetchError extends Error {
  constructor(message, { status = null, missing = false } = {}) {
    super(message);
    this.status = status;
    this.missing = missing;
  }
}

async function getJSON(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (err) {
    throw new FetchError(`Could not reach ${url} (${err.message}).`);
  }
  if (!res.ok) throw new FetchError(`${url} returned HTTP ${res.status}.`, { status: res.status, missing: res.status === 404 });
  try {
    return await res.json();
  } catch (_) {
    throw new FetchError(`${url} did not return valid JSON.`);
  }
}

function runCheck({ answer, asOf, budget }) {
  if (DATA_SOURCE === "fixture") return getJSON(ENDPOINTS.fixture.check);
  const body = { answer };
  if (asOf) body.as_of = asOf;
  if (budget !== null) body.budget = budget;
  return getJSON(ENDPOINTS.api.check, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------- tabs ----------

function selectTab(name, { focus = false } = {}) {
  const active = TABS.includes(name) ? name : "check";
  for (const tab of TABS) {
    const button = document.getElementById(`tab-${tab}`);
    const panel = document.getElementById(`panel-${tab}`);
    const isActive = tab === active;
    button.setAttribute("aria-selected", String(isActive));
    button.tabIndex = isActive ? 0 : -1;
    panel.hidden = !isActive;
  }
  if (focus) document.getElementById(`tab-${active}`).focus();
  if (location.hash.slice(1) !== active) history.replaceState(null, "", `#${active}`);
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
  if (report.verdict) {
    const label = report.verdict.label;
    return { key: label, text: label === "unverifiable" ? "unverifiable" : label };
  }
  if (report.score_basis === "not_time_sensitive") return { key: "not-time-sensitive", text: "not time-sensitive" };
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
    let from = 0;
    let start = answer.indexOf(span, from);
    // skip occurrences already taken by an earlier claim with the same span
    while (start >= 0 && ranges.some((r) => start < r.end && start + span.length > r.start)) {
      from = start + 1;
      start = answer.indexOf(span, from);
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
  const unmatched = claims.length - ranges.length;
  return { block, unmatched };
}

function legend() {
  const item = (cls, text) => h("li", null, h("span", { class: `sw ${cls}`, "aria-hidden": "true" }), text);
  const swatches = h("ul", { class: "legend", "aria-label": "Highlight legend" },
    item("v-changed", "changed"), item("v-current", "current"), item("v-unverifiable", "unverifiable"),
    item("v-other", "not searched / not time-sensitive"));
  // swatch colours reuse the mark backgrounds
  const map = { "v-changed": "--mark-changed", "v-current": "--mark-current", "v-unverifiable": "--mark-unverifiable", "v-other": "--mark-other" };
  swatches.querySelectorAll(".sw").forEach((sw) => {
    const key = [...sw.classList].find((c) => c in map);
    sw.style.background = `var(${map[key]})`;
  });
  return swatches;
}

function summaryStrip(report) {
  const usage = report.usage || {};
  const score = report.answer_score;
  const stat = (label, value) => h("div", { class: "stat" }, h("dt", null, label), h("dd", null, value));
  return h("div", { class: "summary" },
    h("div", { class: "score-plate" },
      h("div", { class: "kicker" }, "Answer freshness"),
      h("div", { class: "big" }, score === null || score === undefined ? "—" : fmt.num(score)),
      h("div", { class: "of" }, score === null || score === undefined ? "no time-sensitive claims scored" : "of 100, mean of scored claims")),
    h("dl", { class: "stats" },
      stat("Claims", String((report.claims || []).length)),
      stat("Searched", `${(report.claims || []).filter((c) => c.searched).length}${report.verification_budget !== null && report.verification_budget !== undefined ? ` / budget ${report.verification_budget}` : ""}`),
      stat("Model cost", fmt.usd(usage.model_cost_usd)),
      stat("Model calls", fmt.num(usage.model_calls)),
      stat("Tavily credits", fmt.num(usage.tavily_credits)),
      stat("Cache hits", fmt.num(usage.tavily_cache_hits)),
      stat("Latency", fmt.ms(usage.latency_ms)),
      stat("Model", report.model || "unknown")));
}

function decayBar(risk) {
  const p = Math.min(1, Math.max(0, Number(risk.p_stale) || 0));
  const fill = h("span", { style: { width: `${p * 100}%` } });
  if (p > 0) fill.style.setProperty("--full", `${100 / p}%`);
  const hl = risk.half_life_days === null || risk.half_life_days === undefined
    ? "no half-life (timeless)"
    : `h = ${fmt.days(risk.half_life_days)} (${risk.half_life_source === "fitted" ? "fitted" : "prior guess"}), age ${fmt.days(risk.age_days)} via ${String(risk.age_basis || "").replace(/_/g, " ")}`;
  return h("div", { class: "metric" },
    h("span", { class: "kicker", id: null }, "P(stale), half-life model"),
    h("div", { class: "decay", role: "img", "aria-label": `P(stale) ${fmt.pct(p)}` }, fill),
    h("div", { class: "decay-caption" }, `${fmt.pct(p)} · ${hl}`));
}

function freshnessBlock(report) {
  const score = report.freshness_score;
  let tone = "none";
  if (score !== null && score !== undefined) tone = score >= 80 ? "hi" : score >= 40 ? "mid" : "lo";
  return h("div", { class: "metric" },
    h("span", { class: "kicker" }, "Freshness score"),
    h("div", { class: "fresh" },
      h("span", { class: `num ${tone}` }, score === null || score === undefined ? "no score" : fmt.num(score)),
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

  return h("li", { class: "claim", id: `claim-${claim.id || index}`, "aria-label": `Claim ${index + 1}` },
    h("div", { class: "claim-head" },
      h("span", { class: "claim-num", "aria-hidden": "true" }, String(index + 1)),
      h("div", { style: { flex: "1", minWidth: "0" } },
        h("h3", { class: "claim-text" }, claim.text || claim.span || "(claim text missing)"),
        h("div", { class: "badges" },
          h("span", { class: "badge class" }, String(claim.volatility_class || "unknown class").replace(/_/g, " ")),
          h("span", { class: `badge ${info.key}` }, info.text),
          claim.is_past_event ? h("span", { class: "badge class" }, "past event") : null,
          claim.explicit_date ? h("span", { class: "badge class" }, `as of ${claim.explicit_date}`) : null))),
    h("div", { class: "claim-grid" },
      decayBar(risk),
      freshnessBlock(report),
      h("div", { class: "metric" },
        h("span", { class: "kicker" }, "Verification rank"),
        h("div", { class: "decay-caption" },
          `rank score ${fmt.num(risk.rank_score, 2)} · from ${RANK_BASIS[risk.rank_basis] || risk.rank_basis || "unknown"}`,
          claim.p_outdated_model !== null && claim.p_outdated_model !== undefined ? ` · model P(outdated) ${fmt.pct(claim.p_outdated_model)}` : "")),
      h("div", { class: "metric" },
        h("span", { class: "kicker" }, "Cache TTL (5% stale risk)"),
        h("div", { class: "decay-caption" }, risk.recommended_ttl_days === null || risk.recommended_ttl_days === undefined ? "none (does not decay)" : fmt.days(risk.recommended_ttl_days)))),
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
  out.replaceChildren();
  if (!report || typeof report !== "object" || !Array.isArray(report.claims)) {
    out.append(stateBox("error", "Report is malformed", "The response did not contain a claims list."));
    return;
  }
  const notes = [];
  if (DATA_SOURCE === "fixture" && typedAnswer && typedAnswer.trim() !== report.answer.trim()) {
    notes.push(stateBox("", "Fixture mode", "Showing the sample report, not a check of the text you typed. Switch DATA_SOURCE to \"api\" in app.js to check live."));
  }
  const { block, unmatched } = annotatedAnswer(report.answer || "", report.claims);
  out.append(...[...notes, summaryStrip(report),
    errorList("Errors for the whole check:", report.errors),
    h("h2", null, "The answer, annotated"),
    block, legend(),
    unmatched ? h("p", { class: "hint" }, `${unmatched} claim span(s) not found verbatim in the answer.`) : null,
    h("h2", null, "Claims"),
    h("p", { class: "section-note" }, `Checked ${fmt.when(report.checked_at)}. Claims are searched in order of rank score until the budget runs out.`)].filter(Boolean));
  if (!report.claims.length) {
    out.append(stateBox("", "No claims found", "The extractor found no factual claims in this answer."));
    return;
  }
  out.append(h("ol", { class: "claims" }, report.claims.map(claimCard)));
}

function initCheck() {
  const form = document.getElementById("check-form");
  const input = document.getElementById("answer-input");
  const button = document.getElementById("check-btn");
  const hint = document.getElementById("check-hint");
  const out = document.getElementById("check-out");
  hint.textContent = DATA_SOURCE === "fixture"
    ? "Fixture mode: Check loads the sample report (tests/fixtures/report.json)."
    : "Posts to /v1/check. Budget = max claims searched with Tavily.";
  out.replaceChildren(stateBox("", "Nothing checked yet", "Paste an answer and press Check to see each claim's freshness."));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const answer = input.value;
    if (DATA_SOURCE === "api" && !answer.trim()) {
      out.replaceChildren(stateBox("error", "No answer to check", "Paste an answer first."));
      return;
    }
    const rawBudget = document.getElementById("budget-input").value;
    const budget = rawBudget === "" ? null : Math.max(0, Math.floor(Number(rawBudget)));
    button.disabled = true;
    out.replaceChildren(stateBox("", "Checking…", "Extracting claims, ranking them, and searching the riskiest."));
    try {
      const report = await runCheck({ answer, asOf: document.getElementById("asof-input").value, budget });
      if (!answer.trim() && report && report.answer) input.value = report.answer;
      renderReport(report, answer);
    } catch (err) {
      out.replaceChildren(stateBox("error", "Check failed", err.message, "Nothing was scored. Try again, or check that the server is running."));
    } finally {
      button.disabled = false;
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

// ---------- Gateway view ----------

function ttlDays(halfLife) {
  return -halfLife * Math.log2(1 - TTL_EPSILON);
}

function rowLabel(row) {
  return `${row.model} · ${row.virtual_key || "no virtual key"}`;
}

function renderGateway(summary) {
  const out = document.getElementById("gateway-out");
  const rows = Array.isArray(summary.rows) ? summary.rows : [];
  const usage = summary.usage || {};
  const totals = rows.reduce((t, r) => ({
    seen: t.seen + (r.answers_seen || 0), checked: t.checked + (r.answers_checked || 0),
    verified: t.verified + (r.claims_verified || 0), changed: t.changed + (r.claims_changed || 0),
  }), { seen: 0, checked: 0, verified: 0, changed: 0 });
  const stat = (label, value) => h("div", { class: "stat" }, h("dt", null, label), h("dd", null, value));

  const table = h("div", { class: "table-wrap" }, h("table", null,
    h("caption", null, "Stale rate = claims changed / claims verified, per model and virtual key"),
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, "Model"), h("th", { scope: "col" }, "Virtual key"),
      h("th", { scope: "col", class: "num" }, "Answers seen"), h("th", { scope: "col", class: "num" }, "Checked"),
      h("th", { scope: "col", class: "num" }, "Claims"), h("th", { scope: "col", class: "num" }, "Verified"),
      h("th", { scope: "col", class: "num" }, "Changed"), h("th", { scope: "col", class: "num" }, "Stale rate"),
      h("th", { scope: "col", class: "num" }, "Mean score"))),
    h("tbody", null, rows.map((r) => h("tr", null,
      h("th", { scope: "row" }, r.model), h("td", null, r.virtual_key || h("span", { class: "muted" }, "none")),
      h("td", { class: "num" }, fmt.num(r.answers_seen)), h("td", { class: "num" }, fmt.num(r.answers_checked)),
      h("td", { class: "num" }, fmt.num(r.claims_found)), h("td", { class: "num" }, fmt.num(r.claims_verified)),
      h("td", { class: "num" }, fmt.num(r.claims_changed)),
      h("td", { class: "num" }, r.stale_rate === null || r.stale_rate === undefined ? h("span", { class: "muted" }, "— nothing verified") : fmt.pct(r.stale_rate, 1)),
      h("td", { class: "num" }, fmt.num(r.mean_answer_score, 1)))))));

  const halfLives = summary.half_lives || {};
  const sourceOf = summary.half_life_source || {};
  const hlRows = Object.entries(halfLives).sort((a, b) => a[1] - b[1]);
  const hlTable = h("div", { class: "table-wrap" }, h("table", null,
    h("caption", null, `Half-lives in use and recommended cache TTL at ε = ${TTL_EPSILON} (TTL = −h · log₂(1 − ε))`),
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, "Class"), h("th", { scope: "col", class: "num" }, "Half-life"),
      h("th", { scope: "col" }, "Source"), h("th", { scope: "col", class: "num" }, "TTL"))),
    h("tbody", null, hlRows.map(([cls, hl]) => h("tr", null,
      h("th", { scope: "row" }, cls.replace(/_/g, " ")), h("td", { class: "num" }, fmt.days(hl)),
      h("td", null, sourceOf[cls] === "fitted" ? h("span", { class: "src-fitted" }, "fitted") : h("span", { class: "src-prior" }, sourceOf[cls] === "prior_guess" ? "prior guess" : "unknown")),
      h("td", { class: "num" }, fmt.days(ttlDays(hl))))),
    h("tr", null, h("th", { scope: "row" }, "timeless"), h("td", { class: "num muted" }, "—"), h("td", { class: "muted" }, "never decays"), h("td", { class: "num muted" }, "no expiry")))));

  const charted = rows.filter((r) => r.stale_rate !== null && r.stale_rate !== undefined);
  out.replaceChildren(...[
    h("h2", null, "Stale rate across gateway traffic"),
    h("div", { class: "meta-row" },
      h("span", null, `window ${fmt.when(summary.window_start)} → ${fmt.when(summary.window_end)}`),
      h("span", null, `generated ${fmt.when(summary.generated_at)}`)),
    h("dl", { class: "stats", style: { marginTop: "14px" } },
      stat("Logs scanned", fmt.num(summary.logs_scanned)),
      stat("Answers seen", fmt.num(totals.seen)),
      stat("Answers checked", fmt.num(totals.checked)),
      stat("Sample cap", fmt.num(summary.sample_cap)),
      stat("Claims verified", fmt.num(totals.verified)),
      stat("Claims changed", fmt.num(totals.changed)),
      stat("Search budget", fmt.num(summary.verification_budget)),
      stat("Overall stale rate", totals.verified ? fmt.pct(totals.changed / totals.verified, 1) : "—")),
    errorList("Audit errors:", summary.errors),
    rows.length ? chartSlot("gateway-chart", "Bar chart of stale rate by model and virtual key") : stateBox("", "No traffic in this window", "The audit found no gateway logs to sample."),
    charted.length < rows.length ? h("p", { class: "hint" }, `${rows.length - charted.length} slice(s) not charted: nothing verified there.`) : null,
    rows.length ? table : null,
    h("h3", { style: { marginTop: "18px" } }, "Usage for this audit"),
    h("dl", { class: "stats" },
      stat("Model calls", fmt.num(usage.model_calls)), stat("Model cost", fmt.usd(usage.model_cost_usd)),
      stat("Tavily calls", fmt.num(usage.tavily_calls)), stat("Tavily credits", fmt.num(usage.tavily_credits)),
      stat("Cache hits", fmt.num(usage.tavily_cache_hits)), stat("Latency", fmt.ms(usage.latency_ms))),
    h("h2", null, "Half-lives and cache TTLs"),
    h("p", { class: "section-note" }, "A cached answer stays under 5% chance of staleness for TTL days. Fitted values come from dated public histories; prior guesses are placeholders until outcomes exist."),
    hlRows.length ? hlTable : stateBox("", "No half-lives reported", "The summary did not include half-life values.")].filter(Boolean));

  if (charted.length) {
    const accent = cssVar("--accent");
    drawChart("gateway-chart", {
      type: "bar",
      data: {
        labels: charted.map(rowLabel),
        datasets: [{ label: "Stale rate", data: charted.map((r) => r.stale_rate * 100), backgroundColor: accent, borderRadius: 2, maxBarThickness: 48 }],
      },
      options: (() => {
        const o = baseChartOptions("Stale rate (%)", null);
        o.indexAxis = "y";
        o.plugins.legend.display = false;
        o.scales.x.min = 0;
        o.scales.x.max = 100;
        o.scales.x.title = { display: true, text: "Stale rate (%)", color: cssVar("--ink-2") };
        o.scales.y.title = { display: false };
        o.plugins.tooltip = { callbacks: { label: (ctx) => `${ctx.parsed.x.toFixed(1)}% of verified claims changed` } };
        return o;
      })(),
    });
  }
}

async function loadGateway() {
  loaded.gateway = true;
  const out = document.getElementById("gateway-out");
  out.replaceChildren(stateBox("", "Loading gateway summary…"));
  try {
    const summary = await getJSON(ENDPOINTS[DATA_SOURCE].gateway);
    if (!summary || typeof summary !== "object") throw new FetchError("Gateway summary is empty.");
    renderGateway(summary);
  } catch (err) {
    loaded.gateway = false;
    out.replaceChildren(stateBox("error", err.missing ? "No gateway audit yet" : "Gateway summary failed to load", err.message,
      "Run an audit, then reopen this tab."));
  }
}

// ---------- Evidence view ----------

function curveDatasets(curves, split) {
  const set = curves[split] || {};
  const order = ["model_p", "halflife", "model_ts", "class_only", "age_only", "random"];
  return order.filter((m) => Array.isArray(set[m])).map((m) => {
    const style = METHOD_STYLE[m];
    const color = cssVar(style.color);
    return {
      label: METHODS[m],
      data: set[m].map((y) => y * 100),
      borderColor: color,
      backgroundColor: color,
      borderWidth: style.width,
      borderDash: style.dash || [],
      pointRadius: 0,
      tension: 0,
    };
  });
}

function summaryTable(summary, split) {
  const set = summary[split] || {};
  const entries = Object.entries(set).sort((a, b) => b[1].auc - a[1].auc);
  const best = entries.length ? entries[0][0] : null;
  return h("div", { class: "table-wrap" }, h("table", null,
    h("caption", null, "Area under the risk-coverage curve, and share of stale claims caught when searching the top 10 / 25 / 50% of claims"),
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, "Ranking"), h("th", { scope: "col", class: "num" }, "AUC"),
      h("th", { scope: "col", class: "num" }, "Caught @10%"), h("th", { scope: "col", class: "num" }, "@25%"), h("th", { scope: "col", class: "num" }, "@50%"))),
    h("tbody", null, entries.map(([m, v]) => h("tr", { class: m === best ? "best" : null },
      h("th", { scope: "row" }, METHODS[m] || m),
      h("td", { class: "num" }, fmt.num(v.auc, 3)),
      h("td", { class: "num" }, fmt.pct(v.catch_at_10)), h("td", { class: "num" }, fmt.pct(v.catch_at_25)), h("td", { class: "num" }, fmt.pct(v.catch_at_50)))))));
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

function renderJ3(slot, result) {
  if (result.status === "missing") {
    slot.replaceChildren(stateBox("", "Live detector (J3): not yet measured", "Results appear here once the live check run writes its summary file."));
    return;
  }
  if (result.status === "error") {
    slot.replaceChildren(stateBox("error", "Live detector (J3) results failed to load", result.message));
    return;
  }
  const scalars = Object.entries(result.data || {}).filter(([, v]) => v === null || ["string", "number", "boolean"].includes(typeof v));
  slot.replaceChildren(h("div", { class: "table-wrap" }, h("table", null,
    h("caption", null, "Live detector (J3) results"),
    h("tbody", null, scalars.map(([k, v]) => h("tr", null, h("th", { scope: "row" }, k.replace(/_/g, " ")), h("td", null, v === null ? "—" : String(v))))))));
}

function renderEvidence(summary, curves, j3) {
  const out = document.getElementById("evidence-out");
  let split = "test_sample";
  const tableSlot = h("div");
  const countLine = h("p", { class: "hint" });

  const redraw = () => {
    tableSlot.replaceChildren(summary ? summaryTable(summary, split) : stateBox("error", "Summary table unavailable", "summary.json did not load."));
    countLine.textContent = summary ? splitCounts(summary, split) : "";
    if (!curves) return;
    const grid = Array.isArray(curves.grid) ? curves.grid.map((x) => Math.round(x * 100)) : [];
    const options = baseChartOptions("Stale claims caught (%)", "Claims searched, riskiest first (%)");
    options.scales.y.min = 0;
    options.scales.y.max = 100;
    options.scales.x.ticks.maxTicksLimit = 11;
    options.interaction = { mode: "index", intersect: false };
    options.plugins.tooltip = { callbacks: { title: (items) => `search top ${items[0].label}%`, label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(0)}% caught` } };
    drawChart("curve-chart", { type: "line", data: { labels: grid, datasets: curveDatasets(curves, split) }, options });
  };

  const radio = (value, label) => h("label", null,
    h("input", { type: "radio", name: "split", value, checked: value === split }), h("span", null, label));
  const picker = h("fieldset", { class: "segmented", style: { padding: "0" } },
    h("legend", { class: "kicker", style: { position: "absolute", left: "-999px" } }, "Dataset"),
    radio("test_sample", "Model sample (n=300)"), radio("test_full", "Full test set"));
  picker.addEventListener("change", (e) => { split = e.target.value; redraw(); });

  const j3Slot = h("div");
  out.replaceChildren(...[
    h("h2", null, "Does the ranking find stale claims early?"),
    h("p", { class: "section-note" }, "Risk-coverage: search claims from riskiest down; the curve shows what share of the truly stale ones you have caught after searching x% of all claims. Higher and further left is better."),
    picker, countLine,
    curves ? chartSlot("curve-chart", "Line chart of stale claims caught against claims searched, one line per ranking method") : stateBox("error", "Curves unavailable", "curves.json did not load."),
    h("div", { class: "caption-box" },
      h("p", null, h("strong", null, "Plain reading: "), "the model's own probability that a claim is outdated ranks better than the half-life model (AUC 0.826 vs 0.782 on the 300-claim sample). Half-life ordering still beats random, age-only and class-only ranking, and it drives cache TTLs where no model call is made."),
      h("p", null, "The dataset covers four classes only: office holder, software version, policy rate, and timeless controls. It has no prices and no laws.")),
    h("h3", { style: { marginTop: "22px" } }, "Summary"),
    tableSlot,
    summary && summary.cutoff ? h("p", { class: "hint" }, `Half-lives fitted on outcomes before ${summary.cutoff}; every test outcome is a change after that date.`) : null,
    h("h2", null, "Live detector results"),
    j3Slot].filter(Boolean));
  renderJ3(j3Slot, j3);
  redraw();
}

async function loadEvidence() {
  loaded.evidence = true;
  const out = document.getElementById("evidence-out");
  out.replaceChildren(stateBox("", "Loading measured results…"));
  const [summary, curves, j3] = await Promise.allSettled([getJSON(RESULTS.summary), getJSON(RESULTS.curves), getJSON(RESULTS.j3)]);
  if (summary.status === "rejected" && curves.status === "rejected") {
    loaded.evidence = false;
    out.replaceChildren(stateBox("error", "No measured results found", summary.reason.message, curves.reason.message));
    return;
  }
  let j3Result;
  if (j3.status === "fulfilled") j3Result = { status: "ok", data: j3.value };
  else if (j3.reason.missing) j3Result = { status: "missing" };
  else j3Result = { status: "error", message: j3.reason.message };
  renderEvidence(summary.status === "fulfilled" ? summary.value : null, curves.status === "fulfilled" ? curves.value : null, j3Result);
}

// ---------- boot ----------

document.getElementById("source-flag").textContent = DATA_SOURCE === "fixture" ? "data: sample fixtures" : "data: live API";
initCheck();
initTabs();
