#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Recovery Capability Drill
# ══════════════════════════════════════════════════════════════════════════════
# Proves, end-to-end against a LIVE server, that the system can recover a lost
# smart device:
#
#   1. Register a user account
#   2. Register a device LINKED to that account (multi-user flow)
#   3. Simulate theft (SIM change + airplane mode + vehicle speed)
#   4. Verify Sentinel marked the device STOLEN + created an evidence case
#   5. Owner launches a COMMUNITY RECOVERY request (Guardian Network)
#   6. A second user opts in as a GUARDIAN and sees the blurred request nearby
#   7. The guardian reports a SIGHTING
#   8. The owner's dashboard sees the sighting in real time
#   9. The owner CLOSES the request → device marked RECOVERED
#
# This is the user-verifiable gate BEFORE Play Store release: if every step
# prints ✅, the product demonstrably recovers a lost device.
#
# Usage:
#   bash scripts/recovery-drill.sh [--server http://localhost:8000]
#   bash scripts/recovery-drill.sh --server https://api.magneetar.me
# ══════════════════════════════════════════════════════════════════════════════

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Accept either:  bash scripts/recovery-drill.sh [--server URL] | [URL]
SERVER_URL="http://localhost:8000"
if [ "${1:-}" = "--server" ]; then
    SERVER_URL="${2:-$SERVER_URL}"
elif [ -n "${1:-}" ]; then
    SERVER_URL="$1"
fi
SERVER_URL="${SERVER_URL%/}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
PASS=0; FAIL=0

step() { echo -e "\n${CYAN}═══════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"; }
ok()   { PASS=$((PASS+1)); echo -e "${GREEN}[✓]${NC} $1"; }
bad()  { FAIL=$((FAIL+1)); echo -e "${RED}[✗]${NC} $1"; }

# ── Read API key from server/.env ─────────────────────────────────────────────
API_KEY=""
if [ -f "$PROJECT_DIR/server/.env" ]; then
    API_KEY=$(grep -oP '^MT_API_KEY=\K.*' "$PROJECT_DIR/server/.env" 2>/dev/null | tr -d '"')
fi
if [ -z "$API_KEY" ]; then
    echo -e "${RED}[✗] MT_API_KEY not found in server/.env. Run scripts/generate-env.sh first.${NC}"
    exit 1
fi

TS=$(date +%s | tail -c 6)
# Fixed accounts: the drill is re-runnable. The FIRST run registers them;
# later runs fall back to login (registration is rate-limited to 3/10min/IP,
# so re-running must not burn the budget).
OWNER_EMAIL="drill-owner@magneetar.local"
GUARDIAN_EMAIL="drill-guardian@magneetar.local"
DEVICE_ID="drill-phone-$TS"
PASSWORD="DrillPass123!"

py() { python3 -c "$1"; }

