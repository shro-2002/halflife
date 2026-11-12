.PHONY: dev demo bifrost bifrost-cache setup api api-bg seed audit test spike eval

PORT_API ?= 8091

# Stock Bifrost (no Redis) + one-time setup + the Half-Life API.
dev: bifrost setup api

bifrost:
	scripts/bifrost.sh base

# Cache-TTL proxy only: needs Redis (docker compose up -d redis).
bifrost-cache:
	docker compose up -d redis
	scripts/bifrost.sh cache

setup:
	uv run python -m halflife.clients.setup_gateway
	uv run python -m halflife.ledger import-fit results/2026-11-12-ordering/summary.json

api:
	uv run uvicorn halflife.api:app --port $(PORT_API) --reload

test:
	uv run pytest -q

spike:
	scripts/spike.sh base

eval:
	uv run python -m eval.run --offline

api-bg:
	uv run python -m halflife.serve_bg --port $(PORT_API)

seed:
	uv run python -m halflife.gateway.seed

audit:
	uv run python -m halflife.gateway.audit --hours 6 --sample-cap 50 --budget 60

# One command: stock Bifrost (no Redis) + setup + demo traffic + audit + API/UI in the background.
demo: bifrost setup seed audit api-bg
