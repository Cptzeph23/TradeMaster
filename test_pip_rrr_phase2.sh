#!/usr/bin/env bash
# ============================================================
# Phase 2 — Pip engine + RRR enforcement test suite
# ============================================================
cd /home/cptzeph/Desktop/Programs/python/forex_bot
source bot/bin/activate

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; ((PASS++)); return 0; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; ((FAIL++)); return 0; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "TEST 1 — Constants loaded"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.constants import (
    SYMBOL_CONFIG, SL_PIPS_MAX, SL_PIPS_IDEAL, SL_PIPS_MIN,
    RRR_CHOICES, PRIORITY_SYMBOLS, DEFAULT_RISK_PERCENT
)
assert SYMBOL_CONFIG['XAUUSD']['pip_size'] == 0.01
assert SYMBOL_CONFIG['EURUSD']['pip_size'] == 0.0001
assert SYMBOL_CONFIG['USDJPY']['pip_size'] == 0.01
assert SL_PIPS_MAX   == 50
assert SL_PIPS_IDEAL == 20
assert SL_PIPS_MIN   == 3
assert 'XAUUSD' in PRIORITY_SYMBOLS
print('  SYMBOL_CONFIG entries:', len(SYMBOL_CONFIG))
print('  SL limits: min=%d ideal=%d max=%d' % (SL_PIPS_MIN,SL_PIPS_IDEAL,SL_PIPS_MAX))
print('  RRR choices:', [r[1] for r in RRR_CHOICES])
" && pass "Constants correct" || fail "Constants error"

section "TEST 2 — Pip calculator core functions"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.pip_calculator import (
    get_pip_size, price_to_pips, pips_to_price,
    sl_price_from_pips, tp_price_from_pips,
    tp_from_sl_and_rrr, calculate_lot_size,
    profit_in_pips, actual_rrr,
)
# XAUUSD Gold
assert get_pip_size('XAUUSD') == 0.01
assert price_to_pips('XAUUSD', 0.50) == 50.0
assert pips_to_price('XAUUSD', 20) == 0.20

# EURUSD
assert get_pip_size('EURUSD') == 0.0001
assert price_to_pips('EURUSD', 0.0050) == 50.0

# USDJPY
assert get_pip_size('USDJPY') == 0.01
assert price_to_pips('USDJPY', 0.50) == 50.0

# SL / TP from pips
sl = sl_price_from_pips('EURUSD', 1.1000, 20, 'buy')
tp = tp_price_from_pips('EURUSD', 1.1000, 40, 'buy')
assert sl == 1.09800, f'Expected 1.09800 got {sl}'
assert tp == 1.10400, f'Expected 1.10400 got {tp}'
print(f'  EURUSD BUY: SL={sl} TP={tp}')

# Gold full setup
sl2, tp2, tp_pips = tp_from_sl_and_rrr('XAUUSD', 2350.0, 20, 3.0, 'buy')
assert sl2 == 2349.80, f'Expected 2349.80 got {sl2}'
assert tp2 == 2350.60, f'Expected 2350.60 got {tp2}'
assert tp_pips == 60.0
print(f'  XAUUSD BUY: SL={sl2} TP={tp2} tp_pips={tp_pips}')

# Lot size
lot = calculate_lot_size(10000, 1.0, 20, 'EURUSD')
assert lot == 0.50, f'Expected 0.50 got {lot}'
print(f'  EURUSD lot (10k,1%,20p) = {lot}')

lot_gold = calculate_lot_size(10000, 1.0, 20, 'XAUUSD')
print(f'  XAUUSD lot (10k,1%,20p) = {lot_gold}')

# Profit pips
p = profit_in_pips('EURUSD', 1.1000, 1.1040, 'buy')
assert p == 40.0, f'Expected 40.0 got {p}'

# Actual RRR
r = actual_rrr('EURUSD', 1.1000, 1.1040, 1.0980, 'buy')
assert r == 2.0, f'Expected 2.0 got {r}'
print('  All pip calculations correct')
" && pass "Pip calculator all correct" || fail "Pip calculator error"

section "TEST 3 — RiskManager build_trade_setup"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.risk_manager import RiskManager

rm = RiskManager(account_balance=10000, risk_percent=1.0, rrr=2.0)

# Gold BUY
setup = rm.build_trade_setup('XAUUSD','buy', entry=2350.0, sl_pips=20)
assert setup is not None
assert setup.sl_pips  == 20.0
assert setup.tp_pips  == 40.0
assert setup.rrr      == 2.0
assert setup.sl_price == 2349.80
assert setup.tp_price == 2350.40
assert setup.lot_size  > 0
print(f'  XAUUSD BUY setup: {setup.to_dict()}')

# EURUSD SELL with RRR=3
setup2 = rm.build_trade_setup('EURUSD','sell', entry=1.1000, sl_pips=20, rrr=3.0)
assert setup2.tp_pips == 60.0
assert setup2.rrr_label == '1:3.0'
print(f'  EURUSD SELL RRR=3: tp_pips={setup2.tp_pips} label={setup2.rrr_label}')
" && pass "build_trade_setup correct" || fail "build_trade_setup error"

section "TEST 4 — RiskManager validate_trade"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.risk_manager import RiskManager

rm = RiskManager(account_balance=10000, risk_percent=1.0, rrr=2.0)

# Valid trade
r = rm.validate_trade('EURUSD','buy', entry=1.1000, sl=1.0980, tp=1.1040)
assert r.valid, f'Should be valid: {r.errors}'
assert r.sl_pips == 20.0
assert r.tp_pips == 40.0
assert r.rrr     == 2.0
print(f'  Valid trade: {r.summary}')

