"""Thin async client for a stock Bifrost gateway.

Inference: OpenAI-compatible /v1/chat/completions with the virtual key in x-bf-vk.
Management: /api/* with admin Basic auth (Bifrost v2.x requires it).
Endpoints and headers verified in docs/SPIKE.md.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from halflife.config import Settings


class ModelError(RuntimeError):
    """A model call failed or returned no usable text."""


@dataclass(frozen=True)
class ChatResult:
    text: str
    request_id: str | None
    provider: str | None
    model: str | None
    cost_usd: float
    latency_ms: float
    cache_hit: bool = False
    is_fallback: bool = False
    raw_usage: dict[str, Any] = field(default_factory=dict)


class ChatModel(Protocol):
    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 1500) -> ChatResult: ...


# USD per million tokens (input, output), Anthropic list prices from the models overview, 2026-11-12.
# Bifrost's logged cost for claude-haiku-5-5 matched these exactly (docs/SPIKE.md live run).
LIST_PRICE_PER_MTOK = {"claude-haiku-5-5": (0.10, 0.50), "claude-haiku-4-5": (1.0, 5.0)}


def _cost(usage: dict[str, Any], model: str | None) -> float:
    """Bifrost puts cost in the log row, not the chat response; estimate from tokens at list price."""
    cost = usage.get("cost")
    if isinstance(cost, dict) and cost.get("total_cost") is not None:
        return float(cost["total_cost"])
    price = LIST_PRICE_PER_MTOK.get((model or "").split("/")[-1])
    if not price:
        return 0.0
    return (usage.get("prompt_tokens", 0) * price[0] + usage.get("completion_tokens", 0) * price[1]) / 1e6


class BifrostClient:
    """Implements ChatModel plus the logging API used by the gateway audit."""

    def __init__(self, settings: Settings, *, timeout_s: float = 60.0, log_concurrency: int = 4) -> None:
        self._s = settings
        self._http = httpx.AsyncClient(base_url=settings.bifrost_url, timeout=timeout_s)
        self._admin = httpx.BasicAuth(settings.admin_user, settings.admin_password)
        self._log_sem = asyncio.Semaphore(log_concurrency)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1500,
        reasoning_effort: str = "none",
        extra_headers: dict[str, str] | None = None,
    ) -> ChatResult:
        # reasoning_effort "none" disables Haiku 5.5 thinking through Bifrost (measured: 288 -> 5
        # output tokens on a yes/no probe). Fallback models are tried by Bifrost on provider failure.
        body: dict[str, Any] = {
            "model": self._s.model,
            "messages": messages,
            # Documented fields (V2): max_completion_tokens and reasoning.effort. "none" turns Haiku 5.5
            # thinking off (probe: 288 -> 5 output tokens); also accepted by the Haiku 4.5 fallback.
            "max_completion_tokens": max_tokens,
            "reasoning": {"effort": reasoning_effort},
        }
        if self._s.fallback_models:
            body["fallbacks"] = list(self._s.fallback_models)
        headers = {"x-bf-vk": self._s.virtual_key, **(extra_headers or {})}
        started = time.perf_counter()
        try:
            resp = await self._http.post("/v1/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as err:
            raise ModelError(f"bifrost unreachable: {err}") from err
        latency_ms = (time.perf_counter() - started) * 1000
        if resp.status_code != 200:
            raise ModelError(f"bifrost {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as err:
            raise ModelError(f"bifrost returned non-JSON body: {resp.text[:120]!r}") from err
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content")
        if not text:
            raise ModelError(f"empty completion (finish_reason={choice.get('finish_reason')})")
        usage = data.get("usage") or {}
        served_model = (resp.headers.get("x-bifrost-routing-info-model") or resp.headers.get("x-bifrost-resolved-model")
                        or data.get("model") or self._s.model)
        return ChatResult(
            text=text,
            request_id=resp.headers.get("x-bifrost-request-id"),
            provider=resp.headers.get("x-bifrost-routing-info-provider") or resp.headers.get("x-bifrost-provider"),
            model=served_model,
            cost_usd=_cost(usage, served_model),
            latency_ms=latency_ms,
            cache_hit=resp.headers.get("x-bifrost-cache-hit", "").lower() == "true",
            is_fallback=resp.headers.get("x-bifrost-routing-info-is-fallback", "").lower() == "true",
            raw_usage=usage,
        )

    async def list_logs(self, *, max_rows: int = 200, page_size: int = 100, **filters: str) -> list[dict[str, Any]]:
        """Newest first. roots_only collapses fallback chains (each retry is its own row, linked by
        parent_request_id) so a request counts once. Pages until max_rows or total_count (limit <= 1000)."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < max_rows:
            params = {"limit": min(page_size, max_rows - len(rows)), "offset": offset, "sort_by": "timestamp",
                      "order": "desc", "roots_only": "true", **filters}
            resp = await self._http.get("/api/logs", params=params, auth=self._admin)
            resp.raise_for_status()
            data = resp.json()
            page = data.get("logs") or []
            rows += page
            offset += len(page)
            if not page or offset >= (data.get("pagination") or {}).get("total_count", 0):
                break
        return rows

    async def get_log(self, log_id: str) -> dict[str, Any]:
        """Full row incl. output_message (the list view omits it). Concurrency-limited."""
        async with self._log_sem:
            resp = await self._http.get(f"/api/logs/{log_id}", auth=self._admin)
        resp.raise_for_status()
        data = resp.json()
        return data.get("log", data)

    async def vk_spend_usd(self, vk_name: str = "halflife-dev") -> float:
        """Authoritative spend: the VK budget's current_usage. Chat responses carry no cost field
        (only the log row does), so runs measure spend as the delta of this value."""
        resp = await self.admin("GET", "/api/governance/virtual-keys")
        resp.raise_for_status()
        for vk in resp.json().get("virtual_keys") or []:
            if vk.get("name") == vk_name:
                return float(sum(b.get("current_usage") or 0.0 for b in vk.get("budgets") or []))
        return 0.0

    async def admin(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self._http.request(method, path, auth=self._admin, **kwargs)

    async def relay_post(self, relay: str, path: str, payload: dict[str, Any]) -> httpx.Response:
        return await self._http.post(
            f"/relay/{relay}{path}", json=payload, headers={"x-bf-vk": self._s.virtual_key}
        )
