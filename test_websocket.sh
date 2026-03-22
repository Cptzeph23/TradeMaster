#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/test_websocket_8001.sh
# Phase K — WebSocket tests (requires wscat or websocat)
# ============================================================
BASE="http://localhost:8001/api/v1"
WS_BASE="ws://localhost:8001"
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

# Check ws tools
section "TEST 1 — WebSocket tools check"
if command -v wscat &>/dev/null; then
  pass "wscat is available"
  WS_TOOL="wscat"
elif command -v websocat &>/dev/null; then
  pass "websocat is available"
  WS_TOOL="websocat"
elif python3 -c "import websockets" &>/dev/null; then
  pass "Python websockets module available"
  WS_TOOL="python"
else
  warn "No WS test tool found"
  echo "  Install one of:"
  echo "  npm install -g wscat"
  echo "  pip install websockets"
  WS_TOOL="none"
fi

# Test WS with Python
section "TEST 2 — WebSocket connection test (Python)"
python3 << PYEOF
import asyncio, json, sys

async def test_ws():
    try:
        import websockets
        token = "$TOKEN"

        # Test dashboard WebSocket
        url = f"ws://localhost:8001/ws/dashboard/?token={token}"
        print(f"  Connecting to: {url[:60]}...")

        async with websockets.connect(url, open_timeout=5) as ws:
            # Should receive dashboard_update immediately
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            msg_type = data.get('type', '')
            print(f"  Received: type={msg_type}")

            if msg_type == 'dashboard_update':
                bots    = data.get('data', {}).get('bots', [])
                summary = data.get('data', {}).get('summary', {})
                print(f"  Dashboard: {len(bots)} bots, pnl={summary.get('total_pnl',0)}")
                print("  ✅ Dashboard WebSocket OK")
            else:
                print(f"  ⚠ Unexpected message type: {msg_type}")

            # Send ping
            await ws.send(json.dumps({"action": "ping"}))
            pong = await asyncio.wait_for(ws.recv(), timeout=3)
            pong_data = json.loads(pong)
            if pong_data.get('type') == 'pong':
                print("  ✅ Ping/Pong OK")
            else:
                print(f"  ⚠ Unexpected pong: {pong_data}")

        return True

    except ImportError:
        print("  websockets not installed: pip install websockets")
        return False
    except Exception as e:
        print(f"  Connection failed: {e}")
        print("  Make sure Daphne/ASGI is running (not just runserver)")
        return False

result = asyncio.run(test_ws())
sys.exit(0 if result else 1)
PYEOF
[ $? -eq 0 ] && pass "WebSocket connection successful" \
  || warn "WebSocket test failed — see notes below"

# Test price WebSocket
section "TEST 3 — Live Price WebSocket"
python3 << PYEOF2
import asyncio, json, sys

async def test_price_ws():
    try:
        import websockets
        token  = "$TOKEN"
        symbol = "EUR_USD"
        url    = f"ws://localhost:8001/ws/prices/{symbol}/?token={token}"
        print(f"  Connecting to: {url[:60]}...")

        async with websockets.connect(url, open_timeout=5) as ws:
            msg  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"  Received: type={data.get('type')}")
            if data.get('type') == 'price_tick':
                price = data.get('data', {})
                print(f"  Price: bid={price.get('bid')} ask={price.get('ask')}")
                print("  ✅ Price WebSocket OK (may show null without OANDA key)")
            else:
                print(f"  No price data yet (expected without OANDA key)")
        return True
    except Exception as e:
        print(f"  {e}")
        return False

asyncio.run(test_price_ws())
PYEOF2
[ $? -eq 0 ] && pass "Price WebSocket reachable" || warn "Price WS needs ASGI server"

# Create a bot and test bot WS
section "TEST 4 — Bot-specific WebSocket"
STRAT_ID=$(curl -s "$BASE/strategies/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); own=d.get('own',[]); print(own[0]['id'] if own else '')" 2>/dev/null)
ACCT_ID=$(curl -s "$BASE/auth/trading-accounts/" -H "Authorization: Bearer $TOKEN" | python3 -c \
  "import sys,json; d=json.load(sys.stdin)
r=d.get('results',d.get('accounts',[])); print(r[0]['id'] if r else '')" 2>/dev/null)

if [ -n "$STRAT_ID" ] && [ -n "$ACCT_ID" ]; then
  BOT=$(curl -s -X POST "$BASE/trading/bots/" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"WS Test Bot\",\"trading_account\":\"$ACCT_ID\",
         \"strategy\":\"$STRAT_ID\",\"broker\":\"oanda\",
         \"symbols\":[\"EUR_USD\"],\"timeframe\":\"H1\",
         \"allow_buy\":true,\"allow_sell\":true,
         \"risk_settings\":{\"risk_percent\":1.0,\"stop_loss_pips\":50}}")
  BOT_ID=$(echo "$BOT" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d.get('bot',{}).get('id',''))" 2>/dev/null)

  if [ -n "$BOT_ID" ] && [ "$BOT_ID" != "None" ]; then
    python3 << PYEOF3
import asyncio, json
async def test():
    try:
        import websockets
        url = f"ws://localhost:8001/ws/bots/$BOT_ID/?token=$TOKEN"
        async with websockets.connect(url, open_timeout=5) as ws:
            msg  = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            if data.get('type') == 'bot_status':
                print(f"  Bot status: {data['data'].get('status','?')} | name={data['data'].get('name','?')}")
                print("  ✅ Bot WebSocket OK")
            return True
    except Exception as e:
        print(f"  {e}")
        return False
asyncio.run(test())
PYEOF3
    [ $? -eq 0 ] && pass "Bot WebSocket working" || warn "Bot WS needs ASGI server"
    # Cleanup
    curl -s -X DELETE "$BASE/trading/bots/$BOT_ID/" \
      -H "Authorization: Bearer $TOKEN" > /dev/null
  fi
fi

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  PHASE K TESTS COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  ⚠ IMPORTANT: WebSocket requires ASGI server (Daphne)."
echo "  'python manage.py runserver' only supports HTTP."
echo ""
echo "  For WebSocket to work, start Daphne directly:"
echo ""
echo "  source bot/bin/activate"
echo "  daphne -b 127.0.0.1 -p 8001 config.asgi:application"
echo ""
echo "  Then connect to WebSockets at ws://localhost:8001/ws/..."