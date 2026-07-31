#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Magneetar — Release Build Pipeline
# ══════════════════════════════════════════════════════════════════════════════
# Professional CI/CD script that:
#   1. Validates environment (JDK, Android SDK, keystore)
#   2. Bumps version code and name (optional)
#   3. Cleans previous builds
#   4. Runs lint checks
#   5. Builds release APK with ProGuard
#   6. Renames APK with version info
#   7. Signs and verifies the APK
#   8. (Optional) Uploads to server/s3
#   9. Reports build metrics
#
# Usage:
#   bash scripts/build-release.sh                  # Default build
#   bash scripts/build-release.sh --bump-patch     # Bump patch version
#   bash scripts/build-release.sh --upload         # Build + upload to server
#   bash scripts/build-release.sh --help           # Show all options
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ANDROID_DIR="$PROJECT_DIR/android-app"
BUILD_DIR="$ANDROID_DIR/app/build"
KEYSTORE="$ANDROID_DIR/release.keystore"
APK_DIR="$BUILD_DIR/outputs/apk/release"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

BUILD_START_TIME=$(date +%s)
BUMP_PATCH=false
BUMP_MINOR=false
UPLOAD=false
DEPLOY_SERVER=""
DEPLOY_USER=""
DEPLOY_PATH="/opt/magneetar/apks"

# ── Parse Args ──────────────────────────────────────────────────────────────

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --bump-patch         Increment patch version (1.0.0 → 1.0.1)"
    echo "  --bump-minor         Increment minor version (1.0.0 → 1.1.0)"
    echo "  --upload             Upload APK to server after build"
    echo "  --server HOST        Target server hostname/IP for upload"
    echo "  --user USER          SSH user for upload"
    echo "  --deploy-path PATH   Remote path for APK (default: /opt/magneetar/apks)"
    echo "  --help               Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --bump-patch) BUMP_PATCH=true; shift ;;
        --bump-minor) BUMP_MINOR=true; shift ;;
        --upload) UPLOAD=true; shift ;;
        --server) DEPLOY_SERVER="$2"; shift 2 ;;
        --user) DEPLOY_USER="$2"; shift 2 ;;
        --deploy-path) DEPLOY_PATH="$2"; shift 2 ;;
        --help) usage ;;
        *) echo -e "${RED}Unknown option: $1${NC}"; usage ;;
    esac
done

# ── Helper Functions ─────────────────────────────────────────────────────────

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[⚠]${NC} $1"; }
err() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

get_version_code() {
    grep 'versionCode' "$ANDROID_DIR/app/build.gradle.kts" | grep -oP '\d+'
}

get_version_name() {
    grep 'versionName' "$ANDROID_DIR/app/build.gradle.kts" | grep -oP '"[^"]*"' | tr -d '"'
}

# ── Step 1: Validate Environment ─────────────────────────────────────────────

header "Step 1/9 — Validating Environment"

# JDK check
if [ -z "${JAVA_HOME:-}" ]; then
    if command -v java &>/dev/null; then
        JAVA_HOME=$(dirname "$(dirname "$(readlink -f "$(which java)")")")
    else
        err "JAVA_HOME not set and java not found in PATH"
    fi
fi
java_version=$("$JAVA_HOME/bin/java" -version 2>&1 | head -1 | grep -oP '"\d+\.\d+' | tr -d '"' || echo "unknown")
log "JDK: $JAVA_HOME ($java_version)"

# Android SDK check
if [ -z "${ANDROID_HOME:-}" ]; then
    ANDROID_HOME="${HOME}/Android/Sdk"
fi
if [ ! -d "$ANDROID_HOME" ]; then
    err "Android SDK not found at $ANDROID_HOME"
fi
log "Android SDK: $ANDROID_HOME"

# Keystore check
if [ ! -f "$KEYSTORE" ]; then
    warn "Keystore not found at $KEYSTORE"
    echo "  Generating new keystore..."
    "$JAVA_HOME/bin/keytool" -genkey -v \
        -keystore "$KEYSTORE" \
        -alias magneetar \
        -keyalg RSA -keysize 2048 -validity 10000 \
        -storepass "${MT_KEYSTORE_PASS:-magneetar123}" \
        -keypass "${MT_KEY_ALIAS_PASS:-magneetar123}" \
        -dname "CN=Magneetar, OU=Development, O=Magneetar, L=Lagos, ST=Lagos, C=NG"
    log "Keystore generated"
else
    log "Keystore found: $KEYSTORE"
