#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Development Server Control
# One-command wrapper around the docker dev stack (docker-compose.dev.yml):
# same runtime as production, zero host-Python surprises, isolated dev data.
#
# Usage:
#   scripts/dev-server.sh start     # build + start (server on :8000, redis)
#   scripts/dev-server.sh stop      # stop the stack (dev data is kept)
#   scripts/dev-server.sh restart   # stop, then start again
#   scripts/dev-server.sh status    # container state + /health
#   scripts/dev-server.sh logs      # follow server logs
#   scripts/dev-server.sh reset     # wipe dev data volumes + rebuild from scratch
#
# The dashboard dev server stays on the host (npm run dev, :3001) and points
# at http://localhost:8000 by default — no config needed.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE="docker compose -f $PROJECT_DIR/docker-compose.dev.yml"

usage() {
  sed -n '3,14p' "$0" | sed 's/^# \{0,1\}//'
}

wait_healthy() {
  echo "Waiting for the API on http://localhost:8000/health …"
  for _ in $(seq 1 30); do
    if curl -sf -m 3 http://localhost:8000/health >/dev/null 2>&1; then
      echo "✅ Dev API is up: http://localhost:8000"
      curl -s -m 3 http://localhost:8000/health; echo
      return 0
    fi
    sleep 2
  done
  echo "❌ API did not become healthy within 60s — check: $COMPOSE logs server" >&2
  return 1
}

case "${1:-}" in
  start)
    $COMPOSE up -d --build
    wait_healthy
    ;;
  stop)
    $COMPOSE down
    echo "Stopped. Dev data (magneetar-dev-data / magneetar-dev-media volumes) is kept."
    ;;
  restart)
    $COMPOSE down
    $COMPOSE up -d --build
    wait_healthy
    ;;
  status)
    $COMPOSE ps
    echo
    if curl -sf -m 3 http://localhost:8000/health >/dev/null 2>&1; then
      echo "API: UP (http://localhost:8000)"
    else
      echo "API: DOWN"
    fi
    ;;
  logs)
    $COMPOSE logs -f --tail=100 server
    ;;
  reset)
    echo "Wiping dev volumes + rebuilding from scratch…"
    $COMPOSE down -v
    $COMPOSE up -d --build
    wait_healthy
    echo "Fresh dev stack ready (empty database)."
    ;;
  *)
    usage
    exit 1
    ;;
esac
