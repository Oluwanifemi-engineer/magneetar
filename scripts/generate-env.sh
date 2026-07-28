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
JWT_SECRET=$(generate_secrets)$(generate_secrets)
ENCRYPTION_KEY=$(generate_secrets)

cat > "$ENV_FILE" << EOF
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR SERVER — Auto-generated Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Core Security
MT_API_KEY=${API_KEY}
MT_JWT_SECRET=${JWT_SECRET}
MT_ENCRYPTION_KEY=${ENCRYPTION_KEY}

# Database (SQLite for development, PostgreSQL for production)
MT_DB_PATH=magneetar.db
# MT_DATABASE_URL=postgresql://magneetar:password@localhost:5432/magneetar

# Docker PostgreSQL password (also stored in server/.db_password)
# MT_DB_PASSWORD=your-db-password

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
# MT_FIREBASE_KEY=path-to-firebase-credentials.json
# MT_SENTRY_DSN=your-sentry-dsn
EOF

# Generate Docker DB password file if --docker flag
if [ "$USE_DOCKER" = "--docker" ]; then
    DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))" 2>/dev/null || python -c "import secrets; print(secrets.token_urlsafe(24))")
    echo "$DB_PASSWORD" > "$PROJECT_DIR/server/.db_password"
    echo "✅ Generated Docker DB password file: server/.db_password"
    echo ""
    # Also append to .env
    echo "" >> "$ENV_FILE"
    echo "# Docker PostgreSQL" >> "$ENV_FILE"
    echo "MT_DB_PASSWORD=${DB_PASSWORD}" >> "$ENV_FILE"
    echo "MT_DATABASE_URL=postgresql://magneetar:${DB_PASSWORD}@db:5432/magneetar" >> "$ENV_FILE"
fi

echo "✅ Generated: $ENV_FILE"
echo ""
echo "   API Key:         ${API_KEY:0:16}..."
echo "   JWT Secret:      ${JWT_SECRET:0:16}..."
echo "   Encryption Key:  ${ENCRYPTION_KEY:0:16}..."
echo ""
echo "   IMPORTANT: Save these credentials securely."
echo "   The API key will be needed to connect the dashboard."
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
