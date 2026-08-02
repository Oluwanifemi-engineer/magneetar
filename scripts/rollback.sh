#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Rollback Script
# Restores the pre-deploy images (tagged by deploy.sh as ":predeploy") and
# recreates the containers. Use this after a failed deploy or a bad release:
#   bash scripts/rollback.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

ROLLBACK_TAG="predeploy"
SERVER_IMAGE="magneetar-server"
DASHBOARD_IMAGE="magneetar-dashboard"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MAGNEETAR — Rollback                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Verify the rollback images exist before doing anything destructive.
MISSING=0
for img in "$SERVER_IMAGE:$ROLLBACK_TAG" "$DASHBOARD_IMAGE:$ROLLBACK_TAG"; do
    if ! docker image inspect "$img" > /dev/null 2>&1; then
        echo "   ❌ $img not found — nothing to roll back to"
        MISSING=1
    fi
done
if [ "$MISSING" -eq 1 ]; then
    echo "   (Run a deploy first: bash scripts/deploy.sh)"
    exit 1
fi

echo "🔄 Restoring pre-deploy images..."
docker tag "$SERVER_IMAGE:$ROLLBACK_TAG" "$SERVER_IMAGE:latest"
docker tag "$DASHBOARD_IMAGE:$ROLLBACK_TAG" "$DASHBOARD_IMAGE:latest"
echo "   ✅ Images restored to :predeploy"

echo "🏗️  Recreating containers from restored images..."
# --force-recreate is REQUIRED: the container's image REFERENCE is still
# 'magneetar-server:latest', so compose would otherwise see no config change
# and silently leave the broken container running.
docker compose up -d --no-deps --force-recreate server dashboard 2>&1

echo "⏳ Waiting for health after rollback..."
for i in $(seq 1 18); do
    if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
        echo "   ✅ Server healthy after rollback"
        break
    fi
    echo "   ⏳ attempt $i/18..."
    sleep 10
done

echo ""
echo "   Rollback complete. If the DB state itself is suspect, restore from a"
echo "   backup: bash scripts/backup-db.sh --list  (then --restore <file>)"
echo ""
