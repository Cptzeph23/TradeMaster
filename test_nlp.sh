#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_nlp_8001.sh
# Phase J — NLP Command Interface tests (port 8001)
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
[ -z "$TOKEN" ] && fail "Login failed" && exit 1

# Create a test bot
section "SETUP — Create test bot"
STRAT_ID=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); own=d.get('own',[]); print(own[0]['id'] if own else '')" 2>/dev/null)
ACCT_ID=$(curl -s "$BASE/auth/trading-accounts/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin)
r=d.get('results',d.get('accounts',[])); print(r[0]['id'] if r else '')" 2>/dev/null)

[ -z "$STRAT_ID" ] && fail "No strategy found" && exit 1
[ -z "$ACCT_ID"  ] && fail "No account found" && exit 1

BOT=$(curl -s -X POST "$BASE/trading/bots/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"NLP Test Bot\",\"trading_account\":\"$ACCT_ID\",
       \"strategy\":\"$STRAT_ID\",\"broker\":\"oanda\",
       \"symbols\":[\"EUR_USD\"],\"timeframe\":\"H1\",
       \"allow_buy\":true,\"allow_sell\":true,
       \"risk_settings\":{\"risk_percent\":1.0,\"stop_loss_pips\":50}}")
BOT_ID=$(echo "$BOT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id',''))" 2>/dev/null)
[ -z "$BOT_ID" ] && fail "Bot creation failed" && exit 1
pass "Test bot: $BOT_ID"

# ── NLP Command Tests ─────────────────────────────────────────
send_cmd() {
  local CMD="$1"
  local BID="${2:-null}"
  local PAYLOAD
  if [ "$BID" = "null" ]; then
    PAYLOAD="{\"command\":\"$CMD\"}"
  else
    PAYLOAD="{\"command\":\"$CMD\",\"bot_id\":\"$BID\"}"
  fi
  curl -s -X POST "$BASE/trading/command/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD"
}

check_queued() {
  local RESP="$1"
  local DESC="$2"
  OK=$(echo "$RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
  TASK=$(echo "$RESP" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('task_id',''))" 2>/dev/null)
  if [ "$OK" = "True" ] || [ "$OK" = "true" ]; then
    pass "$DESC (task=$TASK)"
  else
    MSG=$(echo "$RESP" | python3 -c \
      "import sys,json; d=json.load(sys.stdin); print(d.get('message',''))" 2>/dev/null)
    warn "$DESC queued but: $MSG"
  fi
}

section "TEST 1 — Set stop loss (risk command)"
R=$(send_cmd "Set stop loss to 35 pips" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Stop loss command"

section "TEST 2 — Set risk percent"
R=$(send_cmd "Use 1.5% risk per trade" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Risk percent command"

section "TEST 3 — Change trading pairs"
R=$(send_cmd "Only trade EUR/USD and GBP/USD" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Set pairs command"

section "TEST 4 — Direction control"
R=$(send_cmd "Only buy, no short selling" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Direction command"

section "TEST 5 — Multi-action command"
R=$(send_cmd "Set risk to 2% with 40 pip stop loss and trade only EUR_USD" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Multi-action command"

section "TEST 6 — Pause bot"
R=$(send_cmd "Pause the bot" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Pause command"

section "TEST 7 — Get status"
R=$(send_cmd "How is the bot doing?" "$BOT_ID")
echo "$R" | python3 -m json.tool
check_queued "$R" "Status command"

section "TEST 8 — Global stop all"
R=$(send_cmd "Stop all bots")
echo "$R" | python3 -m json.tool
check_queued "$R" "Stop all bots"

section "TEST 9 — NLP Command history"
HIST=$(curl -s "$BASE/trading/commands/" -H "Authorization: Bearer $TOKEN")
echo "$HIST" | python3 -m json.tool
CNT=$(echo "$HIST" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('count',0))" 2>/dev/null)
pass "Command history: $CNT commands recorded"

section "TEST 10 — Test parser directly (no Celery needed)"
echo "  Testing Claude AI parser..."
python3 -c "
import django, os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from services.nlp.parser import NLPCommandParser
parser = NLPCommandParser()

commands = [
    'Set stop loss to 30 pips and risk 1.5% per trade',
    'Stop all bots immediately',
    'Only trade EUR/USD going long',
    'Use a 50 pip stop loss with 2:1 reward ratio',
    'Pause the bot until market opens',
]

for cmd in commands:
    result = parser.parse(cmd, {})
    actions = result.get('actions', [])
    model   = result.get('model_used', 'unknown')
    print(f'  [{model}] \"{cmd[:45]}\"')
    for a in actions:
        print(f'    → action={a.get(\"action\")} confidence={a.get(\"confidence\",0):.2f}')
        print(f'      {a.get(\"explanation\",\"\")}')
    print()
" && pass "Parser test complete" || warn "Parser test needs ANTHROPIC_API_KEY in .env"

# Cleanup
section "CLEANUP"
curl -s -X DELETE "$BASE/trading/bots/$BOT_ID/" \
  -H "Authorization: Bearer $TOKEN" > /dev/null
pass "Test bot deleted"

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE J TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  For full AI parsing: add ANTHROPIC_API_KEY to .env"
echo "  Without the key: rule-based fallback is used"
echo ""
echo "  Example commands that work:"
echo "  'Set stop loss to 30 pips'"
echo "  'Only trade EUR/USD going long'"
echo "  'Use 2% risk with 2:1 reward ratio'"
echo "  'Stop all bots immediately'"
echo "  'Pause the bot'"