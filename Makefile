.PHONY: dev bifrost bifrost-cache setup api test spike eval

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

api:
	uv run uvicorn halflife.api:app --port $(PORT_API) --reload

test:
	uv run pytest -q

spike:
	scripts/spike.sh base

eval:
	uv run python -m eval.run --offline
