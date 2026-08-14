#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — APK Installer + Install Diagnostic
# Installs the release APK on a connected Android device via ADB.
#
# Android's on-device "App not installed" message hides the real reason —
# adb never lies. This script prints the exact failure when an install fails,
# and it handles the case that breaks every other installer for THIS app:
# Magneetar protects itself from removal (device admin + accessibility guard +
# optional device-owner hard block), so an old install can linger invisibly
# and make new installs fail with a plain "App not installed".
#
# Usage:
#   bash scripts/install-apk.sh                    # Interactive mode
#   bash scripts/install-apk.sh -y                 # Non-interactive (no clean)
#   bash scripts/install-apk.sh -y --clean         # Non-interactive + clean install
#   bash scripts/install-apk.sh -y --sideload      # Sideload (SMS-relay) flavor
#   bash scripts/install-apk.sh --apk /path/x.apk  # Install a specific APK
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="com.magneetar.app"
ADMIN_COMPONENT="$PACKAGE_NAME/com.magneetar.app.AdminReceiver"

# Default to the `play` flavor — it is the build the download page serves and
# the one testers actually install. `--sideload` switches to the full
# SMS-relay flavor used for development.
APK_PATH="$PROJECT_DIR/android-app/app/build/outputs/apk/play/release/app-play-release.apk"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Parse Args ──────────────────────────────────────────────────────────────

CLEAN_INSTALL=false
INTERACTIVE=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--yes) INTERACTIVE=false ;;
        --clean) CLEAN_INSTALL=true ;;
        --sideload) APK_PATH="$PROJECT_DIR/android-app/app/build/outputs/apk/sideload/release/app-sideload-release.apk" ;;
        --apk) APK_PATH="$2"; shift ;;
        *) echo -e "${RED}Unknown argument: $1${NC}"; exit 1 ;;
    esac
    shift
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
    if [[ "$APK_PATH" == *sideload* ]]; then
        ./gradlew assembleSideloadRelease --no-daemon
    else
        ./gradlew assemblePlayRelease --no-daemon
    fi
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

# ── Device Diagnostics (the info that explains a failed install) ────────────

echo -e "${CYAN}── Device info ─────────────────────────────────────────────${NC}"
echo -e "  Model:         $(adb shell getprop ro.product.manufacturer 2>/dev/null | tr -d '\r') $(adb shell getprop ro.product.model 2>/dev/null | tr -d '\r')"
echo -e "  Android:       $(adb shell getprop ro.build.version.release 2>/dev/null | tr -d '\r') (API $(adb shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r'))"

INSTALLED_VERSION=""
if adb shell pm list packages 2>/dev/null | grep -q "^package:$PACKAGE_NAME$"; then
    INSTALLED_VERSION=$(adb shell dumpsys package "$PACKAGE_NAME" 2>/dev/null | grep -m1 "versionName=" | sed 's/.*versionName=//' | tr -d '\r')
    echo -e "  Magneetar:     ${YELLOW}STILL INSTALLED (version $INSTALLED_VERSION)${NC} ← uninstall before installing"
else
    echo -e "  Magneetar:     not installed"
fi

# Device-owner / active-admin state — the two ways Magneetar hard-blocks uninstall.
if adb shell dpm list-owners 2>/dev/null | grep -q "$PACKAGE_NAME"; then
    echo -e "  Device owner:  ${RED}YES${NC} — setUninstallBlocked is active; uninstall is hard-blocked until removed"
elif adb shell dumpsys device_policy 2>/dev/null | grep -q "active admin: $ADMIN_COMPONENT\|$PACKAGE_NAME"; then
    echo -e "  Device admin:  ${YELLOW}active${NC} — uninstall is disabled in Settings until admin is deactivated"
else
    echo -e "  Device admin:  none active"
fi

# ── Confirmation ────────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  Package:     ${NC}$PACKAGE_NAME"
echo -e "${CYAN}  APK:         ${NC}$APK_PATH ($(du -sh "$APK_PATH" | cut -f1))"
echo -e "${CYAN}  Version:     ${NC}$(grep 'versionName' "$PROJECT_DIR/android-app/app/build.gradle.kts" | grep -o '\"[^\"]*\"' | tr -d '\"')"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$INTERACTIVE" = true ]; then
    read -rp "Clean install (uninstall first)? [y/N] " CLEAN_RESPONSE
    if [[ "$CLEAN_RESPONSE" =~ ^[Yy]$ ]]; then
        CLEAN_INSTALL=true
    fi
fi

# ── Clean (handles Magneetar's own uninstall protection) ────────────────────

if [ "$CLEAN_INSTALL" = true ]; then
    echo -e "${YELLOW}Cleaning previous install...${NC}"

    # Device owner hard-blocks even `adb uninstall`. Lift it first.
    if adb shell dpm list-owners 2>/dev/null | grep -q "$PACKAGE_NAME"; then
        echo -e "  Removing device-owner state (needed before uninstall)..."
        adb shell dpm remove-active-admin "$ADMIN_COMPONENT" >/dev/null 2>&1 || true
        adb uninstall "$PACKAGE_NAME" >/dev/null 2>&1 || true
    else
        adb uninstall "$PACKAGE_NAME" >/dev/null 2>&1 || true
    fi

    # Verify it actually went away — if not, fail loudly with the fix.
    if adb shell pm list packages 2>/dev/null | grep -q "^package:$PACKAGE_NAME$"; then
        echo -e "${RED}Magneetar is still installed and refused to uninstall.${NC}"
        echo "This is the app's uninstall protection. On the phone:"
        echo "  Settings → Security → Device admin apps → Magneetar → Deactivate"
        echo "  Settings → Accessibility → 'System Update Protection' → OFF"
        echo "Then rerun this script with --clean. (On Samsung also check"
        echo "  Settings → Battery → Background usage limits → App protection.)"
        exit 1
    fi
    echo -e "  ${GREEN}Old install removed.${NC}"
    echo ""
fi

# ── Install ─────────────────────────────────────────────────────────────────

echo -e "${YELLOW}Installing APK...${NC}"
# Do NOT swallow the error — on failure adb prints the definitive
# INSTALL_FAILED_* reason that the phone's "App not installed" hides.
if ! adb install -r "$APK_PATH"; then
    echo ""
    echo -e "${RED}Install failed.${NC} The line above (e.g. INSTALL_FAILED_*) is the"
    echo "real reason — record it verbatim. Common ones:"
    echo "  INSTALL_FAILED_UPDATE_INCOMPATIBLE  → old install still present (run --clean)"
    echo "  INSTALL_FAILED_VERSION_DOWNGRADE    → phone has a NEWER version already"
    echo "  INSTALL_FAILED_OLDER_SDK            → Android too old (need 7.0+)"
    echo "  INSTALL_FAILED_USER_RESTRICTED      → OEM/'Install apps' restriction"
    echo "  INSTALL_FAILED_INVALID_APK          → file corrupt — redownload from magneetar.me"
    exit 1
fi

# ── Verify ──────────────────────────────────────────────────────────────────

INSTALLED_VERSION=$(adb shell dumpsys package "$PACKAGE_NAME" 2>/dev/null | grep -m1 "versionName=" | sed 's/.*versionName=//' | tr -d '\r')
echo -e "${GREEN}APK installed successfully!${NC} (version $INSTALLED_VERSION)"
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
