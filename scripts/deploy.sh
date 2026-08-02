#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Deploy Script (no-breaking-changes edition)
# Pulls latest code, backs up the DB, rebuilds Docker images, and restarts
# services — with a health gate and a rollback image tag so a bad deploy can
# be reverted without data loss.
# Usage: bash scripts/deploy.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# ── Rollback helpers ───────────────────────────────────────────────────────────
# Before rebuilding, tag the currently-running images so a failed health gate
# can be rolled back with: bash scripts/rollback.sh  (or the manual commands
# printed on failure).
ROLLBACK_TAG="predeploy"
SERVER_IMAGE="magneetar-server"
DASHBOARD_IMAGE="magneetar-dashboard"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MAGNEETAR — Deploy Script                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── 0. Pre-flight: require a clean compose state ──────────────────────────────
if ! docker compose version > /dev/null 2>&1; then
    echo "   ❌ docker compose not available — aborting"
    exit 1
fi

# ── 1. Pull latest code ──────────────────────────────────────────────────────
echo "📦 Pulling latest code..."
if git pull 2>&1; then
    echo "   ✅ Code updated"
else
    echo "   ⚠️  Git pull failed, continuing with current code"
fi
echo ""

# ── 2. Generate env if needed ────────────────────────────────────────────────
if [ ! -f server/.env ] || [ ! -s server/.env ]; then
    echo "🔐 Generating environment secrets..."
    bash scripts/generate-env.sh
    echo "   ✅ Environment generated"
    echo ""
fi

# ── 3. BACKUP the live database FIRST ─────────────────────────────────────────
# A failed deploy must never cost data. backup-db.sh snapshots the SQLite
# volume via the online-backup API (no downtime, integrity-checked restores).
echo "🗄️  Backing up live database (pre-deploy checkpoint)..."
if bash scripts/backup-db.sh; then
    echo "   ✅ Database backup taken"
else
    echo "   ❌ Database backup FAILED — refusing to deploy over a DB we cannot restore"
    exit 1
fi
echo ""

# ── 4. Tag current images for rollback ────────────────────────────────────────
echo "🏷️  Tagging current images for rollback (${ROLLBACK_TAG})..."
for img in "$SERVER_IMAGE" "$DASHBOARD_IMAGE"; do
    if docker image inspect "$img:latest" > /dev/null 2>&1; then
        docker tag "$img:latest" "$img:$ROLLBACK_TAG" && echo "   ✅ $img:latest -> $img:$ROLLBACK_TAG"
    else
        echo "   ⚠️  $img:latest not found — nothing to tag (first deploy?)"
    fi
done
echo ""

# ── 5. Build and restart services (no deps — never touch db/cloudflared) ─────
# --no-deps keeps PostgreSQL and the tunnel running untouched; only the two
# app services are recreated. Rebuild failures leave the OLD containers up.
echo "🏗️  Building and restarting Docker services (server + dashboard only)..."
docker compose up --build -d --no-deps server dashboard 2>&1
echo "   ✅ Services rebuilt and restarted"
echo ""

# ── 6. Health gate with retries ────────────────────────────────────────────────
# Wait up to HEALTH_RETRIES × 10s for /health to come back "online". This is
# the point where a bad image is caught BEFORE it serves traffic.
# The gate also verifies the SERVING container is the freshly-built one by
# checking its uptime is small — a stale container from a missed recreate
# would otherwise pass the gate and keep serving the old image.
HEALTH_RETRIES=18   # 3 minutes max
HEALTH_OK=0
echo "⏳ Waiting for server health (up to ${HEALTH_RETRIES}x10s)..."
for i in $(seq 1 "$HEALTH_RETRIES"); do
    UPTIME=$(curl -sf http://localhost:8002/health 2>/dev/null | python3 -c "import json,sys; print(int(json.load(sys.stdin).get('uptime', 99999)))" 2>/dev/null || echo 99999)
    if [ "$UPTIME" -lt 180 ]; then
        HEALTH_OK=1
        echo "   ✅ Server is healthy (attempt $i, uptime ${UPTIME}s)"
        break
    fi
    echo "   ⏳ health check attempt $i/${HEALTH_RETRIES} (uptime ${UPTIME}s — waiting for the new container)..."
    sleep 10
done

if [ "$HEALTH_OK" -ne 1 ]; then
    echo ""
    echo "   ❌ ❌ ❌  DEPLOY FAILED — server did not become healthy"
    echo ""
    echo "   Immediate rollback:"
    echo "     bash scripts/rollback.sh"
    echo "   or manually:"
    echo "     docker tag $SERVER_IMAGE:$ROLLBACK_TAG $SERVER_IMAGE:latest"
    echo "     docker tag $DASHBOARD_IMAGE:$ROLLBACK_TAG $DASHBOARD_IMAGE:latest"
    echo "     docker compose up -d --no-deps server dashboard"
    echo ""
    echo "   Inspect the failure:"
    echo "     docker compose logs --tail=100 server"
    exit 1
fi

if curl -sf -o /dev/null http://localhost:3000 > /dev/null 2>&1; then
    echo "   ✅ Dashboard is serving"
else
    echo "   ⚠️  Dashboard may not be ready yet — re-checking in 10s..."
    sleep 10
    if curl -sf -o /dev/null http://localhost:3000 > /dev/null 2>&1; then
        echo "   ✅ Dashboard is serving"
    else
        echo "   ⚠️  Dashboard still not responding — check 'docker compose logs dashboard'"
    fi
fi
echo ""

# ── 7. Ensure Cloudflare tunnel is running ────────────────────────────────────
echo "🔒 Checking Cloudflare tunnel..."
if pgrep -f 'cloudflared tunnel run magneetar' > /dev/null 2>&1; then
    echo "   ✅ Cloudflare tunnel is running"
else
    echo "   ⚠️  Cloudflare tunnel not running — restarting..."
    nohup cloudflared tunnel run magneetar > /tmp/cloudflared.log 2>&1 &
    sleep 3
    if pgrep -f 'cloudflared tunnel run magneetar' > /dev/null 2>&1; then
        echo "   ✅ Cloudflare tunnel restarted"
    else
        echo "   ❌ Failed to restart Cloudflare tunnel"
    fi
fi
echo ""

# ── 8. Verify public endpoints via Cloudflare ─────────────────────────────────
echo "🌐 Checking public endpoints..."
if curl -sf https://api.magneetar.me/health > /dev/null 2>&1; then
    echo "   ✅ api.magneetar.me is live"
else
    echo "   ⚠️  api.magneetar.me not responding — check Cloudflare tunnel"
fi
echo ""

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           ✅  Deploy Complete!                              ║"
echo "║                                                              ║"
echo "║  API:       https://api.magneetar.me/health                  ║"
echo "║  Dashboard: https://app.magneetar.me                         ║"
echo "║  Rollback:  bash scripts/rollback.sh                         ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
