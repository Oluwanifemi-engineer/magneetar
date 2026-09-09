"""
Observability Domain

Owns: Metrics collection, health checks, error tracking, analytics,
      dashboard statistics, performance monitoring.

This domain has read-only access to data owned by other domains
(views/materialized stats, not direct table writes).

Extracted from: routes/metrics.py, health checks in main.py

Domain Events Consumed (read-only):
  - All domain events (for aggregation and alerting)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from auth import user_id_from_subject
from logging_config import get_logger

logger = get_logger("magneetar.observability")


# ─── Server metrics ────────────────────────────────────────────────────────────


def get_server_metrics() -> dict:
    """Get server-level metrics (process-level, not DB)."""
    import time

    try:
        from main import SERVER_START
    except ImportError:
        SERVER_START = time.time()

    uptime_seconds = time.time() - SERVER_START

    return {
        "uptime_seconds": round(uptime_seconds, 1),
        "environment": __import__("config").settings.ENVIRONMENT,
    }


# ─── Dashboard statistics ──────────────────────────────────────────────────────


def get_dashboard_stats(
    conn: sqlite3.Connection,
    auth_token: str,
) -> dict:
    """Get dashboard statistics.

    Users see stats scoped to their own devices. Admin/operators see global
    stats (no user_id from the auth token).
    """
    user_id = user_id_from_subject(auth_token)

    if user_id:
        total_devices = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE owner_id=?",
            (user_id,),
        ).fetchone()[0]
        active_devices = conn.execute(
            """SELECT COUNT(*) FROM devices
               WHERE owner_id=? AND
               datetime(last_seen) > datetime('now', '-5 minutes')""",
            (user_id,),
        ).fetchone()[0]
        stolen_devices = conn.execute(
            """SELECT COUNT(*) FROM devices
               WHERE is_stolen=1 AND owner_id=?""",
            (user_id,),
        ).fetchone()[0]
        total_locations = conn.execute(
            """SELECT COUNT(*) FROM locations l
               JOIN devices d ON l.device_id=d.id
               WHERE d.owner_id=?""",
            (user_id,),
        ).fetchone()[0]
        total_media = conn.execute(
            """SELECT COUNT(*) FROM media m
               JOIN devices d ON m.device_id=d.id
               WHERE d.owner_id=?""",
            (user_id,),
        ).fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = conn.execute(
            """SELECT COUNT(*) FROM alerts a
               JOIN devices d ON a.device_id=d.id
               WHERE d.owner_id=? AND a.sent_at > ?""",
            (user_id, today),
        ).fetchone()[0]
    else:
        total_devices = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_devices = conn.execute(
            """SELECT COUNT(*) FROM devices
               WHERE datetime(last_seen) > datetime('now', '-5 minutes')"""
        ).fetchone()[0]
        stolen_devices = conn.execute("SELECT COUNT(*) FROM devices WHERE is_stolen=1").fetchone()[0]
        total_locations = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        total_media = conn.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE sent_at > ?",
            (today,),
        ).fetchone()[0]

    return {
        "total_devices": total_devices,
        "active_devices": active_devices,
        "stolen_devices": stolen_devices,
        "recovered_devices": 0,
        "total_locations": total_locations,
        "total_media": total_media,
        "alerts_today": alerts_today,
    }


# ─── Analytics (MVP metrics) ───────────────────────────────────────────────────


def get_analytics(conn: sqlite3.Connection) -> dict:
    """MVP analytics for the dashboard.

    Active device counts by day (last 7 days), command status breakdown,
    total devices and locations.
    """
    active_devices = conn.execute(
        """SELECT date(server_timestamp) as day,
                  COUNT(DISTINCT device_id) as count
           FROM locations
           WHERE server_timestamp > datetime('now', '-7 days')
           GROUP BY date(server_timestamp) ORDER BY day"""
    ).fetchall()

    command_stats = conn.execute("SELECT status, COUNT(*) as count FROM commands GROUP BY status").fetchall()

    total_devices = conn.execute("SELECT COUNT(*) as cnt FROM devices").fetchone()["cnt"]

    total_locations = conn.execute("SELECT COUNT(*) as cnt FROM locations").fetchone()["cnt"]

    return {
        "active_devices_7d": [dict(r) for r in active_devices],
        "command_stats": {r["status"]: r["count"] for r in command_stats},
        "total_devices": total_devices,
        "total_locations": total_locations,
    }


# ─── Error log management ──────────────────────────────────────────────────────


def list_errors(
    conn: sqlite3.Connection,
    limit: int = 50,
    unresolved_only: bool = False,
) -> dict:
    """List server errors with optional filter for unresolved only.
    Admin-only (operators only — regular accounts cannot see this)."""
    if unresolved_only:
        rows = conn.execute(
            """SELECT * FROM error_log
               WHERE resolved=0
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM error_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

    count_row = conn.execute("SELECT COUNT(*) as cnt FROM error_log WHERE resolved=0").fetchone()

    return {
        "errors": [dict(r) for r in rows],
        "unresolved_count": count_row["cnt"] if count_row else 0,
        "total_count": conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0],
    }


def resolve_error(
    conn: sqlite3.Connection,
    error_id: int,
    auth: str,
    notes: str = "",
) -> dict:
    """Mark an error as resolved. Admin-only."""
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """UPDATE error_log SET resolved=1, resolved_at=?,
           resolved_by=?, notes=? WHERE id=?""",
        (now, auth, notes, error_id),
    )
    conn.commit()

    from database import log_audit

    log_audit(
        "error_resolved",
        actor=auth,
        details=f"Error #{error_id}: {notes}",
    )

    return {
        "status": "ok",
        "message": f"Error #{error_id} marked as resolved",
    }
