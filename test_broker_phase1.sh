#!/usr/bin/env bash
# ============================================================
# Phase 1 — full broker abstraction layer test suite
# ============================================================
cd /home/cptzeph/Desktop/Programs/python/forex_bot
source bot/bin/activate

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m';  NC='\033[0m'
PASS=0; FAIL=0

pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; ((PASS++)); return 0; }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; ((FAIL++)); return 0; }
warn() { echo -e "${YELLOW}  ⚠  WARN${NC} — $1"; }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── Test 1: All imports clean ─────────────────────────────────
section "TEST 1 — All module imports"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.exceptions import (
    BrokerError, BrokerConnectionError, BrokerOrderError,
    BrokerAuthError, BrokerSymbolError, BrokerPositionError,
    BrokerRateLimitError,
)
from services.broker_api.types import (
    AccountInfo, PositionInfo, OrderResult, PriceInfo
)
from services.broker_api.base   import BrokerInterface
from services.broker_api.oanda_service import OandaBroker
from services.broker_api.mt5_service   import MT5Broker
from services.broker_api import get_broker, get_broker_for_bot
print('All imports OK')
" && pass "All imports clean" || fail "Import error — check file placement"

# ── Test 2: Dataclass structures ──────────────────────────────
section "TEST 2 — Dataclass structures"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.types import AccountInfo, PositionInfo, OrderResult, PriceInfo

ai  = AccountInfo(account_id='123', broker='OANDA', balance=10000.0, equity=10050.0)
pi  = PositionInfo(ticket='456', symbol='EURUSD', order_type='buy',
                   volume=0.10, entry_price=1.09234, current_price=1.09300)
oi  = OrderResult(success=True, ticket='789', symbol='EURUSD',
                  order_type='buy', volume=0.10, entry_price=1.09234)
pri = PriceInfo(symbol='EURUSD', bid=1.09230, ask=1.09234)

assert ai.balance == 10000.0
assert ai.is_demo == True
assert oi.failed  == False
assert round(pri.mid, 5) == 1.09232
assert pri.spread_pips   == 0.4

# XAUUSD spread pip check
gold = PriceInfo(symbol='XAUUSD', bid=2350.10, ask=2350.40)
assert gold.spread_pips == 3.0, f'Expected 3.0 got {gold.spread_pips}'

print(f'  AccountInfo:  balance={ai.balance}, is_demo={ai.is_demo}')
print(f'  PositionInfo: {pi.order_type} {pi.volume} {pi.symbol}')
print(f'  OrderResult:  success={oi.success}, failed={oi.failed}')
print(f'  PriceInfo:    mid={pri.mid}, spread_pips={pri.spread_pips}')
print(f'  XAUUSD pips:  {gold.spread_pips}')
print('All assertions passed')
" && pass "Dataclasses correct" || fail "Dataclass assertion failed"

# ── Test 3: BrokerInterface is abstract ───────────────────────
section "TEST 3 — BrokerInterface is abstract"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.base import BrokerInterface
import inspect

# Count abstract methods
abstract = [
    n for n, m in inspect.getmembers(BrokerInterface)
    if getattr(m, '__isabstractmethod__', False)
]
print(f'  Abstract methods ({len(abstract)}): {abstract}')
assert len(abstract) == 11, f'Expected 11 abstract methods, got {len(abstract)}'

# Must raise TypeError
try:
    BrokerInterface({})
    print('  FAIL — should have raised TypeError')
    import sys; sys.exit(1)
except TypeError as e:
    print(f'  Cannot instantiate: {str(e)[:60]}')
print('OK')
" && pass "BrokerInterface correctly abstract (11 methods)" || fail "Abstract class check failed"

# ── Test 4: OandaBroker implements all methods ────────────────
section "TEST 4 — OandaBroker completeness"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.base        import BrokerInterface
from services.broker_api.oanda_service import OandaBroker
import inspect

required = [n for n, m in inspect.getmembers(BrokerInterface)
            if getattr(m, '__isabstractmethod__', False)]
missing  = [n for n in required if not hasattr(OandaBroker, n)]

print(f'  Required: {len(required)}, Missing: {missing if missing else \"none\"}')
assert not missing, f'Missing: {missing}'

b = OandaBroker({'api_key':'test','account_id':'101-001-0000001-001','environment':'practice'})
assert repr(b).startswith('<OandaBroker')
print(f'  Instance: {b}')
print('OK')
" && pass "OandaBroker implements all 11 abstract methods" || fail "OandaBroker incomplete"

# ── Test 5: MT5Broker implements all methods ──────────────────
section "TEST 5 — MT5Broker completeness"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.base      import BrokerInterface
from services.broker_api.mt5_service import MT5Broker
import inspect

required = [n for n, m in inspect.getmembers(BrokerInterface)
            if getattr(m, '__isabstractmethod__', False)]
missing  = [n for n in required if not hasattr(MT5Broker, n)]
print(f'  Required: {len(required)}, Missing: {missing if missing else \"none\"}')
assert not missing, f'Missing: {missing}'

