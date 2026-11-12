"""Deterministic stand-ins for the model and search, for offline tests."""

from collections.abc import Callable
from typing import Any

from halflife.clients.bifrost import ChatResult, ModelError
from halflife.clients.tavily import SearchError, SearchResult

Responder = Callable[[list[dict[str, str]]], str]


class FakeChat:
    """Returns scripted text. `script` is either a list (consumed in order) or a function of messages.

    A scripted value that is an Exception instance is raised instead of returned.
    """

    def __init__(self, script: list[Any] | Responder, *, cost_usd: float = 0.0001) -> None:
        self._script = script
        self._cost = cost_usd
        self.calls: list[list[dict[str, str]]] = []

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 1500, **_: Any) -> ChatResult:
        self.calls.append(messages)
        if callable(self._script):
            out: Any = self._script(messages)
        elif self._script:
            out = self._script.pop(0)
        else:
            raise ModelError("fake script exhausted")
        if isinstance(out, Exception):
            raise out
        return ChatResult(text=out, request_id=f"fake-{len(self.calls)}", provider="fake", model="fake-model",
                          cost_usd=self._cost, latency_ms=1.0)


class FakeSearch:
    """Maps a query substring to a list of Tavily-shaped results. Unmatched queries return []."""

    def __init__(self, table: dict[str, list[dict[str, Any]] | Exception] | None = None) -> None:
        self._table = table or {}
        self.queries: list[tuple[str, dict[str, Any]]] = []

    async def search(self, query: str, **params: Any) -> SearchResult:
        self.queries.append((query, params))
        for needle, results in self._table.items():
            if needle.lower() in query.lower():
                if isinstance(results, Exception):
                    raise results
                return SearchResult({"query": query, **params}, results, False, 1, 1.0)
        return SearchResult({"query": query, **params}, [], False, 1, 1.0)


__all__ = ["FakeChat", "FakeSearch", "ModelError", "SearchError"]