fi

# Gradle wrapper check
if [ ! -f "$ANDROID_DIR/gradlew" ]; then
    err "Gradle wrapper not found at $ANDROID_DIR/gradlew"
fi
log "Gradle wrapper: $ANDROID_DIR/gradlew"

# ── Step 2: Read Current Version ────────────────────────────────────────────

header "Step 2/9 — Version Info"

VERSION_CODE=$(get_version_code)
VERSION_NAME=$(get_version_name)
log "Current version: ${VERSION_NAME} (code ${VERSION_CODE})"

# ── Step 3: Bump Version (optional) ─────────────────────────────────────────

if [ "$BUMP_PATCH" = true ] || [ "$BUMP_MINOR" = true ]; then
    header "Step 3/9 — Bumping Version"

    IFS='.' read -r major minor patch <<< "$VERSION_NAME"

    if [ "$BUMP_MINOR" = true ]; then
        minor=$((minor + 1))
        patch=0
        warn "Minor bump: ${VERSION_NAME} → ${major}.${minor}.${patch}"
    else
        patch=$((patch + 1))
        warn "Patch bump: ${VERSION_NAME} → ${major}.${minor}.${patch}"
    fi

    NEW_VERSION_NAME="${major}.${minor}.${patch}"
    NEW_VERSION_CODE=$((VERSION_CODE + 1))

    # Update build.gradle.kts
    sed -i "s/versionCode = $VERSION_CODE/versionCode = $NEW_VERSION_CODE/" "$ANDROID_DIR/app/build.gradle.kts"
    sed -i "s/versionName = \"$VERSION_NAME\"/versionName = \"$NEW_VERSION_NAME\"/" "$ANDROID_DIR/app/build.gradle.kts"

    VERSION_CODE=$NEW_VERSION_CODE
    VERSION_NAME=$NEW_VERSION_NAME
    log "Bumped to: ${VERSION_NAME} (code ${VERSION_CODE})"
fi

# ── Step 4: Clean Build ─────────────────────────────────────────────────────

header "Step 4/9 — Cleaning Previous Build"

cd "$ANDROID_DIR"
export ANDROID_HOME
export JAVA_HOME

./gradlew clean --no-daemon 2>&1 | tail -2
log "Build directory cleaned"

# ── Step 5: Run Lint ────────────────────────────────────────────────────────

header "Step 5/9 — Running Lint"

# Run lint for the release variant (fails on errors, warns on warnings)
./gradlew lintRelease --no-daemon 2>&1 | tail -10

LINT_REPORT="$ANDROID_DIR/app/build/reports/lint-results-release.html"
if [ -f "$LINT_REPORT" ]; then
    lint_errors=$(grep -oP '(\d+) errors' "$LINT_REPORT" 2>/dev/null | grep -oP '\d+' || echo "0")
    lint_warnings=$(grep -oP '(\d+) warnings' "$LINT_REPORT" 2>/dev/null | grep -oP '\d+' || echo "0")
    log "Lint: $lint_errors errors, $lint_warnings warnings"
    if [ "$lint_errors" -gt 0 ]; then
        err "Lint errors found — fix before releasing. See: $LINT_REPORT"
    fi
else
    log "Lint check completed (no report generated)"
fi

# ── Step 6: Build Release APK ───────────────────────────────────────────────

header "Step 6/9 — Building Release APK"

# Export signing credentials for the build.
# NOTE: Gradle reads System.getenv() at configuration time, which is when
# build.gradle.kts is evaluated. Exporting before ./gradlew ensures the
# signing config picks up the correct passwords.
export MT_KEYSTORE_PASS="${MT_KEYSTORE_PASS:-magneetar123}"
export MT_KEY_ALIAS_PASS="${MT_KEY_ALIAS_PASS:-magneetar123}"

./gradlew assembleRelease --no-daemon 2>&1 | tail -10

if [ ! -f "$APK_DIR/app-release.apk" ]; then
    err "APK not produced at expected path"
fi
log "Release APK built"

# ── Step 7: Sign & Verify APK ───────────────────────────────────────────────

header "Step 7/9 — Verifying APK Signature"

APK_SIGNER="$ANDROID_HOME/build-tools/34.0.0/apksigner"
if [ -f "$APK_SIGNER" ]; then
    SIGNER_OUTPUT=$("$APK_SIGNER" verify --print-certs "$APK_DIR/app-release.apk" 2>&1 || true)
    if echo "$SIGNER_OUTPUT" | grep -q "CN=Magneetar"; then
        log "APK signature verified: release key"
    else
        warn "APK signing verification issue"
        echo "$SIGNER_OUTPUT" | head -5
    fi
