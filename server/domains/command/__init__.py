"""
Command & Control Domain

Owns: Remote command dispatch (lock, siren, wipe, camera, locate),
      command queueing, delivery via WebSocket/SMS/FCM, command status
      tracking, SMS relay processing.

Data tables: commands
Extracted from: routes/devices.py (command portions), sms_relay.py

Domain Events Published:
  - command_queued         {command_id, device_id, type, channel}
  - command_delivered      {command_id, device_id, channel}
  - command_acknowledged   {command_id, device_id, status}
  - command_failed         {command_id, device_id, reason}
  - sms_ack_received       {command_id, device_id, from_number}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from logging_config import get_logger
from websocket_manager import broadcast_to_dashboards

logger = get_logger("magneetar.command")

# ─── Public API ────────────────────────────────────────────────────────────────


def enqueue_command(
    conn: sqlite3.Connection,
    device_id: str,
    command: str,
    params: str = "",
    priority: int = 5,
    delivery_channel: Optional[str] = None,
) -> int:
    """Issue a remote command to a device.

    Returns the new command row id. Priority 1 = highest urgency
    (theft-response: siren, capture); 5 = standard (locate).
    """
    now = datetime.now(timezone.utc).isoformat()

    # Deduplicate against an identical already-pending row so a repeated
    # dashboard action never piles up duplicate commands on the device.
    dup = conn.execute(
        "SELECT 1 FROM commands WHERE device_id=? AND command=? " "AND status='pending' LIMIT 1",
        (device_id, command),
    ).fetchone()
    if dup:
        cmd = conn.execute(
            "SELECT id FROM commands WHERE device_id=? AND command=? " "AND status='pending' LIMIT 1",
            (device_id, command),
        ).fetchone()
        return cmd["id"]

    # Expiry policy mirrors the device-side evidence/expiry windows:
    # siren/alarm = 5 min (sensitive, time-critical); captures = 30 min;
    # standard commands = 1 hour; locate = 2 hours.
    if command in ("alarm", "siren"):
        expires_in = timedelta(minutes=5)
    elif command in ("capture_photo_front", "capture_photo_back", "capture_audio"):
        expires_in = timedelta(minutes=30)
    elif command == "locate":
        expires_in = timedelta(hours=2)
    else:
        expires_in = timedelta(hours=1)
    expires_at = (datetime.now(timezone.utc) + expires_in).isoformat()

    cur = conn.execute(
        """INSERT INTO commands (device_id, command, params, status, priority,
           issued_at, expires_at, delivery_channel)
           VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)""",
        (
            device_id,
            command,
            params,
            priority,
            now,
            expires_at,
            delivery_channel or "poll",
        ),
    )
    conn.commit()

    cmd_id = cur.lastrowid
    logger.info(
        "command_queued",
        extra={
            "extra_data": {
                "command_id": cmd_id,
                "device_id": device_id,
                "command": command,
                "priority": priority,
                "channel": delivery_channel or "poll",
            }
        },
    )
    broadcast_to_dashboards(
        {
            "type": "command_queued",
            "data": {
                "command_id": cmd_id,
                "device_id": device_id,
                "command": command,
                "priority": priority,
                "channel": delivery_channel or "poll",
            },
        }
    )
    return cmd_id


def acknowledge_command(
    conn: sqlite3.Connection,
    device_id: str,
    command_id: int,
    status: str,
    failure_reason: Optional[str] = None,
) -> dict:
    """Record a device's acknowledgment of a command.

    status: 'executed' | 'failed' | 'expired'
    failure_reason: human-readable explanation for a 'failed' status
        (e.g. 'Microphone muted — set Microphone to Allow all the time').
    """
    now = datetime.now(timezone.utc).isoformat()

    # A failure_reason is only meaningful for 'failed' — persist it then,
    # and always clear it on 'executed' so a stale reason from an earlier
    # failed attempt never lingers on a row that later succeeded.
    reason = failure_reason if status == "failed" else None

    cur = conn.execute(
        """UPDATE commands
           SET status=?, executed_at=?, failure_reason=?
           WHERE id=? AND device_id=?""",
        (status, now, reason, command_id, device_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        raise KeyError(f"Command {command_id} not found for device {device_id}")

    broadcast_to_dashboards(
        {
            "type": "command_ack",
            "data": {
                "command_id": command_id,
                "device_id": device_id,
                "status": status,
                "failure_reason": failure_reason,
            },
        }
    )
    logger.info(
        "command_acknowledged",
        extra={
            "extra_data": {
                "command_id": command_id,
                "device_id": device_id,
                "status": status,
            }
        },
    )
    return {"status": "ok", "command_id": command_id, "device_id": device_id}


def poll_pending_commands(conn: sqlite3.Connection, device_id: str) -> list[dict]:
    """Return the pending commands for a device that the device should execute.

    Excludes:
    - SMS-delivered commands (already routed to the device over SMS when
      it was offline — the device must not double-execute them when it comes
      back online and polls).
    - Expired commands (their expires_at has passed).
    """
    rows = conn.execute(
        """SELECT id, command, params, priority
           FROM commands
           WHERE device_id=?
             AND status='pending'
             AND (delivery_channel IS NULL OR delivery_channel != 'sms')
             AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
           ORDER BY priority ASC""",
        (device_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_command(conn: sqlite3.Connection, command_id: int) -> Optional[dict]:
    """Fetch a single command by id (for dashboard detail view)."""
    row = conn.execute("SELECT * FROM commands WHERE id=?", (command_id,)).fetchone()
    return dict(row) if row else None


# ─── Internal helpers ──────────────────────────────────────────────────────────


def _queue_auto_action(
    conn: sqlite3.Connection,
    device_id: str,
    command: str,
) -> None:
    """Queue one auto-action command (priority 1, poll delivery), deduplicated.

    Shared by geofence auto-actions and the failed-unlock 'theftie' reaction.
    The exit/lock transition fires exactly once, but the device may keep pinging
    from outside/locked — without this guard each ping would queue another
    capture/siren until the first expired.
    """
    pending = conn.execute(
        """SELECT 1 FROM commands
           WHERE device_id=? AND command=? AND status='pending' LIMIT 1""",
        (device_id, command),
    ).fetchone()
    if pending:
        return

    now = datetime.now(timezone.utc).isoformat()
    # Mirror enqueue_command's expiry policy: alarm is sensitive (5 min),
    # evidence captures get the standard 30-minute window.
    if command == "alarm":
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    else:
        expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    conn.execute(
        """INSERT INTO commands (device_id, command, params, status, priority,
           issued_at, expires_at, delivery_channel)
           VALUES (?, ?, '', 'pending', 1, ?, ?, 'poll')""",
        (device_id, command, now, expires),
    )
    conn.commit()
