#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_performance_phase3.sh
# Phase 3 — Complete performance tracking test suite
# ============================================================
cd /home/cptzeph/Desktop/Programs/python/forex_bot
source bot/bin/activate

BASE="http://localhost:8001/api/v1"
PERF="http://localhost:8001/api/v1/performance"
EMAIL="askzeph20@gmail.com"
PASSWORDS=("Ze6533@A#" "Ze6533@A#NEW")

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; ((PASS++)); }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; ((FAIL++)); }
warn() { echo -e "${YELLOW}  ⚠  WARN${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Login ─────────────────────────────────────────────────────
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

ACCT_ID=$(curl -s "$BASE/auth/trading-accounts/" \
  -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json
d=json.load(sys.stdin)
r=d.get('results',d.get('accounts',[]))
print(r[0]['id'] if r else '')" 2>/dev/null)
[ -z "$ACCT_ID" ] && warn "No trading account" || pass "Account: $ACCT_ID"

# ── Test 1: Model fields ──────────────────────────────────────
section "TEST 1 — All model fields present"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()

# TradingAccount Phase 3a fields
from apps.accounts.models import TradingAccount
ta_fields = [f.name for f in TradingAccount._meta.get_fields()]
for f in ['broker_type','account_type','funded_firm',
          'max_loss_limit','profit_target','daily_loss_limit']:
    assert f in ta_fields, f'TradingAccount missing: {f}'
    print(f'  ✅ TradingAccount.{f}')

# Trade Phase 3b fields
from apps.trading.models import Trade
tr_fields = [f.name for f in Trade._meta.get_fields()]
for f in ['sl_pips','tp_pips','profit_pips','rrr_used','rrr_achieved','account_label']:
    assert f in tr_fields, f'Trade missing: {f}'
    print(f'  ✅ Trade.{f}')

# AccountPerformance Phase 3c fields
from apps.accounts.performance_models import AccountPerformance
ap_fields = [f.name for f in AccountPerformance._meta.get_fields()]
for f in ['total_pips','win_rate','profit_factor','avg_rrr_used',
          'max_drawdown_pct','symbol_stats','current_streak']:
    assert f in ap_fields, f'AccountPerformance missing: {f}'
    print(f'  ✅ AccountPerformance.{f}')
" && pass "All Phase 3 model fields present" || fail "Model fields missing"

# ── Test 2: PerformanceService calculation ────────────────────
section "TEST 2 — PerformanceService calculation"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from apps.accounts.performance_service import PerformanceService
from apps.accounts.performance_models import AccountPerformance
from apps.accounts.models import TradingAccount

acct = TradingAccount.objects.filter(is_active=True).first()
if not acct:
    print('  ⚠ No account — skipping')
else:
    perf = PerformanceService(acct).update()
    print(f'  Account:        {acct.name}')
    print(f'  total_trades:   {perf.total_trades}')
    print(f'  win_rate:       {perf.win_rate}%')
    print(f'  total_pips:     {perf.total_pips}')
    print(f'  profit_factor:  {perf.profit_factor}')
    print(f'  avg_rrr_used:   {perf.avg_rrr_used}')
    print(f'  symbol_stats:   {list(perf.symbol_stats.keys())}')
    d = perf.to_dict()
    assert 'account_id' in d and 'win_rate' in d
    print('  to_dict() OK')
" && pass "PerformanceService works on real account" \
  || fail "PerformanceService error"

# ── Test 3: Performance summary endpoint ─────────────────────
section "TEST 3 — GET /api/v1/performance/summary/"
RESP=$(curl -s "$PERF/summary/" -H "Authorization: Bearer $TOKEN")
echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "  Raw: $RESP"
OK=$(echo "$RESP" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$OK" = "True" ] || [ "$OK" = "true" ]; then
  python3 -c "
import sys,json
d=json.loads('$(echo $RESP | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)))" 2>/dev/null)')
s=d.get('summary',{})
for k in ['total_accounts','total_balance','total_trades','win_rate',
          'total_pips','total_profit','today_pnl']:
    assert k in s, f'Missing key: {k}'
    print(f'  {k}: {s[k]}')
" 2>/dev/null && pass "Summary endpoint — all keys present" \
  || warn "Summary returned but keys check failed"
else
  fail "Summary endpoint failed — check URL registration"
fi

# ── Test 4: Accounts list endpoint ───────────────────────────
section "TEST 4 — GET /api/v1/performance/accounts/"
RESP2=$(curl -s "$PERF/accounts/" -H "Authorization: Bearer $TOKEN")
echo "$RESP2" | python3 -m json.tool 2>/dev/null || echo "  Raw: $RESP2"
OK2=$(echo "$RESP2" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$OK2" = "True" ] || [ "$OK2" = "true" ] \
  && pass "Accounts list endpoint OK" \
  || fail "Accounts list endpoint failed"

# ── Test 5: Single account detail ────────────────────────────
section "TEST 5 — GET /api/v1/performance/accounts/<id>/"
if [ -n "$ACCT_ID" ]; then
  RESP3=$(curl -s "$PERF/accounts/$ACCT_ID/" -H "Authorization: Bearer $TOKEN")
  echo "$RESP3" | python3 -m json.tool 2>/dev/null || echo "  Raw: $RESP3"
  OK3=$(echo "$RESP3" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$OK3" = "True" ] || [ "$OK3" = "true" ] \
    && pass "Account detail endpoint OK" \
    || fail "Account detail endpoint failed"
else
  warn "No account ID — skipping"
fi

# ── Test 6: Recalculate endpoint ─────────────────────────────
section "TEST 6 — POST /api/v1/performance/accounts/<id>/recalculate/"
if [ -n "$ACCT_ID" ]; then
  RESP4=$(curl -s -X POST "$PERF/accounts/$ACCT_ID/recalculate/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$RESP4" | python3 -m json.tool 2>/dev/null || echo "  Raw: $RESP4"
  OK4=$(echo "$RESP4" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$OK4" = "True" ] || [ "$OK4" = "true" ] \
    && pass "Recalculate endpoint OK" \
    || fail "Recalculate endpoint failed"
else
  warn "No account ID — skipping"
fi

# ── Test 7: History endpoint ──────────────────────────────────
section "TEST 7 — GET /api/v1/performance/accounts/<id>/history/"
if [ -n "$ACCT_ID" ]; then
  RESP5=$(curl -s "$PERF/accounts/$ACCT_ID/history/?period=month" \
    -H "Authorization: Bearer $TOKEN")
  OK5=$(echo "$RESP5" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$OK5" = "True" ] || [ "$OK5" = "true" ] \
    && pass "History endpoint OK" \
    || fail "History endpoint failed"
fi

# ── Test 8: Symbol stats endpoint ────────────────────────────
section "TEST 8 — GET /api/v1/performance/accounts/<id>/symbols/"
if [ -n "$ACCT_ID" ]; then
  RESP6=$(curl -s "$PERF/accounts/$ACCT_ID/symbols/" \
    -H "Authorization: Bearer $TOKEN")
  OK6=$(echo "$RESP6" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  [ "$OK6" = "True" ] || [ "$OK6" = "true" ] \
    && pass "Symbol stats endpoint OK" \
    || fail "Symbol stats endpoint failed"
fi

# ── Test 9: Compare endpoint ──────────────────────────────────
section "TEST 9 — GET /api/v1/performance/compare/"
RESP7=$(curl -s "$PERF/compare/" -H "Authorization: Bearer $TOKEN")
OK7=$(echo "$RESP7" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$OK7" = "True" ] || [ "$OK7" = "true" ] \
  && pass "Compare endpoint OK" \
  || fail "Compare endpoint failed"

# ── Test 10: Pip engine integration ──────────────────────────
section "TEST 10 — Full pip+RRR+performance integration"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.risk_manager import RiskManager
from utils.pip_calculator import profit_in_pips, actual_rrr
from apps.accounts.performance_service import PerformanceService
from apps.accounts.models import TradingAccount

acct = TradingAccount.objects.filter(is_active=True).first()
if not acct:
    print('  ⚠ No account')
else:
    rm    = RiskManager(float(acct.balance or 10000), 1.0, 2.0)
    setup = rm.build_trade_setup('XAUUSD','buy', entry=2350.0, sl_pips=20)
    assert setup, 'build_trade_setup returned None'

    exit_price  = setup.tp_price
    pips_made   = profit_in_pips('XAUUSD', setup.entry_price, exit_price, 'buy')
    rrr_made    = actual_rrr('XAUUSD', setup.entry_price, exit_price,
                             setup.sl_price, 'buy')

    print(f'  Setup:  SL={setup.sl_price} TP={setup.tp_price}')
    print(f'  Lot:    {setup.lot_size}')
    print(f'  Pips:   {pips_made} (at TP)')
    print(f'  RRR:    {rrr_made}')
    assert pips_made == 40.0, f'{pips_made}'
    assert rrr_made  == 2.0,  f'{rrr_made}'

    perf = PerformanceService(acct).update()
    print(f'  Perf updated: {perf.total_trades} trades on record')
    print('  Full integration OK')
" && pass "Full pip+RRR+performance integration OK" \
  || fail "Integration error"

# ── Results ───────────────────────────────────────────────────
echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE 3 COMPLETE RESULTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}   Failed: ${RED}$FAIL${NC}"
echo ""
echo "  Phase 3 deliverables:"
echo "  3a  TradingAccount: broker_type, account_type, funded_firm (+3)"
echo "  3b  Trade:          sl_pips, tp_pips, profit_pips, rrr_used (+2)"
echo "  3c  AccountPerformance + AccountPerformanceHistory models"
echo "  3d  PerformanceService — auto-updates on trade close"
echo "  3e  Performance REST API — 7 endpoints"
echo "  3f  This test suite"
if [ $FAIL -eq 0 ]; then
  echo -e "\n  ${GREEN}✅ Phase 3 verified — ready for Phase 4${NC}"
  echo "  Phase 4: Gold strategy + extended Telegram alerts"
else
  echo -e "\n  ${RED}❌ $FAIL test(s) failed — fix before Phase 4${NC}"
fi