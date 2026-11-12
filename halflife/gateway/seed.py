"""Seed DEMO traffic through stock Bifrost so the audit has real requests to show.

    uv run python -m halflife.gateway.seed [--n 40]

Creates two demo virtual keys (`demo-support-bot`, `demo-docs-assistant`, $1 budget each) and sends a
mix of time-sensitive and timeless questions, alternating two models (claude-haiku-5-5, knowledge cutoff
Jun 2026; claude-haiku-4-5, cutoff Feb 2025). Every request carries the log label `x-bf-lh-traffic: demo`
and the keys are prefixed `demo-`, so the UI can mark this as demo traffic. Prints request ids.
"""

import argparse
import asyncio
import json

from halflife.clients.bifrost import BifrostClient
from halflife.config import ROOT, load_settings

DEMO_KEYS = ("demo-support-bot", "demo-docs-assistant")
MODELS = ("anthropic/claude-haiku-5-5", "anthropic/claude-haiku-4-5")
SYSTEM = "Answer in one to three sentences. Be specific: give names, versions, numbers and prices where relevant."
QUESTIONS = [
    "What is the latest stable version of Python?", "Who is the CEO of Intel?",
    "What is the Bank of England base rate?", "How much does Netflix's Standard plan cost in the US?",
    "What is the current LTS version of Node.js?", "Who is the Prime Minister of the United Kingdom?",
    "What is the US federal funds target range?", "What is the latest version of React?",
    "Who chairs the US Federal Reserve?", "What is the annual 401(k) contribution limit?",
    "What does a US Forever stamp cost?", "Who is the Prime Minister of Canada?",
    "What is the ECB deposit facility rate?", "What is the latest Ubuntu LTS release?",
    "When do the EU AI Act's high-risk obligations apply?", "What chip does the newest MacBook Air use?",
    "What is the UK National Living Wage?", "What is the latest stable Go release?",
    "Who is the UN Secretary-General?", "How much is Amazon Prime per month in the US?",
    "What is the boiling point of water at sea level?", "What is the speed of light in vacuum?",
    "Who wrote Pride and Prejudice?", "What is the chemical formula of water?",
    "How many continents are there?", "What year did the Berlin Wall fall?",
    "What is the atomic number of carbon?", "What is Pythagoras' theorem?",
    "Who painted the Mona Lisa?", "How many bones are in the adult human body?",
    "What is the latest TypeScript version?", "Who is the King of Norway?",
    "What is the Bank of Canada policy rate?", "What is the US federal minimum wage?",
    "What is the latest iPhone model?", "What is the Social Security wage base?",
    "What is the capital of Australia?", "What is the freezing point of water in Fahrenheit?",
    "What is the latest Rust version?", "What is the Reserve Bank of India repo rate?",
]


async def ensure_demo_keys(bf: BifrostClient, budget_usd: float = 1.0) -> dict[str, str]:
    resp = await bf.admin("GET", "/api/governance/virtual-keys")
    resp.raise_for_status()
    have = {k["name"]: k["value"] for k in resp.json().get("virtual_keys") or []}
    out = {}
    for name in DEMO_KEYS:
        if name not in have:
            body = {"name": name, "description": "Half-Life DEMO traffic",
                    "provider_configs": [{"provider": "anthropic", "weight": 1.0, "allowed_models": ["*"], "key_ids": ["*"]}],
                    "budgets": [{"max_limit": budget_usd, "reset_duration": "1M"}], "is_active": True}
            r = await bf.admin("POST", "/api/governance/virtual-keys", json=body)
            r.raise_for_status()
            have[name] = r.json().get("virtual_key", r.json())["value"]
        out[name] = have[name]
    return out


async def send(bf: BifrostClient, vk: str, model: str, question: str) -> dict:
    body = {"model": model, "max_completion_tokens": 400, "reasoning": {"effort": "none"},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]}
    r = await bf._http.post("/v1/chat/completions", json=body, headers={"x-bf-vk": vk, "x-bf-lh-traffic": "demo"})
    return {"status": r.status_code, "request_id": r.headers.get("x-bifrost-request-id"), "model": model, "question": question}


async def seed(n: int = 40, questions: list[str] | None = None) -> list[dict]:
    s = load_settings()
    bf = BifrostClient(s)
    keys = await ensure_demo_keys(bf)
    qs = (questions or QUESTIONS)[:n]
    sem = asyncio.Semaphore(4)

    async def one(i: int, q: str):
        vk = keys[DEMO_KEYS[i % 2]]
        model = MODELS[(i // 2) % 2]
        async with sem:
            return await send(bf, vk, model, q)

    sent = await asyncio.gather(*(one(i, q) for i, q in enumerate(qs)))
    await bf.aclose()
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "seeded_requests.json").write_text(json.dumps(sent, indent=1))
    return sent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    sent = asyncio.run(seed(ap.parse_args().n))
    ok = sum(r["status"] == 200 for r in sent)
    print(f"seeded {ok}/{len(sent)} demo requests (ids in data/seeded_requests.json)")


if __name__ == "__main__":
    main()
