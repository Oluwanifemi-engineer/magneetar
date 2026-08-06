#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Generate Production .env
# Usage: ./scripts/generate-env.sh [--docker]
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/server/.env"
USE_DOCKER="${1:-}"

# Generate secrets using Python
generate_secrets() {
    python3 -c "
import secrets
print(secrets.token_hex(32))
" 2>/dev/null || python -c "
import secrets
print(secrets.token_hex(32))
" 2>/dev/null || {
        echo "ERROR: Python not found" >&2
        exit 1
    }
}

echo "🔐 Generating Magneetar secrets..."

API_KEY=$(generate_secrets)
DEVICE_KEY=$(generate_secrets)
JWT_SECRET=$(generate_secrets)$(generate_secrets)
ENCRYPTION_KEY=$(generate_secrets)

cat > "$ENV_FILE" << EOF
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR SERVER — Auto-generated Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Core Security
# MT_API_KEY — the MASTER key (operator-only). Dashboard admin login + step-up.
# NEVER put this in the APK.
MT_API_KEY=${API_KEY}
# MT_DEVICE_KEY — the LOW-PRIVILEGE device key embedded in the public APK.
# Device endpoints only; extracting it from the APK must buy nothing.
MT_DEVICE_KEY=${DEVICE_KEY}
# MT_LEGACY_DEVICE_KEY — OPTIONAL. The PRE-split master key, accepted for
# device-scope auth only, so APKs built before the key split (which embedded
# the old master key) keep working until users upgrade. Remove once the
# installed fleet has upgraded.
# MT_LEGACY_DEVICE_KEY=
MT_JWT_SECRET=${JWT_SECRET}
MT_ENCRYPTION_KEY=${ENCRYPTION_KEY}

# Database — SQLite is the single data plane (WAL mode + online-backup
# script). MT_DB_PATH must point at the persisted volume in Docker:
#   /app/data/magneetar.db
MT_DB_PATH=magneetar.db
# Optional PostgreSQL adapter (EXPERIMENTAL, schema may lag SQLite — see
# database_postgres.py). Not needed for the Docker stack.
# MT_DATABASE_URL=postgresql://magneetar:password@localhost:5432/magneetar

# Environment
MT_ENVIRONMENT=development
MT_HOST=0.0.0.0
MT_PORT=8000
MT_LOG_LEVEL=info

# Limits
MT_MAX_DEVICES=10
MT_RETENTION_DAYS=90

# Alert Services (optional — configure for production alerts)
# MT_SENDGRID_KEY=your-sendgrid-api-key
# MT_TERMII_KEY=your-termii-api-key
# MT_TWILIO_SID=your-twilio-sid
# MT_TWILIO_AUTH_TOKEN=your-twilio-auth-token
#
# FCM push alerts — MT_FIREBASE_KEY must be a FIREBASE SERVICE-ACCOUNT JSON
# (path or inline JSON), NOT the legacy FCM server key (deprecated June 2024;
# starts with 'AIza' and does NOT work with firebase-admin).
# Run: bash scripts/firebase-setup.sh   → downloads server/firebase-service-account.json
# Bare metal:  MT_FIREBASE_KEY=./firebase-service-account.json
# Docker:      MT_FIREBASE_KEY=/app/firebase-service-account.json  (file auto-mounted)
# MT_FIREBASE_KEY=
#
# Sentry crash reporting (backend):
# MT_SENTRY_DSN=your-sentry-dsn
EOF

# The --docker flag used to generate a PostgreSQL password + .db_password
# secret file. Since v1.3.1 the stack is SQLite-only (single data plane), so
# there is nothing extra to generate — the flag is kept for CLI compatibility
# and prints a short note.
if [ "$USE_DOCKER" = "--docker" ]; then
    echo "ℹ️  SQLite-only deployment: no DB password file needed (PostgreSQL removed from the stack)."
    echo ""
fi

echo "✅ Generated: $ENV_FILE"
echo ""
echo "   API Key (master): ${API_KEY:0:16}..."
echo "   Device Key:       ${DEVICE_KEY:0:16}..."
echo "   JWT Secret:       ${JWT_SECRET:0:16}..."
echo "   Encryption Key:   ${ENCRYPTION_KEY:0:16}..."
echo ""
echo "   IMPORTANT: Save these credentials securely."
echo "   - Master key (MT_API_KEY): dashboard admin login. Keep server-side."
echo "   - Device key (MT_DEVICE_KEY): what the Android APK embeds (low privilege)."
echo ""

# Print docker info if requested
if [ "$USE_DOCKER" = "--docker" ]; then
    echo "🐳 To deploy with Docker Compose:"
    echo "   docker compose up --build -d"
    echo ""
    echo "   Dashboard will be at: http://localhost:3000"
    echo "   API will be at:       http://localhost:8000"
    echo "   Health check:         http://localhost:8000/health"
fi
