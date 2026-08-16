#!/usr/bin/env bash
# Build a clean source tarball for a tagged Magneetar release.
#
# Purpose: Magneetar's repo is private (commit diary not exposed) but the
# "open source" claim on the site stays honest — each tagged release ships
# a verifiable source tarball + SHA-256, the same way many security tools
# publish. The tarball is a snapshot of the TREE at the tag, not the .git
# history, so the S-ID/fix-timeline diary never leaves the private repo.
#
# Usage:
#   scripts/make-source-tarball.sh [tag] [output-dir]
#   scripts/make-source-tarball.sh          # HEAD (current working tree)
#   scripts/make-source-tarball.sh v1.4.4 /tmp/releases
#
# Outputs: <output-dir>/magneetar-<version>-source.tar.gz + .sha256

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="${1:-HEAD}"
OUT_DIR="${2:-dist}"

if [ "$TAG" = "HEAD" ]; then
    VERSION="$(cat "$REPO_ROOT/VERSION")"
    echo "==> No tag given — using HEAD (working tree), version from VERSION file"
else
    if ! git -C "$REPO_ROOT" rev-parse "$TAG" >/dev/null 2>&1; then
        echo "ERROR: tag '$TAG' does not exist" >&2
        exit 1
    fi
    VERSION="${TAG#v}"
fi

mkdir -p "$OUT_DIR"
STAGE="$OUT_DIR/magneetar-$VERSION-source"
TARBALL="$OUT_DIR/magneetar-$VERSION-source.tar.gz"

echo "==> Exporting tree at $TAG (no .git history, no build artifacts)"
rm -rf "$STAGE"
mkdir -p "$STAGE"
if [ "$TAG" = "HEAD" ]; then
    # Untracked-but-needed files (like this script or the gitmessage
    # template) are NOT in HEAD's tree — copy from the working tree so the
    # tarball reflects what's actually on disk, then strip artifacts.
    cp -r "$REPO_ROOT"/. "$STAGE"/ 2>/dev/null || true
    # The working-tree copy drags .git along — remove it (history stays private).
    rm -rf "$STAGE/.git"
else
    git -C "$REPO_ROOT" archive --format=tar "$TAG" | tar -x -C "$STAGE"
fi

# HEAD copy also has no version marker; write VERSION for clarity.
echo "$VERSION" > "$STAGE/VERSION"

echo "==> Stripping anything that must never ship (secrets, keystores, APKs, builds)"
rm -rf \
    "$STAGE/.git" \
    "$STAGE/.env" "$STAGE"/*/.env "$STAGE"/**/.env 2>/dev/null || true
find "$STAGE" -name '*.jks' -o -name '*.keystore' -o -name '*.keystore.*' \
    -o -name '*.p12' -o -name 'id_*' -o -name '*.env' -o -name '.env*' | while read -r f; do
    rm -f "$f"
done
rm -f "$STAGE"/android-app/release.keystore.* 2>/dev/null || true
# Firebase / Google service-account keys must never ship, even untracked copies.
rm -f "$STAGE"/server/firebase-key.json \
    "$STAGE"/server/firebase-service-account.json \
    "$STAGE"/android-app/**/google-services.json 2>/dev/null || true
find "$STAGE" -name 'firebase-key.json' -o -name 'firebase-service-account.json' \
    -o -name 'google-services.json' | while read -r f; do rm -f "$f"; done
rm -rf \
    "$STAGE"/node_modules \
    "$STAGE"/dashboard/node_modules \
    "$STAGE"/dashboard/.next \
    "$STAGE"/dist \
    "$STAGE"/android-app/.gradle \
    "$STAGE"/android-app/app/build \
    "$STAGE"/android-app/build \
    "$STAGE"/dashboard/build \
    "$STAGE"/server/static/apk \
    "$STAGE"/server/venv \
    "$STAGE"/server/.venv \
    "$STAGE"/server/__pycache__ \
    "$STAGE"/server/**/__pycache__ 2>/dev/null || true
find "$STAGE" -name '*.apk' -o -name '*.aab' -o -name '*.pyc' | while read -r f; do rm -f "$f"; done

echo "==> Verifying no secrets leaked into the tarball"
# Tight patterns only — code references like `grep '^MT_API_KEY='` or
# placeholder docs must NOT trip this. A real key is 32+ hex chars.
if grep -rIlE \
    --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=venv \
    --exclude-dir=.venv --exclude-dir=dist --exclude-dir=build \
    -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
    -e 'MT_API_KEY=[0-9a-f]{16,}' \
    -e 'MT_JWT_SECRET=[0-9a-f]{16,}' \
    -e 'MT_SENTRY_DSN=https://[0-9a-f]{32}' \
    -e '"private_key"' \
    "$STAGE" 2>/dev/null | grep -q .; then
    echo "ERROR: potential secret found in tarball — aborting" >&2
    exit 1
fi

echo "==> Packing"
tar -czf "$TARBALL" -C "$OUT_DIR" "$(basename "$STAGE")"
rm -rf "$STAGE"

SHA=$(sha256sum "$TARBALL" | awk '{print $1}')
echo "$SHA  $(basename "$TARBALL")" > "$TARBALL.sha256"

echo
echo "✅ $TARBALL"
echo "   sha256: $SHA"
echo
echo "Next (owner): upload the tarball to the release page for $TAG,"
echo "and add the checksum to the download page's source section."
