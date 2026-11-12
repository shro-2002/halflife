#!/usr/bin/env bash
# J0 spike: reproduces every mechanism Half-Life depends on, against stock Bifrost.
# Usage: scripts/spike.sh [base|cache]
#   base  (default): stock Bifrost, no Redis. Cache step is skipped.
#   cache: Bifrost cache profile; run `docker compose up -d redis` first.
# Starts Bifrost if it is not running. Never prints secrets. Raw responses go to .cache/spike/.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
PROFILE="${1:-base}"
B="${BIFROST_URL:-http://localhost:${BIFROST_PORT:-8088}}"
OUT=.cache/spike; mkdir -p "$OUT"
ADMIN=(-u "$BIFROST_ADMIN_USERNAME:$BIFROST_ADMIN_PASSWORD")
MODEL="${HALFLIFE_MODEL:-anthropic/claude-haiku-5-5}"
pass(){ printf '  [ok]   %s\n' "$1"; }
fail(){ printf '  [FAIL] %s\n' "$1"; }

[[ -n "${BIFROST_URL:-}" ]] || scripts/bifrost.sh "$PROFILE"

echo "1. health"
curl -sf "$B/health" >/dev/null && pass "gateway up at $B" || { fail "gateway down"; exit 1; }

echo "2. Anthropic provider key (management API)"
[[ -n "${ANTHROPIC_API_KEY:-}" ]] || { fail "ANTHROPIC_API_KEY empty in .env"; exit 1; }
if curl -sf "${ADMIN[@]}" "$B/api/providers/anthropic" >/dev/null; then
  pass "anthropic provider already configured"
else
  # env. reference: Bifrost reads the key from its own environment; the raw key never crosses the API.
  code=$(curl -s -o "$OUT/provider.json" -w '%{http_code}' "${ADMIN[@]}" -X POST "$B/api/providers" \
    -H 'Content-Type: application/json' \
    -d '{"provider":"anthropic","keys":[{"name":"anthropic-primary","value":"env.ANTHROPIC_API_KEY","models":["*"],"weight":1.0}]}')
  [[ "$code" =~ ^2 ]] && pass "anthropic provider added ($code)" || { fail "add provider -> $code (see $OUT/provider.json)"; exit 1; }
fi

echo "3. virtual key with \$10 budget"
VK=$(curl -s "${ADMIN[@]}" "$B/api/governance/virtual-keys" | python3 -c '
import sys,json
d=json.load(sys.stdin); ks=d.get("virtual_keys",d) if isinstance(d,dict) else d
print(next((k["value"] for k in ks if k.get("name")=="halflife-dev"),""))' 2>/dev/null || true)
if [[ -z "$VK" ]]; then
  curl -s "${ADMIN[@]}" -X POST "$B/api/governance/virtual-keys" -H 'Content-Type: application/json' -d '{
    "name":"halflife-dev","description":"Half-Life build budget",
    "provider_configs":[{"provider":"anthropic","weight":1.0,"allowed_models":["*"],"key_ids":["*"]}],
    "budgets":[{"max_limit":10.00,"reset_duration":"1M"}],"is_active":true}' > "$OUT/vk.json"
  VK=$(python3 -c 'import json;d=json.load(open(".cache/spike/vk.json"));v=d.get("virtual_key",d);print(v.get("value",""))')
fi
[[ -n "$VK" ]] && pass "virtual key halflife-dev ready (value hidden)" || { fail "no VK (see $OUT/vk.json)"; exit 1; }
echo "$VK" > .cache/vk.txt; chmod 600 .cache/vk.txt

echo "4. chat completion through the VK"
curl -s "$B/v1/chat/completions" -H 'Content-Type: application/json' -H "x-bf-vk: $VK" \
  -d "{\"model\":\"$MODEL\",\"max_tokens\":40,\"messages\":[{\"role\":\"user\",\"content\":\"Spike check: reply with the word pong.\"}]}" \
  -D "$OUT/chat.headers" -o "$OUT/chat.json"
python3 -c 'import json;d=json.load(open(".cache/spike/chat.json"));print("  reply:",d["choices"][0]["message"]["content"][:60])' \
  && pass "chat ok" || fail "chat failed (see $OUT/chat.json)"

echo "5. read it back from the logging API"
# Log id == x-bifrost-request-id. Writes are async, so poll the single-row endpoint
# (the list view omits output_message).
LID=$(grep -i '^x-bifrost-request-id' "$OUT/chat.headers" | tr -d '\r' | awk '{print $2}')
for _ in $(seq 1 10); do
  curl -s "${ADMIN[@]}" "$B/api/logs/$LID" > "$OUT/log_detail.json"
  grep -q '"output_message"' "$OUT/log_detail.json" && break; sleep 1
done
python3 - <<'EOF' && pass "request read back from logs" || fail "logs unreadable (see .cache/spike/logs.json)"
import json
l=json.load(open(".cache/spike/log_detail.json")); l=l.get("log",l)
print("  latest:",l["provider"],l["model"],"vk:",l["virtual_key_name"],"cost:",l["cost"])
print("  prompt:",l["input_history"][-1]["content"][:50],"| answer:",l["output_message"]["content"][:30])
EOF

if [[ "$PROFILE" == "cache" ]]; then
echo "6. cache headers: write then hit"
body="{\"model\":\"$MODEL\",\"max_tokens\":400,\"messages\":[{\"role\":\"user\",\"content\":\"Spike cache probe $(date +%s): what is 2+2?\"}]}"
for i in 1 2; do
  curl -s "$B/v1/chat/completions" -H 'Content-Type: application/json' -H "x-bf-vk: $VK" \
    -H 'x-bf-cache-key: halflife-spike' -H 'x-bf-cache-ttl: 120' -d "$body" \
    -D "$OUT/cache$i.headers" -o "$OUT/cache$i.json"
  sleep 1
done
grep -i 'x-bifrost-cache\|cache' "$OUT/cache2.headers" | tr -d '\r' | sed 's/^/  /' || true
python3 - <<'EOF' && pass "second call served from cache" || fail "no cache hit observed (see .cache/spike/cache2.*)"
import json
d=json.load(open(".cache/spike/cache2.json"))
dbg=(d.get("extra_fields") or {}).get("cache_debug") or {}
print("  cache_debug:",dbg)
assert dbg.get("cache_hit") is True
EOF
else
  echo "6. cache headers: skipped (base profile has no Redis; run: docker compose up -d redis && scripts/spike.sh cache)"
fi

echo "7. Tavily search through the Bifrost relay (run 'make setup' once to create it)"
curl -s "$B/relay/tavily/search" -H "x-bf-vk: $VK" -H 'Content-Type: application/json' \
  -d '{"query":"latest stable Python release","search_depth":"basic","max_results":3,"time_range":"year"}' > "$OUT/tavily.json"
python3 -c 'import json;d=json.load(open(".cache/spike/tavily.json"));r=d["results"];print("  results:",len(r),"|",r[0]["url"])' \
  && pass "tavily via relay ok (1 credit; appears in Relay Logs under the VK)" || fail "relay search failed (see $OUT/tavily.json)"
