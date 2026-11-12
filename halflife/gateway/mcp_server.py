"""`check_freshness` as an MCP tool, served over streamable HTTP and registered in Bifrost's MCP gateway.

    uv run python -m halflife.gateway.mcp_server            # serves http://127.0.0.1:8092/mcp
    uv run python -m halflife.gateway.mcp_server --register # also adds it to Bifrost (POST /api/mcp/client)

Any model behind Bifrost can then call the tool through Bifrost's MCP gateway to check its own draft
answer before replying. The tool runs the same pipeline as POST /v1/check with a verification budget.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime

import uvicorn
from mcp.server.mcpserver import MCPServer

from halflife.clients.bifrost import BifrostClient
from halflife.clients.tavily import DiskCache, TavilyViaRelay
from halflife.config import load_settings
from halflife.pipeline import CheckOptions, check_answer

PORT = 8092
GRANT_TO = ("demo-support-bot", "demo-docs-assistant")
MAX_ANSWER_CHARS = 20_000
server = MCPServer(name="halflife", instructions="Check whether the factual claims in an answer are still current.")


def compact(report) -> dict:
    """What a calling model needs: per-claim verdict, score, corrected value and sources."""
    return {
        "answer_score": report.answer_score,
        "claims": [{"claim": c.claim.text, "class": c.claim.volatility_class.value,
                    "verdict": c.verdict.label.value if c.verdict else None, "freshness_score": c.freshness_score,
                    "score_basis": c.score_basis.value, "current_value": c.verdict.current_value if c.verdict else None,
                    "sources": c.verdict.source_urls if c.verdict else []} for c in report.claims],
        "errors": report.errors,
    }


@server.tool(name="check_freshness", description=(
    "Find time-sensitive factual claims in an answer, verify the riskiest ones against live web sources "
    "(Tavily), and return a 0-100 freshness score per claim with the current value and sources when a claim "
    "is outdated. Use before stating prices, versions, office holders, rates or laws."))
async def check_freshness(answer: str, budget: int = 3) -> str:
    s = load_settings()
    bf = BifrostClient(s)
    try:
        report = await check_answer(answer[:MAX_ANSWER_CHARS], model=bf,
                                    searcher=TavilyViaRelay(bf, s.relay_name, DiskCache(s.cache_dir)),
                                    opts=CheckOptions(as_of=s.model_cutoff, today=datetime.now(UTC).date(),
                                                      budget=max(0, min(budget, 10))))
        return json.dumps(compact(report))
    finally:
        await bf.aclose()


async def register(url: str) -> dict:
    """Idempotently add this server to Bifrost's MCP gateway."""
    bf = BifrostClient(load_settings())
    try:
        existing = await bf.admin("GET", "/api/mcp/clients", params={"search": "halflife"})
        if existing.status_code == 200 and "halflife" in existing.text:
            status = "already registered"
        else:
            body = {"name": "halflife", "connection_type": "http", "connection_string": url, "tools_to_execute": ["*"]}
            resp = await bf.admin("POST", "/api/mcp/client", json=body)
            status = f"registered ({resp.status_code})"
        # Grant the tool to CALLER keys (the demo apps), never to Half-Life's own key: Bifrost injects
        # granted tools into that key's chat calls, and the extractor/judge would start calling the tool.
        keys = (await bf.admin("GET", "/api/governance/virtual-keys")).json().get("virtual_keys") or []
        granted = []
        for k in keys:
            if k["name"] in GRANT_TO:
                await bf.admin("PUT", f"/api/governance/virtual-keys/{k['id']}",
                               json={"mcp_configs": [{"mcp_client_name": "halflife", "tools_to_execute": ["*"]}]})
                granted.append(k["name"])
            elif k["name"] == "halflife-dev" and k.get("mcp_configs"):
                await bf.admin("PUT", f"/api/governance/virtual-keys/{k['id']}", json={"mcp_configs": []})
        return {"status": status, "granted_to": granted}
    finally:
        await bf.aclose()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}/mcp"
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    if args.register:
        async def serve_and_register():
            config = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
            task = asyncio.create_task(config.serve())
            await asyncio.sleep(2)
            print(await register(url))
            await task
        asyncio.run(serve_and_register())
    else:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
