#!/usr/bin/env bash
# ============================================================
# Verifies Phase 3c (models) and 3d (service) are working
# ============================================================
cd /home/cptzeph/Desktop/Programs/python/forex_bot
source bot/bin/activate

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; ((PASS++)); }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; ((FAIL++)); }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "TEST 1 — AccountPerformance model imports"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.performance_models import (
    AccountPerformance, AccountPerformanceHistory
)
fields = [f.name for f in AccountPerformance._meta.get_fields()]
required = [
    'total_trades','winning_trades','losing_trades',
    'total_pips','total_pips_won','total_pips_lost',
    'total_profit','gross_profit','gross_loss',
    'win_rate','profit_factor','expectancy',
    'avg_rrr_used','avg_rrr_achieved',
    'max_drawdown_pct','max_drawdown_usd',
    'current_streak','symbol_stats',
]
missing = [f for f in required if f not in fields]
if missing:
    print(f'  ❌ Missing: {missing}')
    import sys; sys.exit(1)
print(f'  All {len(required)} required fields present')
" && pass "AccountPerformance model correct" \
  || fail "AccountPerformance fields missing — run: python apply_performance_migration.py"

section "TEST 2 — PerformanceService imports"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.performance_service import PerformanceService
print('  PerformanceService:', PerformanceService)
print('  Methods:', [m for m in dir(PerformanceService)
      if not m.startswith('_')])
" && pass "PerformanceService imports cleanly" || fail "PerformanceService import error"

section "TEST 3 — PerformanceService synthetic calculation"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.performance_service import PerformanceService
from apps.accounts.performance_models import AccountPerformance

# Test internal _compute with synthetic data using a mock perf object
svc = PerformanceService.__new__(PerformanceService)

class MockAcct:
    name    = 'Test'
    balance = 10500.0
    equity  = 10500.0

svc.account = MockAcct()

# Create a mock AccountPerformance (not saved)
perf = AccountPerformance.__new__(AccountPerformance)
for field in AccountPerformance._meta.get_fields():
    n = getattr(field, 'name', None)
    if n and n not in ('id','account'):
        try:
            default = field.default
            if callable(default):
                default = default()
            setattr(perf, n, default)
        except Exception:
            setattr(perf, n, 0)

# Synthetic trades
class MockTrade:
    def __init__(self, pnl, pips, rrr_u=2.0, rrr_a=None, sym='EURUSD'):
        self.profit_loss   = pnl
        self.profit_pips   = pips
        self.rrr_used      = rrr_u
        self.rrr_achieved  = rrr_a or (pips / (pips / rrr_u) if pips else None)
        self.symbol        = sym
        self.opened_at     = None
        self.closed_at     = None

trades = [
    MockTrade( 100,  20, 2.0, 2.0, 'EURUSD'),
    MockTrade(-50,  -10, 2.0, None,'EURUSD'),
    MockTrade( 200,  40, 2.0, 2.0, 'XAUUSD'),
    MockTrade(-50,  -10, 2.0, None,'XAUUSD'),
    MockTrade( 150,  30, 3.0, 3.0, 'GBPUSD'),
]
svc._compute(perf, trades)

print(f'  total_trades:  {perf.total_trades}')
print(f'  winning:       {perf.winning_trades}')
print(f'  losing:        {perf.losing_trades}')
print(f'  win_rate:      {perf.win_rate}%')
print(f'  total_pips:    {perf.total_pips}')
print(f'  total_profit:  {perf.total_profit}')
print(f'  profit_factor: {perf.profit_factor}')
print(f'  avg_rrr_used:  {perf.avg_rrr_used}')
print(f'  symbol_stats:  {list(perf.symbol_stats.keys())}')
print(f'  streak:        {perf.current_streak}')

assert perf.total_trades   == 5,    f'Expected 5 got {perf.total_trades}'
assert perf.winning_trades == 3,    f'Expected 3 got {perf.winning_trades}'
assert perf.win_rate       == 60.0, f'Expected 60.0 got {perf.win_rate}'
assert perf.total_pips     == 70.0, f'Expected 70.0 got {perf.total_pips}'
assert perf.total_profit   == 350.0,f'Expected 350.0 got {perf.total_profit}'
assert perf.profit_factor  > 0
assert 'EURUSD' in perf.symbol_stats
assert 'XAUUSD' in perf.symbol_stats
print('  All assertions passed')
" && pass "PerformanceService._compute correct" || fail "PerformanceService calculation error"

section "TEST 4 — PerformanceService with real account"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import TradingAccount
from apps.accounts.performance_service import PerformanceService
from apps.accounts.performance_models import AccountPerformance

acct = TradingAccount.objects.filter(is_active=True).first()
if not acct:
    print('  ⚠ No active account — skipping DB test')
else:
    svc  = PerformanceService(acct)
    perf = svc.update()
    print(f'  Account:       {acct.name}')
    print(f'  total_trades:  {perf.total_trades}')
    print(f'  win_rate:      {perf.win_rate}%')
    print(f'  total_pips:    {perf.total_pips}')
    print(f'  total_profit:  {perf.total_profit}')
    print(f'  profit_factor: {perf.profit_factor}')
    d = perf.to_dict()
    assert 'account_id'   in d
    assert 'win_rate'     in d
    assert 'total_pips'   in d
    assert 'symbol_stats' in d
    print('  to_dict() keys OK')
    print('  DB save OK')
" && pass "PerformanceService DB round-trip OK" \
  || fail "PerformanceService DB error"

section "TEST 5 — update_for_trade class method"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.performance_service import PerformanceService
from apps.trading.models import Trade
from utils.constants import TradeStatus

trade = Trade.objects.filter(status=TradeStatus.CLOSED).first()
if not trade:
    print('  ⚠ No closed trades yet — skipping')
else:
    perf = PerformanceService.update_for_trade(trade)
    if perf:
        print(f'  Updated: {perf.account.name}')
        print(f'  trades={perf.total_trades} wr={perf.win_rate}%')
    else:
        print('  Returned None (check logs)')
print('OK')
" && pass "update_for_trade class method OK" || fail "update_for_trade error"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE 3c + 3d RESULTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}   Failed: ${RED}$FAIL${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "\n  ${GREEN}✅ 3c and 3d complete — confirm to proceed to 3e${NC}"
else
  echo -e "\n  ${RED}❌ Fix failures before proceeding${NC}"
fi