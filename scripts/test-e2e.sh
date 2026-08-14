#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — End-to-End Test Script
# Simulates a complete theft scenario
# Usage: ./scripts/test-e2e.sh [SERVER_URL] [API_KEY]
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SERVER_URL="${1:-http://localhost:8000}"
API_KEY="${2:-}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
FAIL=0
TOTAL=0

assert_status() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    TOTAL=$((TOTAL + 1))

    if [[ "$actual" == "$expected" ]]; then
        echo -e "  ${GREEN}✓${NC} $desc (HTTP $actual)"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗${NC} $desc (expected $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

# ─── Get API Key if not provided ──────────────────────────────────────────────

if [[ -z "$API_KEY" ]]; then
    if [[ -f "server/.env" ]]; then
        API_KEY=$(grep MT_API_KEY server/.env | cut -d= -f2)
    elif [[ -f ".env" ]]; then
        API_KEY=$(grep MT_API_KEY .env | cut -d= -f2)
    fi
fi

if [[ -z "$API_KEY" ]]; then
    echo -e "${RED}Error: API_KEY not provided. Usage: $0 [SERVER_URL] [API_KEY]${NC}"
    exit 1
fi

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║        MAGNEETAR — End-to-End Test Suite                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Server: ${YELLOW}$SERVER_URL${NC}"
echo -e "  API Key: ${YELLOW}${API_KEY:0:8}...${NC}"
echo ""

# ─── Test 1: Health Check ────────────────────────────────────────────────────

echo -e "${CYAN}1. Health Check${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/health")
assert_status "GET /health" "200" "$STATUS"
echo ""

# ─── Test 2: Device Registration ─────────────────────────────────────────────

echo -e "${CYAN}2. Device Registration${NC}"
DEVICE_ID="test-device-$(date +%s)"
REGISTER_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/device/register" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"fingerprint\": \"test-fingerprint-$(date +%s)\",
        \"model\": \"Test Phone\",
        \"os_version\": \"Android 14\",
        \"app_version\": \"1.0.0\"
    }")
STATUS=$(echo "$REGISTER_RESP" | tail -1)
BODY=$(echo "$REGISTER_RESP" | head -n -1)
assert_status "POST /api/device/register" "200" "$STATUS"

DEVICE_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
if [[ -n "$DEVICE_TOKEN" ]]; then
    echo -e "  ${GREEN}✓${NC} Got device JWT token"
else
    echo -e "  ${RED}✗${NC} Failed to get device token"
fi
echo ""

# ─── Test 3: Location Report ─────────────────────────────────────────────────

echo -e "${CYAN}3. Location Reports${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/device/location" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DEVICE_TOKEN" \
    -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"lat\": 9.0820,
        \"lng\": 8.6753,
        \"accuracy\": 10.0,
        \"provider\": \"gps\",
        \"battery_percent\": 85,
        \"speed\": 0.5
    }")
assert_status "POST /api/device/location" "200" "$STATUS"

# Send second location
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/device/location" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DEVICE_TOKEN" \
    -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"lat\": 9.0825,
        \"lng\": 8.6758,
        \"accuracy\": 8.0,
        \"provider\": \"gps\",
        \"battery_percent\": 84
    }")
assert_status "POST /api/device/location (2nd)" "200" "$STATUS"
echo ""

# ─── Test 4: Command Issuance ────────────────────────────────────────────────

echo -e "${CYAN}4. Commands${NC}"
# F-02: dashboard routes are JWT-only — the shared x-api-key no longer
# authenticates them (it ships in every APK, so it must stay a bootstrap-only
# credential). Log in for a dashboard token before issuing commands.
CMD_LOGIN=$(curl -s -X POST "$SERVER_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"api_key\": \"$API_KEY\"}")
CMD_TOKEN=$(echo "$CMD_LOGIN" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
if [[ -n "$CMD_TOKEN" ]]; then
    echo -e "  ${GREEN}✓${NC} Got dashboard JWT for command issuance"
else
    echo -e "  ${RED}✗${NC} Login failed — cannot issue commands (key wrong?)"
fi
CMD_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/dashboard/command" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CMD_TOKEN" \
    -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"command\": \"ping\"
    }")
