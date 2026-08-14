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

# ── Version wiring ─────────────────────────────────────────────────────────────
# Export the repo release version so compose can bake it into the dashboard's
# NEXT_PUBLIC_APP_VERSION fallback badge (${MT_APP_VERSION:-1.4.0} in
# docker-compose.yml). Kept in sync with the APP_VERSION build arg for the server.
MT_APP_VERSION="$(cat "$PROJECT_DIR/VERSION" 2>/dev/null || echo 1.4.0)"
export MT_APP_VERSION
echo "   📦 Releasing v${MT_APP_VERSION}"

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

# ── 4.5 Bring up the realtime broadcast bus (Redis) ──────────────────────────
# The server's WebSocket fan-out across its uvicorn workers runs on a Redis
# pub/sub channel (MT_REDIS_URL). `--no-deps` below never starts
# dependencies, so Redis must be started explicitly. Safe to re-run: up is
# idempotent.
echo "🚀 Ensuring Redis (realtime broadcast bus) is up..."
docker compose up -d redis 2>&1
echo "   ✅ Redis service ensured"
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
# The gate also verifies the SERVING container is the freshly-built one: the
# /health response no longer exposes uptime publicly (F-08 — it revealed
# deploy timing), so freshness is checked against the container's own start
# time via docker inspect. A stale container from a missed recreate would
# otherwise pass the gate and keep serving the old image.
HEALTH_RETRIES=18   # 3 minutes max
HEALTH_OK=0
SERVER_CONTAINER=$(docker compose ps -q server 2>/dev/null || true)
container_age() {
    if [ -z "$SERVER_CONTAINER" ]; then
        echo 99999
        return
    fi
    STARTED=$(docker inspect -f '{{.State.StartedAt}}' "$SERVER_CONTAINER" 2>/dev/null || echo "")
    if [ -z "$STARTED" ]; then
        echo 99999
        return
    fi
    # StartedAt is RFC3339 (e.g. 2026-08-14T19:00:00.123456789Z) — convert to epoch.
    START_EPOCH=$(date -d "$STARTED" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    echo $(( NOW_EPOCH - START_EPOCH ))
}
echo "⏳ Waiting for server health (up to ${HEALTH_RETRIES}x10s)..."
for i in $(seq 1 "$HEALTH_RETRIES"); do
    UPTIME=$(container_age)
    # Health must ALSO report online — a container that started but failed to
    # bind (or is crash-looping) would look "fresh" forever otherwise.
    STATUS=$(curl -sf http://localhost:8002/health 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    if [ "$UPTIME" -lt 180 ] && [ "$STATUS" = "online" ]; then
        HEALTH_OK=1
        echo "   ✅ Server is healthy (attempt $i, container age ${UPTIME}s, status $STATUS)"
        break
    fi
    echo "   ⏳ health check attempt $i/${HEALTH_RETRIES} (container age ${UPTIME}s, status ${STATUS:-unknown} — waiting for the new container)..."
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
# The tunnel runs as the `cloudflared` Docker COMPOSE service (routing to the
# compose service names server/dashboard). It must NOT be re-launched as a
# host process: a host-level `cloudflared tunnel run` registers the SAME
# tunnel name and steers ingress to localhost:8000 (unreachable on the host),
# producing 502s on the public endpoints until it is killed. Only manage the
# container.
echo "🔒 Checking Cloudflare tunnel (Docker service)..."
if docker compose ps cloudflared --format '{{.Status}}' 2>/dev/null | grep -qi 'Up'; then
    echo "   ✅ Cloudflare tunnel container is running"
else
    echo "   ⚠️  Cloudflare tunnel container down — restarting..."
    docker compose up -d --no-deps cloudflared 2>&1 || echo "   ❌ Failed to restart Cloudflare tunnel container"
fi
echo ""

# ── 8. Verify public endpoints via Cloudflare ─────────────────────────────────
echo "🌐 Checking public endpoints..."
if curl -sf https://api.magneetar.me/health > /dev/null 2>&1; then
    echo "   ✅ api.magneetar.me is live"
else
    echo "   ⚠️  api.magneetar.me not responding — check Cloudflare tunnel"
fi

# The dashboard is served under TWO public hostnames (magneetar.me — the
# marketing domain printed on flyers/security.txt — and app.magneetar.me).
# They share one origin (both route to the dashboard container via the
# tunnel), so a successful deploy MUST leave them serving the same build.
# Compare the chunk-hash of each host's HTML: a divergence here means one
# host is serving a stale bundle (e.g. an edge cache or a second origin),
# which previously went unnoticed because only app.* was checked.
page_chunk_hash() {
    curl -sf "$1" 2>/dev/null | grep -oE '/_next/static/chunks/[a-zA-Z0-9_-]+\.js' | sort -u | md5sum | cut -d' ' -f1
}
BARE_HASH=$(page_chunk_hash https://magneetar.me/)
APP_HASH=$(page_chunk_hash https://app.magneetar.me/)
if [ -n "$BARE_HASH" ] && [ "$BARE_HASH" = "$APP_HASH" ]; then
    echo "   ✅ magneetar.me and app.magneetar.me serve the same build (chunk $BARE_HASH)"
else
    echo "   ❌ BUILD DIVERGENCE: magneetar.me=($BARE_HASH) app.magneetar.me=($APP_HASH)"
    echo "      Both hosts must serve the same bundle — purge edge caches and re-check."
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
