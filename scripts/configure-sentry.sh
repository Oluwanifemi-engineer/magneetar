#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Sentry Crash Reporting Setup
# Configures Sentry for both the server and Android app.
#
# Prerequisites:
#   1. A Sentry account (sign up at https://sentry.io)
#   2. Your Sentry DSN (found in Sentry → Projects → Create Project)
#
# Usage:
#   bash scripts/configure-sentry.sh <your-sentry-dsn>
#
# Example:
#   bash scripts/configure-sentry.sh https://abc123def456@o123456.ingest.sentry.io/654321
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        MAGNEETAR — Sentry Crash Reporting Setup             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Validate DSN ────────────────────────────────────────────────────────────

if [ $# -lt 1 ]; then
    echo -e "${RED}❌ Error: No Sentry DSN provided.${NC}"
    echo ""
    echo "Usage: bash scripts/configure-sentry.sh <your-sentry-dsn>"
    echo ""
    echo "To get your DSN:"
    echo "  1. Go to https://sentry.io"
    echo "  2. Create a new project (choose 'FastAPI' for server, 'Android' for app)"
    echo "  3. Copy the DSN string (starts with https://)"
    echo ""
    echo "Example:"
    echo -e "  ${CYAN}bash scripts/configure-sentry.sh https://abc123def456@o123456.ingest.sentry.io/654321${NC}"
    echo ""
    exit 1
fi

SENTRY_DSN="$1"

# Validate DSN format
if [[ ! "$SENTRY_DSN" =~ ^https://.+@.+\.ingest\.sentry\.io/[0-9]+$ ]]; then
    echo -e "${YELLOW}⚠ Warning: DSN format may be invalid.${NC}"
    echo "  Expected format: https://<key>@o<org>.ingest.sentry.io/<project_id>"
    echo "  Got: $SENTRY_DSN"
    echo ""
    read -rp "Continue anyway? [y/N] " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

echo -e "${GREEN}✅ DSN format accepted${NC}"
echo ""

# ── Step 1: Configure Server ────────────────────────────────────────────────

echo -e "${CYAN}[1/3] Configuring Server...${NC}"

SERVER_ENV="$PROJECT_DIR/server/.env"

if [ -f "$SERVER_ENV" ]; then
    # Uncomment or update the SENTRY_DSN line
    if grep -q '^MT_SENTRY_DSN=' "$SERVER_ENV"; then
        sed -i "s|^MT_SENTRY_DSN=.*|MT_SENTRY_DSN=$SENTRY_DSN|" "$SERVER_ENV"
        echo -e "  ${GREEN}✅ Updated MT_SENTRY_DSN in server/.env${NC}"
    elif grep -q '^# MT_SENTRY_DSN=' "$SERVER_ENV"; then
        sed -i "s|^# MT_SENTRY_DSN=.*|MT_SENTRY_DSN=$SENTRY_DSN|" "$SERVER_ENV"
        echo -e "  ${GREEN}✅ Uncommented and set MT_SENTRY_DSN in server/.env${NC}"
    else
        echo "MT_SENTRY_DSN=$SENTRY_DSN" >> "$SERVER_ENV"
        echo -e "  ${GREEN}✅ Added MT_SENTRY_DSN to server/.env${NC}"
    fi
else
    echo "MT_SENTRY_DSN=$SENTRY_DSN" > "$SERVER_ENV"
    echo -e "  ${GREEN}✅ Created server/.env with MT_SENTRY_DSN${NC}"
fi

echo ""

# ── Step 2: Restart Server to Pick Up New Env ───────────────────────────────

echo -e "${CYAN}[2/3] Restarting Server to Apply Changes...${NC}"

if command -v docker &>/dev/null && docker ps --filter name=magneetar-server --format '{{.Names}}' 2>/dev/null | grep -q magneetar-server; then
    cd "$PROJECT_DIR"
    docker compose restart server 2>&1
    echo -e "  ${GREEN}✅ Server restarted${NC}"
else
    echo -e "  ${YELLOW}⚠ Docker not available or server not running.${NC}"
    echo "  Restart the server manually after Sentry is configured."
fi

echo ""

# ── Step 3: Android App Instructions ────────────────────────────────────────

echo -e "${CYAN}[3/3] Android App Configuration${NC}"
echo ""
echo "The Android app reads the DSN from the build config field SENTRY_DSN."
echo "You can configure it in two ways:"
echo ""
echo "  Option A: Set environment variable before building:"
echo -e "    ${CYAN}export MT_SENTRY_DSN=\"$SENTRY_DSN\"${NC}"
echo -e "    ${CYAN}cd android-app && ./gradlew assembleRelease${NC}"
echo ""
echo "  Option B: Create local.properties in android-app/:"
echo -e "    ${CYAN}echo \"SENTRY_DSN=$SENTRY_DSN\" >> android-app/local.properties${NC}"
echo -e "    ${CYAN}cd android-app && ./gradlew assembleRelease${NC}"
echo ""
echo "  Option C: For the release APK, update the build command:"
echo -e "    ${CYAN}cd android-app && ./gradlew assembleRelease -PSENTRY_DSN=\"$SENTRY_DSN\"${NC}"
echo ""

# ── Verify Server Sentry Initialization ─────────────────────────────────────

echo -e "${CYAN}Verifying Sentry initialization...${NC}"
sleep 2

if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Server is running${NC}"
    echo ""
    echo "Check server logs for Sentry initialization:"
    echo -e "  ${CYAN}docker logs magneetar-server 2>&1 | grep -i sentry${NC}"
else
    echo -e "  ${YELLOW}⚠ Could not reach server on localhost:8002${NC}"
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          ✅ Sentry Configuration Complete!                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  1. Rebuild the Android APK with Sentry enabled:"
echo -e "     ${CYAN}cd android-app && ./gradlew assembleRelease -PSENTRY_DSN=\"$SENTRY_DSN\"${NC}"
echo ""
echo "  2. Sentry will now capture crashes from:"
echo "     - Server: Unhandled exceptions, slow requests, error logs"
echo "     - Android App: Crashes, ANRs, native crashes"
echo ""
echo "  3. To disable Sentry temporarily, comment out the DSN:"
echo -e "     ${CYAN}sed -i 's/^MT_SENTRY_DSN=/# MT_SENTRY_DSN=/' server/.env${NC}"
echo ""
