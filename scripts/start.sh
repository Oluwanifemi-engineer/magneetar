#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Start All Services
# Usage: ./scripts/start.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/server"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ─── Check Environment ────────────────────────────────────────────────────────

if [[ ! -f "$SERVER_DIR/.env" ]]; then
    log_error ".env file not found at $SERVER_DIR/.env"
    log_error "Run: cp server/.env.example server/.env && edit server/.env"
    exit 1
fi

# ─── Start Server ─────────────────────────────────────────────────────────────

log_info "Starting Magneetar server..."

cd "$SERVER_DIR"

# Activate virtualenv if it exists
if [[ -d "venv" ]]; then
    source venv/bin/activate
fi

# Check if uvicorn is available
if ! command -v uvicorn &> /dev/null; then
    log_error "uvicorn not found. Install with: pip install uvicorn"
    exit 1
fi

# Start the server
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
