#!/usr/bin/env bash
# ============================================================
# Phase D — Strategy API tests
# Usage: bash test_strategies.sh
# NOTE: Run this in a SECOND terminal while server is running
#       in the first terminal via: python manage.py runserver
# ============================================================

BASE="http://localhost:8001/api/v1"
EMAIL="askzeph20@gmail.com"
PASSWORD="Ze6533@A#NEW"   # updated password from Phase C test

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── 0. Check server is up ────────────────────────────────────
section "PREFLIGHT — Check server is reachable"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$BASE/auth/login/")
if [ "$HTTP" = "000" ]; then
  echo -e "${RED}  ❌ Server is NOT running on localhost:8000${NC}"
  echo -e "${YELLOW}  Start it with: python manage.py runserver${NC}"
  exit 1
fi
pass "Server is up (HTTP $HTTP)"

# ── 1. Login to get token ────────────────────────────────────
section "TEST 1 — Login"

# Try new password first, fall back to original
LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

SUCCESS=$(echo "$LOGIN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success','false'))" 2>/dev/null)

if [ "$SUCCESS" != "True" ] && [ "$SUCCESS" != "true" ]; then
  echo "  New password failed, trying original..."
  PASSWORD="Ze6533@A#"
  LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
  SUCCESS=$(echo "$LOGIN" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success','false'))" 2>/dev/null)
fi

if [ "$SUCCESS" != "True" ] && [ "$SUCCESS" != "true" ]; then
  echo "  Login response: $LOGIN"
  fail "Cannot login — check credentials"
  exit 1
fi

TOKEN=$(echo "$LOGIN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")
pass "Logged in — token obtained"
echo -e "  ${CYAN}Token:${NC} ${TOKEN:0:50}..."

# ── 2. List strategy plugins ─────────────────────────────────
section "TEST 2 — List Strategy Plugins"
PLUGINS=$(curl -s "$BASE/strategies/plugins/" \
  -H "Authorization: Bearer $TOKEN")
echo "$PLUGINS" | python3 -m json.tool
COUNT=$(echo "$PLUGINS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
if [ "$COUNT" -ge 4 ] 2>/dev/null; then
  pass "All $COUNT strategy plugins registered"
else
  fail "Expected 4 plugins, got '$COUNT'"
fi

# ── 3. Create MA Crossover strategy ─────────────────────────
section "TEST 3 — Create MA Crossover Strategy"
MA=$(curl -s -X POST "$BASE/strategies/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "EUR/USD Golden Cross",
    "description": "50/200 EMA crossover on EUR/USD H1",
    "strategy_type": "ma_crossover",
    "parameters": {
      "fast_period": 50,
      "slow_period": 200,
      "ma_type": "EMA",
      "atr_sl_mult": 1.5,
      "atr_tp_mult": 3.0,
      "rsi_filter": true
    },
    "symbols": ["EUR_USD"],
    "timeframe": "H1"
  }')
echo "$MA" | python3 -m json.tool
MA_ID=$(echo "$MA" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('id',''))" 2>/dev/null)
[ -n "$MA_ID" ] && [ "$MA_ID" != "None" ] \
  && pass "MA Crossover strategy created (id=$MA_ID)" \
  || fail "MA Crossover creation failed"

# ── 4. Create RSI Reversal strategy ─────────────────────────
section "TEST 4 — Create RSI Reversal Strategy"
RSI=$(curl -s -X POST "$BASE/strategies/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "RSI Oversold Bounce",
    "strategy_type": "rsi_reversal",
    "parameters": {
      "rsi_period": 14,
      "oversold": 30,
      "overbought": 70,
      "trend_filter": true
    },
    "symbols": ["GBP_USD", "EUR_USD"],
    "timeframe": "H4"
  }')
echo "$RSI" | python3 -m json.tool
RSI_ID=$(echo "$RSI" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('id',''))" 2>/dev/null)
[ -n "$RSI_ID" ] && [ "$RSI_ID" != "None" ] \
  && pass "RSI Reversal strategy created (id=$RSI_ID)" \
  || fail "RSI Reversal creation failed"

# ── 5. Create Breakout strategy ──────────────────────────────
section "TEST 5 — Create Breakout Strategy"
BO=$(curl -s -X POST "$BASE/strategies/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "20-Bar Donchian Breakout",
    "strategy_type": "breakout",
    "parameters": {
      "channel_period": 20,
      "adx_filter": true,
      "adx_threshold": 25,
      "volume_filter": false
    },
    "symbols": ["USD_JPY"],
    "timeframe": "H1"
  }')
echo "$BO" | python3 -m json.tool
BO_ID=$(echo "$BO" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('id',''))" 2>/dev/null)
[ -n "$BO_ID" ] && [ "$BO_ID" != "None" ] \
  && pass "Breakout strategy created (id=$BO_ID)" \
  || fail "Breakout creation failed"

# ── 6. Create Mean Reversion strategy ───────────────────────
section "TEST 6 — Create Mean Reversion Strategy"
MR=$(curl -s -X POST "$BASE/strategies/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "BB Mean Reversion",
    "strategy_type": "mean_reversion",
    "parameters": {
      "bb_period": 20,
      "bb_std": 2.0,
      "rsi_confirm": true,
      "adx_filter": true
    },
    "symbols": ["EUR_USD"],
    "timeframe": "H1"
  }')
echo "$MR" | python3 -m json.tool
MR_ID=$(echo "$MR" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('id',''))" 2>/dev/null)
[ -n "$MR_ID" ] && [ "$MR_ID" != "None" ] \
  && pass "Mean Reversion strategy created (id=$MR_ID)" \
  || fail "Mean Reversion creation failed"

# ── 7. List all strategies ───────────────────────────────────
section "TEST 7 — List My Strategies"
LIST=$(curl -s "$BASE/strategies/" \
  -H "Authorization: Bearer $TOKEN")
echo "$LIST" | python3 -m json.tool
OWN=$(echo "$LIST" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(len(d.get('own',[])))" 2>/dev/null)
pass "Listed strategies — own count: $OWN"

# ── 8. Get strategy detail ───────────────────────────────────
if [ -n "$MA_ID" ] && [ "$MA_ID" != "None" ]; then
  section "TEST 8 — Get Strategy Detail"
  DETAIL=$(curl -s "$BASE/strategies/$MA_ID/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$DETAIL" | python3 -m json.tool
  DNAME=$(echo "$DETAIL" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('name',''))" 2>/dev/null)
  [ "$DNAME" = "EUR/USD Golden Cross" ] \
    && pass "Detail returned correct strategy name" \
    || fail "Unexpected name: '$DNAME'"

  # ── 9. Update strategy ──────────────────────────────────
  section "TEST 9 — Update Strategy (PATCH)"
  PATCH=$(curl -s -X PATCH "$BASE/strategies/$MA_ID/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name": "EUR/USD Golden Cross v2", "parameters": {"fast_period": 21, "slow_period": 200, "ma_type": "EMA"}}')
  echo "$PATCH" | python3 -m json.tool
  PNAME=$(echo "$PATCH" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('name',''))" 2>/dev/null)
  [ "$PNAME" = "EUR/USD Golden Cross v2" ] \
    && pass "Strategy updated to '$PNAME'" \
    || fail "Update may have failed: '$PNAME'"
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE D TEST COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Strategy IDs created:"
echo "  MA Crossover:    $MA_ID"
echo "  RSI Reversal:    $RSI_ID"
echo "  Breakout:        $BO_ID"
echo "  Mean Reversion:  $MR_ID"
echo ""