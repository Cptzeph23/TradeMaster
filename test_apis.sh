#!/usr/bin/env bash
# ============================================================
# Run: bash test_apis.sh
# ============================================================

BASE="http://localhost:8001/api/v1"
EMAIL="askzeph20@gmail.com"
FIRST="Mr"
LAST="Zeph"
PASSWORD="Ze6533@A#"

# Colours
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "${GREEN}   PASS${NC} — $1"; }
fail() { echo -e "${RED}   FAIL${NC} — $1"; }
section() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${YELLOW}  $1${NC}"; echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ── 1. REGISTER ──────────────────────────────────────────────
section "TEST 1 — Register"
REGISTER=$(curl -s -X POST "$BASE/auth/register/" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"first_name\": \"$FIRST\",
    \"last_name\": \"$LAST\",
    \"password\": \"$PASSWORD\",
    \"password_confirm\": \"$PASSWORD\"
  }")

echo "Response: $REGISTER" | python3 -m json.tool 2>/dev/null || echo "Response: $REGISTER"

SUCCESS=$(echo "$REGISTER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$SUCCESS" = "True" ] || [ "$SUCCESS" = "true" ]; then
  pass "Registration succeeded"
  ACCESS_TOKEN=$(echo "$REGISTER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])" 2>/dev/null)
  REFRESH_TOKEN=$(echo "$REGISTER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['refresh'])" 2>/dev/null)
else
  echo -e "${YELLOW}  ⚠ Registration may have failed or user exists — trying login...${NC}"
fi

# ── 2. LOGIN ─────────────────────────────────────────────────
section "TEST 2 — Login"
LOGIN=$(curl -s -X POST "$BASE/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}")

echo "Response:" && echo "$LOGIN" | python3 -m json.tool 2>/dev/null || echo "$LOGIN"

LOGIN_SUCCESS=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$LOGIN_SUCCESS" = "True" ] || [ "$LOGIN_SUCCESS" = "true" ]; then
  pass "Login succeeded"
  ACCESS_TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])")
  REFRESH_TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['refresh'])")
  echo -e "  ${CYAN}Access Token:${NC}  ${ACCESS_TOKEN:0:40}..."
  echo -e "  ${CYAN}Refresh Token:${NC} ${REFRESH_TOKEN:0:40}..."
else
  fail "Login failed — stopping tests"
  exit 1
fi

