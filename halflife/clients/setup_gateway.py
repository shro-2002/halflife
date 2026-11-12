"""Idempotent setup of the stock Bifrost objects Half-Life needs.

    uv run python -m halflife.clients.setup_gateway

Creates (if missing): the Anthropic provider (key read by Bifrost from env.ANTHROPIC_API_KEY),
a `tavily` relay (key read from env.TAVILY_API_KEY), and the `halflife-dev` virtual key with a
$10 budget and a grant on the relay. Writes the VK value to .cache/vk.txt (mode 600). Prints no secrets.
"""

import asyncio
import os
import sys
from typing import Any

from halflife.clients.bifrost import BifrostClient
from halflife.config import ROOT, load_settings

VK_NAME = "halflife-dev"
BUDGET_USD = float(os.environ.get("HALFLIFE_BUDGET_USD", "10"))

RELAY: dict[str, Any] = {
    "name": "tavily",
    "description": "Tavily web search for Half-Life verification",
    "base_url": "https://api.tavily.com",
    "auth": {"type": "bearer"},
    "credential": {"value": "env.TAVILY_API_KEY"},
    # Free tier: priced at $0 so search does not consume the model budget. An operator on a paid
    # plan sets cost_per_request (e.g. 0.008 per basic credit) and the VK budget then covers both.
    "usage": {"cost_per_request": 0},
    "routes": [{"method": "POST", "path": "/search"}],
}


async def _ensure_provider(bf: BifrostClient) -> str:
    if (await bf.admin("GET", "/api/providers/anthropic")).status_code == 200:
        return "anthropic provider present"
    # Add-provider takes no keys; keys go to /api/providers/{provider}/keys (V2, Bifrost API reference).
    resp = await bf.admin("POST", "/api/providers", json={"provider": "anthropic"})
    resp.raise_for_status()
    key = {"name": "anthropic-primary", "value": "env.ANTHROPIC_API_KEY", "models": ["*"], "weight": 1.0}
    resp = await bf.admin("POST", "/api/providers/anthropic/keys", json=key)
    resp.raise_for_status()
    return "anthropic provider and key added"


async def _ensure_relay(bf: BifrostClient) -> str:
    resp = await bf.admin("GET", "/api/relays", params={"search": RELAY["name"]})
    resp.raise_for_status()
    data = resp.json()
    relays = data.get("relays", data) if isinstance(data, dict) else data
    if any(r.get("name") == RELAY["name"] for r in relays or []):
        return "relay present"
    resp = await bf.admin("POST", "/api/relays", json=RELAY)
    if resp.status_code >= 300:
        raise RuntimeError(f"create relay {resp.status_code}: {resp.text[:300]}")
    return "relay created"


async def _ensure_vk(bf: BifrostClient) -> tuple[str, str]:
    resp = await bf.admin("GET", "/api/governance/virtual-keys")
    resp.raise_for_status()
    keys = resp.json().get("virtual_keys") or []
    existing = next((k for k in keys if k.get("name") == VK_NAME), None)
    grants = [{"relay_name": RELAY["name"]}]
    if existing:
        if {g.get("relay_name") for g in existing.get("relay_grants") or []} != {RELAY["name"]}:
            upd = await bf.admin("PUT", f"/api/governance/virtual-keys/{existing['id']}", json={"relay_grants": grants})
            if upd.status_code >= 300:
                raise RuntimeError(f"grant relay {upd.status_code}: {upd.text[:300]}")
            return existing["value"], "virtual key present, relay granted"
        return existing["value"], "virtual key present"
    body = {
        "name": VK_NAME,
        "description": "Half-Life build budget",
        "provider_configs": [{"provider": "anthropic", "weight": 1.0, "allowed_models": ["*"], "key_ids": ["*"]}],
        "budgets": [{"max_limit": BUDGET_USD, "reset_duration": "1M"}],
        "relay_grants": grants,
        "is_active": True,
    }
    resp = await bf.admin("POST", "/api/governance/virtual-keys", json=body)
    if resp.status_code >= 300:
        raise RuntimeError(f"create vk {resp.status_code}: {resp.text[:300]}")
    vk = resp.json().get("virtual_key", resp.json())
    return vk["value"], "virtual key created"


async def main() -> int:
    bf = BifrostClient(load_settings())
    try:
        print(await _ensure_provider(bf))
        print(await _ensure_relay(bf))
        value, msg = await _ensure_vk(bf)
        print(msg)
        port = os.environ.get("BIFROST_PORT", "8088")
        for vk_file in {ROOT / ".cache" / f"vk-{port}.txt", ROOT / ".cache" / "vk.txt"} if port == "8088" else {ROOT / ".cache" / f"vk-{port}.txt"}:
            vk_file.parent.mkdir(exist_ok=True)
            vk_file.write_text(value)
            vk_file.chmod(0o600)
    finally:
        await bf.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