b = MT5Broker({'login':123456,'password':'test','server':'ICMarkets-Demo'})
print(f'  Instance:        {b}')
print(f'  MT5 lib loaded:  {b._mt5 is not None}')
print('OK')
" && pass "MT5Broker implements all 11 abstract methods" || fail "MT5Broker incomplete"

# ── Test 6: get_broker() factory ─────────────────────────────
section "TEST 6 — Broker factory"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api import get_broker
from services.broker_api.oanda_service import OandaBroker
from services.broker_api.mt5_service   import MT5Broker

class FakeAccount:
    def __init__(self, broker_type, account_id='test-123'):
        self.broker_type = broker_type
        self.account_id  = account_id
        self.broker      = broker_type
    def get_api_key(self):
        return 'test-key'

oanda = get_broker(FakeAccount('oanda'))
mt5   = get_broker(FakeAccount('mt5'))
dflt  = get_broker(FakeAccount('unknown'))  # should default to OANDA

assert isinstance(oanda, OandaBroker), f'Got {type(oanda)}'
assert isinstance(mt5,   MT5Broker),   f'Got {type(mt5)}'
assert isinstance(dflt,  OandaBroker), f'Got {type(dflt)}'

print(f'  oanda  → {type(oanda).__name__}')
print(f'  mt5    → {type(mt5).__name__}')
print(f'  unknown→ {type(dflt).__name__} (defaulted to OANDA)')
print('OK')
" && pass "Factory returns correct connector type" || fail "Factory error"

# ── Test 7: Exceptions hierarchy ─────────────────────────────
section "TEST 7 — Exception hierarchy"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.broker_api.exceptions import (
    BrokerError, BrokerConnectionError, BrokerOrderError,
    BrokerAuthError, BrokerSymbolError, BrokerPositionError,
    BrokerRateLimitError,
)
# All must be subclasses of BrokerError
for cls in [BrokerConnectionError, BrokerOrderError, BrokerAuthError,
            BrokerSymbolError, BrokerPositionError, BrokerRateLimitError]:
    assert issubclass(cls, BrokerError), f'{cls} is not a BrokerError subclass'
    print(f'  {cls.__name__:28} ✓ subclass of BrokerError')

# BrokerOrderError carries retcode
e = BrokerOrderError('test', retcode=10004)
assert e.retcode == 10004
print(f'  BrokerOrderError.retcode = {e.retcode}')
print('OK')
" && pass "Exception hierarchy correct" || fail "Exception hierarchy error"

# ── Test 8: OANDA live connection (optional) ──────────────────
section "TEST 8 — OANDA live connection (requires .env)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.conf import settings
api_key = getattr(settings, 'OANDA_API_KEY', '')
acct_id = getattr(settings, 'OANDA_ACCOUNT_ID', '')
env     = getattr(settings, 'OANDA_ENVIRONMENT', 'practice')

if not api_key:
    print('  OANDA_API_KEY not in .env — skipping live test')
    print('  Add these to .env to enable:')
    print('    OANDA_API_KEY=your-personal-access-token')
    print('    OANDA_ACCOUNT_ID=101-001-xxxxxxx-001')
    print('    OANDA_ENVIRONMENT=practice')
else:
    from services.broker_api.oanda_service import OandaBroker
    broker = OandaBroker({'api_key':api_key,'account_id':acct_id,'environment':env})
    ok = broker.connect()
    if ok:
        info = broker.get_account_info()
        print(f'  Connected  : {info.broker}')
        print(f'  Account    : {info.account_id}')
        print(f'  Balance    : {info.balance} {info.currency}')
        print(f'  Equity     : {info.equity}')
        print(f'  Mode       : {\"LIVE\" if info.is_live else \"DEMO\"}')
        broker.disconnect()
        print('  Live test PASSED')
    else:
        print('  Connection failed — check credentials in .env')
"

# ── Test 9: MT5 lib check ─────────────────────────────────────
section "TEST 9 — MT5 library availability"
python3 -c "
try:
    import MetaTrader5 as mt5
    v = getattr(mt5, '__version__', 'unknown')
    print(f'  MetaTrader5 installed — version: {v}')
    print('  MT5 live test available')
except ImportError:
    print('  MetaTrader5 not installed (expected on Linux without Wine)')
    print('  Install on Windows: pip install MetaTrader5')
    print('  Linux alternative:  Wine + MT5 terminal + pip install MetaTrader5')
"

# ── Summary ───────────────────────────────────────────────────
echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE 1 RESULTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}   Failed: ${RED}$FAIL${NC}"
echo ""
echo "  Files in services/broker_api/:"
echo "    exceptions.py    — 7 custom exception classes"
echo "    types.py         — AccountInfo, PositionInfo, OrderResult, PriceInfo"
echo "    base.py          — BrokerInterface (11 abstract methods)"
echo "    oanda_service.py — OandaBroker (OANDA REST v20)"
echo "    mt5_service.py   — MT5Broker (MetaTrader5 Python lib)"
echo "    __init__.py      — get_broker() / get_broker_for_bot() factory"
if [ $FAIL -eq 0 ]; then
  echo -e "\n  ${GREEN}✅ Phase 1 complete — proceed to Phase 2${NC}"
else
  echo -e "\n  ${RED}❌ $FAIL test(s) failed — fix before proceeding${NC}"
fi
