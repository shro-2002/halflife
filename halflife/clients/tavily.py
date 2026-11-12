"""Tavily search through a Bifrost relay, with an on-disk cache in front.

Order per call: disk cache (free) -> Bifrost relay /relay/<name>/search (1 credit for basic).
The relay holds the Tavily key, applies the virtual key's access and budget, and logs the call
in Bifrost's Relay Logs. Cache key = request payload + UTC date, so a day's evidence is reused
but tomorrow's check searches again.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from halflife.clients.bifrost import BifrostClient

CREDITS_PER_DEPTH = {"basic": 1, "fast": 1, "ultra-fast": 1, "advanced": 2}


class SearchError(RuntimeError):
    """A search failed; callers fail open and record it."""


@dataclass(frozen=True)
class SearchResult:
    payload: dict[str, Any]
    results: list[dict[str, Any]]
    from_cache: bool
    credits: int
    latency_ms: float


class Searcher(Protocol):
    async def search(self, query: str, **params: Any) -> SearchResult: ...


class DiskCache:
    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(payload: dict[str, Any], day: date) -> str:
        blob = json.dumps(payload, sort_keys=True) + day.isoformat()
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._root / f"{key}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        (self._root / f"{key}.json").write_text(json.dumps(value))


class TavilyViaRelay:
    def __init__(self, bifrost: BifrostClient, relay: str, cache: DiskCache, *, offline: bool = False) -> None:
        self._bf = bifrost
        self._relay = relay
        self._cache = cache
        self._offline = offline  # True: cache only, never spend credits (make eval)

    async def search(self, query: str, **params: Any) -> SearchResult:
        payload = {"query": query, "search_depth": "basic", "max_results": 5, "include_usage": True, **params}
        key = DiskCache.key(payload, datetime.now(UTC).date())
        cached = self._cache.get(key)
        if cached is not None:
            return SearchResult(payload, cached.get("results", []), True, 0, 0.0)
        if self._offline:
            raise SearchError("offline mode: no cached evidence for this query")
        started = time.perf_counter()
        try:
            resp = await self._bf.relay_post(self._relay, "/search", payload)
        except Exception as err:  # httpx errors and timeouts alike: fail open upstream
            raise SearchError(f"relay unreachable: {err}") from err
        latency_ms = (time.perf_counter() - started) * 1000
        if resp.status_code != 200:
            raise SearchError(f"relay {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        self._cache.put(key, {"payload": payload, "results": data.get("results", []), "fetched_at": datetime.now(UTC).isoformat()})
        usage = data.get("usage") or {}
        credits = int(usage.get("credits", CREDITS_PER_DEPTH.get(payload["search_depth"], 1)))  # actual, from Tavily
        return SearchResult(payload, data.get("results", []), False, credits, latency_ms)
