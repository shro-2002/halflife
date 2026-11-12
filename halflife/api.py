"""HTTP API and static UI.

    uv run uvicorn halflife.api:app --port 8091

POST /v1/check            AnswerReport for one answer (check mode: every time-sensitive claim verified
                          unless a budget is given). Requires `x-halflife-key` when HALFLIFE_API_KEY is
                          set; rate-limited per client IP. NOT recorded in the fact ledger: half-lives
                          are refitted only from the gateway audit, which reads Bifrost's own logs, so
                          ad-hoc callers cannot poison the fit.
GET  /v1/gateway/summary  latest gateway audit summary (written by `python -m halflife.gateway.audit`)
GET  /health              liveness, plus whether Bifrost answers
GET  /                    the web UI; /results/* and /fixtures/* are served read-only for it
"""

import hmac
from dataclasses import replace
import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from halflife.clients.bifrost import BifrostClient
from halflife.clients.tavily import DiskCache, TavilyViaRelay
from halflife.config import ROOT, load_settings
from halflife.ledger import Ledger
from halflife.pipeline import CheckOptions, check_answer
from halflife.schemas import AgeBasis, AnswerReport, GatewaySummary

log = logging.getLogger("halflife.api")
SUMMARY_PATH = ROOT / "data" / "gateway_summary.json"
MAX_ANSWER_CHARS = 20_000
MAX_BUDGET = 20
RATE_LIMIT_PER_MIN = int(os.environ.get("HALFLIFE_RATE_LIMIT_PER_MIN", "10"))
FAILED_AUTH_PER_MIN = 5
# ponytail: in-process sliding windows, per replica; use a shared store if scaled out.
_hits: dict[str, deque[float]] = defaultdict(deque)  # allowed requests, per client
_fails: dict[str, deque[float]] = defaultdict(deque)  # failed auth attempts, per client


def _over_limit(buckets: dict[str, deque[float]], key: str, limit: int, *, record: bool) -> bool:
    now, window = time.monotonic(), buckets[key]
    while window and now - window[0] > 60:
        window.popleft()
    over = len(window) >= limit
    if record and not over:
        window.append(now)
    if not window:
        del buckets[key]  # evict idle clients so state stays bounded
    return over


def _too_many(key: str) -> HTTPException:
    return HTTPException(status_code=429, detail={"code": "RATE_LIMITED", "message": "try again in a minute"},
                         headers={"Retry-After": "60"})


def require_access(request: Request, x_halflife_key: str | None = Header(default=None)) -> None:
    # Client IP as seen by uvicorn; behind a proxy run uvicorn with --proxy-headers --forwarded-allow-ips.
    ip = request.client.host if request.client else "unknown"
    expected = os.environ.get("HALFLIFE_API_KEY", "")
    if expected and not hmac.compare_digest((x_halflife_key or "").encode(), expected.encode()):
        if _over_limit(_fails, ip, FAILED_AUTH_PER_MIN, record=True):
            raise _too_many(ip)
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "missing or bad x-halflife-key"})
    if _over_limit(_hits, ip, RATE_LIMIT_PER_MIN, record=True):
        raise _too_many(ip)


class CheckRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    as_of: date | None = Field(default=None, description="Defaults to the runtime model's knowledge cutoff")
    age_basis: Literal["model_cutoff", "cache_write", "explicit_date"] = "model_cutoff"
    budget: int | None = Field(default=None, ge=0, le=MAX_BUDGET)
    answer_model: str | None = Field(default=None, max_length=200)
    simulate_primary_down: bool = Field(default=False, description="Demo: point the primary model at an unavailable "
                                        "ID so Bifrost's fallback (claude-haiku-4-5) serves the check")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings
    app.state.bifrost = BifrostClient(settings)
    app.state.searcher = TavilyViaRelay(app.state.bifrost, settings.relay_name, DiskCache(settings.cache_dir))
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    yield
    await app.state.bifrost.aclose()


app = FastAPI(title="Half-Life", version="0.1.0", lifespan=lifespan)


def _half_lives(settings) -> dict:
    with Ledger(settings.db_path) as ledger:
        return ledger.half_lives()


@app.post("/v1/check", response_model=AnswerReport, dependencies=[Depends(require_access)])
async def check(req: CheckRequest) -> AnswerReport:
    s = app.state.settings
    today = datetime.now(UTC).date()
    opts = CheckOptions(as_of=req.as_of or s.model_cutoff, today=today, age_basis=AgeBasis(req.age_basis),
                        budget=req.budget, mode="check", answer_model=req.answer_model)
    model = app.state.bifrost
    if req.simulate_primary_down:
        model = BifrostClient(replace(s, model=s.model + "-unavailable"))
    try:
        report = await check_answer(req.answer, model=model, searcher=app.state.searcher,
                                    opts=opts, half_lives=_half_lives(s))
    except Exception as err:  # fail open at the edge: never a stack trace to the client
        log.exception("check failed")
        raise HTTPException(status_code=502, detail={"code": "CHECK_FAILED", "message": type(err).__name__}) from err
    finally:
        if model is not app.state.bifrost:
            await model.aclose()
    return report


@app.get("/v1/gateway/summary", response_model=GatewaySummary)
async def gateway_summary() -> GatewaySummary:
    if not SUMMARY_PATH.exists():
        raise HTTPException(status_code=404, detail={"code": "NO_AUDIT_YET",
                                                     "message": "Run: uv run python -m halflife.gateway.audit"})
    return GatewaySummary.model_validate_json(SUMMARY_PATH.read_text())


@app.get("/health")
async def health() -> JSONResponse:
    try:
        resp = await app.state.bifrost._http.get("/health", timeout=3)
        bifrost = "ok" if resp.status_code == 200 else f"status {resp.status_code}"
    except Exception as err:
        bifrost = f"unreachable: {type(err).__name__}"
    return JSONResponse({"status": "ok", "checks": {"bifrost": bifrost}})


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")


app.mount("/web", StaticFiles(directory=ROOT / "web", check_dir=False), name="web")
app.mount("/results", StaticFiles(directory=ROOT / "results", check_dir=False), name="results")
app.mount("/fixtures", StaticFiles(directory=ROOT / "tests" / "fixtures", check_dir=False), name="fixtures")


def _dump_openapi() -> None:  # handy for docs: python -m halflife.api
    print(json.dumps(app.openapi(), indent=1)[:2000])


if __name__ == "__main__":
    _dump_openapi()