STATUS=$(echo "$CMD_RESP" | tail -1)
assert_status "POST /api/dashboard/command (ping)" "200" "$STATUS"

# Poll commands as device
CMDS_RESP=$(curl -s -w "\n%{http_code}" "$SERVER_URL/api/device/commands/$DEVICE_ID" \
    -H "Authorization: Bearer $DEVICE_TOKEN")
STATUS=$(echo "$CMDS_RESP" | tail -1)
assert_status "GET /api/device/commands" "200" "$STATUS"
echo ""

# ─── Test 5: Dashboard Auth ──────────────────────────────────────────────────

echo -e "${CYAN}5. Dashboard Authentication${NC}"
LOGIN_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"api_key\": \"$API_KEY\"}")
STATUS=$(echo "$LOGIN_RESP" | tail -1)
BODY=$(echo "$LOGIN_RESP" | head -n -1)
assert_status "POST /api/auth/login" "200" "$STATUS"

DASH_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
echo ""

# ─── Test 6: Dashboard Endpoints ─────────────────────────────────────────────

echo -e "${CYAN}6. Dashboard Endpoints${NC}"

DEVICES_RESP=$(curl -s -w "\n%{http_code}" "$SERVER_URL/api/dashboard/devices" \
    -H "Authorization: Bearer $DASH_TOKEN")
STATUS=$(echo "$DEVICES_RESP" | tail -1)
assert_status "GET /api/dashboard/devices" "200" "$STATUS"

STATS_RESP=$(curl -s -w "\n%{http_code}" "$SERVER_URL/api/dashboard/stats" \
    -H "Authorization: Bearer $DASH_TOKEN")
STATUS=$(echo "$STATS_RESP" | tail -1)
assert_status "GET /api/dashboard/stats" "200" "$STATUS"

LOCS_RESP=$(curl -s -w "\n%{http_code}" "$SERVER_URL/api/dashboard/locations/$DEVICE_ID" \
    -H "Authorization: Bearer $DASH_TOKEN")
STATUS=$(echo "$LOCS_RESP" | tail -1)
assert_status "GET /api/dashboard/locations" "200" "$STATUS"
echo ""

# ─── Test 7: Geofence ────────────────────────────────────────────────────────

echo -e "${CYAN}7. Geofences${NC}"
FENCE_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/dashboard/geofence" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DASH_TOKEN" \
    -d "{
        \"device_id\": \"$DEVICE_ID\",
        \"name\": \"Home\",
        \"center_lat\": 9.0820,
        \"center_lng\": 8.6753,
        \"radius_meters\": 100,
        \"is_safe_zone\": true
    }")
STATUS=$(echo "$FENCE_RESP" | tail -1)
assert_status "POST /api/dashboard/geofence" "200" "$STATUS"
echo ""

# ─── Test 8: Evidence ────────────────────────────────────────────────────────

echo -e "${CYAN}8. Evidence${NC}"
EVID_RESP=$(curl -s -w "\n%{http_code}" "$SERVER_URL/api/dashboard/evidence/$DEVICE_ID" \
    -H "Authorization: Bearer $DASH_TOKEN")
STATUS=$(echo "$EVID_RESP" | tail -1)
assert_status "GET /api/dashboard/evidence" "200" "$STATUS"
echo ""

# ─── Test 9: Token Refresh ───────────────────────────────────────────────────

echo -e "${CYAN}9. Token Refresh${NC}"
REFRESH_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])" 2>/dev/null || echo "")
if [[ -n "$REFRESH_TOKEN" ]]; then
    REFRESH_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/auth/refresh" \
        -H "Content-Type: application/json" \
        -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}")
    STATUS=$(echo "$REFRESH_RESP" | tail -1)
    assert_status "POST /api/auth/refresh" "200" "$STATUS"
else
    echo -e "  ${YELLOW}⊘${NC} Skipped (no refresh token)"
