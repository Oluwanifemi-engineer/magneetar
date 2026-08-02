#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Enable HARD Uninstall Protection (Device Owner mode)
# ══════════════════════════════════════════════════════════════════════════════
# By default, Magneetar's active Device Admin already blocks uninstallation:
# Android refuses to uninstall the app until the admin is deactivated (and
# deactivation shows a strong warning + alerts the server).
#
# For the HARD block (Settings "Uninstall" disabled entirely, `adb uninstall`
# fails), the app must be the DEVICE OWNER. This script provisions that via:
#
#     adb shell dpm set-device-owner com.magneetar.app/.AdminReceiver
#
# ── REQUIREMENTS ──────────────────────────────────────────────────────────────
#   • USB debugging enabled on the phone, device connected & authorized
#   • Device must have NO accounts set up (remove Google/other accounts first)
#   • For best results on a phone already in use: back up, factory reset, and
#     run this script BEFORE adding any account during setup
#
# ── AFTER PROVISIONING ───────────────────────────────────────────────────────
#   • Magneetar calls setUninstallBlocked(true) automatically on launch /
#     admin activation — uninstall becomes impossible through the UI or adb.
#   • To REMOVE it later:  adb shell dpm remove-active-admin com.magneetar.app/.AdminReceiver
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}Magneetar — Hard Uninstall Protection (Device Owner)${NC}"
echo ""

if ! command -v adb &>/dev/null; then
    echo -e "${RED}Error: adb not found. Install Android SDK platform-tools.${NC}" >&2
    exit 1
fi

if ! adb get-state &>/dev/null; then
    echo -e "${RED}Error: no device connected / authorized. Run 'adb devices' first.${NC}" >&2
    exit 1
fi

echo -e "${YELLOW}Checking device state…${NC}"
# A device that already has accounts cannot take a device owner via adb.
ACCOUNTS=$(adb shell pm list accounts 2>/dev/null || true)
if echo "$ACCOUNTS" | grep -q "Account"; then
    echo -e "${YELLOW}⚠  This device has accounts configured. Device-owner provisioning via adb"
    echo -e "   typically FAILS with 'Not allowed to set the device owner'.${NC}"
    echo -e "   Recommended: back up → factory reset → run this script during setup."
    read -r -p "Attempt anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
fi

echo ""
echo -e "${CYAN}Provisioning Magneetar as device owner…${NC}"
OUTPUT=$(adb shell dpm set-device-owner com.magneetar.app/.AdminReceiver 2>&1) || {
    echo -e "${RED}Provisioning failed:${NC}"
    echo "$OUTPUT"
    echo ""
    echo -e "${YELLOW}Common fixes:${NC}"
    echo "  1. Remove all accounts (Settings → Accounts → remove each)"
    echo "  2. Disable screen lock temporarily (device owner needs none)"
    echo "  3. Or factory-reset and run during first setup"
    exit 1
}

echo -e "${GREEN}✓ Device owner set.${NC}"
echo -e "${GREEN}✓ Open Magneetar once — it will apply the hard uninstall block automatically.${NC}"
echo ""
echo -e "${YELLOW}To verify:${NC}   adb shell dpm list-owners"
echo -e "${YELLOW}To remove:${NC}   adb shell dpm remove-active-admin com.magneetar.app/.AdminReceiver"
