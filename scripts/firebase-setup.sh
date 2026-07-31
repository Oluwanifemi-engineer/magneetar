#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Firebase Project Automation
# ══════════════════════════════════════════════════════════════════════════════
# Uses Firebase CLI (v15+) to:
#   1. Check / guide Firebase authentication
#   2. Create a Firebase project named "magneetar"
#   3. Register Android app with package "com.magneetar.app"
#   4. Download google-services.json
#   5. Enable Cloud Messaging API
#   6. Configure server .env with FCM server key
#
# Prerequisites:
#   - Node.js 18+
#   - A Google account with billing enabled (Firebase Spark plan is free)
#
# Usage:
#   bash scripts/firebase-setup.sh              # Full automated setup
#   bash scripts/firebase-setup.sh --ci-token   # Use existing CI token
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FIREBASE_BIN="$PROJECT_DIR/node_modules/.bin/firebase"
FCM_CONFIG="$PROJECT_DIR/android-app/google-services.json"
SERVER_ENV="$PROJECT_DIR/server/.env"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ── Step 0: Validate environment ────────────────────────────────────────────

header "Step 0/6 — Validating Environment"

if [ ! -f "$FIREBASE_BIN" ]; then
    err "Firebase CLI not found. Run: npm install firebase-tools --save-dev"
fi

FIREBASE_VER=$("$FIREBASE_BIN" --version 2>/dev/null)
log "Firebase CLI: v${FIREBASE_VER}"

# Validate google-services.json is a placeholder (not real)
if [ -f "$FCM_CONFIG" ]; then
    if grep -q "magneetar-placeholder" "$FCM_CONFIG" 2>/dev/null; then
        warn "Placeholder google-services.json detected (project not yet created)"
    else
        log "Real google-services.json already present"
        exit 0
    fi
fi

# ── Step 1: Firebase Authentication ─────────────────────────────────────────

header "Step 1/6 — Firebase Authentication"

if [ -n "${FIREBASE_TOKEN:-}" ]; then
    log "Using FIREBASE_TOKEN from environment"
elif [ -f "$HOME/.config/configstore/firebase-tools.json" ]; then
    log "Existing Firebase session detected"
else
    echo ""
    echo -e "${YELLOW}  Firebase requires Google authentication.${NC}"
    echo ""
    echo -e "  ${BOLD}Option A: Browser login (recommended)${NC}"
    echo -e "  Run this command in your terminal:"
    echo -e "  ${CYAN}  npx firebase-tools login${NC}"
    echo ""
    echo -e "  ${BOLD}Option B: CI token (headless)${NC}"
    echo -e "  1. Run on your local machine:"
    echo -e "     ${CYAN}  npx firebase-tools login:ci${NC}"
    echo -e "  2. Set the token:"
    echo -e "     ${CYAN}  export FIREBASE_TOKEN=\"your-token-here\"${NC}"
    echo -e "  3. Re-run this script"
    echo ""
    err "Authentication required. Use one of the options above."
fi

# ── Step 2: Create Firebase Project ─────────────────────────────────────────

header "Step 2/6 — Creating Firebase Project"

PROJECT_ID="magneetar-$(date +%s)"
echo -e "  Project name: ${CYAN}Magneetar${NC}"
echo -e "  Project ID:   ${CYAN}$PROJECT_ID${NC}"
echo ""

# Optional auth args for headless (CI) usage — empty array keeps call sites clean
TOKEN_ARGS=()
[ -n "${FIREBASE_TOKEN:-}" ] && TOKEN_ARGS=(--token "$FIREBASE_TOKEN")

"$FIREBASE_BIN" projects:create "Magneetar" \
    --project "$PROJECT_ID" \
    --display-name "Magneetar" \
    "${TOKEN_ARGS[@]}" 2>&1 | head -5

log "Project created: $PROJECT_ID"

# ── Step 3: Register Android App ────────────────────────────────────────────

header "Step 3/6 — Registering Android App"

# Create a temporary Firebase app registration directory
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$TMP_DIR"

# Use Firebase CLI to add an Android app
"$FIREBASE_BIN" apps:create \
    --project "$PROJECT_ID" \
    --package-name "com.magneetar.app" \
    --display-name "Magneetar Android" \
    ANDROID \
    "${TOKEN_ARGS[@]}" 2>&1 | head -3

log "Android app registered"

# ── Step 4: Download google-services.json ───────────────────────────────────

header "Step 4/6 — Downloading google-services.json"