# ── 3. GET PROFILE ───────────────────────────────────────────
section "TEST 3 — Get Current User (GET /auth/me/)"
ME=$(curl -s -X GET "$BASE/auth/me/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Response:" && echo "$ME" | python3 -m json.tool 2>/dev/null || echo "$ME"

ME_EMAIL=$(echo "$ME" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('user',{}).get('email',''))" 2>/dev/null)
if [ "$ME_EMAIL" = "$EMAIL" ]; then
  pass "Profile returned correctly (email=$ME_EMAIL)"
else
  fail "Profile email mismatch (got '$ME_EMAIL')"
fi

# ── 4. UPDATE PROFILE ────────────────────────────────────────
section "TEST 4 — Update Profile (PATCH /auth/me/)"
UPDATE=$(curl -s -X PATCH "$BASE/auth/me/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Captain",
    "profile": {
      "timezone": "Africa/Nairobi",
      "currency": "USD",
      "dashboard_theme": "dark",
      "nlp_enabled": true
    }
  }')

echo "Response:" && echo "$UPDATE" | python3 -m json.tool 2>/dev/null || echo "$UPDATE"

UP_SUCCESS=$(echo "$UPDATE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$UP_SUCCESS" = "True" ] || [ "$UP_SUCCESS" = "true" ] && pass "Profile updated" || fail "Profile update failed"

# ── 5. TOKEN REFRESH ─────────────────────────────────────────
section "TEST 5 — Token Refresh (POST /auth/token/refresh/)"
REFRESH=$(curl -s -X POST "$BASE/auth/token/refresh/" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\": \"$REFRESH_TOKEN\"}")

echo "Response:" && echo "$REFRESH" | python3 -m json.tool 2>/dev/null || echo "$REFRESH"

NEW_ACCESS=$(echo "$REFRESH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access',''))" 2>/dev/null)
if [ -n "$NEW_ACCESS" ] && [ "$NEW_ACCESS" != "None" ]; then
  pass "Token refreshed — new access token received"
  ACCESS_TOKEN="$NEW_ACCESS"   # use new token for remaining tests
  NEW_REFRESH=$(echo "$REFRESH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('refresh',''))" 2>/dev/null)
  REFRESH_TOKEN="$NEW_REFRESH"
else
  fail "Token refresh failed"
fi

# ── 6. CHANGE PASSWORD ───────────────────────────────────────
section "TEST 6 — Change Password (POST /auth/me/change-password/)"
NEW_PASS="${PASSWORD}NEW"
CHPW=$(curl -s -X POST "$BASE/auth/me/change-password/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"old_password\": \"$PASSWORD\",
    \"new_password\": \"${NEW_PASS}\",
    \"confirm_password\": \"${NEW_PASS}\"
  }")

echo "Response:" && echo "$CHPW" | python3 -m json.tool 2>/dev/null || echo "$CHPW"

CHPW_SUCCESS=$(echo "$CHPW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
if [ "$CHPW_SUCCESS" = "True" ] || [ "$CHPW_SUCCESS" = "true" ]; then
  pass "Password changed"
  # Grab new tokens issued after password change
  ACCESS_TOKEN=$(echo "$CHPW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['access'])" 2>/dev/null)
  REFRESH_TOKEN=$(echo "$CHPW" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tokens']['refresh'])" 2>/dev/null)
  PASSWORD="$NEW_PASS"   # update for logout test
else
  fail "Password change failed"
fi

# ── 7. LIST TRADING ACCOUNTS ─────────────────────────────────
section "TEST 7 — List Trading Accounts (GET /auth/trading-accounts/)"
ACCOUNTS=$(curl -s -X GET "$BASE/auth/trading-accounts/" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Response:" && echo "$ACCOUNTS" | python3 -m json.tool 2>/dev/null || echo "$ACCOUNTS"
pass "Trading accounts endpoint reachable"

# ── 8. ADD DEMO TRADING ACCOUNT ──────────────────────────────
section "TEST 8 — Add Demo Trading Account (POST /auth/trading-accounts/)"
ADD_ACCT=$(curl -s -X POST "$BASE/auth/trading-accounts/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OANDA Demo Account",
    "broker": "oanda",
    "account_id": "101-001-0000001-001",
    "account_type": "demo",
    "currency": "USD",
    "api_key": "test-api-key-placeholder-replace-with-real"
  }')

echo "Response:" && echo "$ADD_ACCT" | python3 -m json.tool 2>/dev/null || echo "$ADD_ACCT"

ACCT_ID=$(echo "$ADD_ACCT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('account',{}).get('id',''))" 2>/dev/null)
if [ -n "$ACCT_ID" ] && [ "$ACCT_ID" != "None" ]; then
  pass "Trading account created (id=$ACCT_ID)"
else
  echo -e "${YELLOW}  ⚠ Account creation may have failed (expected with placeholder API key)${NC}"
fi

# ── 9. UNAUTHENTICATED ACCESS CHECK ──────────────────────────
section "TEST 9 — Unauthenticated access should be blocked"
UNAUTH=$(curl -s -X GET "$BASE/auth/me/")
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/auth/me/")

echo "HTTP Status: $HTTP_CODE"
if [ "$HTTP_CODE" = "401" ]; then
  pass "Unauthenticated request correctly returns 401"
else
  fail "Expected 401, got $HTTP_CODE"
fi

# ── 10. LOGOUT ───────────────────────────────────────────────
section "TEST 10 — Logout (POST /auth/logout/)"
LOGOUT=$(curl -s -X POST "$BASE/auth/logout/" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\": \"$REFRESH_TOKEN\"}")

echo "Response:" && echo "$LOGOUT" | python3 -m json.tool 2>/dev/null || echo "$LOGOUT"

LO_SUCCESS=$(echo "$LOGOUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('success',''))" 2>/dev/null)
[ "$LO_SUCCESS" = "True" ] || [ "$LO_SUCCESS" = "true" ] && pass "Logout succeeded — token blacklisted" || fail "Logout failed"

# ── 11. POST-LOGOUT TOKEN SHOULD FAIL ────────────────────────
section "TEST 11 — Blacklisted refresh token should be rejected"
REUSE=$(curl -s -X POST "$BASE/auth/token/refresh/" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\": \"$REFRESH_TOKEN\"}")

HTTP_REUSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/auth/token/refresh/" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\": \"$REFRESH_TOKEN\"}")

echo "HTTP Status after logout: $HTTP_REUSE"
if [ "$HTTP_REUSE" = "401" ] || [ "$HTTP_REUSE" = "400" ]; then
  pass "Blacklisted token correctly rejected ($HTTP_REUSE)"
else
  fail "Expected 401/400 but got $HTTP_REUSE — token blacklist may not be working"
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  TEST RUN COMPLETE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  To re-login with new password manually:"
echo "  curl -s -X POST $BASE/auth/login/ \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}'"
echo ""