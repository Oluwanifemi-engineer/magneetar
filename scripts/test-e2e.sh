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
    if [[ -f ".env" ]]; then
        API_KEY=$(grep MT_API_KEY .env | cut -d= -f2)
    elif [[ -f "server/.env" ]]; then
        API_KEY=$(grep MT_API_KEY server/.env | cut -d= -f2)
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
CMD_RESP=$(curl -s -w "\n%{http_code}" -X POST "$SERVER_URL/api/dashboard/command" \
    -H "Content-Type: application/json" \
    -H "x-api-key: $API_KEY" \
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

# ─── Test 10: Invalid Auth ───────────────────────────────────────────────────

echo -e "${CYAN}10. Security${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/dashboard/devices" \
    -H "x-api-key: invalid-key")
assert_status "Reject invalid API key" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/dashboard/devices" \
    -H "Authorization: Bearer invalid-token")
assert_status "Reject invalid JWT" "401" "$STATUS"
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
