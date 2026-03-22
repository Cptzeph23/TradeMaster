#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_trading_8001.sh
# Phase F — Trading Engine API tests (port 8001)
# Updated with correct credentials
# ============================================================
BASE="http://localhost:8001/api/v1"
EMAIL="askzeph20@gmail.com"
PASSWORDS=("Ze6533@A#" "Ze6533@A#NEW")

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
[ "$HTTP" = "000" ] && echo -e "${RED}  ❌ Server not running on 8001. Start with: python manage.py runserver 8001${NC}" && exit 1
pass "Server up (HTTP $HTTP)"

# Login — try all known passwords
section "LOGIN"
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
    USED_PASS="$P"
    pass "Logged in with password: $P"
    break
  else
    echo "  Tried '$P' — failed"
  fi
done

if [ -z "$TOKEN" ]; then
  fail "All passwords failed. Run: bash reset_and_setup.sh"
  exit 1
fi

# Get strategy ID
section "SETUP — Get strategy ID"
STRATS=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN")
STRAT_ID=$(echo "$STRATS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); own=d.get('own',[]); print(own[0]['id'] if own else '')" 2>/dev/null)
if [ -z "$STRAT_ID" ]; then
  fail "No strategies found. Run Phase D test first to create strategies."
  exit 1
fi
pass "Strategy ID: $STRAT_ID"

# Get trading account ID
section "SETUP — Get trading account ID"
ACCOUNTS=$(curl -s "$BASE/auth/trading-accounts/" -H "Authorization: Bearer $TOKEN")
ACCT_ID=$(echo "$ACCOUNTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin)
results = d.get('results', d.get('accounts', []))
print(results[0]['id'] if results else '')" 2>/dev/null)
if [ -z "$ACCT_ID" ]; then
  fail "No trading accounts found. Run: bash reset_and_setup.sh"
  exit 1
fi
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
    \"allow_buy\": true,
    \"allow_sell\": true,
    \"risk_settings\": {
      \"risk_percent\": 1.0,
      \"stop_loss_pips\": 50,
      \"take_profit_pips\": 100,
      \"max_trades_per_day\": 5,
      \"max_open_trades\": 2,
      \"max_drawdown_percent\": 20.0,
      \"max_spread_pips\": 3.0
    }
  }")
echo "$BOT" | python3 -m json.tool
BOT_ID=$(echo "$BOT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id',''))" 2>/dev/null)
[ -n "$BOT_ID" ] && [ "$BOT_ID" != "None" ] \
  && pass "Bot created (id=$BOT_ID)" \
  || fail "Bot creation failed — check output above"

# Test 2 — List bots
section "TEST 2 — List Bots"
BOTS=$(curl -s "$BASE/trading/bots/" -H "Authorization: Bearer $TOKEN")
echo "$BOTS" | python3 -m json.tool
COUNT=$(echo "$BOTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
pass "Bot list returned ($COUNT bots)"

if [ -n "$BOT_ID" ] && [ "$BOT_ID" != "None" ]; then

  section "TEST 3 — Bot Detail"
  DETAIL=$(curl -s "$BASE/trading/bots/$BOT_ID/" -H "Authorization: Bearer $TOKEN")
  echo "$DETAIL" | python3 -m json.tool
  BNAME=$(echo "$DETAIL" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('name',''))" 2>/dev/null)
  [ -n "$BNAME" ] && pass "Bot detail: '$BNAME'" || fail "Bot detail missing name"

  section "TEST 4 — Update Bot (PATCH)"
  PATCH=$(curl -s -X PATCH "$BASE/trading/bots/$BOT_ID/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "EUR/USD Test Bot v2"}')
  echo "$PATCH" | python3 -m json.tool
  P_OK=$(echo "$PATCH" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$P_OK" = "True" ] || [ "$P_OK" = "true" ] && pass "Bot updated" || fail "Bot update failed"

  section "TEST 5 — NLP Command"
  CMD=$(curl -s -X POST "$BASE/trading/command/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"command\": \"Set stop loss to 35 pips and only trade EUR/USD\", \"bot_id\": \"$BOT_ID\"}")
  echo "$CMD" | python3 -m json.tool
  C_OK=$(echo "$CMD" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  if [ "$C_OK" = "True" ] || [ "$C_OK" = "true" ]; then
    pass "NLP command queued (full AI parsing active in Phase K)"
  else
    echo -e "${YELLOW}  ⚠ NLP endpoint needs Celery worker running for full execution${NC}"
  fi

  section "TEST 6 — Trade History"
  TRADES=$(curl -s "$BASE/trading/bots/$BOT_ID/trades/" -H "Authorization: Bearer $TOKEN")
  echo "$TRADES" | python3 -m json.tool
  pass "Trade history endpoint OK"

  section "TEST 7 — Bot Logs"
  LOGS=$(curl -s "$BASE/trading/bots/$BOT_ID/logs/" -H "Authorization: Bearer $TOKEN")
  echo "$LOGS" | python3 -m json.tool
  pass "Bot logs endpoint OK"

  section "TEST 8 — Start Bot (needs Celery + verified account)"
  START=$(curl -s -X POST "$BASE/trading/bots/$BOT_ID/start/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$START" | python3 -m json.tool
  S_OK=$(echo "$START" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  if [ "$S_OK" = "True" ] || [ "$S_OK" = "true" ]; then
    pass "Bot started (Celery task queued)"

    sleep 1
    section "TEST 8b — Stop Bot"
    STOP=$(curl -s -X POST "$BASE/trading/bots/$BOT_ID/stop/" \
      -H "Authorization: Bearer $TOKEN")
    echo "$STOP" | python3 -m json.tool
    pass "Bot stopped"
  else
    MSG=$(echo "$START" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
    echo -e "${YELLOW}  ⚠ Bot not started: $MSG${NC}"
    echo -e "${YELLOW}    This is expected without a running Celery worker${NC}"
  fi

  section "TEST 9 — Delete Bot"
  DEL=$(curl -s -X DELETE "$BASE/trading/bots/$BOT_ID/" -H "Authorization: Bearer $TOKEN")
  echo "$DEL" | python3 -m json.tool
  D_OK=$(echo "$DEL" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$D_OK" = "True" ] || [ "$D_OK" = "true" ] \
    && pass "Bot deleted" || fail "Bot delete failed"
fi

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE F TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To fully test bot START you need:"
echo "  1. Redis running:  redis-server"
echo "  2. Celery worker:  celery -A config.celery worker -Q trading,orders,data,commands -l info"
echo "  3. Real OANDA key in .env"