# Get the app ID and download config
APP_IDS=$("$FIREBASE_BIN" apps:list --project "$PROJECT_ID" --json "${TOKEN_ARGS[@]}" 2>/dev/null | \
    python3 -c "import sys,json; apps=json.load(sys.stdin).get('apps',[]); [print(a['appId']) for a in apps if a.get('packageName')=='com.magneetar.app']" 2>/dev/null || true)

if [ -n "$APP_IDS" ]; then
    APP_ID=$(echo "$APP_IDS" | head -1)
    log "App ID: $APP_ID"

    "$FIREBASE_BIN" apps:android:get-config \
        --project "$PROJECT_ID" \
        --app "$APP_ID" \
        "${TOKEN_ARGS[@]}" 2>/dev/null > "$FCM_CONFIG"

    log "google-services.json downloaded to: $FCM_CONFIG"
else
    warn "Could not auto-download google-services.json"
    echo "  Please download it manually from Firebase Console"
    echo "  and save to: $FCM_CONFIG"
fi

cd "$PROJECT_DIR"

# ── Step 5: Enable Cloud Messaging & Get Server Key ─────────────────────────

header "Step 5/6 — Configuring Cloud Messaging"

# Enable FCM API via Google Cloud
echo -e "  Enabling Firebase Cloud Messaging API..."
if command -v gcloud &>/dev/null; then
    if gcloud services enable fcm.googleapis.com \
        --project "$PROJECT_ID" 2>/dev/null; then
        log "FCM API enabled"
    else
        warn "Could not enable FCM API via gcloud. Enable manually at:
  https://console.cloud.google.com/apis/library/fcm.googleapis.com"
    fi
else
    warn "gcloud CLI not found. Enable FCM API manually at:
  https://console.cloud.google.com/apis/library/fcm.googleapis.com"
fi

# Get the FCM server key from Firebase
FCM_KEY=$("$FIREBASE_BIN" apps:android:get-config \
    --project "$PROJECT_ID" \
    --app "$APP_ID" \
    "${TOKEN_ARGS[@]}" 2>/dev/null | python3 -c "
import sys,json
try:
    cfg = json.load(sys.stdin)
    # Extract the current_key from api_key array
    for client in cfg.get('client', []):
        for api_key in client.get('api_key', []):
            key = api_key.get('current_key', '')
            if key and not key.startswith('AIzaSyPlaceholder'):
                print(key)
                sys.exit(0)
except: pass
" 2>/dev/null || true)

if [ -n "$FCM_KEY" ]; then
    if [ -f "$SERVER_ENV" ]; then
        if grep -q "^MT_FIREBASE_KEY=" "$SERVER_ENV"; then
            sed -i "s|^MT_FIREBASE_KEY=.*|MT_FIREBASE_KEY=\"$FCM_KEY\"|" "$SERVER_ENV"
        else
            echo "MT_FIREBASE_KEY=\"$FCM_KEY\"" >> "$SERVER_ENV"
        fi
        log "Server .env updated with FCM server key"
    fi
fi

# ── Step 6: Verification ────────────────────────────────────────────────────

header "Step 6/6 — Verification"

echo ""
echo -e "  ${BOLD}Checklist:${NC}"
echo ""
echo -e "  ${GREEN}[ ]${NC} Project created: ${CYAN}$PROJECT_ID${NC}"
echo -e "  ${GREEN}[ ]${NC} Android app registered: ${CYAN}com.magneetar.app${NC}"

if [ -f "$FCM_CONFIG" ] && ! grep -q "magneetar-placeholder" "$FCM_CONFIG" 2>/dev/null; then
    echo -e "  ${GREEN}[✓]${NC} google-services.json: ${CYAN}real config${NC}"
else
    echo -e "  ${GREEN}[ ]${NC} google-services.json: ${YELLOW}still placeholder${NC}"
fi

if grep -q "MT_FIREBASE_KEY=" "$SERVER_ENV" 2>/dev/null; then
    echo -e "  ${GREEN}[✓]${NC} Server FCM key: ${CYAN}configured${NC}"
else
    echo -e "  ${GREEN}[ ]${NC} Server FCM key: ${YELLOW}not configured${NC}"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Firebase setup complete!                                   ${NC}"
echo -e "${GREEN}                                                              ${NC}"
echo -e "${GREEN}  Next: Build the Android app to verify FCM integration:${NC}"
echo -e "  ${CYAN}  cd android-app && ./gradlew assembleDebug${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
