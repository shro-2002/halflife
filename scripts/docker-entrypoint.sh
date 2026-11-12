#!/usr/bin/env sh
# Container entrypoint: stock Bifrost (base profile) on loopback, one-time setup, then the Half-Life API.
set -eu
npx -y @maximhq/bifrost --transport-version v2.5.1 -app-dir /app/bifrost/base -host 127.0.0.1 \
  -port "$BIFROST_PORT" -log-style json &
for _ in $(seq 1 60); do curl -sf "http://127.0.0.1:$BIFROST_PORT/health" >/dev/null && break; sleep 1; done
uv run --no-dev python -m halflife.clients.setup_gateway
exec uv run --no-dev uvicorn halflife.api:app --host 0.0.0.0 --port 8091 --proxy-headers --forwarded-allow-ips="*"
