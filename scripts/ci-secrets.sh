#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — CI Secret Setup (build-apk.yml)
# ══════════════════════════════════════════════════════════════════════════════
# Configures the GitHub Actions secrets the release-signing workflow needs:
#
#   KEYSTORE_BASE64   base64 of android-app/release.keystore (gitignored)
#   KEYSTORE_PASS     store password          (android-app/local.properties)
#   KEY_ALIAS         signing alias           (android-app/local.properties)
#   KEY_ALIAS_PASS    key password            (android-app/local.properties)
#   API_KEY           the server master key   (android-app/local.properties,
#                     MUST match server/.env MT_API_KEY)
#   SERVER_URL        (optional, default https://api.magneetar.me)
#
# All values come from gitignored local files — nothing secret is stored in
# this script or in git. Without gh installed, it prints the exact commands
# to paste. With gh authenticated, `--apply` sets them directly.
#
# Usage:
#   bash scripts/ci-secrets.sh          # print ready-to-paste commands
#   bash scripts/ci-secrets.sh --apply  # set secrets via gh (needs gh auth)
#   bash scripts/ci-secrets.sh --help
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ANDROID_DIR="$PROJECT_DIR/android-app"
LOCAL_PROPS="$ANDROID_DIR/local.properties"
KEYSTORE="$ANDROID_DIR/release.keystore"

APPLY=false
REPO="${GH_REPO:-Oluwanifemi-engineer/magneetar}"

for arg in "$@"; do
    case "$arg" in
        --apply) APPLY=true ;;
        --help|-h)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

fail() { echo -e "\033[0;31m[✗] $1\033[0m" >&2; exit 1; }
log()  { echo -e "\033[0;32m[✓]\033[0m $1"; }
warn() { echo -e "\033[0;33m[⚠]\033[0m $1" >&2; }

# ── Validate sources ─────────────────────────────────────────────────────────
[ -f "$LOCAL_PROPS" ] || fail "Missing $LOCAL_PROPS (gitignored) — run scripts/build-release.sh once to generate it"
[ -f "$KEYSTORE" ] || fail "Missing $KEYSTORE (gitignored) — run scripts/build-release.sh once to generate it"

read_prop() {
    grep "^$1=" "$LOCAL_PROPS" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '[:space:]'
}

KEYSTORE_PASS="$(read_prop KEYSTORE_PASS)"
KEY_ALIAS="$(read_prop KEY_ALIAS)"
KEY_ALIAS_PASS="$(read_prop KEY_ALIAS_PASS)"
API_KEY="$(read_prop API_KEY)"
SERVER_URL="${SERVER_URL:-https://api.magneetar.me}"

[ -n "$KEYSTORE_PASS" ] || fail "KEYSTORE_PASS not in $LOCAL_PROPS"
[ -n "$KEY_ALIAS" ] || fail "KEY_ALIAS not in $LOCAL_PROPS"
[ -n "$KEY_ALIAS_PASS" ] || fail "KEY_ALIAS_PASS not in $LOCAL_PROPS"
[ -n "$API_KEY" ] || fail "API_KEY not in $LOCAL_PROPS"

# Sanity: the key must match the server's current MT_API_KEY (a mismatch ships
# an APK the server 401s — devices stay offline).
if [ -f "$PROJECT_DIR/server/.env" ]; then
    SERVER_KEY="$(grep '^MT_API_KEY=' "$PROJECT_DIR/server/.env" | head -1 | cut -d= -f2- | tr -d '[:space:]')"
    if [ -n "$SERVER_KEY" ] && [ "$SERVER_KEY" != "$API_KEY" ]; then
        warn "API_KEY in local.properties does NOT match server/.env MT_API_KEY — devices built from this key will be rejected (401)."
    fi
fi

KEYSTORE_B64="$(base64 -w0 "$KEYSTORE")"

log "Sources validated: keystore=$(stat -c%s "$KEYSTORE")B, alias=[$KEY_ALIAS], api_key=${API_KEY:0:8}…"

# ── Emit ─────────────────────────────────────────────────────────────────────
if [ "$APPLY" = true ]; then
    command -v gh >/dev/null 2>&1 || fail "gh CLI not installed. Run: bash scripts/ci-secrets.sh (print mode) and paste the commands."
    gh auth status >/dev/null 2>&1 || fail "gh not authenticated. Run: gh auth login"

    printf '%s' "$KEYSTORE_B64" | gh secret set KEYSTORE_BASE64 --repo "$REPO"
    printf '%s' "$KEYSTORE_PASS" | gh secret set KEYSTORE_PASS --repo "$REPO"
    printf '%s' "$KEY_ALIAS" | gh secret set KEY_ALIAS --repo "$REPO"
    printf '%s' "$KEY_ALIAS_PASS" | gh secret set KEY_ALIAS_PASS --repo "$REPO"
    printf '%s' "$API_KEY" | gh secret set API_KEY --repo "$REPO"
    printf '%s' "$SERVER_URL" | gh secret set SERVER_URL --repo "$REPO"
    log "All secrets set on $REPO (KEYSTORE_BASE64, KEYSTORE_PASS, KEY_ALIAS, KEY_ALIAS_PASS, API_KEY, SERVER_URL)"
    warn "Optional: GOOGLE_SERVICES_JSON (base64 of android-app/app/google-services.json) for real Firebase push."
    echo "  base64 -w0 android-app/app/google-services.json | gh secret set GOOGLE_SERVICES_JSON --repo $REPO"
else
    cat <<EOF
───────────────────────────────────────────────────────────────────────────────
 Paste these into your terminal (gh must be authenticated: gh auth login).
 Values are read live from your gitignored local files — the commands below
 are complete and ready to run.

$(command -v gh >/dev/null 2>&1 || echo '  # NOTE: gh is not installed on this machine yet — install it, then run:')

  gh auth login
  gh repo set-default $REPO

  printf '%s' '$KEYSTORE_B64' | gh secret set KEYSTORE_BASE64 --repo $REPO
  printf '%s' '$KEYSTORE_PASS' | gh secret set KEYSTORE_PASS --repo $REPO
  printf '%s' '$KEY_ALIAS' | gh secret set KEY_ALIAS --repo $REPO
  printf '%s' '$KEY_ALIAS_PASS' | gh secret set KEY_ALIAS_PASS --repo $REPO
  printf '%s' '$API_KEY' | gh secret set API_KEY --repo $REPO
  printf '%s' '$SERVER_URL' | gh secret set SERVER_URL --repo $REPO

  # Optional — real Firebase push (base64 of your google-services.json):
  # base64 -w0 android-app/app/google-services.json | gh secret set GOOGLE_SERVICES_JSON --repo $REPO

  # Verify:
  gh secret list --repo $REPO

───────────────────────────────────────────────────────────────────────────────
EOF
    echo ""
    warn "KEYSTORE_BASE64 contains the keystore — anyone with repo write access can read it."
    warn "Printing it here is safe on YOUR machine; never paste it into a public chat."
fi
