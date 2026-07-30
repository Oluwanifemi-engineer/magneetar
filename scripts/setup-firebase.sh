#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Firebase Cloud Messaging Setup Guide
# ══════════════════════════════════════════════════════════════════════════════
# This script does NOT automate Firebase Console operations (which require
# manual login and project creation). Instead it:
#   1. Validates the current placeholder google-services.json
#   2. Provides step-by-step Firebase Console instructions
#   3. Generates the correct server .env config for FCM
#   4. Tests the FCM configuration after setup
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FCM_CONFIG="$PROJECT_DIR/android-app/google-services.json"
SERVER_ENV="$PROJECT_DIR/server/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         Magneetar — Firebase Cloud Messaging Setup          ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Check current FCM config ───────────────────────────────────────

echo -e "${YELLOW}[1/5] Checking current google-services.json...${NC}"

if [ -f "$FCM_CONFIG" ]; then
    if grep -q "magneetar-placeholder" "$FCM_CONFIG"; then
        echo -e "  ${YELLOW}⚠ Placeholder detected — Firebase not configured.${NC}"
    else
        echo -e "  ${GREEN}✅ Real google-services.json found.${NC}"
    fi
else
    echo -e "  ${RED}❌ google-services.json missing entirely.${NC}"
fi

# ── Step 2: Firebase Console Instructions ───────────────────────────────────

echo ""
echo -e "${YELLOW}[2/5] Firebase Console Setup Instructions${NC}"
echo ""
echo -e "Follow these steps in your browser:"
echo ""
echo -e "${CYAN}  Step 1:${NC} Go to https://console.firebase.google.com"
echo -e "${CYAN}  Step 2:${NC} Sign in with your Google account"
echo -e "${CYAN}  Step 3:${NC} Click ${GREEN}\"Add project\"${NC}"
echo -e "         → Name: ${GREEN}\"Magneetar\"${NC}"
echo -e "         → Disable Google Analytics (or enable if desired)"
echo -e "         → Click ${GREEN}\"Create project\"${NC}"
echo ""
echo -e "${CYAN}  Step 4:${NC} Once created, click the ${GREEN}\"Android\"${NC} icon to add an Android app"
echo -e "         → Package name: ${GREEN}\"com.magneetar.app\"${NC}"
echo -e "         → App nickname: \"Magneetar\""
echo -e "         → Click ${GREEN}\"Register app\"${NC}"
echo ""
echo -e "${CYAN}  Step 5:${NC} ${GREEN}Download google-services.json${NC}"
echo -e "         → Click ${GREEN}\"Download google-services.json\"${NC}"
echo -e "         → Save it to: ${GREEN}$FCM_CONFIG${NC} (overwrite the placeholder)"
echo -e "         → Click \"Next\" then \"Continue to console\""
echo ""
echo -e "${CYAN}  Step 6:${NC} In Firebase Console left menu, go to"
echo -e "         ${GREEN}\"Project Settings\" → \"Cloud Messaging\"${NC}"
echo -e "         → Copy the ${GREEN}\"Server key\"${NC}"
echo -e "         → Save it as MT_FIREBASE_KEY in ${GREEN}$SERVER_ENV${NC}"
echo ""

# ── Step 3: Auto-validate when the file is replaced ────────────────────────

echo -e "${YELLOW}[3/5] Validation Tool${NC}"
echo -e "  When you've downloaded the real google-services.json, run:"
echo -e "  ${CYAN}  grep 'current_key\\|project_number\\|mobilesdk_app_id' $FCM_CONFIG${NC}"
echo ""
echo -e "  A valid file should show real values (not placeholder/zeros):"
echo ""

if [ -f "$FCM_CONFIG" ]; then
    CHECK=$(grep -E '(current_key|project_number|mobilesdk_app_id)' "$FCM_CONFIG" | head -3)
    echo "  $CHECK"
fi

# ── Step 4: Server .env configuration ───────────────────────────────────────

echo ""
echo -e "${YELLOW}[4/5] Server FCM Configuration${NC}"

if [ -f "$SERVER_ENV" ]; then
    # Check if MT_FIREBASE_KEY is already set
    if grep -q "^MT_FIREBASE_KEY=" "$SERVER_ENV" && ! grep -q "^MT_FIREBASE_KEY=\"\"" "$SERVER_ENV"; then
        echo -e "  ${GREEN}✅ MT_FIREBASE_KEY is already configured.${NC}"
    else
        echo -e "  ${YELLOW}⚠ MT_FIREBASE_KEY is empty or missing.${NC}"
        echo -e "  Add this line to $SERVER_ENV:"
        echo -e "  ${CYAN}  MT_FIREBASE_KEY=\"your-server-key-from-firebase-console\"${NC}"
    fi
else
    echo -e "  ${YELLOW}⚠ Server .env file not found at $SERVER_ENV${NC}"
fi

# ── Step 5: Test FCM after setup ───────────────────────────────────────────

echo ""
echo -e "${YELLOW}[5/5] Post-Setup Verification${NC}"
echo ""
echo -e "  After replacing google-services.json and configuring MT_FIREBASE_KEY:"
echo ""
echo -e "  ${CYAN}  1. Rebuild the Android app:${NC}"
echo -e "     cd android-app && ./gradlew assembleDebug"
echo ""
echo -e "  ${CYAN}  2. Restart the server:${NC}"
echo -e "     cd server && source venv/bin/activate && python3 main.py"
echo ""
echo -e "  ${CYAN}  3. Install APK on device and verify FCM token registration:${NC}"
echo -e "     adb install -r android-app/app/build/outputs/apk/debug/app-debug.apk"
echo ""
echo -e "  ${CYAN}  4. Check server logs for FCM token:${NC}"
echo -e "     grep 'FCM token registered' /var/log/magneetar/server.log"
echo -e "     # Or if running without log file, check stdout for:"
echo -e "     # 'FCM token registered' with device_id in output"
echo ""
echo -e "  ${CYAN}  5. Send a test push from the Firebase Console:${NC}"
echo -e "     Firebase Console → Cloud Messaging → Send your first message"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup guide complete. Follow steps 2-5 above manually.${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
