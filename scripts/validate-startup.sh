#!/usr/bin/env bash
# ─── Magneetar Startup Validation ────────────────────────────────────────────
# Pre-flight checks before server starts. Ensures critical environment
# variables are set, the database is writable, ports are available, and
# required Python packages are installed.
#
# Usage:
#   bash scripts/validate-startup.sh              # Full validation (exit 0/1)
#   bash scripts/validate-startup.sh --server     # Only server-side checks
#   bash scripts/validate-startup.sh --dashboard  # Only dashboard checks
#   bash scripts/validate-startup.sh --quiet      # Silent — just exit code
#
# Exit codes:
#   0 = All checks pass
#   1 = Configuration error (env vars missing or invalid)
#   2 = Infrastructure error (port in use, DB not writable)
#   3 = Dependency error (missing packages)
#   4 = Mixed errors

set -euo pipefail

# ── Configuration ───────────────────────────────────────────────────────────
SERVER_DIR="$(cd "$(dirname "$0")/../server" && pwd)"
DASHBOARD_DIR="$(cd "$(dirname "$0")/../dashboard" && pwd)"
QUIET=false
CHECK_SERVER=true
CHECK_DASHBOARD=true
EXIT_CODE=0
HAS_CONFIG_ERR=false
HAS_INFRA_ERR=false
HAS_DEPS_ERR=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --quiet) QUIET=true ;;
        --server) CHECK_DASHBOARD=false ;;
        --dashboard) CHECK_SERVER=false ;;
        *) echo "Unknown: $arg"; exit 1 ;;
    esac
done

log() {
    if [ "$QUIET" = false ]; then echo -e "$1"; fi
}

pass() { log "  ✅ $1"; }
warn() { log "  ⚠️  $1"; }
fail() {
    log "  ❌ $1"
    case "$2" in
        config) HAS_CONFIG_ERR=true ;;
        infra)  HAS_INFRA_ERR=true ;;
        deps)   HAS_DEPS_ERR=true ;;
    esac
}

# ═══════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════

log ""
log "╔══════════════════════════════════════════════════════════════╗"
log "║   Magneetar Startup Validation                             ║"
log "║   $(date -u '+%Y-%m-%d %H:%M:%S UTC')                      ║"
log "╚══════════════════════════════════════════════════════════════╝"
log ""

