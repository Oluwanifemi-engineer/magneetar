#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Database Backup Script
# Dumps PostgreSQL database, rotates old backups, optionally syncs to cloud.
# Usage:
#   bash scripts/backup-db.sh                    # Create a backup
#   bash scripts/backup-db.sh --restore <file>   # Restore from backup
#   bash scripts/backup-db.sh --list             # List available backups
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS=7  # Keep backups for 7 days
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/magneetar_$TIMESTAMP.sql.gz"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

mkdir -p "$BACKUP_DIR"

# ── Parse arguments ──────────────────────────────────────────────────────────
RESTORE_FILE=""
LIST_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --restore)
            RESTORE_FILE="$2"
            shift 2
            ;;
        --list)
            LIST_MODE=true
            shift
            ;;
        *)
            echo "Usage: $0 [--restore <file>] [--list]"
            exit 1
            ;;
    esac
done

# ── List backups ─────────────────────────────────────────────────────────────
if $LIST_MODE; then
    echo -e "${GREEN}Available backups:${NC}"
    echo ""
    if ls "$BACKUP_DIR"/magneetar_*.sql.gz 1>/dev/null 2>&1; then
        # shellcheck disable=SC2012  # ls -lh gives human-readable sizes for display
        ls -lh "$BACKUP_DIR"/magneetar_*.sql.gz | awk '{print $6, $7, $8, " — ", $NF}'
    else
        echo "   No backups found."
    fi
    echo ""
    echo "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo '0B')"
    exit 0
fi

# ── Restore mode ─────────────────────────────────────────────────────────────
if [ -n "$RESTORE_FILE" ]; then
    if [ ! -f "$RESTORE_FILE" ]; then
        echo -e "${RED}❌ Backup file not found: $RESTORE_FILE${NC}"
        exit 1
    fi

    echo -e "${YELLOW}⚠️  WARNING: Restoring will overwrite the current database!${NC}"
    echo -n "Are you sure you want to continue? (yes/no): "
    read -r confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi

    echo -e "${GREEN}🔄 Restoring from: $RESTORE_FILE${NC}"
    gunzip -c "$RESTORE_FILE" | docker exec -i magneetar-db psql -U magneetar -d magneetar
    echo -e "${GREEN}✅ Restore complete!${NC}"
    exit 0
fi

# ── Backup mode ──────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MAGNEETAR — Database Backup                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if Docker is running
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'magneetar-db'; then
    echo -e "${RED}❌ magneetar-db container is not running${NC}"
    echo "   Start the stack first: docker compose up -d db"
    exit 1
fi

# Create backup
echo -e "${GREEN}📦 Creating backup...${NC}"
if docker exec magneetar-db pg_dump -U magneetar -d magneetar --no-owner | gzip > "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}   ✅ Backup created: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
else
    echo -e "${RED}   ❌ Backup failed${NC}"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Rotate old backups (keep last 7 days)
echo -e "${GREEN}🧹 Cleaning old backups...${NC}"
find "$BACKUP_DIR" -name "magneetar_*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null
OLD_COUNT=$(find "$BACKUP_DIR" -name "magneetar_*.sql.gz" | wc -l)
echo -e "${GREEN}   ✅ $OLD_COUNT backups retained (${RETENTION_DAYS}-day rotation)${NC}"
echo ""

echo -e "${GREEN}✅ Backup complete!${NC}"
echo ""
echo "   File:   $BACKUP_FILE"
echo "   Size:   $BACKUP_SIZE"
echo "   To restore: bash $0 --restore $BACKUP_FILE"
echo "   To list backups: bash $0 --list"
echo ""
