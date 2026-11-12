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


def _cost(usage: dict[str, Any]) -> float:
    cost = usage.get("cost") or {}
    return float(cost.get("total_cost") or 0.0) if isinstance(cost, dict) else 0.0


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
            "max_tokens": max_tokens,
            "reasoning_effort": reasoning_effort,
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
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content")
        if not text:
            raise ModelError(f"empty completion (finish_reason={choice.get('finish_reason')})")
        usage = data.get("usage") or {}
        return ChatResult(
            text=text,
            request_id=resp.headers.get("x-bifrost-request-id"),
            provider=resp.headers.get("x-bifrost-provider"),
            model=resp.headers.get("x-bifrost-resolved-model") or data.get("model"),
            cost_usd=_cost(usage),
            latency_ms=latency_ms,
            cache_hit=resp.headers.get("x-bifrost-cache-hit", "").lower() == "true",
            is_fallback=resp.headers.get("x-bifrost-routing-info-is-fallback", "").lower() == "true",
            raw_usage=usage,
        )

    async def list_logs(self, *, limit: int = 50, offset: int = 0, **filters: str) -> list[dict[str, Any]]:
        params = {"limit": limit, "offset": offset, "sort_by": "timestamp", "order": "desc", **filters}
        resp = await self._http.get("/api/logs", params=params, auth=self._admin)
        resp.raise_for_status()
        return resp.json().get("logs") or []

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
