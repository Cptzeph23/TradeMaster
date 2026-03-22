#!/usr/bin/env bash
# ============================================================
# ABSOLUTE PATH: /opt/forex_bot/reset_and_setup.sh
# Resets password and creates a demo trading account directly
# via Django shell — no broker API key needed for testing.
# Run: bash reset_and_setup.sh
# ============================================================
BASE_DIR="/home/cptzeph/Desktop/Programs/python/forex_bot"
EMAIL="askzeph20@gmail.com"
PASSWORD="Ze6533@A#"

cd "$BASE_DIR"
source bot/bin/activate

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1 — Reset password"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python manage.py shell << PYEOF
from apps.accounts.models import User, TradingAccount, UserProfile
from utils.constants import Broker, AccountType

# Reset password
try:
    u = User.objects.get(email='$EMAIL')
    u.set_password('$PASSWORD')
    u.is_active   = True
    u.is_verified = True
    u.save()
    print(f"✅ Password reset for {u.email}")
except User.DoesNotExist:
    u = User.objects.create_user(
        email      = '$EMAIL',
        password   = '$PASSWORD',
        first_name = 'Mr',
        last_name  = 'Zeph',
    )
    u.is_active   = True
    u.is_verified = True
    u.save()
    print(f"✅ User created: {u.email}")

# Ensure profile exists
UserProfile.objects.get_or_create(user=u)
print("✅ UserProfile OK")

# Create demo trading account (no real API key needed for testing)
acct, created = TradingAccount.objects.get_or_create(
    user       = u,
    broker     = 'oanda',
    account_id = '101-001-0000001-001',
    defaults   = {
        'name':         'OANDA Demo (Test)',
        'account_type': 'demo',
        'currency':     'USD',
        'balance':      10000,
        'equity':       10000,
        'is_active':    True,
        'is_verified':  True,
    }
)
# Set a dummy encrypted API key so encryption works
acct.set_api_key('test-placeholder-key-replace-with-real-oanda-key')
acct.save()

action = 'Created' if created else 'Found existing'
print(f"✅ {action} trading account: {acct.name} (id={acct.id})")
print(f"")
print(f"══════════════════════════════════════")
print(f"  Setup complete!")
print(f"  Email:    $EMAIL")
print(f"  Password: $PASSWORD")
print(f"  Account:  {acct.id}")
print(f"══════════════════════════════════════")
PYEOF

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2 — Verify login works"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
RESULT=$(curl -s -X POST "http://localhost:8001/api/v1/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

SUCCESS=$(echo "$RESULT" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)

if [ "$SUCCESS" = "True" ] || [ "$SUCCESS" = "true" ]; then
  echo "  ✅ Login verified — password is correct"
  TOKEN=$(echo "$RESULT" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Step 3 — Verify trading account via API"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  ACCOUNTS=$(curl -s "http://localhost:8001/api/v1/auth/trading-accounts/" \
    -H "Authorization: Bearer $TOKEN")
  echo "$ACCOUNTS" | python3 -m json.tool
  echo ""
  echo "  ✅ All done. Now run: bash test_trading_8001.sh"
else
  echo "  ❌ Login still failing. Response:"
  echo "$RESULT" | python3 -m json.tool
  echo ""
  echo "  Try manually:"
  echo "  python manage.py changepassword \$(python manage.py shell -c \"from apps.accounts.models import User; print(User.objects.get(email='$EMAIL').username if hasattr(User.objects.get(email='$EMAIL'), 'username') else 'N/A')\")"
fi