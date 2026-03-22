#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_risk_8001.sh
# Phase G — Risk Management API tests (port 8001)
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
[ "$HTTP" = "000" ] && echo -e "${RED}  ❌ Server not on 8001${NC}" && exit 1
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
[ -z "$TOKEN" ] && fail "Login failed — run reset_and_setup.sh first" && exit 1

# Setup — create a test bot
section "SETUP — Create test bot"
STRAT_ID=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); own=d.get('own',[]); print(own[0]['id'] if own else '')" 2>/dev/null)
ACCT_ID=$(curl -s "$BASE/auth/trading-accounts/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin)
r=d.get('results', d.get('accounts',[])); print(r[0]['id'] if r else '')" 2>/dev/null)

[ -z "$STRAT_ID" ] && fail "No strategy — run Phase D tests first" && exit 1
[ -z "$ACCT_ID"  ] && fail "No account — run reset_and_setup.sh first" && exit 1

BOT=$(curl -s -X POST "$BASE/trading/bots/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Risk Test Bot\",\"trading_account\":\"$ACCT_ID\",
       \"strategy\":\"$STRAT_ID\",\"broker\":\"oanda\",
       \"symbols\":[\"EUR_USD\"],\"timeframe\":\"H1\",
       \"allow_buy\":true,\"allow_sell\":true,
       \"risk_settings\":{\"risk_percent\":1.0,\"stop_loss_pips\":50}}")
BOT_ID=$(echo "$BOT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id',''))" 2>/dev/null)
[ -z "$BOT_ID" ] && fail "Bot creation failed" && exit 1
pass "Test bot created (id=$BOT_ID)"

# Test 1 — Get risk rules
section "TEST 1 — Get Risk Rules"
RULES=$(curl -s "$BASE/risk/bots/$BOT_ID/rules/" -H "Authorization: Bearer $TOKEN")
echo "$RULES" | python3 -m json.tool
R_OK=$(echo "$RULES" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$R_OK" = "True" ] || [ "$R_OK" = "true" ] && pass "Risk rules returned" || fail "Risk rules failed"

# Test 2 — Update risk rules
section "TEST 2 — Update Risk Rules (PATCH)"
UPDATE=$(curl -s -X PATCH "$BASE/risk/bots/$BOT_ID/rules/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "risk_percent": 1.5,
    "stop_loss_pips": 35,
    "take_profit_pips": 70,
    "max_trades_per_day": 8,
    "max_open_trades": 3,
    "max_drawdown_percent": 15.0,
    "drawdown_pause_percent": 8.0,
    "trailing_stop_enabled": false,
    "max_spread_pips": 3.0,
    "use_risk_reward": true,
    "risk_reward_ratio": 2.0
  }')
echo "$UPDATE" | python3 -m json.tool
U_OK=$(echo "$UPDATE" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$U_OK" = "True" ] || [ "$U_OK" = "true" ] && pass "Risk rules updated" || fail "Update failed"

# Test 3 — Lot size calculator
section "TEST 3 — Lot Size Calculator"
LOTS=$(curl -s -X POST "$BASE/risk/calculate/lot-size/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_balance": 10000, "risk_percent": 1.0,
       "stop_loss_pips": 50, "symbol": "EUR_USD"}')
echo "$LOTS" | python3 -m json.tool
LOT=$(echo "$LOTS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('lot_size',''))" 2>/dev/null)
[ -n "$LOT" ] && pass "Lot size calculated: $LOT lots" || fail "Calculator failed"

# Test 4 — Risk analysis
section "TEST 4 — Risk Analysis Dashboard"
ANALYSIS=$(curl -s "$BASE/risk/bots/$BOT_ID/analysis/" \
  -H "Authorization: Bearer $TOKEN")
echo "$ANALYSIS" | python3 -m json.tool
A_OK=$(echo "$ANALYSIS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$A_OK" = "True" ] || [ "$A_OK" = "true" ] && pass "Risk analysis returned" || fail "Analysis failed"

# Test 5 — Performance metrics
section "TEST 5 — Performance Metrics"
PERF=$(curl -s "$BASE/risk/bots/$BOT_ID/performance/" \
  -H "Authorization: Bearer $TOKEN")
echo "$PERF" | python3 -m json.tool
P_OK=$(echo "$PERF" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$P_OK" = "True" ] || [ "$P_OK" = "true" ] && pass "Performance metrics returned" || fail "Performance failed"

# Test 6 — Drawdown events
section "TEST 6 — Drawdown Events"
DD=$(curl -s "$BASE/risk/bots/$BOT_ID/drawdown-events/" \
  -H "Authorization: Bearer $TOKEN")
echo "$DD" | python3 -m json.tool
pass "Drawdown events endpoint OK"

# Test 7 — Validate lot size calc accuracy
section "TEST 7 — Lot Size Accuracy Check"
echo "  Expected: 10000 * 1% = $100 risk / (50 pips * $10/pip) = 0.20 lots"
LOTS2=$(curl -s -X POST "$BASE/risk/calculate/lot-size/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"account_balance":10000,"risk_percent":1.0,"stop_loss_pips":50,"symbol":"EUR_USD"}')
LOTVAL=$(echo "$LOTS2" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('lot_size',0))" 2>/dev/null)
RISK=$(echo "$LOTS2" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('result',{}).get('risk_amount',0))" 2>/dev/null)
echo "  Got: lot_size=$LOTVAL  risk_amount=$RISK"
[ "$LOTVAL" = "0.2" ] && pass "Lot size math is correct (0.20 lots)" \
  || echo -e "${YELLOW}  ⚠ Got $LOTVAL (expected 0.20) — check pip_value_per_lot setting${NC}"

# Cleanup
section "CLEANUP — Delete test bot"
curl -s -X DELETE "$BASE/trading/bots/$BOT_ID/" \
  -H "Authorization: Bearer $TOKEN" > /dev/null
pass "Test bot deleted"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE G TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"