fi
echo ""

# ─── Test 9.5: Account Claim (multi-user re-link) ──────────────────────────────

echo -e "${CYAN}9.5 Account Claim (device re-link on sign-in)${NC}"
# The "sign in on the phone" path: a user registers an account, then claims
# an unowned device (by its per-device key). The device must become visible
# in THAT user's scoped dashboard view — the fix for "my phone is online but
# my dashboard doesn't show it" (device was registered while unlinked).
CLAIM_EMAIL="e2e-claim-$(date +%s)@test.local"
CLAIM_USER=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$CLAIM_EMAIL\", \"password\": \"Test-Pass-12345\"}")
STATUS=$(echo "$CLAIM_USER" | tail -1)
BODY=$(echo "$CLAIM_USER" | head -n -1)
assert_status "POST /api/auth/register (claim user)" "200" "$STATUS"

CLAIM_USER_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
CLAIM_DEVICE_ID="claim-$(date +%s)"
CLAIM_DEVICE_KEY=$(python3 -c "import uuid; print(uuid.uuid4().hex)")
# Register the device WITHOUT a user token (unlinked, as after a fresh install).
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/device/register" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -d "{\"device_id\": \"$CLAIM_DEVICE_ID\", \"fingerprint\": \"fp-claim-$(date +%s)\", \"model\": \"Claim Test\", \"device_key\": \"$CLAIM_DEVICE_KEY\"}")
assert_status "POST /api/device/register (unlinked)" "200" "$STATUS"
# Claim it with the user token + per-device key (what DeviceLinker does).
CLAIM_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/device/claim" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $CLAIM_USER_TOKEN" \
    -H "x-device-key: $CLAIM_DEVICE_KEY" \
    -d "{\"device_id\": \"$CLAIM_DEVICE_ID\"}")
STATUS=$(echo "$CLAIM_RESP" | tail -1)
assert_status "POST /api/device/claim" "200" "$STATUS"
# The claimed device must appear in the USER's scoped device list.
USER_DEVICES=$(curl -s "$SERVER_URL/api/dashboard/devices" \
    -H "Authorization: Bearer $CLAIM_USER_TOKEN")
if echo "$USER_DEVICES" | python3 -c "import sys, json; sys.exit(0 if any(d['id']=='$CLAIM_DEVICE_ID' for d in json.load(sys.stdin)['devices']) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Claimed device visible to owning user's dashboard"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Claimed device NOT visible to owning user"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))
# A SECOND user must NOT see the claimed device (ownership boundary).
OTHER_EMAIL="e2e-other-$(date +%s)@test.local"
OTHER_TOKEN=$(curl -s -X POST "$SERVER_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$OTHER_EMAIL\", \"password\": \"Test-Pass-12345\"}" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")
OTHER_DEVICES=$(curl -s "$SERVER_URL/api/dashboard/devices" \
    -H "Authorization: Bearer $OTHER_TOKEN")
if echo "$OTHER_DEVICES" | python3 -c "import sys, json; sys.exit(0 if not any(d['id']=='$CLAIM_DEVICE_ID' for d in json.load(sys.stdin)['devices']) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Claimed device hidden from other users"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Claimed device leaked to another account"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))
echo ""

# ─── Test 9.6: Password-Gated Device Deletion (step-up) ───────────────────────

echo -e "${CYAN}9.6 Password-Gated Device Deletion (step-up)${NC}"
# Destructive delete must NOT work with a missing or wrong step-up password.
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/dashboard/devices/$CLAIM_DEVICE_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DASH_TOKEN" \
    -d "{}")
assert_status "DELETE without step-up password" "400" "$STATUS"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/dashboard/devices/$CLAIM_DEVICE_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DASH_TOKEN" \
    -d "{\"password\": \"wrong-password\"}")
assert_status "DELETE with wrong step-up password" "401" "$STATUS"
# Correct password (admin mode = master API key) → 200 and gone.
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/dashboard/devices/$CLAIM_DEVICE_ID" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $DASH_TOKEN" \
    -d "{\"password\": \"$API_KEY\"}")
