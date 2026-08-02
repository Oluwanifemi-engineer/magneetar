#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Firebase Project Automation
# ══════════════════════════════════════════════════════════════════════════════
# Uses Firebase CLI (v15+) to:
#   1. Check / guide Firebase authentication
#   2. Create a Firebase project named "magneetar"
#   3. Register Android app with package "com.magneetar.app"
#   4. Download google-services.json    #   5. Enable Cloud Messaging API
    #   6. Download a Firebase service-account JSON and configure server .env
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

# Optional auth args for headless (CI) usage — empty array keeps call sites clean.
# NOTE: call sites use the "${arr[@]+...}" idiom because plain "${arr[@]}" on an
# EMPTY array errors under `set -u` on bash < 4.4 (macOS ships bash 3.2).
TOKEN_ARGS=()
[ -n "${FIREBASE_TOKEN:-}" ] && TOKEN_ARGS=(--token "$FIREBASE_TOKEN")

"$FIREBASE_BIN" projects:create "Magneetar" \
    --project "$PROJECT_ID" \
    --display-name "Magneetar" \
    "${TOKEN_ARGS[@]+"${TOKEN_ARGS[@]}"}" 2>&1 | head -5

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
    "${TOKEN_ARGS[@]+"${TOKEN_ARGS[@]}"}" 2>&1 | head -3

log "Android app registered"

# ── Step 4: Download google-services.json ───────────────────────────────────

header "Step 4/6 — Downloading google-services.json"

# Get the app ID and download config
APP_IDS=$("$FIREBASE_BIN" apps:list --project "$PROJECT_ID" --json "${TOKEN_ARGS[@]+"${TOKEN_ARGS[@]}"}" 2>/dev/null | \
    python3 -c "import sys,json; apps=json.load(sys.stdin).get('apps',[]); [print(a['appId']) for a in apps if a.get('packageName')=='com.magneetar.app']" 2>/dev/null || true)

if [ -n "$APP_IDS" ]; then
    APP_ID=$(echo "$APP_IDS" | head -1)
    log "App ID: $APP_ID"

    "$FIREBASE_BIN" apps:android:get-config \
        --project "$PROJECT_ID" \
        --app "$APP_ID" \
        "${TOKEN_ARGS[@]+"${TOKEN_ARGS[@]}"}" 2>/dev/null > "$FCM_CONFIG"

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

# ── Service account key (NOT the legacy server key) ──────────────────────
# Google deprecated the legacy FCM "server key" (the API key from
# google-services.json) in June 2024. The server sends pushes with the
# firebase-admin SDK, which REQUIRES a service-account JSON — the legacy
# key simply does not work. Download the default Firebase service account
# (PROJECT_ID@appspot.gserviceaccount.com) key and point MT_FIREBASE_KEY
# at the JSON file (or paste its contents as a JSON string).
SA_EMAIL="$PROJECT_ID@appspot.gserviceaccount.com"
SA_KEY_FILE="$PROJECT_DIR/server/firebase-service-account.json"

SA_DOWNLOADED=0
if command -v gcloud &>/dev/null; then
    echo -e "  Downloading service account key for ${CYAN}$SA_EMAIL${NC}..."
    if gcloud iam service-accounts keys create "$SA_KEY_FILE" \
        --iam-account="$SA_EMAIL" \
        --project="$PROJECT_ID" 2>/dev/null; then
        log "Service account key saved to server/firebase-service-account.json"
        SA_DOWNLOADED=1
    else
        warn "Could not create service account key (the default Firebase SA may not exist yet)."
    fi
else
    warn "gcloud CLI not found — service account key must be downloaded manually."
fi

if [ "$SA_DOWNLOADED" -eq 0 ]; then
    warn "Manual step required — download the service account key:"
    echo "  Firebase Console → Project settings → Service accounts"
    echo "  → Generate new private key → save as:"
    echo "  ${CYAN}server/firebase-service-account.json${NC}"
    echo "  Then set MT_FIREBASE_KEY to that file path (or its JSON contents)."
fi

if [ -f "$SA_KEY_FILE" ] && [ -f "$SERVER_ENV" ]; then
    if grep -q "^MT_FIREBASE_KEY=" "$SERVER_ENV"; then
        sed -i "s|^MT_FIREBASE_KEY=.*|MT_FIREBASE_KEY=\"$SA_KEY_FILE\"|" "$SERVER_ENV"
    else
        echo "MT_FIREBASE_KEY=\"$SA_KEY_FILE\"" >> "$SERVER_ENV"
    fi
    log "Server .env updated with FCM service account path"
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

if grep -q "^MT_FIREBASE_KEY=" "$SERVER_ENV" 2>/dev/null; then
    echo -e "  ${GREEN}[✓]${NC} FCM service account: ${CYAN}configured${NC}"
else
    echo -e "  ${GREEN}[ ]${NC} FCM service account: ${YELLOW}not configured${NC}"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Firebase setup complete!                                   ${NC}"
echo -e "${GREEN}                                                              ${NC}"
echo -e "${GREEN}  Next: Build the Android app to verify FCM integration:${NC}"
echo -e "  ${CYAN}  cd android-app && ./gradlew assembleDebug${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
