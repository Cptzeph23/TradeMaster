#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/setup_telegram.sh
# Interactive Telegram bot setup wizard
# Run once: bash setup_telegram.sh
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
VENV="${PROJECT_DIR}/bot"
[ ! -f "$VENV/bin/activate" ] && VENV="/opt/forex_bot_venv"
source "$VENV/bin/activate"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo ""
echo "════════════════════════════════════════"
echo "  ForexBot — Telegram Setup Wizard"
echo "════════════════════════════════════════"
echo ""

# Check python-telegram-bot installed
python3 -c "import telegram" 2>/dev/null || {
    echo -e "${YELLOW}Installing python-telegram-bot...${NC}"
    pip install "python-telegram-bot==13.15" --quiet
    echo -e "${GREEN}Installed${NC}"
}

echo -e "${CYAN}Step 1 — Create your Telegram bot${NC}"
echo "  1. Open Telegram → search for @BotFather"
echo "  2. Send: /newbot"
echo "  3. Follow instructions to name your bot"
echo "  4. Copy the token BotFather gives you"
echo ""
read -p "Paste your bot token here: " BOT_TOKEN

if [ -z "$BOT_TOKEN" ]; then
    echo "No token provided — skipping"
    exit 0
fi

echo ""
echo -e "${CYAN}Step 2 — Get your Chat ID${NC}"
echo "  1. Message your new bot anything (e.g. 'hello')"
echo "  2. Then visit this URL in your browser:"
echo "  https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
echo "  3. Look for 'chat': {'id': <YOUR_CHAT_ID>}"
echo ""
read -p "Paste your Chat ID here: " CHAT_ID

echo ""
echo -e "${CYAN}Step 3 — Webhook secret (auto-generated)${NC}"
WEBHOOK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
echo "  Secret: $WEBHOOK_SECRET"

# Update .env
python3 - << PYEOF
import re

env_path = "$ENV_FILE"
token    = "$BOT_TOKEN"
chat_id  = "$CHAT_ID"
secret   = "$WEBHOOK_SECRET"

with open(env_path) as f:
    content = f.read()

def set_env(content, key, value):
    if f'{key}=' in content:
        content = re.sub(rf'^{key}=.*$', f'{key}={value}', content, flags=re.MULTILINE)
    else:
        content += f'\n{key}={value}\n'
    return content

content = set_env(content, 'TELEGRAM_BOT_TOKEN',      token)
content = set_env(content, 'TELEGRAM_CHAT_ID',        chat_id)
content = set_env(content, 'TELEGRAM_WEBHOOK_SECRET', secret)

with open(env_path, 'w') as f:
    f.write(content)
print('✅ .env updated')
PYEOF

echo ""
echo -e "${CYAN}Step 4 — Test connection${NC}"
python3 - << PYEOF2
import telegram, sys
token = "$BOT_TOKEN"
try:
    bot  = telegram.Bot(token=token)
    info = bot.get_me()
    print(f'✅ Bot connected: @{info.username} ({info.first_name})')
except Exception as e:
    print(f'❌ Connection failed: {e}')
    sys.exit(1)
PYEOF2

echo ""
echo -e "${CYAN}Step 5 — Set webhook (requires public HTTPS URL)${NC}"
read -p "Enter your domain (e.g. https://yourdomain.com) or press Enter to skip: " DOMAIN

if [ -n "$DOMAIN" ]; then
    WEBHOOK_URL="${DOMAIN}/api/v1/telegram/webhook/${WEBHOOK_SECRET}/"
    python3 - << PYEOF3
import telegram
bot = telegram.Bot(token="$BOT_TOKEN")
result = bot.set_webhook(url="$WEBHOOK_URL")
if result:
    print(f'✅ Webhook set: $WEBHOOK_URL')
else:
    print('❌ Webhook setup failed')
PYEOF3
else
    echo -e "${YELLOW}  Webhook skipped — for local dev use polling mode:${NC}"
    echo "  python manage.py telegram_poll"
fi

echo ""
echo "════════════════════════════════════════"
echo -e "${GREEN}  Telegram setup complete!${NC}"
echo "════════════════════════════════════════"
echo ""
echo "  Send a message to your bot and try:"
echo "  /help   /status   /pnl   /trades"
echo ""
echo "  Restart Daphne for changes to take effect:"
echo "  daphne -b 127.0.0.1 -p 8001 config.asgi:application"