#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Database + Media Backup Script
# Backs up the live SQLite database (the app's data plane) AND the evidence
# media store (photos/audio/video on disk, v1.4 media refactor) from the
# magneetar-server container, rotates old backups, and optionally syncs to an
# off-site rclone remote (MT_RCLONE_REMOTE, e.g. "mybackups:magneetar").
# Usage:
#   bash scripts/backup-db.sh                          # Create DB + media backup
#   bash scripts/backup-db.sh --restore <file>         # Restore DB from backup
#   bash scripts/backup-db.sh --restore-media <file>   # Restore media store
#   bash scripts/backup-db.sh --list                   # List available backups
#   bash scripts/backup-db.sh --sync                   # Force off-site sync
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS=7  # Keep backups for 7 days
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/magneetar_$TIMESTAMP.db.gz"
MEDIA_BACKUP_FILE="$BACKUP_DIR/magneetar_media_$TIMESTAMP.tar.gz"

# The app's live data plane is SQLite, mounted on the persisted volume
# /app/data inside the magneetar-server container (MT_DB_PATH). The Postgres
# container is optional and holds no app data, so backups must target SQLite.
# Evidence media lives at /app/media (magneetar-media volume, MT_MEDIA_DIR).
SERVER_CONTAINER="magneetar-server"
DB_PATH="/app/data/magneetar.db"  # inside the container (persisted volume)

# Off-site sync target. When unset (and no --sync flag), backup stays local.
# Set MT_RCLONE_REMOTE in the environment or root .env, e.g.:
#   MT_RCLONE_REMOTE="mybackups:magneetar"
RCLONE_REMOTE="${MT_RCLONE_REMOTE:-}"

# Make a user-local rclone visible to cron (cron runs with a minimal PATH and
# ~/.local/bin is not included). Idempotent; no-op when already on PATH.
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

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
RESTORE_MEDIA=""
LIST_MODE=false
FORCE_SYNC=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --restore)
            RESTORE_FILE="$2"
            shift 2
            ;;
        --restore-media)
            RESTORE_MEDIA="$2"
            shift 2
            ;;
        --list)
            LIST_MODE=true
            shift
            ;;
        --sync)
            FORCE_SYNC=true
            shift
            ;;
        *)
            echo "Usage: $0 [--restore <file>] [--restore-media <file>] [--list] [--sync]"
            exit 1
            ;;
    esac
done

# ── Off-site sync (shared by backup mode) ────────────────────────────────────
sync_to_remote() {
    local file="$1"
    if [ "$FORCE_SYNC" != "true" ] && [ -z "$RCLONE_REMOTE" ]; then
        return 0  # not configured — local-only backup
    fi
    if ! command -v rclone >/dev/null 2>&1; then
        echo -e "${YELLOW}   ⚠️  Off-site sync skipped: rclone is not installed (apt install rclone)${NC}"
        return 0
    fi
    if [ -z "$RCLONE_REMOTE" ]; then
        echo -e "${YELLOW}   ⚠️  Off-site sync skipped: MT_RCLONE_REMOTE is not set${NC}"
        return 0
    fi
    if rclone copy "$file" "$RCLONE_REMOTE" 2>/tmp/rclone_err; then
        echo -e "${GREEN}   ☁️  Synced to off-site remote: $RCLONE_REMOTE/$(basename "$file")${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Off-site sync FAILED (backup is still safe locally): $(head -1 /tmp/rclone_err)${NC}"
    fi
}

# ── List backups ─────────────────────────────────────────────────────────────
if $LIST_MODE; then
    echo -e "${GREEN}Available backups:${NC}"
    echo ""
    FOUND=false
    if ls "$BACKUP_DIR"/magneetar_*.db.gz 1>/dev/null 2>&1; then
        FOUND=true
        # shellcheck disable=SC2012  # ls -lh gives human-readable sizes for display
        ls -lh "$BACKUP_DIR"/magneetar_*.db.gz | awk '{print $6, $7, $8, " — DB:  ", $NF}'
    fi
    if ls "$BACKUP_DIR"/magneetar_media_*.tar.gz 1>/dev/null 2>&1; then
        FOUND=true
        # shellcheck disable=SC2012
        ls -lh "$BACKUP_DIR"/magneetar_media_*.tar.gz | awk '{print $6, $7, $8, " — MEDIA:", $NF}'
    fi
    if [ "$FOUND" = false ]; then
        echo "   No backups found."
    fi
    echo ""
    echo "Total size: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo '0B')"
    exit 0
fi

