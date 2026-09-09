"""
Magneetar Dashboard Command Routes (extracted from routes/dashboard.py — Phase 0).

Remote command endpoints for the web dashboard:
- Issue command (lock, alarm, wipe, capture, lost_mode)
- Command history per device
- Delete single command (step-up gated)
- Clear command history (step-up gated)

Commands support multi-channel delivery:
- FCM push (always attempted — fast, reliable)
- SMS relay (fallback when device is offline + owner enabled SMS)
- Device poll (default channel)
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from auth import check_command_rate_limit, check_rate_limit, require_dashboard_auth
from database import get_db, log_audit
from fastapi import APIRouter, Depends, HTTPException, Query
from logging_config import get_logger
from models import CommandRequest
from routes.dashboard_helpers import (
    _assert_device_access,
    _verify_stepup_password,
)

logger = get_logger("magneetar")

router = APIRouter()


# ─── Commands (Dashboard Issue) ──────────────────────────────────────────────


@router.post("/api/dashboard/command")
async def issue_command(
    cmd: CommandRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Issue a command to a device."""
    _assert_device_access(db, cmd.device_id, auth, min_role="admin")
    if not check_command_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    if cmd.command == "wipe":
        if cmd.params != "CONFIRMED_WIPE":
            raise HTTPException(
                status_code=400,
                detail="Wipe requires params='CONFIRMED_WIPE'",
            )
        _verify_stepup_password(db, auth, cmd.password)

    # ── Offline Command Relay (SMS) ──────────────────────────────────────
    device = db.execute(
        "SELECT sms_phone, sms_commands_enabled, device_key_hash, last_seen " "FROM devices WHERE id=?",
        (cmd.device_id,),
    ).fetchone()

    delivery_channel = "poll"
    sms_phone = (device["sms_phone"] or "") if device else ""
    sms_enabled = bool(device and device["sms_commands_enabled"])
    device_offline = True
    if device and device["last_seen"]:
        try:
            last_seen = datetime.fromisoformat(device["last_seen"])
            device_offline = (datetime.now(timezone.utc) - last_seen).total_seconds() > 300
        except Exception:
            device_offline = True

    has_device_key = bool(device and device["device_key_hash"])
    if sms_enabled and sms_phone and device_offline and has_device_key:
        if not check_rate_limit(f"sms:{cmd.device_id}", "sms_command", 5, 1):
            raise HTTPException(
                status_code=429,
                detail=("SMS command relay rate limit exceeded " "— try again in a minute"),
            )
        delivery_channel = "sms"

    # ── Expiry calculation ───────────────────────────────────────────────
    sms_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=24 * 60)).isoformat()
    poll_expires_minutes = (
        5 if cmd.command in ("wipe", "lock", "alarm") else (24 * 60 if cmd.command == "lost_mode" else 30)
    )
    poll_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=poll_expires_minutes)).isoformat()
    expires_at = sms_expires_at if delivery_channel == "sms" else poll_expires_at

    # ── Priority ─────────────────────────────────────────────────────────
    priority = cmd.priority
    if (
        cmd.command
        in (
            "wipe",
            "lock",
            "alarm",
            "capture_photo",
            "capture_photo_front",
            "capture_audio",
            "lost_mode",
        )
        and priority > 1
    ):
        priority = 1

    cur = db.execute(
        "INSERT INTO commands "
        "(device_id, command, params, priority, issued_at, expires_at, "
        "delivery_channel) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            cmd.device_id,
            cmd.command,
            cmd.params,
            priority,
            now,
            expires_at,
            delivery_channel,
        ),
    )
    db.commit()

    command_id = cur.lastrowid

    # ── SMS delivery (best-effort) ───────────────────────────────────────
    sms_delivered = False
    if delivery_channel == "sms":
        from sms_relay import command_sms_body, send_command_sms

        sms_body = command_sms_body(
            device["device_key_hash"],
            command_id,
            cmd.command,
            cmd.params or "",
        )
        sms_delivered = send_command_sms(sms_phone, sms_body)
        log_audit(
            "command_sms_relay",
            actor=auth,
            details=(
                f"Command: {cmd.command} #{command_id} to {cmd.device_id} "
                f"via SMS to {sms_phone} → "
                f"{'delivered' if sms_delivered else 'SEND FAILED'}"
            ),
        )

        if not sms_delivered:
            db.execute(
                "UPDATE commands SET delivery_channel='poll', expires_at=? " "WHERE id=?",
                (poll_expires_at, command_id),
            )
            db.commit()
            delivery_channel = "poll"

    # ── FCM Command Push (always attempt) ───────────────────────────────
    fcm_pushed = False
    try:
        from fcm_command import push_command_to_device

        fcm_pushed = await push_command_to_device(
            device_id=cmd.device_id,
            command=cmd.command,
            command_id=command_id,
            params=cmd.params,
            priority=priority,
        )
        if fcm_pushed:
            log_audit(
                "command_fcm_push",
                actor=auth,
                details=(f"Command: {cmd.command} #{command_id} to " f"{cmd.device_id} via FCM"),
            )
    except Exception as e:
        logger.warning(f"FCM command push failed for {cmd.device_id}: {e}")

    log_audit(
        "command_issued",
        actor=auth,
        details=f"Command: {cmd.command} to {cmd.device_id}",
    )

    return {
        "status": "queued",
        "command_id": command_id,
        "delivery": delivery_channel,
        "sms_delivered": sms_delivered,
        "fcm_pushed": fcm_pushed,
    }