assert_status "DELETE with correct step-up password" "200" "$STATUS"
echo ""

# ─── Test 10: Invalid Auth ───────────────────────────────────────────────────

echo -e "${CYAN}10. Security${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/dashboard/devices" \
    -H "x-api-key: invalid-key")
assert_status "Reject invalid API key" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/dashboard/devices" \
    -H "Authorization: Bearer invalid-token")
assert_status "Reject invalid JWT" "401" "$STATUS"
echo ""

# ─── Test 11: Self-Cleanup (no table pollution) ─────────────────────────────

echo -e "${CYAN}11. Self-Cleanup${NC}"
# Every row this suite created (main test device + claim device) is deleted
# with the step-up password so repeated runs never pollute the devices table
# (the old suite leaked a fresh test-device-* row on every run).
for CLEANUP_DID in "$DEVICE_ID" "$CLAIM_DEVICE_ID"; do
    if [[ -n "${CLEANUP_DID:-}" ]]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/dashboard/devices/$CLEANUP_DID" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $DASH_TOKEN" \
            -d "{\"password\": \"$API_KEY\"}")
        if [[ "$STATUS" == "200" ]]; then
            echo -e "  ${GREEN}✓${NC} Cleaned up $CLEANUP_DID"
        else
            echo -e "  ${YELLOW}⊘${NC} Cleanup of $CLEANUP_DID returned HTTP $STATUS (already gone?)"
        fi
    fi
done
# The claim/other accounts from Test 9.5 are GDPR-deleted so repeated runs
# never pollute the users table (their devices cascade away with them).
for CLEANUP_TOKEN in "$CLAIM_USER_TOKEN" "$OTHER_TOKEN"; do
    if [[ -n "${CLEANUP_TOKEN:-}" ]]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/user/account" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $CLEANUP_TOKEN" \
            -d '{"confirm": true}')
        if [[ "$STATUS" == "200" ]]; then
            echo -e "  ${GREEN}✓${NC} GDPR-deleted Test 9.5 account"
        else
            echo -e "  ${YELLOW}⊘${NC} GDPR cleanup of Test 9.5 account returned HTTP $STATUS"
        fi
    fi
done
echo ""

# ─── Test 12: User Setup Journey (pairing, commands, media, RBAC, GDPR) ────────
# The full new-user onboarding chain, end-to-end: account → device → pair a
# second user → command round-trip → evidence photo → RBAC isolation → GDPR
# deletion. Every account created here is permanently deleted at the end, so
# repeated runs never pollute the users table.

echo -e "${CYAN}12. User Setup Journey${NC}"
TS="$(date +%s)-$$"
SETUP_PASS="Str0ng-Setup-Pass-$(date +%s)"
U1_EMAIL="e2e-setup-a-${TS}@test.local"
U2_EMAIL="e2e-setup-b-${TS}@test.local"
D1_ID="setup-dev-a-${TS}"
D2_ID="setup-dev-b-${TS}"
D1_KEY="setup-device-key-a-${TS}"
D2_KEY="setup-device-key-b-${TS}"

# 12.1 — Account A registers and auto-links its device (app's first-launch flow)
U1_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$U1_EMAIL\", \"password\": \"$SETUP_PASS\", \"display_name\": \"Setup User A\"}")
STATUS=$(echo "$U1_RESP" | tail -1)
BODY=$(echo "$U1_RESP" | head -n -1)
assert_status "POST /api/auth/register (user A)" "200" "$STATUS"
U1_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")

D1_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/device/register" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -H "Authorization: Bearer $U1_TOKEN" \
    -d "{\"device_id\": \"$D1_ID\", \"fingerprint\": \"fp-setup-a-${TS}\", \"model\": \"Pixel 8\", \"os_version\": \"Android 14\", \"app_version\": \"1.4.1\", \"device_key\": \"$D1_KEY\"}")
STATUS=$(echo "$D1_RESP" | tail -1)
BODY=$(echo "$D1_RESP" | head -n -1)
assert_status "POST /api/device/register (auto-linked)" "200" "$STATUS"
D1_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")