# ── Restore media mode ───────────────────────────────────────────────────────
if [ -n "$RESTORE_MEDIA" ]; then
    if [ ! -f "$RESTORE_MEDIA" ]; then
        echo -e "${RED}❌ Media backup file not found: $RESTORE_MEDIA${NC}"
        exit 1
    fi

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$SERVER_CONTAINER"; then
        echo -e "${RED}❌ $SERVER_CONTAINER container is not running${NC}"
        echo "   Start the stack first: docker compose up -d server"
        exit 1
    fi

    echo -e "${YELLOW}⚠️  WARNING: Restoring will replace the current media store!${NC}"
    echo -n "Are you sure you want to continue? (yes/no): "
    read -r confirm
    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi

    echo -e "${GREEN}🔄 Restoring media store from: $RESTORE_MEDIA${NC}"
    # Move the current media dir aside (rollback path), then extract the
    # backup. Media files are server-generated UUIDs, so a clean replace is
    # safe and leaves no stale files from outside the backup.
    if ! docker exec "$SERVER_CONTAINER" sh -c \
        'rm -rf /app/media.old && mv /app/media /app/media.old 2>/dev/null; mkdir -p /app/media'; then
        echo -e "${RED}   ❌ Could not prepare the container media dir${NC}"
        exit 1
    fi
    if gzip -t "$RESTORE_MEDIA" 2>/dev/null && gunzip -c "$RESTORE_MEDIA" | docker exec -i "$SERVER_CONTAINER" tar -xzf - -C /app; then
        # Clean up the rollback dir only after a successful extraction.
        docker exec "$SERVER_CONTAINER" rm -rf /app/media.old 2>/dev/null || true
        echo -e "${GREEN}✅ Media restore complete! Evidence files are back in place.${NC}"
    else
        # Extraction failed — roll back to the pre-restore state.
        docker exec "$SERVER_CONTAINER" sh -c 'rm -rf /app/media && mv /app/media.old /app/media' 2>/dev/null || true
        echo -e "${RED}   ❌ Media restore failed — previous media store restored${NC}"
        exit 1
    fi
    exit 0
fi

# ── Restore DB mode ──────────────────────────────────────────────────────────
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
        echo -e "${GREEN}   Tip: also restore the media store if this backup predates/replaces evidence files:${NC}"
        echo -e "   ${GREEN}   bash $0 --restore-media $BACKUP_DIR/magneetar_media_*.tar.gz${NC}"
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
echo "║           MAGNEETAR — Database + Media Backup               ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check that the server container is running
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$SERVER_CONTAINER"; then
    echo -e "${RED}❌ $SERVER_CONTAINER container is not running${NC}"
    echo "   Start the stack first: docker compose up -d server"
    exit 1
fi

# ── 1. Database snapshot (SQLite online backup API) ─────────────────────────
echo -e "${GREEN}📦 Creating database backup...${NC}"
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
    echo -e "${GREEN}   ✅ DB backup created: $BACKUP_FILE (${BACKUP_SIZE})${NC}"
else
    echo -e "${RED}   ❌ DB backup failed${NC}"
    docker exec "$SERVER_CONTAINER" rm -f /tmp/magneetar_backup.db 2>/dev/null || true
    rm -f "$TMP_DB" "$BACKUP_FILE"
    exit 1
fi

# ── 2. Media store tarball (evidence files on the persisted volume) ──────────
echo -e "${GREEN}📁 Creating media backup...${NC}"
# Stream the tarball straight to the host — no container temp file needed.
if docker exec "$SERVER_CONTAINER" tar -czf - -C /app media > "$MEDIA_BACKUP_FILE" 2>/dev/null \
   && gzip -t "$MEDIA_BACKUP_FILE" 2>/dev/null \
   && tar -tzf "$MEDIA_BACKUP_FILE" >/dev/null 2>&1; then
    MEDIA_BACKUP_SIZE=$(du -h "$MEDIA_BACKUP_FILE" | cut -f1)
    MEDIA_COUNT=$(tar -tzf "$MEDIA_BACKUP_FILE" 2>/dev/null | grep -c '\.' || true)
    echo -e "${GREEN}   ✅ Media backup created: $MEDIA_BACKUP_FILE (${MEDIA_BACKUP_SIZE}, $MEDIA_COUNT files)${NC}"
else
    # An empty or missing media dir produces a valid (empty) tarball; only a
    # real failure lands here. Don't fail the whole backup over media — the DB
    # is the critical piece — but DO remove the partial tarball.
    rm -f "$MEDIA_BACKUP_FILE"
    echo -e "${YELLOW}   ⚠️  Media backup failed or media dir missing — DB backup still safe${NC}"
fi

# ── 3. Off-site sync ─────────────────────────────────────────────────────────
if [ -n "$MEDIA_BACKUP_FILE" ] && [ -f "$MEDIA_BACKUP_FILE" ]; then
    sync_to_remote "$MEDIA_BACKUP_FILE"
fi
sync_to_remote "$BACKUP_FILE"

# ── 4. Rotation (keep last 7 days for both kinds) ────────────────────────────
echo -e "${GREEN}🧹 Cleaning old backups...${NC}"
find "$BACKUP_DIR" -name "magneetar_*.db.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null
find "$BACKUP_DIR" -name "magneetar_media_*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null
OLD_COUNT=$(find "$BACKUP_DIR" -name "magneetar_*.*.gz" -o -name "magneetar_media_*.tar.gz" | wc -l)
echo -e "${GREEN}   ✅ $OLD_COUNT backups retained (${RETENTION_DAYS}-day rotation)${NC}"
echo ""

echo -e "${GREEN}✅ Backup complete!${NC}"
echo ""
echo "   DB:    $BACKUP_FILE"
if [ -f "$MEDIA_BACKUP_FILE" ]; then
    echo "   Media: $MEDIA_BACKUP_FILE"
fi
echo "   To restore DB:    bash $0 --restore $BACKUP_FILE"
if [ -f "$MEDIA_BACKUP_FILE" ]; then
    echo "   To restore media: bash $0 --restore-media $MEDIA_BACKUP_FILE"
fi
echo "   To list backups:  bash $0 --list"
echo ""