@router.get("/api/dashboard/commands/{device_id}")
async def get_command_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get command history for a device."""
    _assert_device_access(db, device_id, auth, min_role="viewer")

    db.execute(
        """UPDATE commands SET status='expired'
           WHERE device_id=? AND status='pending' AND expires_at IS NOT NULL
             AND datetime(expires_at) <= datetime('now')""",
        (device_id,),
    )
    db.commit()

    rows = db.execute(
        "SELECT * FROM commands WHERE device_id=? ORDER BY issued_at DESC LIMIT 50",
        (device_id,),
    ).fetchall()

    return {"commands": [dict(r) for r in rows]}


# ─── Command Deletion (history cleanup, step-up gated) ───────────────────────


@router.delete("/api/dashboard/commands/{command_id}")
async def delete_command(
    command_id: int,
    body: dict = None,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Delete a single command from history, gated by a step-up password."""
    row = db.execute("SELECT device_id FROM commands WHERE id=?", (command_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_device_access(db, row["device_id"], auth, min_role="admin")

    _verify_stepup_password(db, auth, (body or {}).get("password"))

    db.execute("DELETE FROM commands WHERE id=?", (command_id,))
    db.commit()
    log_audit(
        "command_deleted",
        actor=auth,
        details=f"Command: {command_id}, device: {row['device_id']}",
    )
    return {"status": "ok", "deleted_id": command_id}


@router.delete("/api/dashboard/commands/device/{device_id}")
async def clear_command_history(
    device_id: str,
    body: dict = None,
    only_finished: bool = Query(True),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Delete command history for a device, gated by a step-up password."""
    _assert_device_access(db, device_id, auth, min_role="admin")

    _verify_stepup_password(db, auth, (body or {}).get("password"))

    if only_finished:
        cur = db.execute(
            "DELETE FROM commands WHERE device_id=? AND status != 'pending'",
            (device_id,),
        )
    else:
        cur = db.execute("DELETE FROM commands WHERE device_id=?", (device_id,))
    db.commit()
    log_audit(
        "command_history_cleared",
        actor=auth,
        details=f"Device: {device_id}, only_finished={only_finished}",
    )
    return {"status": "ok", "deleted": cur.rowcount if cur else 0}