# ═══════════════════════════════════════════════════════════════════════════
# 1. ENVIRONMENT VARIABLES (Server)
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_SERVER" = true ]; then
    log "─── Server: Environment Variables ───"

    # Load .env if present
    if [ -f "$SERVER_DIR/.env" ]; then
        set -a
        source "$SERVER_DIR/.env"
        set +a
        pass "Loaded environment from $SERVER_DIR/.env"
    else
        warn "No .env file found at $SERVER_DIR/.env — will use system env vars"
    fi

    # Required vars
    REQUIRED_VARS=(
        "MT_API_KEY:API key (min 32 chars hex)"
        "MT_JWT_SECRET:JWT signing secret (min 64 chars hex)"
        "MT_ENCRYPTION_KEY:Encryption key (64 hex chars = 32 bytes)"
    )

    for entry in "${REQUIRED_VARS[@]}"; do
        var_name="${entry%%:*}"
        var_desc="${entry#*:}"
        var_value="${!var_name:-}"

        if [ -z "$var_value" ]; then
            fail "$var_name is not set ($var_desc)" config
        elif [ "$var_name" = "MT_API_KEY" ] && [ "${#var_value}" -lt 32 ]; then
            fail "$var_name is too short: ${#var_value} chars (min 32)" config
        elif [ "$var_name" = "MT_JWT_SECRET" ] && [ "${#var_value}" -lt 64 ]; then
            fail "$var_name is too short: ${#var_value} chars (min 64)" config
        elif [ "$var_name" = "MT_ENCRYPTION_KEY" ]; then
            # Validate hex format (64 chars = 32 bytes)
            if ! echo "$var_value" | grep -qE '^[0-9a-fA-F]{64}$'; then
                fail "$var_name must be exactly 64 hex characters (32 bytes)" config
            else
                pass "$var_name is set and valid"
            fi
        else
            pass "$var_name is set"
        fi
    done

    # Optional vars — just warn if not set
    OPTIONAL_VARS=(
        "MT_DATABASE_URL:PostgreSQL URL (optional, falls back to SQLite)"
        "MT_SENDGRID_KEY:SendGrid API key for email alerts"
        "MT_TERMII_KEY:Termii API key for SMS alerts in Nigeria"
        "MT_TWILIO_SID:Twilio SID for WhatsApp alerts"
        "MT_TWILIO_AUTH_TOKEN:Twilio auth token"
        "MT_FIREBASE_KEY:Firebase credentials path/JSON for push notifications"
        "MT_SENTRY_DSN:Sentry DSN for error tracking"
    )
    for entry in "${OPTIONAL_VARS[@]}"; do
        var_name="${entry%%:*}"
        var_desc="${entry#*:}"
        if [ -z "${!var_name:-}" ]; then
            warn "$var_name not set — $var_desc"
        fi
    done

    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 2. DATABASE WRITABILITY (Server)
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_SERVER" = true ]; then
    log "─── Server: Database ───"

    DB_PATH="${MT_DB_PATH:-$SERVER_DIR/magneetar.db}"

    if [ "$DB_PATH" = ":memory:" ]; then
        warn "In-memory database — data will not persist across restarts"
    else
        # Check parent directory is writable
        DB_DIR="$(dirname "$DB_PATH")"
        if [ ! -d "$DB_DIR" ]; then
            fail "Database directory does not exist: $DB_DIR" infra
        elif [ ! -w "$DB_DIR" ]; then
            fail "Database directory is not writable: $DB_DIR" infra
        else
            pass "Database directory is writable: $DB_DIR"
        fi

        # If DB file exists, check it's readable/writable
        if [ -f "$DB_PATH" ]; then
            if [ ! -r "$DB_PATH" ]; then
                fail "Database file exists but is not readable: $DB_PATH" infra
            elif [ ! -w "$DB_PATH" ]; then
                fail "Database file exists but is not writable: $DB_PATH" infra
            else
                pass "Database file is accessible: $DB_PATH"
            fi
        else
            pass "Database file will be created on first startup: $DB_PATH"
        fi

        # Check disk space
        AVAILABLE_KB=$(df "$DB_DIR" 2>/dev/null | tail -1 | awk '{print $4}')
        if [ -n "$AVAILABLE_KB" ] && [ "$AVAILABLE_KB" -lt 102400 ]; then
            warn "Low disk space on database volume: $((AVAILABLE_KB / 1024)) MB remaining"
        elif [ -n "$AVAILABLE_KB" ]; then
            pass "Sufficient disk space: $((AVAILABLE_KB / 1024)) MB available"
        fi
    fi
    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 3. PORT AVAILABILITY (Server)
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_SERVER" = true ]; then
    log "─── Server: Port Availability ───"

    PORT="${MT_PORT:-8000}"

    if command -v ss &>/dev/null; then
        if ss -tln "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
            warn "Port $PORT is already in use (ss)"
        else
            pass "Port $PORT is available"
        fi
    elif command -v netstat &>/dev/null; then
        if netstat -tln 2>/dev/null | grep -q ":$PORT "; then
            warn "Port $PORT is already in use (netstat)"
        else
            pass "Port $PORT is available"
        fi
    else
        # Fallback: try binding with python
        if python3 -c "
import socket
s = socket.socket()
try:
    s.bind(('0.0.0.0', $PORT))
    s.close()
    print('ok')
except OSError:
    print('inuse')
