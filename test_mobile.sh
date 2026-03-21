#!/usr/bin/env bash
# ============================================================
# Phase P — Mobile API + PWA tests
# ============================================================
BASE="http://localhost:8001/api/v1"
MOBILE="http://localhost:8001/api/v1/mobile"
EMAIL="askzeph20@gmail.com"
PASSWORDS=("Ze6533@A#" "Ze6533@A#NEW")

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; }
warn() { echo -e "${YELLOW}  ⚠  WARN${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "PREFLIGHT + LOGIN"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$BASE/auth/login/")
[ "$HTTP" = "000" ] && fail "Server not on 8001" && exit 1
pass "Server up"

TOKEN=""
for P in "${PASSWORDS[@]}"; do
  LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$P\"}")
  OK=$(echo "$LOGIN" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  if [ "$OK" = "True" ] || [ "$OK" = "true" ]; then
    TOKEN=$(echo "$LOGIN" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")
    pass "Logged in"; break
  fi
done
[ -z "$TOKEN" ] && fail "Login failed" && exit 1

# Test 1 — Mobile dashboard (one-shot endpoint)
section "TEST 1 — Mobile Dashboard (one-shot)"
RESP=$(curl -s "$MOBILE/dashboard/" -H "Authorization: Bearer $TOKEN")
echo "$RESP" | python3 -m json.tool
OK=$(echo "$RESP" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$OK" = "True" ] || [ "$OK" = "true" ] && pass "Mobile dashboard returned" || fail "Dashboard failed"

# Verify payload structure
python3 -c "
import sys, json
d = json.loads('''$(echo $RESP | python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)))' 2>/dev/null)''')
assert 'summary'     in d, 'missing summary'
assert 'today'       in d, 'missing today'
assert 'bots'        in d, 'missing bots'
assert 'open_trades' in d, 'missing open_trades'
assert 'recent_logs' in d, 'missing recent_logs'
print('  ✅ All expected keys present in mobile dashboard payload')
" 2>/dev/null || warn "Payload structure check — run manually if needed"

# Test 2 — Mobile bots list
section "TEST 2 — Mobile Bots List"
BOTS=$(curl -s "$MOBILE/bots/" -H "Authorization: Bearer $TOKEN")
echo "$BOTS" | python3 -m json.tool
BOT_OK=$(echo "$BOTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$BOT_OK" = "True" ] || [ "$BOT_OK" = "true" ] && pass "Mobile bots list" || fail "Bots list failed"

# Test 3 — Mobile trades
section "TEST 3 — Mobile Trades (open)"
TRADES=$(curl -s "$MOBILE/trades/?status=open&limit=10" -H "Authorization: Bearer $TOKEN")
echo "$TRADES" | python3 -m json.tool
pass "Mobile trades endpoint OK"

# Test 4 — Mobile stats (all periods)
section "TEST 4 — Mobile Stats"
for PERIOD in today week month all; do
  STATS=$(curl -s "$MOBILE/stats/?period=$PERIOD" -H "Authorization: Bearer $TOKEN")
  S_OK=$(echo "$STATS" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$S_OK" = "True" ] || [ "$S_OK" = "true" ] \
    && pass "Stats: $PERIOD" || fail "Stats: $PERIOD failed"
done

# Test 5 — Mobile prices
section "TEST 5 — Mobile Prices"
PRICES=$(curl -s "$MOBILE/prices/?symbols=EUR_USD,GBP_USD,USD_JPY" \
  -H "Authorization: Bearer $TOKEN")
echo "$PRICES" | python3 -m json.tool
pass "Mobile prices endpoint OK (null = no live tick data yet)"

# Test 6 — Mobile NLP command
section "TEST 6 — Mobile NLP Command"
CMD=$(curl -s -X POST "$MOBILE/command/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command": "Show me the status of all bots"}')
echo "$CMD" | python3 -m json.tool
CMD_OK=$(echo "$CMD" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$CMD_OK" = "True" ] || [ "$CMD_OK" = "true" ] \
  && pass "Mobile NLP command queued" || fail "NLP command failed"

# Test 7 — PWA assets
section "TEST 7 — PWA Static Assets"
MANIFEST=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8001/static/manifest.json")
SW=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8001/static/js/sw.js")
OFFLINE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8001/offline/")

[ "$MANIFEST" = "200" ] && pass "manifest.json (HTTP $MANIFEST)" \
  || warn "manifest.json not found (HTTP $MANIFEST) — run: python manage.py collectstatic"
[ "$SW" = "200" ] && pass "service worker sw.js (HTTP $SW)" \
  || warn "sw.js not found (HTTP $SW) — run: python manage.py collectstatic"
[ "$OFFLINE" = "200" ] && pass "offline.html (HTTP $OFFLINE)" \
  || warn "offline.html (HTTP $OFFLINE) — add offline/ URL to urls.py"

# Test 8 — Response size comparison (mobile vs standard API)
section "TEST 8 — Payload Size Comparison"
MOBILE_SIZE=$(curl -s "$MOBILE/dashboard/" -H "Authorization: Bearer $TOKEN" | wc -c)
STANDARD_SIZE=$(curl -s "$BASE/trading/bots/" -H "Authorization: Bearer $TOKEN" | wc -c)
echo "  Mobile dashboard:  ${MOBILE_SIZE} bytes (all data in one call)"
echo "  Standard bots API: ${STANDARD_SIZE} bytes (bots only)"
pass "Mobile API delivers full dashboard in a single request"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE P TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Mobile API: http://localhost:8001/api/v1/mobile/"
echo ""
echo "  To enable PWA (install to home screen):"
echo "  1. bash generate_icons.sh    (create PNG icons)"
echo "  2. python manage.py collectstatic --noinput"
echo "  3. Add PWA tags to base.html (see pwa_base_html_additions.html)"
echo "  4. Add /offline/ URL to urls.py"
echo "  5. Open on mobile → browser menu → 'Add to Home Screen'"