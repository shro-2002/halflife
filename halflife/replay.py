"""Replay mode for public hosting: serve recorded reports and the saved audit; cap live checks per day.

Enable with HALFLIFE_REPLAY=1 (the Docker image sets it). Then:
- POST /v1/check returns a RECORDED report (report.recorded = true, no spend) when the answer is one of the UI's
  example answers; any other answer is a live check, at most HALFLIFE_LIVE_CHECKS_PER_DAY (default 20) per UTC day.
- GET /v1/gateway/summary serves the saved audit (results/2026-11-12-gateway-audit), marked recorded.

Record the example reports (live, small spend):  uv run python -m halflife.replay record
"""

import asyncio
import json
import os
from datetime import UTC, date, datetime

from halflife.config import ROOT
from halflife.schemas import AnswerReport, GatewaySummary

RECORDED_DIR = ROOT / "results" / "2026-11-12-recorded"
EXAMPLES_PATH = RECORDED_DIR / "examples.json"
SAVED_AUDIT = ROOT / "results" / "2026-11-12-gateway-audit" / "summary.json"
# Must match the example answers in web/app.js (EXAMPLES).
EXAMPLE_ANSWERS = {
    "stale": "The Bank of England base rate is 5.25%. The latest LTS release of Node.js is Node 20.",
    "timeless": "Water boils at 100 degrees Celsius at sea level, and the speed of light is about 299,792 km/s.",
    "mixed": "Satya Nadella is the CEO of Microsoft. A Netflix Standard plan costs $15.49 per month.",
}


def enabled() -> bool:
    return os.environ.get("HALFLIFE_REPLAY") == "1"


def daily_cap() -> int:
    return int(os.environ.get("HALFLIFE_LIVE_CHECKS_PER_DAY", "20"))


def per_ip_cap() -> int:
    return int(os.environ.get("HALFLIFE_LIVE_CHECKS_PER_IP_PER_DAY", "5"))


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


class Recorded:
    def __init__(self) -> None:
        data = json.loads(EXAMPLES_PATH.read_text()) if EXAMPLES_PATH.exists() else {}
        self._by_answer = {_norm(v["answer"]): v["report"] for v in data.values()}

    def lookup(self, answer: str) -> AnswerReport | None:
        raw = self._by_answer.get(_norm(answer))
        if raw is None:
            return None
        return AnswerReport.model_validate(raw).model_copy(update={"recorded": True})


def saved_audit() -> GatewaySummary | None:
    if not SAVED_AUDIT.exists():
        return None
    return GatewaySummary.model_validate_json(SAVED_AUDIT.read_text()).model_copy(update={"recorded": True})


class DailyCap:
    """ponytail: in-process counter per UTC day; a multi-replica deployment needs a shared counter."""

    def __init__(self) -> None:
        self.day: date | None = None
        self.used = 0
        self.by_ip: dict[str, int] = {}

    def _roll(self) -> None:
        today = datetime.now(UTC).date()
        if self.day != today:
            self.day, self.used, self.by_ip = today, 0, {}

    def try_take(self, cap: int, ip: str = "", ip_cap: int | None = None) -> bool:
        """Global daily cap plus a per-client quota so one client cannot use everyone's allowance."""
        self._roll()
        if self.used >= cap or (ip_cap is not None and self.by_ip.get(ip, 0) >= ip_cap):
            return False
        self.used += 1  # taken before the check runs, so concurrent requests cannot overshoot
        self.by_ip[ip] = self.by_ip.get(ip, 0) + 1
        return True

    def give_back(self, ip: str = "") -> None:
        """Refund a slot when the live check failed."""
        self.used = max(self.used - 1, 0)
        if self.by_ip.get(ip):
            self.by_ip[ip] -= 1

    def remaining(self, cap: int) -> int:
        self._roll()
        return max(cap - self.used, 0)


async def _record() -> None:
    from halflife.clients.bifrost import BifrostClient
    from halflife.clients.tavily import DiskCache, TavilyViaRelay
    from halflife.config import load_settings
    from halflife.pipeline import CheckOptions, check_answer

    s = load_settings()
    bf = BifrostClient(s)
    searcher = TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir))
    out = {}
    for key, answer in EXAMPLE_ANSWERS.items():
        rep = await check_answer(answer, model=bf, searcher=searcher,
                                 opts=CheckOptions(as_of=s.model_cutoff, today=datetime.now(UTC).date(), answer_model=s.model))
        out[key] = {"answer": answer, "recorded_at": datetime.now(UTC).isoformat(), "report": json.loads(rep.model_dump_json())}
        print(key, [(c.claim.text[:40], c.verdict.label.value if c.verdict else c.score_basis.value) for c in rep.claims])
    await bf.aclose()
    RECORDED_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLES_PATH.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["record"]:
        asyncio.run(_record())
    else:
        print(__doc__)