" 2>/dev/null | grep -q ok; then
            pass "Port $PORT is available (python probe)"
        else
            warn "Port $PORT may be in use (python probe failed)"
        fi
    fi
    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 4. PYTHON DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_SERVER" = true ]; then
    log "─── Server: Python Dependencies ───"

    VENV_DIR=""
    # Find virtualenv
    if [ -d "$SERVER_DIR/venv" ]; then
        VENV_DIR="$SERVER_DIR/venv"
    elif [ -d "$SERVER_DIR/../venv" ]; then
        VENV_DIR="$(cd "$SERVER_DIR/../venv" && pwd)"
    fi

    if [ -n "$VENV_DIR" ]; then
        pass "Virtualenv found: $VENV_DIR"
    else
        warn "No virtualenv found — relying on system Python packages"
    fi

    # Check critical packages
    PYTHON="${VENV_DIR:+$VENV_DIR/bin/python}"
    PYTHON="${PYTHON:-python3}"

    CRITICAL_PACKAGES=(
        "fastapi:FastAPI framework"
        "uvicorn:ASGI server"
        "sqlite3:SQLite (stdlib)"
        "httpx:HTTP client"
        "pydantic:Data validation"
        "jose:JWT token handling"
    )

    for entry in "${CRITICAL_PACKAGES[@]}"; do
        pkg_name="${entry%%:*}"
        pkg_desc="${entry#*:}"

        if $PYTHON -c "import $pkg_name" 2>/dev/null; then
            pass "$pkg_name is available ($pkg_desc)"
        else
            fail "$pkg_name is missing ($pkg_desc)" deps
        fi
    done

    # Optional packages
    OPTIONAL_PACKAGES=(
        "firebase_admin:Firebase push notifications"
        "sentry_sdk:Sentry error tracking"
        "reportlab:PDF evidence generation"
        "PIL:Image processing (from Pillow)"
    )

    for entry in "${OPTIONAL_PACKAGES[@]}"; do
        pkg_name="${entry%%:*}"
        pkg_desc="${entry#*:}"

        if $PYTHON -c "import ${pkg_name%%:*}" 2>/dev/null; then
            pass "Optional $pkg_name is available ($pkg_desc)"
        else
            warn "Optional $pkg_name not installed ($pkg_desc)"
        fi
    done

    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 5. DASHBOARD CHECKS
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_DASHBOARD" = true ]; then
    log "─── Dashboard: Node.js & Dependencies ───"

    # Check Node.js
    if command -v node &>/dev/null; then
        NODE_VER=$(node --version 2>/dev/null || echo "unknown")
        pass "Node.js is available: $NODE_VER"
    else
        fail "Node.js is not installed" deps
    fi

    # Check npm
    if command -v npm &>/dev/null; then
        NPM_VER=$(npm --version 2>/dev/null || echo "unknown")
        pass "npm is available: v$NPM_VER"
    else
        fail "npm is not installed" deps
    fi

    # Check node_modules
    if [ -d "$DASHBOARD_DIR/node_modules" ]; then
        pass "node_modules directory exists"
    else
        warn "node_modules not found — run: cd dashboard && npm install"
    fi

    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 6. FILESYSTEM CHECKS
# ═══════════════════════════════════════════════════════════════════════════

if [ "$CHECK_SERVER" = true ]; then
    log "─── Server: Filesystem ───"

    # Check logs directory
    LOG_DIR="${MT_LOG_DIR:-/tmp/magneetar}"
    if mkdir -p "$LOG_DIR" 2>/dev/null; then
        pass "Log directory is writable: $LOG_DIR"
    else
        warn "Cannot create log directory: $LOG_DIR"
    fi

    # Check static directory for APK
    STATIC_DIR="$SERVER_DIR/static/apk"
    if [ -d "$STATIC_DIR" ]; then
        APK_COUNT=$(ls -1 "$STATIC_DIR"/*.apk 2>/dev/null | wc -l)
        if [ "$APK_COUNT" -gt 0 ]; then
            pass "APK files found: $APK_COUNT in $STATIC_DIR"
        else
            warn "No APK files in $STATIC_DIR"
        fi
    else
        warn "Static APK directory not found: $STATIC_DIR"
    fi

    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# 7. DOCKER CHECK (if applicable)
# ═══════════════════════════════════════════════════════════════════════════

if [ -f "$(dirname "$0")/../docker-compose.yml" ]; then
    log "─── Docker ───"
    if command -v docker &>/dev/null; then
        if docker info 2>/dev/null | head -5 | grep -q "Server Version"; then
            pass "Docker is running"
        else
            warn "Docker is installed but daemon may not be running"
        fi
    else
        warn "Docker not found — compose deployments will fail"
    fi
    log ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

log "╔══════════════════════════════════════════════════════════════╗"
log "║   Validation Summary                                       ║"
log "╚══════════════════════════════════════════════════════════════╝"
log ""

# Determine exit code
if [ "$HAS_CONFIG_ERR" = true ]; then
    log "  🔴 Configuration errors:    ❌ Check ./.env or env vars"
    EXIT_CODE=1
fi
if [ "$HAS_INFRA_ERR" = true ]; then
    log "  🔴 Infrastructure errors:   ❌ Port/Disk/DB issues"
    [ "$EXIT_CODE" -eq 0 ] && EXIT_CODE=2
fi
if [ "$HAS_DEPS_ERR" = true ]; then
    log "  🔴 Dependency errors:       ❌ Install missing packages"
    [ "$EXIT_CODE" -eq 0 ] && EXIT_CODE=3
fi

if [ "$HAS_CONFIG_ERR" = false ] && [ "$HAS_INFRA_ERR" = false ] && [ "$HAS_DEPS_ERR" = false ]; then
    log "  🟢 All checks passed — ready to start"
    EXIT_CODE=0
fi

log ""

exit $EXIT_CODE