# SL too wide (>50 pips)
r2 = rm.validate_trade('EURUSD','buy', entry=1.1000, sl=1.0940, tp=1.1120)
assert not r2.valid
assert any('exceeds maximum' in e for e in r2.errors)
print(f'  SL too wide: {r2.errors[0]}')

# RRR too low
r3 = rm.validate_trade('EURUSD','buy', entry=1.1000, sl=1.0980, tp=1.1010)
assert not r3.valid
assert any('RRR' in e for e in r3.errors)
print(f'  Low RRR: {r3.errors[0]}')

# SL wrong side
r4 = rm.validate_trade('EURUSD','buy', entry=1.1000, sl=1.1020, tp=1.1040)
assert not r4.valid
print(f'  Wrong SL side: {r4.errors[0]}')
" && pass "validate_trade all cases correct" || fail "validate_trade error"

section "TEST 5 — RRR enforcement on signal"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.risk_manager import RiskManager

rm = RiskManager(account_balance=10000, risk_percent=1.0, rrr=2.0)

# Strategy returns SL but bad TP — enforce_rrr recalculates TP
sl, tp, sl_p, tp_p = rm.enforce_rrr_on_signal(
    'EURUSD', 'buy', entry=1.1000, sl_price=1.0980
)
assert sl_p == 20.0
assert tp_p == 40.0
assert tp   == 1.1040
print(f'  Enforced RRR: sl={sl}({sl_p}p) tp={tp}({tp_p}p)')

# adjust_sl_to_max — SL too wide, pull it in
adjusted = rm.adjust_sl_to_max('EURUSD','buy', entry=1.1000, sl_price=1.0940)
from utils.pip_calculator import price_to_pips
pips = price_to_pips('EURUSD', abs(1.1000 - adjusted))
assert pips == 50.0, f'Expected 50.0 got {pips}'
print(f'  Adjusted SL: {adjusted} ({pips}p = max allowed)')
" && pass "RRR enforcement correct" || fail "RRR enforcement error"

section "TEST 6 — PipAwareRiskCalculator integration"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from apps.risk_management.calculator import PipAwareRiskCalculator

calc = PipAwareRiskCalculator(10000, risk_percent=1.0, rrr=2.0)

# build_setup
setup = calc.build_setup('XAUUSD','buy', entry=2350.0, sl_pips=20)
assert setup is not None
print(f'  Setup: {setup.to_dict()}')

# validate
r = calc.validate('EURUSD','buy', 1.1000, sl=1.0980, tp=1.1040)
assert r.valid
print(f'  Validate: {r.summary}')

# lot_size
lot = calc.lot_size('EURUSD', sl_pips=20)
assert lot == 0.50
print(f'  Lot size: {lot}')

# pips helpers
assert calc.pips('EURUSD', 0.0020) == 20.0
assert calc.pip_size('XAUUSD') == 0.01
print(f'  Pip helpers OK')

# profit pips
p = calc.profit_pips('EURUSD', 1.1000, 1.1040, 'buy')
assert p == 40.0
print(f'  Profit pips: {p}')
" && pass "PipAwareRiskCalculator integrated" || fail "PipAwareRiskCalculator error"

section "TEST 7 — SL pip boundary checks"
python3 -c "
import django,os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from utils.risk_manager import RiskManager
rm = RiskManager(10000, 1.0, 2.0)

# Below min (3 pips)
s = rm.build_trade_setup('EURUSD','buy', entry=1.1000, sl_pips=2)
assert s is None, 'Should reject SL < 3 pips'
print('  SL=2p rejected ✓')

# At min (3 pips)
s = rm.build_trade_setup('EURUSD','buy', entry=1.1000, sl_pips=3)
assert s is not None, 'Should accept SL=3 pips'
print('  SL=3p accepted ✓')

# At max (50 pips)
s = rm.build_trade_setup('EURUSD','buy', entry=1.1000, sl_pips=50)
assert s is not None, 'Should accept SL=50 pips'
print('  SL=50p accepted ✓')

# Above max (51 pips)
s = rm.build_trade_setup('EURUSD','buy', entry=1.1000, sl_pips=51)
assert s is None, 'Should reject SL > 50 pips'
print('  SL=51p rejected ✓')

# Warning for > ideal (20 pips) but <= max
s = rm.build_trade_setup('EURUSD','buy', entry=1.1000, sl_pips=30)
assert s is not None
assert any('ideal' in w for w in s.warnings)
print(f'  SL=30p accepted with warning: {s.warnings[0]}')
" && pass "SL boundary checks correct" || fail "SL boundary error"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE 2 RESULTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}   Failed: ${RED}$FAIL${NC}"
echo ""
echo "  Files delivered:"
echo "  utils/constants.py          ← SYMBOL_CONFIG, RRR_CHOICES, SL limits"
echo "  utils/pip_calculator.py     ← get_pip_size, lot_size, profit_pips..."
echo "  utils/risk_manager.py       ← RiskManager, TradeSetup, ValidationResult"
echo "  apps/risk_management/       ← PipAwareRiskCalculator (appended)"
echo "    calculator.py"
if [ $FAIL -eq 0 ]; then
  echo -e "\n  ${GREEN}✅ Phase 2 complete — proceed to Phase 3${NC}"
else
  echo -e "\n  ${RED}❌ $FAIL test(s) failed — fix before proceeding${NC}"
fi