# 12.2 — Pairing code: user B claims an ownerless device with the code
# shown on the phone (first 8 hex chars of SHA-256(device_key)).
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/device/register" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
    -d "{\"device_id\": \"$D2_ID\", \"fingerprint\": \"fp-setup-b-${TS}\", \"model\": \"Samsung A54\", \"os_version\": \"Android 14\", \"app_version\": \"1.4.1\", \"device_key\": \"$D2_KEY\"}")
assert_status "POST /api/device/register (ownerless)" "200" "$STATUS"

U2_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$U2_EMAIL\", \"password\": \"$SETUP_PASS\", \"display_name\": \"Setup User B\"}")
STATUS=$(echo "$U2_RESP" | tail -1)
BODY=$(echo "$U2_RESP" | head -n -1)
assert_status "POST /api/auth/register (user B)" "200" "$STATUS"
U2_TOKEN=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin)['token'])" 2>/dev/null || echo "")

PAIR_CODE=$(printf '%s' "$D2_KEY" | sha256sum | cut -c1-8)
PAIR_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/dashboard/devices/claim-by-pairing" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $U2_TOKEN" \
    -d "{\"device_id\": \"$D2_ID\", \"pairing_code\": \"$PAIR_CODE\"}")
STATUS=$(echo "$PAIR_RESP" | tail -1)
assert_status "POST /api/dashboard/devices/claim-by-pairing" "200" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/dashboard/devices/claim-by-pairing" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $U2_TOKEN" \
    -d "{\"device_id\": \"$D2_ID\", \"pairing_code\": \"00000000\"}")
assert_status "Wrong pairing code rejected" "403" "$STATUS"

# 12.3 — Ownership boundaries: each user sees only their own device.
if curl -s "$SERVER_URL/api/dashboard/devices" -H "Authorization: Bearer $U2_TOKEN" \
    | python3 -c "import sys, json; d=json.load(sys.stdin)['devices']; sys.exit(0 if any(x['id']=='$D2_ID' for x in d) and not any(x['id']=='$D1_ID' for x in d) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} User B sees own device only (RBAC isolation)"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} RBAC isolation broken (device list wrong)"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# 12.4 — Command round-trip: issue alarm → device polls → acks → dashboard shows executed
CMD_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/dashboard/command" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $U1_TOKEN" \
    -d "{\"device_id\": \"$D1_ID\", \"command\": \"alarm\", \"params\": \"\", \"priority\": 5}")
STATUS=$(echo "$CMD_RESP" | tail -1)
BODY=$(echo "$CMD_RESP" | head -n -1)
assert_status "POST /api/dashboard/command (alarm)" "200" "$STATUS"
CMD_ID=$(echo "$BODY" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('command_id', d.get('id', 0)))" 2>/dev/null || echo "0")

if curl -s "$SERVER_URL/api/device/commands/$D1_ID" -H "Authorization: Bearer $D1_TOKEN" \
    | python3 -c "import sys, json; d=json.load(sys.stdin)['commands']; sys.exit(0 if any(c['id']==$CMD_ID and c['command']=='alarm' for c in d) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Device polls and receives the alarm command"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Device poll did not return the pending command"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$SERVER_URL/api/device/commands/$CMD_ID/ack" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $D1_TOKEN" \
    -d '{"status": "executed"}')
assert_status "POST /api/device/commands/{id}/ack" "200" "$STATUS"

if curl -s "$SERVER_URL/api/dashboard/commands/$D1_ID" -H "Authorization: Bearer $U1_TOKEN" \
    | python3 -c "import sys, json; d=json.load(sys.stdin)['commands']; sys.exit(0 if any(c['id']==$CMD_ID and c['status']=='executed' for c in d) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Dashboard shows command as executed"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Dashboard command status not executed"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