# Get a user token — try register, fall back to login when the account
# already exists (previous run) so repeated drills keep working.
get_user_token() {
    local email="$1" name="$2" resp token
    resp=$(curl -s -m 10 -X POST "$SERVER_URL/api/auth/register" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\",\"display_name\":\"$name\"}")
    token=$(echo "$resp" | py 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
    if [ -z "$token" ]; then
        resp=$(curl -s -m 10 -X POST "$SERVER_URL/api/auth/user/login" \
            -H 'Content-Type: application/json' \
            -d "{\"email\":\"$email\",\"password\":\"$PASSWORD\"}")
        token=$(echo "$resp" | py 'import sys,json; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
    fi
    echo "$token"
}

echo -e "${BOLD}Magneetar Recovery Drill${NC} — server: $SERVER_URL"
echo "  owner:   $OWNER_EMAIL"
echo "  device:  $DEVICE_ID"

# ── 1. Health check ───────────────────────────────────────────────────────────
step "1/9 — Server health"
if curl -s -m 8 "$SERVER_URL/health" | grep -q '"status":"online"'; then
    ok "Server online"
else
    bad "Server unreachable at $SERVER_URL — start it first (cd server && ./venv/bin/uvicorn main:app --port 8000)"
    echo -e "\n${RED}Recovery drill aborted — no live server.${NC}"
    exit 1
fi

# ── 2. Register owner account ─────────────────────────────────────────────────
step "2/9 — Register owner account"
OWNER_TOKEN=$(get_user_token "$OWNER_EMAIL" "Drill Owner")
if [ -n "$OWNER_TOKEN" ]; then
    ok "Owner account ready (token ${OWNER_TOKEN:0:12}...)"
else
    bad "Owner registration failed — register rate limit may be exhausted. Wait ~10 min or clear rate_limits."
    exit 1
fi

# ── 3. Register linked device ─────────────────────────────────────────────────
step "3/9 — Register device linked to account"
DEV_REG=$(curl -s -m 10 -X POST "$SERVER_URL/api/device/register" \
    -H 'Content-Type: application/json' \
    -H "x-api-key: $API_KEY" \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -d "{\"device_id\":\"$DEVICE_ID\",\"fingerprint\":\"drill-fp-$DEVICE_ID\",\"model\":\"Drill Pixel 8\",\"os_version\":\"Android 15\",\"app_version\":\"1.1.0\",\"device_key\":\"drillkey-$DEVICE_ID\"}")
DEV_TOKEN=$(echo "$DEV_REG" | py 'import sys,json; print(json.load(sys.stdin).get("token",""))')
if [ -n "$DEV_TOKEN" ]; then
    ok "Device registered + account-linked (device token ${DEV_TOKEN:0:12}...)"
else
    bad "Device registration failed: $DEV_REG"
    exit 1
fi

# ── 4. Simulate theft ─────────────────────────────────────────────────────────
step "4/9 — Simulate theft (SIM change + airplane + location off + vehicle speed)"
# The FIRST ping already carries the full theft signature. Sentinel scores it
# >= 80 (sim 35 + airplane 15 + location-disabled 20 + vehicle speed 25 = 95)
# and, with no location history yet, activates theft mode immediately (the
# confirmation cap only applies once prior pings exist). Three pings total to
# be safe.
for i in 1 2 3; do
    LAT=$(py "print(round(9.0820 + $i*0.004, 6))")
    LNG=$(py "print(round(8.6753 + $i*0.004, 6))")
    curl -s -m 10 -X POST "$SERVER_URL/api/device/location" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer $DEV_TOKEN" \
        -d "{\"device_id\":\"$DEVICE_ID\",\"lat\":$LAT,\"lng\":$LNG,\"speed\":35.0,\"sim_changed\":true,\"is_airplane_mode\":true,\"is_location_enabled\":false,\"battery_percent\":85,\"ping_sequence\":$i,\"provider\":\"gps\",\"confidence_level\":\"HIGH\"}" > /dev/null
    sleep 1
done

# Confirm from the server's perspective
sleep 1
DEV_STATE=$(curl -s -m 10 "$SERVER_URL/api/dashboard/devices" -H "Authorization: Bearer $OWNER_TOKEN")
MODE=$(echo "$DEV_STATE" | py "
import sys,json
devs=json.load(sys.stdin).get('devices',[])
for d in devs:
    if d['id']=='$DEVICE_ID':
        print(d.get('operating_mode',''))
        break
")
STOLEN=$(echo "$DEV_STATE" | py "
import sys,json
devs=json.load(sys.stdin).get('devices',[])
for d in devs:
    if d['id']=='$DEVICE_ID':
        print('yes' if d.get('is_stolen') else 'no')
        break
")
if [ "$MODE" = "stolen" ] && [ "$STOLEN" = "yes" ]; then
    ok "Sentinel marked device STOLEN (operating_mode=$MODE)"
else
    bad "Device NOT marked stolen (mode=$MODE, is_stolen=$STOLEN). Theft signature may need more pings."
fi

# Verify an evidence case was auto-created
EVIDENCE=$(curl -s -m 10 "$SERVER_URL/api/dashboard/evidence/$DEVICE_ID" -H "Authorization: Bearer $OWNER_TOKEN")
CASE_ID=$(echo "$EVIDENCE" | py 'import sys,json; print(json.load(sys.stdin).get("case_id",""))')
if [ -n "$CASE_ID" ]; then
    ok "Evidence case auto-created: $CASE_ID"
else
    bad "No evidence case created"
fi

# ── 5. Launch community recovery ──────────────────────────────────────────────
step "5/9 — Owner launches community recovery (Guardian Network)"
REC=$(curl -s -m 10 -X POST "$SERVER_URL/api/recovery/requests" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $OWNER_TOKEN" \
    -d "{\"device_id\":\"$DEVICE_ID\",\"description\":\"Black Pixel 8 in a grey case, lost near Abuja mall\"}")
REC_ID=$(echo "$REC" | py 'import sys,json; print(json.load(sys.stdin).get("id",""))')
if [ -n "$REC_ID" ]; then
    ok "Recovery request launched: $REC_ID"
else
    bad "Recovery launch failed: $REC"
fi

# ── 6. Guardian opts in + scans nearby ────────────────────────────────────────
step "6/9 — Guardian opts in and scans nearby"
GTOKEN=$(get_user_token "$GUARDIAN_EMAIL" "Drill Guardian")
if [ -z "$GTOKEN" ]; then
    bad "Guardian account unavailable — register rate limit may be exhausted."
fi

OPT_IN=$(curl -s -m 10 -X POST "$SERVER_URL/api/guardian/opt-in" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $GTOKEN" \
    -d '{"opted_in":true,"radius_km":50,"handle":"EagleEye"}')
if [ -n "$GTOKEN" ] && echo "$OPT_IN" | grep -q '"opted_in":true'; then
    ok "Guardian opted in (handle: EagleEye)"
else
    bad "Guardian opt-in failed: $OPT_IN"
fi

NEARBY=$(curl -s -m 10 "$SERVER_URL/api/recovery/nearby?lat=9.09&lng=8.68&radius_km=50" \
    -H "Authorization: Bearer $GTOKEN")
N_COUNT=$(echo "$NEARBY" | py 'import sys,json; print(len(json.load(sys.stdin).get("requests",[])))')
N_MODEL=$(echo "$NEARBY" | py 'import sys,json; r=json.load(sys.stdin).get("requests",[]); print(r[0].get("device_model","") if r else "")')
N_BLUR=$(echo "$NEARBY" | py 'import sys,json; r=json.load(sys.stdin).get("requests",[]); print(r[0].get("blurred_lat","") if r else "")')
if [ "$N_COUNT" -ge 1 ] && [ "$N_MODEL" = "Drill Pixel 8" ]; then
    ok "Guardian sees the request nearby (model: $N_MODEL, blurred area lat=$N_BLUR)"
else
    bad "Guardian saw $N_COUNT nearby requests (expected ≥1). $NEARBY"
fi

# ── 7. Guardian reports a sighting ────────────────────────────────────────────
step "7/9 — Guardian reports a sighting"
SIGHT=$(curl -s -m 10 -X POST "$SERVER_URL/api/recovery/sightings" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $GTOKEN" \
    -d "{\"request_id\":\"$REC_ID\",\"lat\":9.095,\"lng\":8.682,\"note\":\"Saw this phone on a bus bench near the mall entrance\"}")
SID=$(echo "$SIGHT" | py 'import sys,json; print(json.load(sys.stdin).get("sighting_id",""))')
if [ -n "$SID" ]; then
    ok "Sighting #$SID reported by EagleEye"
else
    bad "Sighting report failed: $SIGHT"
fi

# ── 8. Owner sees the sighting ────────────────────────────────────────────────
step "8/9 — Owner's dashboard receives the sighting"
OWNER_REQS=$(curl -s -m 10 "$SERVER_URL/api/recovery/requests" -H "Authorization: Bearer $OWNER_TOKEN")
S_COUNT=$(echo "$OWNER_REQS" | py "
import sys,json
reqs=json.load(sys.stdin).get('requests',[])
for r in reqs:
    if r['id']=='$REC_ID':
        print(r.get('sighting_count',0)); break
")
S_HANDLE=$(echo "$OWNER_REQS" | py "
import sys,json
reqs=json.load(sys.stdin).get('requests',[])
for r in reqs:
    if r['id']=='$REC_ID' and r.get('sightings'):
        print(r['sightings'][0].get('guardian_handle','')); break
")
if [ "$S_COUNT" -ge 1 ] && [ "$S_HANDLE" = "EagleEye" ]; then
    ok "Owner sees $S_COUNT sighting(s) from $S_HANDLE"
else
    bad "Owner sighting count=$S_COUNT handle=$S_HANDLE"
fi

# ── 9. Close → device recovered ───────────────────────────────────────────────
step "9/9 — Owner closes the request → device recovered"
CLOSE=$(curl -s -m 10 -X POST "$SERVER_URL/api/recovery/requests/$REC_ID/close" \
    -H "Authorization: Bearer $OWNER_TOKEN")
if echo "$CLOSE" | grep -q 'recovered'; then
    ok "Recovery request closed — device marked recovered"
else
    bad "Close failed: $CLOSE"
fi

FINAL=$(curl -s -m 10 "$SERVER_URL/api/dashboard/devices" -H "Authorization: Bearer $OWNER_TOKEN")
F_MODE=$(echo "$FINAL" | py "
import sys,json
devs=json.load(sys.stdin).get('devices',[])
for d in devs:
    if d['id']=='$DEVICE_ID':
        print(d.get('operating_mode','')); break
")
if [ "$F_MODE" = "normal" ]; then
    ok "Device operating_mode back to normal — RECOVERED ✅"
else
    bad "Device operating_mode=$F_MODE (expected normal)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  RECOVERY DRILL RESULT: ${PASS} passed, ${FAIL} failed${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}  ✅ The system proved it can RECOVER A LOST SMART DEVICE.${NC}"
    echo -e "     Registered → linked → stolen → evidence → community recovery"
    echo -e "     → guardian sighting → recovered. Ready for Play Store review."
else
    echo -e "${RED}  ❌ $FAIL step(s) failed. See above for details.${NC}"
fi
echo ""
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
