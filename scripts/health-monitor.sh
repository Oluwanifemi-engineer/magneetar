#!/usr/bin/env bash
# ─── Magneetar Health Monitor ───────────────────────────────────────────────
# Checks API health endpoint at regular intervals.
# Logs failures and can be configured to send alerts.
#
# Usage:
#   bash scripts/health-monitor.sh              # Single check (exit 0/1)
#   bash scripts/health-monitor.sh --watch      # Continuous monitoring
#   bash scripts/health-monitor.sh --init-cron  # Set up 5-min cron job
#
# Environment: MT_API_ENDPOINT (default: https://api.magneetar.me)
#              MT_ALERT_EMAIL (default: none — email alerts on failure)

set -euo pipefail

API="${MT_API_ENDPOINT:-https://api.magneetar.me}"
LOG_DIR="/tmp/magneetar-monitor"
LOG_FILE="$LOG_DIR/health.log"
ALERT_EMAIL="${MT_ALERT_EMAIL:-}"

mkdir -p "$LOG_DIR"

check_health() {
    local ts
    ts=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

    # Use curl with timeout and capture HTTP status
    local http_code
    http_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 15 "$API/health" 2>/dev/null || echo "000")

    if [ "$http_code" = "200" ]; then
        echo "$ts | ✅ UP | HTTP $http_code | $API/health" >> "$LOG_FILE"
        echo "✅ UP — $API/health (HTTP $http_code)"
        return 0
    else
        echo "$ts | ❌ DOWN | HTTP $http_code | $API/health" >> "$LOG_FILE"
        echo "❌ DOWN — $API/health (HTTP $http_code)"

        # Alert if email configured
        if [ -n "$ALERT_EMAIL" ] && command -v mail &>/dev/null; then
            echo "Magneetar DOWN at $ts (HTTP $http_code)" | \
                mail -s "🚨 Magneetar DOWN — $API" "$ALERT_EMAIL"
        fi

        return 1
    fi
}

show_status() {
    echo "=== Magneetar Health Monitor ==="
    echo "Endpoint: $API/health"
    echo "Log: $LOG_FILE"
    echo ""
    if [ -f "$LOG_FILE" ]; then
        echo "Last 10 checks:"
        tail -10 "$LOG_FILE"
        echo ""
        echo "Uptime stats:"
        local total
        total=$(wc -l < "$LOG_FILE")
        local up
        up=$(grep -c '✅' "$LOG_FILE" || true)
        local down
        down=$(grep -c '❌' "$LOG_FILE" || true)
        if [ "$total" -gt 0 ]; then
            local pct
            pct=$((up * 100 / total))
            echo "  Total checks: $total"
            echo "  ✅ Up: $up ($pct%)"
            echo "  ❌ Down: $down"
        fi
    else
        echo "No checks yet. Run: bash $0"
    fi
}

init_cron() {
    local script_path
    script_path="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
    local cron_job="*/5 * * * * cd $(dirname "$script_path")/.. && bash $script_path >> /tmp/magneetar-monitor/cron.log 2>&1"

    if crontab -l 2>/dev/null | grep -q "$script_path"; then
        echo "✅ Cron job already configured"
    else
        (crontab -l 2>/dev/null; echo "# Magneetar — Health check every 5 minutes"; echo "$cron_job") | crontab -
        echo "✅ Cron job installed (every 5 minutes)"
    fi
    crontab -l | grep -A1 'Magneetar.*Health'
}

# ─── Main ───────────────────────────────────────────────────────────────────

case "${1:-}" in
    --watch)
        echo "Monitoring $API/health every 60s... (Ctrl+C to stop)"
        while true; do
            check_health
            sleep 60
        done
        ;;
    --status)
        show_status
        ;;
    --init-cron)
        init_cron
        ;;
    *)
        check_health
        ;;
esac
