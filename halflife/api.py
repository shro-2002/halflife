"""HTTP API and static UI.

    uv run uvicorn halflife.api:app --port 8091

POST /v1/check            AnswerReport for one answer (check mode: every time-sensitive claim verified
                          unless a budget is given). Recorded in the fact ledger.
GET  /v1/gateway/summary  latest gateway audit summary (written by `python -m halflife.gateway.audit`)
GET  /health              liveness, plus whether Bifrost answers
GET  /                    the web UI; /results/* and /fixtures/* are served read-only for it
"""

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
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


class CheckRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    as_of: date | None = Field(default=None, description="Defaults to the runtime model's knowledge cutoff")
    age_basis: Literal["model_cutoff", "cache_write", "explicit_date"] = "model_cutoff"
    budget: int | None = Field(default=None, ge=0, le=MAX_BUDGET)
    answer_model: str | None = Field(default=None, max_length=200)


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


@app.post("/v1/check", response_model=AnswerReport)
async def check(req: CheckRequest) -> AnswerReport:
    s = app.state.settings
    today = datetime.now(UTC).date()
    opts = CheckOptions(as_of=req.as_of or s.model_cutoff, today=today, age_basis=AgeBasis(req.age_basis),
                        budget=req.budget, mode="check", answer_model=req.answer_model)
    try:
        report = await check_answer(req.answer, model=app.state.bifrost, searcher=app.state.searcher,
                                    opts=opts, half_lives=_half_lives(s))
    except Exception as err:  # fail open at the edge: never a stack trace to the client
        log.exception("check failed")
        raise HTTPException(status_code=502, detail={"code": "CHECK_FAILED", "message": type(err).__name__}) from err
    try:
        with Ledger(s.db_path) as ledger:
            ledger.record(report, model=req.answer_model, virtual_key=None)
    except Exception:  # the ledger is best-effort; the user still gets the report
        log.exception("ledger write failed")
        report.errors.append("ledger: write failed")
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