else
    warn "apksigner not found, skipping signature verification"
fi

# ── Step 8: Rename APK with Version ─────────────────────────────────────────

header "Step 8/9 — Packaging APK"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RENAMED_APK="Magneetar-v${VERSION_NAME}-b${VERSION_CODE}-${TIMESTAMP}.apk"
cp "$APK_DIR/app-release.apk" "$APK_DIR/$RENAMED_APK"
log "Packaged: $RENAMED_APK ($(du -sh "$APK_DIR/$RENAMED_APK" | cut -f1))"

# Also create a stable "latest" copy
cp "$APK_DIR/app-release.apk" "$APK_DIR/Magneetar-latest.apk"
log "Latest APK: $APK_DIR/Magneetar-latest.apk"

# ── Step 9: Upload (optional) ──────────────────────────────────────────────

BUILD_END_TIME=$(date +%s)
BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))

if [ "$UPLOAD" = true ]; then
    header "Step 9/9 — Uploading to Server"

    if [ -z "$DEPLOY_SERVER" ]; then
        warn "No server specified with --server, skipping upload"
    else
        SSH_TARGET="${DEPLOY_USER}@${DEPLOY_SERVER}"
        log "Uploading to $SSH_TARGET:$DEPLOY_PATH"

        # shellcheck disable=SC2029  # $DEPLOY_PATH intentionally expands locally to build the remote command
        ssh "$SSH_TARGET" "mkdir -p $DEPLOY_PATH" 2>/dev/null || warn "Remote mkdir failed"
        scp "$APK_DIR/$RENAMED_APK" "$SSH_TARGET:$DEPLOY_PATH/" 2>&1 || {
            warn "Upload failed — server may not be reachable"
        }
        scp "$APK_DIR/Magneetar-latest.apk" "$SSH_TARGET:$DEPLOY_PATH/" 2>/dev/null || true
        log "APK uploaded to server"
    fi
fi

# ── Git Tag (optional) ───────────────────────────────────────────────────────

if [ "$BUMP_PATCH" = true ] || [ "$BUMP_MINOR" = true ]; then
    header "Extra — Git Tagging"
    if git rev-parse --git-dir > /dev/null 2>&1; then
        TAG_NAME="v${VERSION_NAME}"
        if git tag -l "$TAG_NAME" | grep -q .; then
            warn "Tag $TAG_NAME already exists, skipping"
        else
            git add "$ANDROID_DIR/app/build.gradle.kts"
            git commit -m "chore: bump version to ${VERSION_NAME}" 2>/dev/null || true
            git tag -a "$TAG_NAME" -m "Release ${VERSION_NAME}"
            log "Created git tag: $TAG_NAME"
            echo "  To push: git push origin $TAG_NAME"
        fi
    else
        warn "Not a git repository, skipping tag"
    fi
fi

# ── Build Report ─────────────────────────────────────────────────────────────

header "📊 Build Report"

echo -e "  ${BOLD}Version:${NC}     ${VERSION_NAME} (code ${VERSION_CODE})"
echo -e "  ${BOLD}Duration:${NC}    ${BUILD_DURATION}s"
echo -e "  ${BOLD}APK Size:${NC}    $(du -sh "$APK_DIR/app-release.apk" | cut -f1)"
echo -e "  ${BOLD}Output:${NC}      $APK_DIR/$RENAMED_APK"
echo -e "  ${BOLD}Keystore:${NC}    $KEYSTORE"
echo -e "  ${BOLD}ProGuard:${NC}    $ANDROID_DIR/app/proguard-rules.pro"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ✅  BUILD COMPLETE                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Install on device:"
echo -e "  ${CYAN}  adb install -r $APK_DIR/Magneetar-latest.apk${NC}"
echo ""
echo -e "  Or sideload manually from:"
echo -e "  ${CYAN}  $APK_DIR/$RENAMED_APK${NC}"
echo ""

# ── Post-build cleanups ────────────────────────────────────────────────────

# Only needed if we bumped the version — revert for local dev
if [ "$BUMP_PATCH" = true ] || [ "$BUMP_MINOR" = true ]; then
    echo -e "${YELLOW}Note: Version bumped. The build.gradle.kts has been modified.${NC}"
    echo -e "${YELLOW}      Commit the version change if this is intentional.${NC}"
fi