# 12.5 — Evidence photo: upload, list, fetch, integrity (magic bytes + sha256)
JPEG_B64='/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=='
MED_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/device/media" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $D1_TOKEN" \
    -d "{\"device_id\": \"$D1_ID\", \"type\": \"photo\", \"data_b64\": \"$JPEG_B64\", \"lat\": 6.5244, \"lng\": 3.3792}")
STATUS=$(echo "$MED_RESP" | tail -1)
BODY=$(echo "$MED_RESP" | head -n -1)
assert_status "POST /api/device/media (photo)" "200" "$STATUS"
MEDIA_ID=$(echo "$BODY" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('media_id', d.get('id', 0)))" 2>/dev/null || echo "0")

if curl -s "$SERVER_URL/api/dashboard/media/$D1_ID" -H "Authorization: Bearer $U1_TOKEN" \
    | python3 -c "import sys, json; d=json.load(sys.stdin)['media']; sys.exit(0 if any(str(x['id'])=='$MEDIA_ID' for x in d) else 1)" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Photo visible in dashboard media list"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Photo missing from dashboard media list"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))

curl -s "$SERVER_URL/api/dashboard/media/file/$MEDIA_ID" -H "Authorization: Bearer $U1_TOKEN" -o /tmp/e2e-media.json
if python3 - /tmp/e2e-media.json "$JPEG_B64" <<'PY'
import base64, hashlib, json, sys
d = json.load(open(sys.argv[1]))
raw = base64.b64decode(d["data_b64"])
up = base64.b64decode(sys.argv[2])
if not raw.startswith(b"\xff\xd8"): sys.exit(1)          # real JPEG magic
if d["sha256_hash"] != hashlib.sha256(raw).hexdigest(): sys.exit(1)  # row hash
if raw != up: sys.exit(1)                                  # byte-for-byte round-trip
PY
then
    echo -e "  ${GREEN}✓${NC} Media file: real JPEG, sha256 matches, byte-for-byte round-trip"
    PASS=$((PASS + 1))
else
    echo -e "  ${RED}✗${NC} Media file integrity check failed"
    FAIL=$((FAIL + 1))
fi
TOTAL=$((TOTAL + 1))
rm -f /tmp/e2e-media.json

# 12.6 — RBAC negatives: user B must be locked out of A's device entirely
for RBAC in "command|POST|/api/dashboard/command|{\"device_id\": \"$D1_ID\", \"command\": \"alarm\", \"priority\": 5}" \
            "media|GET|/api/dashboard/media/$D1_ID|" \
            "location|GET|/api/dashboard/locations/$D1_ID/live|"; do
    NAME="${RBAC%%|*}"; REST="${RBAC#*|}"; METHOD="${REST%%|*}"; REST="${REST#*|}"; URL="${REST%%|*}"; DATA="${REST#*|}"
    if [[ -n "$DATA" ]]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X "$METHOD" "$SERVER_URL$URL" \
            -H "Content-Type: application/json" -H "Authorization: Bearer $U2_TOKEN" -d "$DATA")
    else
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL$URL" \
            -H "Authorization: Bearer $U2_TOKEN")
    fi
    assert_status "User B blocked from A's $NAME (403)" "403" "$STATUS"
done

# 12.7 — GDPR right-to-erasure: both accounts (and their devices) are gone
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/user/account" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $U1_TOKEN" \
    -d '{"confirm": true}')
assert_status "GDPR delete user A" "200" "$STATUS"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$SERVER_URL/api/user/account" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $U2_TOKEN" \
    -d '{"confirm": true}')
assert_status "GDPR delete user B" "200" "$STATUS"
echo ""

# ─── Summary ──────────────────────────────────────────────────────────────────

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
if [[ $FAIL -eq 0 ]]; then
    echo -e "  ${GREEN}All $TOTAL tests passed! ✓${NC}"
else
    echo -e "  ${YELLOW}$PASS/$TOTAL tests passed${NC}, ${RED}$FAIL failed${NC}"
fi
echo ""
echo -e "  ${CYAN}Device ID:${NC} $DEVICE_ID"
echo -e "  ${CYAN}Test completed:${NC} $(date -Iseconds)"
echo ""

exit $FAIL
