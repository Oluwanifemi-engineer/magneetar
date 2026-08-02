#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Cron Installer (idempotent)
# Installs the two production cron jobs:
#   1. Daily database backup at 03:00  → scripts/backup-db.sh
#   2. Health monitor every 5 minutes  → scripts/health-monitor.sh
# Safe to re-run: existing Magneetar lines are replaced, never duplicated.
# Usage: bash scripts/install-cron.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/tmp/magneetar-monitor"
BACKUP_LOG="/tmp/magneetar-backup.log"

mkdir -p "$LOG_DIR"

# Backup job: 3:00 AM every day (low-traffic window; backup uses the SQLite
# online-backup API, so no downtime even mid-deploy).
BACKUP_LINE="0 3 * * * cd $PROJECT_DIR && bash scripts/backup-db.sh >> $BACKUP_LOG 2>&1"

# Health monitor: every 5 minutes, restarts unhealthy containers + alerts.
MONITOR_LINE="*/5 * * * * cd $PROJECT_DIR && bash $SCRIPT_DIR/health-monitor.sh >> $LOG_DIR/cron.log 2>&1"

# ── Idempotent install: drop old Magneetar lines, add fresh ones ─────────────
CURRENT="$(crontab -l 2>/dev/null || true)"

# Remove previous Magneetar-managed entries (matches on the project path).
CLEANED="$(printf '%s\n' "$CURRENT" | grep -v "magneetar" || true)"

printf '%s\n%s\n%s\n%s\n%s\n' \
  "$CLEANED" \
  "# Magneetar — Daily DB backup at 3:00 AM" \
  "$BACKUP_LINE" \
  "# Magneetar — Health check every 5 minutes" \
  "$MONITOR_LINE" | crontab -

echo "✅ Cron installed:"
echo "   • $BACKUP_LINE"
echo "   • $MONITOR_LINE"
echo ""
echo "Verify with: crontab -l"
