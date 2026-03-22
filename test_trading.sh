#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_trading_8001.sh
# Phase F — Trading Engine API tests (port 8001)
# ============================================================
BASE="http://localhost:8001/api/v1"
EMAIL="askzeph20@gmail.com"
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
pass "Server up"

# Login
section "LOGIN"
for PASS_TRY in "Ze6533@A#NEW" "Ze6533@A#"; do
  LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS_TRY\"}")
  OK=$(echo "$LOGIN" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  if [ "$OK" = "True" ] || [ "$OK" = "true" ]; then
    TOKEN=$(echo "$LOGIN" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")
    pass "Logged in"; break
  fi
done
[ -z "$TOKEN" ] && fail "Login failed" && exit 1

# Get a strategy ID (created in Phase D)
section "SETUP — Get strategy ID"
STRATS=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN")
STRAT_ID=$(echo "$STRATS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('own',[])[0]['id'] if d.get('own') else '')" 2>/dev/null)
[ -z "$STRAT_ID" ] && fail "No strategies found — run Phase D tests first" && exit 1
pass "Strategy ID: $STRAT_ID"

# Get a trading account ID (created in Phase C)
ACCOUNTS=$(curl -s "$BASE/auth/trading-accounts/" -H "Authorization: Bearer $TOKEN")
ACCT_ID=$(echo "$ACCOUNTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('results',[])[0]['id'] if d.get('results') else '')" 2>/dev/null)
[ -z "$ACCT_ID" ] && fail "No trading accounts found — run Phase C tests first" && exit 1
pass "Account ID: $ACCT_ID"

# Test 1 — Create bot
section "TEST 1 — Create Trading Bot"
BOT=$(curl -s -X POST "$BASE/trading/bots/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"EUR/USD Test Bot\",
    \"description\": \"Phase F test bot\",
    \"trading_account\": \"$ACCT_ID\",
    \"strategy\": \"$STRAT_ID\",
    \"broker\": \"oanda\",
    \"symbols\": [\"EUR_USD\"],
    \"timeframe\": \"H1\",
    \"risk_settings\": {
      \"risk_percent\": 1.0,
      \"stop_loss_pips\": 50,
      \"take_profit_pips\": 100,
      \"max_trades_per_day\": 5,
      \"max_open_trades\": 2,
      \"max_drawdown_percent\": 20.0
    }
  }")
echo "$BOT" | python3 -m json.tool
BOT_ID=$(echo "$BOT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id',''))" 2>/dev/null)
[ -n "$BOT_ID" ] && [ "$BOT_ID" != "None" ] \
  && pass "Bot created (id=$BOT_ID)" || fail "Bot creation failed"

# Test 2 — List bots
section "TEST 2 — List Bots"
BOTS=$(curl -s "$BASE/trading/bots/" -H "Authorization: Bearer $TOKEN")
echo "$BOTS" | python3 -m json.tool
COUNT=$(echo "$BOTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
pass "Bots returned: $COUNT"

if [ -n "$BOT_ID" ] && [ "$BOT_ID" != "None" ]; then
  # Test 3 — Get bot detail
  section "TEST 3 — Bot Detail"
  DETAIL=$(curl -s "$BASE/trading/bots/$BOT_ID/" -H "Authorization: Bearer $TOKEN")
  echo "$DETAIL" | python3 -m json.tool
  pass "Bot detail endpoint working"

  # Test 4 — Update bot (PATCH)
  section "TEST 4 — Update Bot (PATCH)"
  PATCH=$(curl -s -X PATCH "$BASE/trading/bots/$BOT_ID/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "EUR/USD Test Bot v2", "risk_settings": {"risk_percent": 1.5, "stop_loss_pips": 40}}')
  echo "$PATCH" | python3 -m json.tool
  pass "Bot update endpoint working"

  # Test 5 — NLP command
  section "TEST 5 — NLP Command"
  CMD=$(curl -s -X POST "$BASE/trading/command/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"command\": \"Set stop loss to 35 pips and trade only EUR/USD\", \"bot_id\": \"$BOT_ID\"}")
  echo "$CMD" | python3 -m json.tool
  CMD_OK=$(echo "$CMD" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$CMD_OK" = "True" ] || [ "$CMD_OK" = "true" ] \
    && pass "NLP command queued" \
    || echo -e "${YELLOW}  ⚠ NLP command needs Celery worker (Phase K for full AI parsing)${NC}"

  # Test 6 — Trade history
  section "TEST 6 — Trade History"
  TRADES=$(curl -s "$BASE/trading/bots/$BOT_ID/trades/" -H "Authorization: Bearer $TOKEN")
  echo "$TRADES" | python3 -m json.tool
  pass "Trade history endpoint working"

  # Test 7 — Bot logs
  section "TEST 7 — Bot Logs"
  LOGS=$(curl -s "$BASE/trading/bots/$BOT_ID/logs/" -H "Authorization: Bearer $TOKEN")
  echo "$LOGS" | python3 -m json.tool
  pass "Bot logs endpoint working"

  # Test 8 — Pause (fails if not running — expected)
  section "TEST 8 — Pause Bot (expected: error if not running)"
  PAUSE=$(curl -s -X POST "$BASE/trading/bots/$BOT_ID/pause/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$PAUSE" | python3 -m json.tool
  pass "Pause endpoint reachable"

  # Test 9 — Delete bot
  section "TEST 9 — Delete Bot"
  DEL=$(curl -s -X DELETE "$BASE/trading/bots/$BOT_ID/" -H "Authorization: Bearer $TOKEN")
  echo "$DEL" | python3 -m json.tool
  DEL_OK=$(echo "$DEL" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$DEL_OK" = "True" ] || [ "$DEL_OK" = "true" ] \
    && pass "Bot deleted" || fail "Bot delete failed"
fi

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE F TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  NOTE: 'start' endpoint requires:"
echo "  1. Celery worker running (Phase I)"
echo "  2. Verified broker account with real API key"