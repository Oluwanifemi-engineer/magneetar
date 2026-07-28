#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Deploy Script
# Pulls latest code, rebuilds Docker images, and restarts services.
# Usage: bash scripts/deploy.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MAGNEETAR — Deploy Script                        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

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

# ── 3. Build and restart services ────────────────────────────────────────────
echo "🏗️  Building and restarting Docker services..."
docker compose up --build -d db server dashboard 2>&1
echo "   ✅ Services rebuilt and restarted"
echo ""

# ── 4. Wait for health checks ────────────────────────────────────────────────
echo "⏳ Waiting for services to be healthy..."
sleep 5

if curl -sf http://localhost:8002/health > /dev/null 2>&1; then
    echo "   ✅ Server is healthy"
else
    echo "   ❌ Server health check failed — check 'docker compose logs server'"
fi

if curl -sf -o /dev/null http://localhost:3000 > /dev/null 2>&1; then
    echo "   ✅ Dashboard is serving"
else
    echo "   ⚠️  Dashboard may not be ready yet"
fi
echo ""

# ── 5. Verify public endpoints via Cloudflare ────────────────────────────────
# ── 5. Ensure Cloudflare tunnel is running ───────────────────────────────
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

# ── 6. Verify public endpoints via Cloudflare ────────────────────────────────
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
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
