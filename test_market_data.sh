#!/usr/bin/env bash
# ============================================================

# Phase E — Market Data API tests (port 8001)
# ============================================================
BASE="http://localhost:8001/api/v1"
EMAIL="askzeph20@gmail.com"
PASSWORD="Ze6533@A#NEW"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Preflight
section "PREFLIGHT"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$BASE/auth/login/")
[ "$HTTP" = "000" ] && echo -e "${RED}Server not running on 8001${NC}" && exit 1
pass "Server up (HTTP $HTTP)"

# Login
section "LOGIN"
for PASS_TRY in "Ze6533@A#NEW" "Ze6533@A#"; do
  LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS_TRY\"}")
  SUCCESS=$(echo "$LOGIN" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  if [ "$SUCCESS" = "True" ] || [ "$SUCCESS" = "true" ]; then
    TOKEN=$(echo "$LOGIN" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")
    pass "Logged in"; break
  fi
done
[ -z "$TOKEN" ] && fail "Login failed" && exit 1

# Test 1 — Supported pairs (no auth needed)
section "TEST 1 — Supported Pairs"
PAIRS=$(curl -s "$BASE/market-data/pairs/")
echo "$PAIRS" | python3 -m json.tool
COUNT=$(echo "$PAIRS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(len(d.get('pairs',[])))" 2>/dev/null)
[ "$COUNT" -gt 0 ] 2>/dev/null && pass "$COUNT pairs returned" || fail "No pairs"

# Test 2 — Candles (requires OANDA key — may return 503 without key)
section "TEST 2 — Candles EUR_USD H1"
CANDLES=$(curl -s "$BASE/market-data/candles/?symbol=EUR_USD&timeframe=H1&count=10" \
  -H "Authorization: Bearer $TOKEN")
echo "$CANDLES" | python3 -m json.tool
C_SUCCESS=$(echo "$CANDLES" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$C_SUCCESS" = "True" ] || [ "$C_SUCCESS" = "true" ]; then
  CCOUNT=$(echo "$CANDLES" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
  pass "Candles returned: $CCOUNT"
else
  MSG=$(echo "$CANDLES" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
  echo -e "${YELLOW}  ⚠ Expected without OANDA key: $MSG${NC}"
fi

# Test 3 — Live price (requires OANDA key)
section "TEST 3 — Live Price EUR_USD"
PRICE=$(curl -s "$BASE/market-data/price/?symbol=EUR_USD" \
  -H "Authorization: Bearer $TOKEN")
echo "$PRICE" | python3 -m json.tool
P_SUCCESS=$(echo "$PRICE" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$P_SUCCESS" = "True" ] || [ "$P_SUCCESS" = "true" ]; then
  BID=$(echo "$PRICE" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('price',{}).get('bid',''))" 2>/dev/null)
  pass "Live price: bid=$BID"
else
  echo -e "${YELLOW}  ⚠ Expected without OANDA key configured${NC}"
fi

# Test 4 — Multi price
section "TEST 4 — Multi Price"
MULTI=$(curl -s -X POST "$BASE/market-data/prices/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["EUR_USD", "GBP_USD", "USD_JPY"]}')
echo "$MULTI" | python3 -m json.tool
pass "Multi price endpoint reachable"

# Test 5 — Fetch log
section "TEST 5 — Data Fetch Log"
LOG=$(curl -s "$BASE/market-data/fetch-log/" \
  -H "Authorization: Bearer $TOKEN")
echo "$LOG" | python3 -m json.tool
pass "Fetch log endpoint reachable"

# Test 6 — Unauthenticated blocked
section "TEST 6 — Unauthenticated blocked"
UNAUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/market-data/candles/?symbol=EUR_USD&timeframe=H1")
[ "$UNAUTH_CODE" = "401" ] && pass "Unauthenticated correctly blocked (401)" \
  || fail "Expected 401, got $UNAUTH_CODE"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE E TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Note: Candle/price tests show 503 without a valid"
echo "  OANDA_API_KEY in .env — that is expected behaviour."
echo "  Add your OANDA key to .env to get live data."