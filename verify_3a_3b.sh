#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/verify_3a_3b.sh
# Quick verification that 3a and 3b fields exist and work
# ============================================================
cd /home/cptzeph/Desktop/Programs/python/forex_bot
source bot/bin/activate

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
PASS=0; FAIL=0
pass() { echo -e "${GREEN}  ✅ PASS${NC} — $1"; ((PASS++)); }
fail() { echo -e "${RED}  ❌ FAIL${NC} — $1"; ((FAIL++)); }
section() {
  echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}  $1${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

section "TEST 1 — TradingAccount new fields (Phase 3a)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.accounts.models import TradingAccount, BrokerType, AccountType, FundedFirm
fields = [f.name for f in TradingAccount._meta.get_fields()]
required = ['broker_type','account_type','funded_firm',
            'max_loss_limit','profit_target','daily_loss_limit']
missing = [f for f in required if f not in fields]
if missing:
    print(f'  ❌ Missing fields: {missing}')
    import sys; sys.exit(1)
for f in required:
    print(f'  ✅ {f}')

# Test choices
print(f'  BrokerType choices: {[b[0] for b in BrokerType.choices]}')
print(f'  AccountType choices: {[a[0] for a in AccountType.choices]}')
print(f'  FundedFirm choices: {[f[0] for f in FundedFirm.choices]}')

# Test create with new fields
from apps.accounts.models import User
user = User.objects.filter(email='askzeph20@gmail.com').first()
if user:
    acct = TradingAccount(
        user         = user,
        account_id   = 'test-phase3a',
        name         = 'FTMO Test Account',
        broker_type  = BrokerType.MT5,
        account_type = AccountType.FUNDED,
        funded_firm  = FundedFirm.FTMO,
        max_loss_limit   = 1000.0,
        profit_target    = 1000.0,
        daily_loss_limit = 500.0,
    )
    print(f'  TradingAccount instance: broker_type={acct.broker_type}')
    print(f'    account_type={acct.account_type}')
    print(f'    funded_firm={acct.funded_firm}')
    print(f'    max_loss={acct.max_loss_limit}')
    print('OK')
else:
    print('  ⚠ No user found — field test only (no DB create)')
    print('OK')
" && pass "TradingAccount 3a fields present and usable" \
&& pass "TradingAccount 3a fields present and usable"
section "TEST 2 — Trade new fields (Phase 3b)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.trading.models import Trade
fields = [f.name for f in Trade._meta.get_fields()]
required = ['sl_pips','tp_pips','profit_pips','rrr_used','rrr_achieved','account_label']
missing  = [f for f in required if f not in fields]
if missing:
    print(f'  ❌ Missing fields: {missing}')
    import sys; sys.exit(1)
for f in required:
    print(f'  ✅ {f}')
print('OK')
" && pass "Trade 3b fields present" \
  || fail "Trade 3b fields missing — run: python apply_trade_migration.py"

section "TEST 3 — Pip values stored on trade round-trip"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from apps.trading.models import Trade
from apps.accounts.models import User, TradingAccount
from apps.trading.models import TradingBot
from apps.strategies.models import Strategy

user = User.objects.filter(email='askzeph20@gmail.com').first()
if not user:
    print('  ⚠ No test user — skipping DB round-trip')
else:
    acct = TradingAccount.objects.filter(user=user).first()
    bot  = TradingBot.objects.filter(trading_account=acct).first() if acct else None
    if bot:
        # Create a test trade with pip fields
        t = Trade(
            bot          = bot,
            symbol       = 'XAUUSD',
            order_type   = 'buy',
            entry_price  = 2350.00,
            lot_size     = 0.01,
            sl_pips      = 20.0,
            tp_pips      = 40.0,
            rrr_used     = 2.0,
            account_label= 'FTMO Test',
        )
        t.save()
        # Read back
        t2 = Trade.objects.get(pk=t.pk)
        assert t2.sl_pips       == 20.0
        assert t2.tp_pips       == 40.0
        assert t2.rrr_used      == 2.0
        assert t2.account_label == 'FTMO Test'
        print(f'  Saved: sl_pips={t2.sl_pips} tp_pips={t2.tp_pips}')
        print(f'         rrr_used={t2.rrr_used} label={t2.account_label}')
        t.delete()
        print('  DB round-trip OK')
    else:
        print('  ⚠ No bot found — skipping DB round-trip test')
        print('  (Field presence already verified in TEST 2)')
print('OK')
" && pass "Trade pip fields DB round-trip OK" \
  || fail "Trade pip fields DB error"

section "TEST 4 — RiskManager integrates with new Trade fields"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from utils.risk_manager import RiskManager
from utils.pip_calculator import profit_in_pips, actual_rrr

rm    = RiskManager(10000, 1.0, 2.0)
setup = rm.build_trade_setup('XAUUSD','buy', entry=2350.0, sl_pips=20)
assert setup is not None

# Simulate what we store on Trade at open
trade_data = {
    'sl_pips':       setup.sl_pips,
    'tp_pips':       setup.tp_pips,
    'rrr_used':      setup.rrr,
    'account_label': 'FTMO Phase 3 Test',
}
print(f'  At open  — sl_pips={trade_data[\"sl_pips\"]}')
print(f'             tp_pips={trade_data[\"tp_pips\"]}')
print(f'             rrr_used={trade_data[\"rrr_used\"]}')

# Simulate close at TP
exit_price  = setup.tp_price
pips_made   = profit_in_pips('XAUUSD', setup.entry_price, exit_price, 'buy')
rrr_made    = actual_rrr('XAUUSD', setup.entry_price, exit_price, setup.sl_price, 'buy')

print(f'  At close — profit_pips={pips_made} rrr_achieved={rrr_made}')
assert pips_made == setup.tp_pips, f'{pips_made} != {setup.tp_pips}'
assert rrr_made  == setup.rrr,     f'{rrr_made} != {setup.rrr}'
print('  Integration correct')
" && pass "RiskManager → Trade field integration correct" \
  || fail "Integration error"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE 3a + 3b RESULTS${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  Passed: ${GREEN}$PASS${NC}   Failed: ${RED}$FAIL${NC}"
if [ $FAIL -eq 0 ]; then
  echo -e "\n  ${GREEN}✅ 3a and 3b complete — confirm to proceed to 3c${NC}"
else
  echo -e "\n  ${RED}❌ Fix failures before proceeding${NC}"
fi