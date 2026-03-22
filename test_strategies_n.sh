#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_strategies_n.sh
# FIXED: list_slugs + correct instantiation + updated API check
# ============================================================
BASE="http://localhost:8001/api/v1"
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

# Test 1 — Plugin registry (uses list_slugs — correct method name)
section "TEST 1 — Strategy Plugin Registry (9 plugins expected)"
python3 -c "
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.strategies.registry import StrategyRegistry

slugs    = StrategyRegistry.list_slugs()
expected = ['ma_crossover','rsi_reversal','breakout','mean_reversion',
            'ichimoku','macd_divergence','stochastic','ema_ribbon','atr_breakout']

print(f'  Registered plugins ({len(slugs)}):')
for slug in sorted(slugs):
    cls    = StrategyRegistry.get(slug)
    status = '✅' if slug in expected else '⚠'
    print(f'  {status} {slug:25} → {cls.__name__}')

missing = [e for e in expected if e not in slugs]
if missing:
    print(f'  ❌ Missing: {missing}')
    sys.exit(1)
print(f'  ✅ All {len(expected)} plugins registered')
" && pass "All 9 plugins in registry" || fail "Registry check failed"

# Test 2 — Plugins API endpoint
section "TEST 2 — Strategy Plugins API Endpoint"
PLUGINS=$(curl -s "$BASE/strategies/plugins/" -H "Authorization: Bearer $TOKEN")
echo "$PLUGINS" | python3 -m json.tool 2>/dev/null || echo "$PLUGINS"
COUNT=$(echo "$PLUGINS" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(len(d.get('plugins',[])))" 2>/dev/null)
[ "${COUNT:-0}" -ge 9 ] 2>/dev/null \
  && pass "API returns $COUNT plugins" \
  || warn "Got ${COUNT:-0} plugins (expected ≥9)"

# Test 3 — Create strategies via API (requires updated model choices)
section "TEST 3 — Create Strategies for New Plugin Types"
NEW_STRATEGIES=(
  "ichimoku|{\"tenkan_period\":9,\"kijun_period\":26,\"senkou_b_period\":52,\"displacement\":26,\"risk_reward\":1.5}"
  "macd_divergence|{\"fast_period\":12,\"slow_period\":26,\"signal_period\":9,\"lookback\":20,\"risk_reward\":2.0}"
  "stochastic|{\"k_period\":14,\"d_period\":3,\"oversold\":20,\"overbought\":80,\"risk_reward\":2.0}"
  "ema_ribbon|{\"ema_periods\":[8,13,21,34,55],\"adx_threshold\":25,\"risk_reward\":3.0}"
  "atr_breakout|{\"baseline_period\":20,\"channel_mult\":2.0,\"risk_reward\":2.5}"
)

CREATED_IDS=()
for entry in "${NEW_STRATEGIES[@]}"; do
  TYPE="${entry%%|*}"
  PARAMS="${entry#*|}"
  RESULT=$(curl -s -X POST "$BASE/strategies/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"Test $TYPE\",
      \"strategy_type\": \"$TYPE\",
      \"symbols\": [\"EUR_USD\"],
      \"timeframe\": \"H1\",
      \"parameters\": $PARAMS
    }")
  ID=$(echo "$RESULT" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('strategy',{}).get('id',''))" 2>/dev/null)
  if [ -n "$ID" ] && [ "$ID" != "None" ]; then
    pass "Created $TYPE (id=$ID)"
    CREATED_IDS+=("$ID")
  else
    MSG=$(echo "$RESULT" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d.get('message','') or str(d.get('errors','')))" 2>/dev/null)
    fail "Failed to create $TYPE: $MSG"
  fi
done

# Test 4 — Signal generation (FIXED instantiation using self.params pattern)
section "TEST 4 — Signal Generation on Synthetic Data"
python3 << 'PYEOF'
import django, os, sys
import numpy as np
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.strategies.registry import StrategyRegistry

# Generate 300 bars of synthetic trending price data
np.random.seed(42)
n = 300
prices = [1.1000]
for i in range(n - 1):
    prices.append(max(prices[-1] + np.random.normal(0.00005, 0.0008), 0.5))

closes = pd.Series(prices)
highs  = closes + np.abs(np.random.normal(0, 0.0004, n))
lows   = closes - np.abs(np.random.normal(0, 0.0004, n))
opens  = closes.shift(1).fillna(closes.iloc[0])
df     = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})

new_slugs = ['ichimoku','macd_divergence','stochastic','ema_ribbon','atr_breakout']
all_ok    = True

for slug in new_slugs:
    try:
        cls      = StrategyRegistry.get(slug)
        # Correct instantiation: pass dict — BaseStrategy stores as self.params
        strategy = cls(cls.DEFAULT_PARAMETERS.copy())
        signal   = strategy.generate_signal(df, 'EUR_USD')
        print(f'  ✅ {slug:20} → action={signal.action:7} '
              f'strength={signal.strength:.2f}  '
              f'reason={signal.reason[:55]}')
    except Exception as e:
        print(f'  ❌ {slug:20} → ERROR: {e}')
        all_ok = False

sys.exit(0 if all_ok else 1)
PYEOF
[ $? -eq 0 ] && pass "All 5 new plugins generate signals" || fail "Signal generation errors"

# Test 5 — Cleanup
section "CLEANUP"
for ID in "${CREATED_IDS[@]}"; do
  curl -s -X DELETE "$BASE/strategies/$ID/" \
    -H "Authorization: Bearer $TOKEN" > /dev/null
done
[ ${#CREATED_IDS[@]} -gt 0 ] && pass "Test strategies deleted"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE N TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  9 strategy plugins registered:"
echo "  Phase D: ma_crossover, rsi_reversal, breakout, mean_reversion"
echo "  Phase N: ichimoku, macd_divergence, stochastic, ema_ribbon, atr_breakout"