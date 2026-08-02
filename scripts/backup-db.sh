#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Database Backup Script
# Backs up the live SQLite database (the app's data plane) from the
# magneetar-server container, rotates old backups, optionally syncs to cloud.
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
BACKUP_FILE="$BACKUP_DIR/magneetar_$TIMESTAMP.db.gz"

# The app's live data plane is SQLite, mounted on the persisted volume
# /app/data inside the magneetar-server container (MT_DB_PATH). The Postgres
# container is optional and holds no app data, so backups must target SQLite.
SERVER_CONTAINER="magneetar-server"
DB_PATH="/app/data/magneetar.db"  # inside the container (persisted volume)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

mkdir -p "$BACKUP_DIR"

# ── Cleanup on exit (remove temp files if interrupted/failed) ───────────────
TMP_DB=""
RESTORE_TMP=""
cleanup() {
    if [ -n "$TMP_DB" ] && [ -f "$TMP_DB" ]; then rm -f "$TMP_DB"; fi
    if [ -n "$RESTORE_TMP" ] && [ -f "$RESTORE_TMP" ]; then rm -f "$RESTORE_TMP"; fi
}
trap cleanup EXIT

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
    if ls "$BACKUP_DIR"/magneetar_*.db.gz 1>/dev/null 2>&1; then
        # shellcheck disable=SC2012  # ls -lh gives human-readable sizes for display
        ls -lh "$BACKUP_DIR"/magneetar_*.db.gz | awk '{print $6, $7, $8, " — ", $NF}'
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

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$SERVER_CONTAINER"; then
        echo -e "${RED}❌ $SERVER_CONTAINER container is not running${NC}"
        echo "   Start the stack first: docker compose up -d server"
        exit 1
    fi

    echo -e "${YELLOW}⚠️  WARNING: Restoring will overwrite the current database!${NC}"
    echo -n "Are you sure you want to continue? (yes/no): "
    read -r confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi

    RESTORE_TMP="$BACKUP_DIR/.restore_tmp_$$.db"
    echo -e "${GREEN}🔄 Restoring from: $RESTORE_FILE${NC}"
    gunzip -c "$RESTORE_FILE" > "$RESTORE_TMP"
    # Verify the backup is a valid SQLite database before overwriting the live DB
    if ! docker cp "$RESTORE_TMP" "$SERVER_CONTAINER:/tmp/magneetar_restore.db" || \
       ! docker exec "$SERVER_CONTAINER" python3 -c "
import sqlite3
chk = sqlite3.connect('/tmp/magneetar_restore.db')
ok = chk.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('integrity:', 'ok' if ok else 'FAILED')
if not ok:
    raise SystemExit(1)
"; then
        echo -e "${RED}   ❌ Backup failed integrity check — restore aborted (live DB untouched)${NC}"
        docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_restore.db 2>/dev/null || true
        exit 1
    fi
    if docker exec "$SERVER_CONTAINER" python3 -c "
import sqlite3
src = sqlite3.connect('/tmp/magneetar_restore.db')
dst = sqlite3.connect('$DB_PATH')
with dst:
    src.backup(dst)
dst.close()
src.close()
"; then
        docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_restore.db
        echo -e "${GREEN}✅ Restore complete! Restart the server to be safe: docker compose restart server${NC}"
    else
        docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_restore.db 2>/dev/null || true
        echo -e "${RED}   ❌ Restore failed — live DB may be in an inconsistent state; restore again or from an earlier backup${NC}"
        exit 1
    fi
    exit 0
fi

# ── Backup mode ──────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           MAGNEETAR — Database Backup                       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check that the server container is running
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$SERVER_CONTAINER"; then
    echo -e "${RED}❌ $SERVER_CONTAINER container is not running${NC}"
    echo "   Start the stack first: docker compose up -d server"
    exit 1
fi

# Create a consistent snapshot via SQLite's online backup API, then copy it out.
echo -e "${GREEN}📦 Creating backup...${NC}"
TMP_DB="$BACKUP_DIR/.backup_tmp_$$.db"
if docker exec "$SERVER_CONTAINER" python3 -c "
import sqlite3
src = sqlite3.connect('$DB_PATH')
dst = sqlite3.connect('/tmp/magneetar_backup.db')
with dst:
    src.backup(dst)
dst.close()
src.close()
" && docker cp "$SERVER_CONTAINER:/tmp/magneetar_backup.db" "$TMP_DB" && gzip -c "$TMP_DB" > "$BACKUP_FILE"; then
    docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_backup.db
    rm -f "$TMP_DB"
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}   ✅ Backup created: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
else
    echo -e "${RED}   ❌ Backup failed${NC}"
    docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_backup.db 2>/dev/null || true
    rm -f "$TMP_DB" "$BACKUP_FILE"
    exit 1
fi

# Rotate old backups (keep last 7 days)
echo -e "${GREEN}🧹 Cleaning old backups...${NC}"
find "$BACKUP_DIR" -name "magneetar_*.db.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null
OLD_COUNT=$(find "$BACKUP_DIR" -name "magneetar_*.db.gz" | wc -l)
echo -e "${GREEN}   ✅ $OLD_COUNT backups retained (${RETENTION_DAYS}-day rotation)${NC}"
echo ""

echo -e "${GREEN}✅ Backup complete!${NC}"
echo ""
echo "   File:   $BACKUP_FILE"
echo "   Size:   $BACKUP_SIZE"
echo "   To restore: bash $0 --restore $BACKUP_FILE"
echo "   To list backups: bash $0 --list"
echo ""
