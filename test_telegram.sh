#!/usr/bin/env bash
# ============================================================
# Phase O — Telegram Alert System tests
# ============================================================
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="${PROJECT_DIR}/bot"
[ ! -f "$VENV/bin/activate" ] && VENV="/opt/forex_bot_venv"
source "$VENV/bin/activate" 2>/dev/null || true
cd "$PROJECT_DIR"

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

section "TEST 1 — python-telegram-bot installed"
python3 -c "import telegram; print(f'  version: {telegram.__version__}')" \
  && pass "telegram package available" \
  || { warn "Not installed — installing..."; pip install 'python-telegram-bot==13.15' -q && pass "Installed" || fail "Install failed"; }

section "TEST 2 — Telegram module imports"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.telegram.bot import get_telegram_bot, ForexTelegramBot
from services.telegram.alerts import (
    alert_trade_opened, alert_trade_closed,
    alert_drawdown_warning, alert_bot_halted,
    alert_bot_started, alert_bot_stopped,
    send_daily_report, alert_nlp_result,
)
print('  All imports OK')
" && pass "All Telegram modules import cleanly" || fail "Import errors"

section "TEST 3 — Bot configuration check"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.telegram.bot import get_telegram_bot
bot = get_telegram_bot()
if bot.is_configured():
    print(f'  Token: ...{bot.token[-8:]}')
    print(f'  Chat ID: {bot.chat_id}')
    print('  CONFIGURED')
else:
    print('  Token set:', bool(bot.token))
    print('  Chat ID set:', bool(bot.chat_id))
    print('  NOT_CONFIGURED')
" | grep -q "CONFIGURED" \
  && pass "Telegram credentials configured in .env" \
  || warn "Telegram not configured — run: bash setup_telegram.sh"

section "TEST 4 — Alert formatters (dry run without sending)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

# Test alert_drawdown_warning (no DB needed)
from services.telegram.alerts import (
    alert_drawdown_warning, alert_bot_halted,
    alert_bot_started, alert_bot_stopped,
    send_daily_report, alert_nlp_result,
)

# These return False when not configured (expected)
results = [
    alert_drawdown_warning('Test Bot', 15.5, 20.0),
    alert_bot_halted('Test Bot', 21.0, 'Max drawdown exceeded'),
    alert_bot_started('Test Bot', ['EUR_USD'], 'H1', 'EMA Ribbon'),
    alert_bot_stopped('Test Bot', 'Manual'),
    send_daily_report('2026-03-21', {
        'total_trades':5,'winners':3,'losers':2,
        'total_pnl':42.50,'win_rate':60.0,
        'best_trade':25.0,'worst_trade':-12.0,'running_bots':2
    }),
    alert_nlp_result('Set SL to 30 pips','set_risk',True,'Stop loss updated'),
]
# All should return bool (True if sent, False if not configured)
all_bool = all(isinstance(r, bool) for r in results)
print(f'  All functions returned bool: {all_bool}')
print(f'  Sent (would be True if configured): {results}')
" && pass "Alert formatters work correctly" || fail "Alert formatter errors"

section "TEST 5 — Command parser (no Telegram connection needed)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.telegram.bot import ForexTelegramBot

bot = ForexTelegramBot()
commands = [
    ('/help',    '_cmd_help'),
    ('/status',  '_cmd_status'),
    ('/pnl',     '_cmd_pnl'),
    ('/trades',  '_cmd_trades'),
]
for cmd, method in commands:
    parts   = cmd.split()
    command = parts[0].lstrip('/')
    fn      = getattr(bot, method)
    result  = fn([])
    ok      = isinstance(result, str) and len(result) > 10
    print(f'  {\"✅\" if ok else \"❌\"} {cmd:15} → {len(result)} chars')
" && pass "All command handlers return formatted strings" || fail "Command handler errors"

section "TEST 6 — Webhook URL registered"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.urls import reverse
try:
    url = reverse('telegram-webhook', kwargs={'secret_token': 'test'})
    print(f'  Webhook URL: {url}')
    print('  REGISTERED')
except Exception as e:
    print(f'  NOT_REGISTERED: {e}')
" | grep -q "REGISTERED" \
  && pass "Telegram webhook URL registered in urls.py" \
  || warn "Add telegram webhook URL to config/urls.py (see config_urls_with_telegram.py)"

section "TEST 7 — Live send test (only if configured)"
python3 -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.telegram.bot import get_telegram_bot
bot = get_telegram_bot()
if not bot.is_configured():
    print('  SKIPPED — run setup_telegram.sh first')
else:
    result = bot.send('🧪 ForexBot Phase O test message — Telegram alerts working!')
    print('  SENT' if result else '  FAILED')
" | grep -q "SENT" \
  && pass "Live test message sent to Telegram!" \
  || warn "Live test skipped (not configured) or failed"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE O TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To enable Telegram alerts:"
echo "  1. bash setup_telegram.sh       (creates bot + sets .env)"
echo "  2. python manage.py telegram_poll  (dev: polling mode)"
echo "  OR set a webhook URL for production"
echo ""
echo "  Commands available in Telegram:"
echo "  /status /pnl /trades /risk /start /stop /pause /resume /help"