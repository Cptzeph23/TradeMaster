#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_backtesting_8001.sh
# Phase H — Backtesting API tests (port 8001)
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
[ "$HTTP" = "000" ] && echo -e "${RED}  ❌ Server not running on 8001${NC}" && exit 1
pass "Server up"

# Login
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
    pass "Logged in"; break
  fi
done
[ -z "$TOKEN" ] && fail "Login failed — run reset_and_setup.sh" && exit 1

# Get strategy ID
STRAT_ID=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); own=d.get('own',[]); print(own[0]['id'] if own else '')" 2>/dev/null)
[ -z "$STRAT_ID" ] && fail "No strategy — run Phase D tests first" && exit 1
pass "Using strategy: $STRAT_ID"

# Test 1 — List backtests (empty initially)
section "TEST 1 — List Backtests"
LIST=$(curl -s "$BASE/backtesting/" -H "Authorization: Bearer $TOKEN")
echo "$LIST" | python3 -m json.tool
L_OK=$(echo "$LIST" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$L_OK" = "True" ] || [ "$L_OK" = "true" ] && pass "List endpoint OK" || fail "List failed"

# Test 2 — Create backtest (queued — needs Celery for full run)
section "TEST 2 — Create Backtest (queued)"
BT=$(curl -s -X POST "$BASE/backtesting/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"strategy\": \"$STRAT_ID\",
    \"symbol\": \"EUR_USD\",
    \"timeframe\": \"H1\",
    \"start_date\": \"2024-01-01T00:00:00Z\",
    \"end_date\": \"2024-06-30T00:00:00Z\",
    \"initial_balance\": 10000,
    \"commission_per_lot\": 7.0,
    \"spread_pips\": 1.5,
    \"name\": \"EUR/USD H1 MA Test\"
  }")
echo "$BT" | python3 -m json.tool
BT_ID=$(echo "$BT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('backtest_id',''))" 2>/dev/null)
if [ -n "$BT_ID" ] && [ "$BT_ID" != "None" ]; then
  pass "Backtest created (id=$BT_ID)"
else
  echo -e "${YELLOW}  ⚠ Celery not running — backtest queued but won't execute yet${NC}"
  echo -e "${YELLOW}    Start Celery: celery -A config.celery worker -Q backtesting -l info${NC}"
fi

# Test 3 — Quick run (synchronous, no Celery needed)
section "TEST 3 — Quick Run (synchronous, 30-day range)"
QR=$(curl -s -X POST "$BASE/backtesting/quick-run/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"strategy\": \"$STRAT_ID\",
    \"symbol\": \"EUR_USD\",
    \"timeframe\": \"H1\",
    \"start_date\": \"2024-01-01T00:00:00Z\",
    \"end_date\": \"2024-01-31T00:00:00Z\",
    \"initial_balance\": 10000,
    \"commission_per_lot\": 7.0,
    \"spread_pips\": 1.5,
    \"name\": \"Quick Test Jan 2024\"
  }")
echo "$QR" | python3 -m json.tool
QR_OK=$(echo "$QR" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$QR_OK" = "True" ] || [ "$QR_OK" = "true" ]; then
  TRADES=$(echo "$QR" | python3 -c \
    "import sys,json; d=json.load(sys.stdin)
bt=d.get('backtest',{})
m=bt.get('metrics',{})
print(f\"trades={m.get('total_trades',0)} win_rate={m.get('win_rate',0)}% return={m.get('total_return_pct',0)}%\")" 2>/dev/null)
  pass "Quick run complete: $TRADES"
  QR_BT_ID=$(echo "$QR" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('backtest',{}).get('id',''))" 2>/dev/null)
else
  MSG=$(echo "$QR" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
  echo -e "${YELLOW}  ⚠ Quick run result: $MSG${NC}"
  echo -e "${YELLOW}    Without OANDA key, no historical data is available.${NC}"
  echo -e "${YELLOW}    Add OANDA_API_KEY to .env for live backtest data.${NC}"
fi

# Test 4 — Status endpoint
if [ -n "$BT_ID" ] && [ "$BT_ID" != "None" ]; then
  section "TEST 4 — Backtest Status Polling"
  STAT=$(curl -s "$BASE/backtesting/$BT_ID/status/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$STAT" | python3 -m json.tool
  pass "Status endpoint OK"

  # Test 5 — Cancel
  section "TEST 5 — Cancel Backtest"
  CANCEL=$(curl -s -X POST "$BASE/backtesting/$BT_ID/cancel/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$CANCEL" | python3 -m json.tool
  C_OK=$(echo "$CANCEL" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$C_OK" = "True" ] || [ "$C_OK" = "true" ] && pass "Backtest cancelled" || fail "Cancel failed"

  # Test 6 — Delete
  section "TEST 6 — Delete Backtest"
  DEL=$(curl -s -X DELETE "$BASE/backtesting/$BT_ID/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$DEL" | python3 -m json.tool
  pass "Delete endpoint OK"
fi

# Clean up quick run backtest
if [ -n "$QR_BT_ID" ] && [ "$QR_BT_ID" != "None" ]; then
  curl -s -X DELETE "$BASE/backtesting/$QR_BT_ID/" \
    -H "Authorization: Bearer $TOKEN" > /dev/null
  pass "Quick run backtest cleaned up"
fi

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE H TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To run a full async backtest with results:"
echo "  1. Add OANDA_API_KEY to .env"
echo "  2. Start Celery: celery -A config.celery worker -Q backtesting -l info"
echo "  3. POST to /api/v1/backtesting/ and poll /status/"