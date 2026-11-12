"""EXPERIMENTAL cache-TTL proxy in front of stock Bifrost (cache profile, needs Redis).

    docker compose up -d redis && BIFROST_PORT=8089 scripts/bifrost.sh cache
    BIFROST_PORT=8089 uv run uvicorn halflife.gateway.proxy:app --port 8093

POST /v1/chat/completions (OpenAI-compatible; pass your Bifrost virtual key in x-bf-vk):
  1. One small Haiku call predicts which volatility class the question depends on.
  2. TTL = time until P(stale) reaches epsilon (0.05) for that class's half-life (ledger fit, else prior).
     Timeless questions get MAX_TTL. The request goes to Bifrost with x-bf-cache-key + x-bf-cache-ttl,
     so Bifrost's own cache plugin stores the answer for exactly that long.
  3. The answer is returned immediately with x-halflife-ttl-seconds / x-halflife-class headers. A
     freshness report is computed in the background and joined to Bifrost's log by x-bifrost-request-id:
     GET /v1/reports/{request_id}.
Experimental because the half-lives are not calibrated (results/2026-11-12-ordering, calibration.json).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import re
from dataclasses import replace
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from halflife.clients.bifrost import BifrostClient
from halflife.clients.tavily import DiskCache, TavilyViaRelay
from halflife.config import load_settings
from halflife.ledger import Ledger
from halflife.pipeline import CheckOptions, check_answer
from halflife.risk import recommended_ttl_days
from halflife.schemas import VolatilityClass

log = logging.getLogger("halflife.proxy")
EPSILON = 0.05
MAX_TTL_S = 30 * 86400
MIN_TTL_S = 60
MAX_REPORTS = 1000
CLASSIFY = """Which kind of fact does a correct answer to this question depend on? Reply with one word from:
software_version, price, rate_or_statistic, office_holder, law_or_regulation, product_spec, timeless.
Question: {q}"""

app = FastAPI(title="Half-Life cache-TTL proxy (experimental)")
_reports: dict[str, dict] = {}  # ponytail: in-memory, bounded; persist if the proxy leaves experimental


def _vk_hash(vk: str) -> str:
    return hashlib.sha256(vk.encode()).hexdigest()[:16]


def cache_key(body: dict, vk: str) -> str:
    """Scoped to the caller's key and every generation parameter (Bifrost also scopes by VK)."""
    params = {k: v for k, v in body.items() if k not in ("stream",)}
    blob = json.dumps({"vk": _vk_hash(vk), "params": params}, sort_keys=True, default=str)
    return "halflife:" + hashlib.sha256(blob.encode()).hexdigest()[:32]


def ttl_seconds(cls: VolatilityClass, half_lives: dict) -> int:
    if cls is VolatilityClass.TIMELESS:
        return MAX_TTL_S
    h = (half_lives.get(cls) or (None,))[0]
    days = recommended_ttl_days(h, EPSILON) if h else None
    return MAX_TTL_S if days is None else max(MIN_TTL_S, min(MAX_TTL_S, int(days * 86400)))


async def predict_class(bf: BifrostClient, question: str) -> VolatilityClass:
    try:
        r = await bf.chat([{"role": "user", "content": CLASSIFY.format(q=question[:2000])}], max_tokens=20)
        word = re.search(r"[a-z_]+", r.text.lower())
        return VolatilityClass(word.group(0)) if word else VolatilityClass.TIMELESS
    except Exception:  # fail open: an unknown class gets the shortest prior half-life's TTL
        return VolatilityClass.SOFTWARE_VERSION


@app.on_event("startup")
async def _startup() -> None:
    app.state.settings = s = load_settings()
    app.state.bf = BifrostClient(s)
    app.state.searcher = TavilyViaRelay(app.state.bf, s.relay_name, DiskCache(s.cache_dir))
    app.state.http = httpx.AsyncClient(base_url=s.bifrost_url, timeout=60)


@app.post("/v1/chat/completions")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    if body.get("stream"):
        raise HTTPException(400, {"code": "STREAMING_UNSUPPORTED", "message": "the experimental proxy is non-streaming"})
    vk = request.headers.get("x-bf-vk") or request.headers.get("authorization", "")
    if not vk:
        raise HTTPException(401, {"code": "UNAUTHORIZED", "message": "send your Bifrost virtual key in x-bf-vk"})
    s = app.state.settings
    # Classification and the background report run on the CALLER's virtual key: Bifrost authenticates
    # it and bills that key; Half-Life's own key is never spent on unauthenticated callers.
    caller_vk = vk.split(" ", 1)[1] if vk.lower().startswith("bearer ") else vk
    bf = BifrostClient(replace(s, virtual_key=caller_vk))
    question = next((m.get("content", "") for m in reversed(body.get("messages") or []) if m.get("role") == "user"), "")
    cls = await predict_class(bf, str(question))
    with Ledger(s.db_path) as ledger:
        half_lives = ledger.half_lives()
    ttl = ttl_seconds(cls, half_lives)
    headers = {"x-bf-cache-key": cache_key(body, caller_vk), "x-bf-cache-ttl": str(ttl), "Content-Type": "application/json"}
    headers["x-bf-vk" if not vk.lower().startswith("bearer") else "Authorization"] = vk
    resp = await app.state.http.post("/v1/chat/completions", content=json.dumps(body), headers=headers)
    rid = resp.headers.get("x-bifrost-request-id", "")
    hit = resp.headers.get("x-bifrost-cache-hit", "").lower() == "true"
    out_headers = {"x-halflife-class": cls.value, "x-halflife-ttl-seconds": str(ttl), "x-halflife-experimental": "ttl",
                   "x-bifrost-request-id": rid, "x-bifrost-cache-hit": "true" if hit else "false"}
    if resp.status_code == 200 and rid and not hit:
        answer = ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        out_headers["x-halflife-report"] = f"/v1/reports/{rid}"
        asyncio.create_task(_report(rid, answer, body.get("model"), bf, _vk_hash(caller_vk)))
    else:
        await bf.aclose()
    return JSONResponse(resp.json(), status_code=resp.status_code, headers=out_headers)


async def _report(rid: str, answer: str, model: str | None, bf: BifrostClient, owner: str) -> None:
    s = app.state.settings
    _reports[rid] = {"status": "pending", "owner": owner}
    try:
        rep = await check_answer(answer, model=bf, searcher=TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir)),
                                 opts=CheckOptions(as_of=s.model_cutoff, today=datetime.now(UTC).date(),
                                                   mode="gateway", answer_model=model, request_id=rid, budget=3))
        _reports[rid] = {"status": "done", "owner": owner, "report": json.loads(rep.model_dump_json())}
    except Exception as err:  # fail open; the answer was already returned
        log.exception("report failed")
        _reports[rid] = {"status": "failed", "owner": owner, "error": type(err).__name__}
    finally:
        await bf.aclose()
    while len(_reports) > MAX_REPORTS:
        _reports.pop(next(iter(_reports)))


@app.get("/v1/reports/{request_id}")
async def report(request_id: str, request: Request) -> JSONResponse:
    vk = request.headers.get("x-bf-vk", "")
    entry = _reports.get(request_id)
    # Same 404 for unknown ids and other callers' reports: ids are not an oracle.
    if not vk or entry is None or not hmac.compare_digest(entry["owner"], _vk_hash(vk)):
        raise HTTPException(404, {"code": "UNKNOWN_REQUEST", "message": "no report for that x-bifrost-request-id"})
    return JSONResponse({k: v for k, v in entry.items() if k != "owner"})
