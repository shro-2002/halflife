#!/usr/bin/env bash
# Start stock Bifrost for Half-Life.
#   scripts/bifrost.sh          base profile: no Redis (check mode, audit)
#   scripts/bifrost.sh cache    cache profile: needs Redis (docker compose up -d redis), for the TTL proxy
# Reads BIFROST_PORT (default 8088) and admin credentials from .env. Waits for /health.
set -euo pipefail
cd "$(dirname "$0")/.."
CALLER_PORT="${BIFROST_PORT:-}"  # an explicit BIFROST_PORT from the caller wins over .env
set -a; source .env; set +a
PROFILE="${1:-base}"
PORT="${CALLER_PORT:-${BIFROST_PORT:-8088}}"
export BIFROST_PORT="$PORT"
BIFROST_VERSION="${BIFROST_VERSION:-v2.5.1}"
mkdir -p .cache
if curl -sf "http://localhost:$PORT/health" >/dev/null; then
  echo "bifrost already up on :$PORT"; exit 0
fi
nohup npx -y @maximhq/bifrost --transport-version "$BIFROST_VERSION" \
  -app-dir "./bifrost/$PROFILE" -port "$PORT" -log-style pretty > ".cache/bifrost-$PROFILE.log" 2>&1 &
for _ in $(seq 1 60); do
  curl -sf "http://localhost:$PORT/health" >/dev/null && { echo "bifrost ($PROFILE) up on :$PORT"; exit 0; }
  sleep 1
done
echo "bifrost failed to start; see .cache/bifrost-$PROFILE.log" >&2; exit 1
