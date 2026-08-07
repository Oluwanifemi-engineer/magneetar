#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — APK Installer
# Installs the release APK on a connected Android device via ADB.
# Usage:
#   bash scripts/install-apk.sh                    # Interactive mode
#   bash scripts/install-apk.sh -y                 # Non-interactive (no clean)
#   bash scripts/install-apk.sh -y --clean         # Non-interactive + clean
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
# The project builds two flavors: `sideload` (full SMS relay — this is the
# installable APK) and `play` (SMS-stripped Play AAB). The old pre-flavor
# path (apk/release/app-release.apk) no longer exists.
APK_PATH="$PROJECT_DIR/android-app/app/build/outputs/apk/sideload/release/app-sideload-release.apk"
PACKAGE_NAME="com.magneetar.app"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Parse Args ──────────────────────────────────────────────────────────────

CLEAN_INSTALL=false
INTERACTIVE=true

for arg in "$@"; do
    case "$arg" in
        -y|--yes) INTERACTIVE=false ;;
        --clean) CLEAN_INSTALL=true ;;
    esac
done

# ── Checks ──────────────────────────────────────────────────────────────────

if ! command -v adb &>/dev/null; then
    echo -e "${RED}Error: ADB not found. Install Android SDK platform-tools.${NC}"
    exit 1
fi

if [ ! -f "$APK_PATH" ]; then
    echo -e "${YELLOW}Release APK not found at:${NC}"
    echo "  $APK_PATH"
    echo -e "${YELLOW}Building release APK first...${NC}"
    cd "$PROJECT_DIR/android-app"
    export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
    export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk}"
    ./gradlew assembleSideloadRelease --no-daemon
    echo ""
fi

# ── Device Check ────────────────────────────────────────────────────────────

DEVICES=$(adb devices | awk '$2 == "device" {print $1}' || true)

if [ -z "$DEVICES" ]; then
    echo -e "${RED}No Android devices connected.${NC}"
    echo "Connect your device via USB and enable USB debugging:"
    echo "  Developer Options → USB Debugging"
    exit 1
fi

echo -e "${GREEN}Found device(s):${NC}"
adb devices | awk '$2 == "device" {printf "  %s\n", $1}'

# ── Confirmation ────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Package:     ${NC}$PACKAGE_NAME"
echo -e "${CYAN}  APK:         ${NC}$APK_PATH ($(du -sh "$APK_PATH" | cut -f1))"
echo -e "${CYAN}  Version:     ${NC}$(grep 'versionName' "$PROJECT_DIR/android-app/app/build.gradle.kts" | grep -o '"[^"]*"' | tr -d '"')"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$INTERACTIVE" = true ]; then
    read -rp "Clean install (uninstall first)? [y/N] " CLEAN_RESPONSE
    if [[ "$CLEAN_RESPONSE" =~ ^[Yy]$ ]]; then
        CLEAN_INSTALL=true
    fi
fi

# ── Install ─────────────────────────────────────────────────────────────────

if [ "$CLEAN_INSTALL" = true ]; then
    echo -e "${YELLOW}Uninstalling previous version...${NC}"
    adb uninstall "$PACKAGE_NAME" || true
    echo ""
fi

echo -e "${YELLOW}Installing APK...${NC}"
adb install -r "$APK_PATH"

echo -e "${GREEN}APK installed successfully!${NC}"
echo ""
echo -e "${YELLOW}Next steps on device:${NC}"
echo "  1. Open Magneetar app"
echo "  2. Create an account or sign in"
echo "  3. Grant all requested permissions"
echo "  4. Enable battery optimization exemption"
echo ""
echo -e "${CYAN}To grant dangerous permissions automatically:${NC}"
echo "  adb shell pm grant $PACKAGE_NAME android.permission.ACCESS_FINE_LOCATION"
echo "  adb shell pm grant $PACKAGE_NAME android.permission.CAMERA"
echo "  adb shell pm grant $PACKAGE_NAME android.permission.RECORD_AUDIO"
