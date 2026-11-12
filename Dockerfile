# Half-Life API + stock Bifrost (base profile, no Redis) in one container, for a public demo.
# Build:  docker build -t halflife .
# Run:    docker run --env-file .env -e HALFLIFE_RATE_LIMIT_PER_MIN=5 -p 8091:8091 halflife
# Bifrost listens only inside the container (127.0.0.1:8088); only the Half-Life API is published.
FROM node:24.22.1-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv curl ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY halflife ./halflife
COPY web ./web
COPY results ./results
COPY tests/fixtures ./tests/fixtures
COPY bifrost/base/config.json ./bifrost/base/config.json
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
RUN uv sync --frozen --no-dev \
    && npm install -g @maximhq/bifrost@1.6.3 \
    && useradd --create-home app && chown -R app /app
USER app

ENV BIFROST_PORT=8088 HALFLIFE_RATE_LIMIT_PER_MIN=5 HALFLIFE_REPLAY=1 HALFLIFE_LIVE_CHECKS_PER_DAY=20
EXPOSE 8091
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
