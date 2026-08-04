"""
Magneetar Dashboard-Facing API Routes
All endpoints for the web dashboard (devices, locations, commands, evidence, etc.)
"""

import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from auth import (
    check_command_rate_limit,
    check_login_rate_limit,
    create_dashboard_tokens,
    refresh_access_token,
    require_dashboard_auth,
    user_id_from_subject,
)
from config import settings
from database import (
    check_rate_limit,
    delete_device_cascade,
    get_db,
    get_db_context,
    log_audit,
)
from evidence import evidence_builder
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from logging_config import get_logger
from models import (
    CommandRequest,
    DeviceClaimByPairingRequest,
    GeofenceRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)

# Shared device helpers live in routes/devices.py; importing them here is
# cycle-safe (devices.py never imports routes/dashboard).
from routes.devices import _user_exists  # noqa: E402

logger = get_logger("magneetar")

router = APIRouter()


def _resolve_user_id(auth: str) -> Optional[str]:
    """Return the user id if the auth subject is a user token, else None (admin)."""
    return user_id_from_subject(auth)


def _parse_json_list(raw) -> Optional[list]:
    """Parse a JSON-TEXT list column; None for NULL or invalid."""
    if raw is None:
        return None
    import json as _json

    try:
        parsed = _json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        return None


def _parse_int(raw) -> Optional[int]:
    """Coerce an hour column to int; None for NULL or unparseable.

    Quiet hours added by the pre-v1.2 migration were ALTERed with TEXT
    affinity, so values on upgraded DBs can arrive as strings ('22').
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _assert_device_access(db, device_id: str, auth: str):
    """Admins can access any device; users only devices linked to their account."""
    user_id = _resolve_user_id(auth)
    if user_id is None:
        return
    row = db.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    if row["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Access denied: device not linked to your account")


def _verify_stepup_password(db, auth: str, raw_password) -> None:
    """Re-authenticate a destructive action with a step-up password.

    Destructive, privacy-sensitive actions (media/device deletion) must not
    succeed on a stolen dashboard session alone — the caller re-authenticates
    with their account password (user mode) or the master API key itself
    (admin mode). Attempts are rate-limited per actor; raises HTTPException
    (400 missing / 401 wrong / 429 throttled).
    """
    from auth import check_password_verify_rate_limit, verify_password

    if not check_password_verify_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Too many verification attempts")

    password = raw_password if isinstance(raw_password, str) else ""
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    user_id = _resolve_user_id(auth)
    if user_id is not None:
        # User mode — verify the account password (bcrypt / PBKDF2).
        with get_db_context() as conn:
            user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")
    else:
        # Admin / API-key mode — re-verify the master API key itself.
        if not hmac.compare_digest(password, settings.API_KEY):
            raise HTTPException(status_code=401, detail="Invalid password")


# ─── Dashboard Auth ──────────────────────────────────────────────────────────


@router.post("/api/auth/login", response_model=TokenResponse)
async def dashboard_login(req: LoginRequest, request: Request):
    """Dashboard login with API key. Rate-limited by real client IP."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    if cf_ip:
        client_ip = cf_ip
    elif forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    if not check_login_rate_limit(client_ip):
        log_audit("login_rate_limited", details=f"IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Too many login attempts")

    if req.api_key != settings.API_KEY:
        log_audit("login_failed", details=f"Invalid API key from IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    log_audit("dashboard_login", actor="dashboard")
    return create_dashboard_tokens(req.api_key)


@router.post("/api/auth/refresh", response_model=TokenResponse)
async def dashboard_refresh(req: RefreshRequest):
    """Refresh dashboard tokens."""
    return refresh_access_token(req.refresh_token)


# ─── Devices ─────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/devices")
async def list_devices(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """List devices with latest location. Users see only their own devices."""
    user_id = _resolve_user_id(auth)
    if user_id:
        devices = db.execute(
            """SELECT d.*,
                      l.lat, l.lng, l.battery_percent, l.sentinel_score, l.threat_level
               FROM devices d
               LEFT JOIN locations l ON d.id = l.device_id
                   AND l.id = (SELECT MAX(id) FROM locations WHERE device_id = d.id)
               WHERE d.owner_id = ?
               ORDER BY d.last_seen DESC""",
            (user_id,),
        ).fetchall()
    else:
        devices = db.execute(
            """SELECT d.*,
                      l.lat, l.lng, l.battery_percent, l.sentinel_score, l.threat_level
               FROM devices d
               LEFT JOIN locations l ON d.id = l.device_id
                   AND l.id = (SELECT MAX(id) FROM locations WHERE device_id = d.id)
               ORDER BY d.last_seen DESC"""
        ).fetchall()

    result = []
    for d in devices:
        is_online = False
        if d["last_seen"]:
            try:
                last_seen = datetime.fromisoformat(d["last_seen"])
                is_online = (datetime.now(timezone.utc) - last_seen).total_seconds() < 300
            except Exception:
                pass

        result.append(
            {
                "id": d["id"],
                "alias": d["alias"],
                "model": d["model"],
                "os_version": d["os_version"],
                "app_version": d["app_version"],
                "last_seen": d["last_seen"],
                "registered": d["registered"],
                "is_stolen": bool(d["is_stolen"]),
                "operating_mode": d["operating_mode"],
                "sentinel_score": d["sentinel_score"] or 0,
                "lat": d["lat"],
                "lng": d["lng"],
                "battery_percent": d["battery_percent"],
                "is_online": is_online,
                "capture_armed": (
                    bool(d["capture_armed"]) if "capture_armed" in d.keys() and d["capture_armed"] is not None else None
                ),
                "archived_at": d["archived_at"] if "archived_at" in d.keys() else None,
                "alert_phone": d["alert_phone"] if "alert_phone" in d.keys() else None,
                "alert_email": d["alert_email"] if "alert_email" in d.keys() else None,
                # Per-device prefs stored as JSON TEXT — parse for the client;
                # NULL (no override) stays None so the UI shows global defaults.
                "alert_channels": (_parse_json_list(d["alert_channels"]) if "alert_channels" in d.keys() else None),
                "enabled_types": (_parse_json_list(d["enabled_types"]) if "enabled_types" in d.keys() else None),
                "quiet_hours_start": (_parse_int(d["quiet_hours_start"]) if "quiet_hours_start" in d.keys() else None),
                "quiet_hours_end": (_parse_int(d["quiet_hours_end"]) if "quiet_hours_end" in d.keys() else None),
            }
        )

    return {"devices": result}


@router.post("/api/dashboard/devices/claim-by-pairing")
async def claim_device_by_pairing(
    req: DeviceClaimByPairingRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Link an ownerless device to the authenticated account using the pairing
    code shown in the Magneetar app on the phone.

    The pairing code is the first 8 hex chars of SHA-256(device_key). The app
    displays it (it holds the raw key); the server stores only the full hash
    (device_key_hash), so verification compares the submitted code against the
    first 8 chars of the stored hash — constant-time, never sharing the key.

    Security model:
    - Only ownerless (or same-owner) devices are claimable; a device owned by
      a REAL other account is 403 (same guard as /api/device/claim).
    - 32 bits of code entropy is safe because attempts are rate-limited per
      user (10 / 10 min) and the code only exists on the physical phone.
    - The per-user device limit still applies (claiming is a NEW link).
    - Admin (dashboard/API-key) sessions can claim too — same ownership guard,
      no limit for the operator, which lets support re-link a lost device.
    """
    # Rate-limit attempts per actor so the 32-bit code can't be brute-forced
    # from the dashboard (a wrong guess is cheap for the caller, not the DB).
    if not check_rate_limit(f"claim_pairing:{auth}", "claim_pairing", 10, 10):
        raise HTTPException(status_code=429, detail="Too many claim attempts — try again shortly")

    user_id = _resolve_user_id(auth)

    # Account-linking is a USER action. Admin (dashboard/API-key) sessions can
    # already see every device — there is nothing for them to claim, and an
    # "admin claim" would just set owner_id=NULL (a no-op). Mirroring
    # /api/device/claim's contract, admin sessions are rejected here.
    if user_id is None:
        raise HTTPException(status_code=403, detail="User authentication required")

    # A stale token from a permanently deleted account must not claim devices
    # (that would re-create a ghost link — same bug class as register/claim).
    if not _user_exists(db, user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")

    device = db.execute("SELECT id, owner_id, device_key_hash FROM devices WHERE id=?", (req.device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Constant-time pairing-code check against the first 8 hex chars of the
    # stored SHA-256 of the device key. A device with no key hash (e.g. an old
    # build registered via API key only) has no pairing code — 403.
    stored_hash = device["device_key_hash"] or ""
    if len(stored_hash) < 8 or not hmac.compare_digest(req.pairing_code, stored_hash[:8]):
        raise HTTPException(status_code=403, detail="Invalid pairing code")

    existing_owner = device["owner_id"]
    # Same guard as /api/device/claim: only block when the existing owner is a
    # REAL account that isn't the caller. Ghost-owned (deleted account) rows
    # stay claimable; same-owner re-claims stay idempotent.
    if existing_owner and existing_owner != user_id and _user_exists(db, existing_owner):
        raise HTTPException(status_code=403, detail="Device already linked to another account")

    if existing_owner != user_id:
        from routes.devices import _enforce_device_limit

        _enforce_device_limit(db, user_id)

    db.execute("UPDATE devices SET owner_id=? WHERE id=?", (user_id, req.device_id))
    db.commit()

    from websocket_manager import update_device_owner

    update_device_owner(req.device_id, user_id)
    log_audit("device_claimed_by_pairing", actor=auth, details=f"Device: {req.device_id}")

    return {"status": "ok", "device_id": req.device_id, "owner_id": user_id}


@router.patch("/api/dashboard/devices/{device_id}/alias")
async def update_device_alias(
    device_id: str,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Update device alias/name."""
    _assert_device_access(db, device_id, auth)
    alias = body.get("alias", "").strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Alias is required")

    db.execute("UPDATE devices SET alias=? WHERE id=?", (alias, device_id))
    db.commit()
    log_audit(
        "device_alias_updated",
        actor=auth,
        details=f"Device: {device_id}, Alias: {alias}",
    )

    return {"status": "ok", "alias": alias}


@router.patch("/api/dashboard/devices/{device_id}/alert-settings")
async def update_device_alert_settings(
    device_id: str,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Set per-device alert preferences (recipients, channels, enabled types,
    quiet hours). Empty string/None clears the override to global defaults."""
    _assert_device_access(db, device_id, auth)
    device = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    import json as _json

    from alerts import ALL_ALERT_TYPES, ALL_CHANNELS

    alert_phone = (body.get("alert_phone") or "").strip()
    alert_email = (body.get("alert_email") or "").strip()

    # Validate phone if provided — must be E.164-like (start with +) or empty.
    if alert_phone and not alert_phone.startswith("+"):
        raise HTTPException(
            status_code=400,
            detail="Alert phone must be in E.164 format starting with '+'",
        )
    if alert_email and "@" not in alert_email:
        raise HTTPException(status_code=400, detail="Invalid alert email address")

    # Channels: optional list from ALL_CHANNELS; None/empty clears to all.
    alert_channels_raw = body.get("alert_channels")
    alert_channels = None
    if alert_channels_raw is not None:
        if not isinstance(alert_channels_raw, list):
            raise HTTPException(status_code=400, detail="alert_channels must be a list")
        invalid = set(alert_channels_raw) - set(ALL_CHANNELS)
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid channels: {sorted(invalid)}")
        alert_channels = _json.dumps(list(dict.fromkeys(alert_channels_raw))) if alert_channels_raw else None

    # Enabled types: optional list from ALL_ALERT_TYPES; None/empty clears to all.
    enabled_raw = body.get("enabled_types")
    enabled_types = None
    if enabled_raw is not None:
        if not isinstance(enabled_raw, list):
            raise HTTPException(status_code=400, detail="enabled_types must be a list")
        invalid = set(enabled_raw) - set(ALL_ALERT_TYPES)
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid alert types: {sorted(invalid)}")
        enabled_types = _json.dumps(list(dict.fromkeys(enabled_raw))) if enabled_raw else None

    # Quiet hours: optional ints 0-23; None clears. Booleans are excluded
    # (True is an int subclass in Python and would pass isinstance()). A
    # one-sided window is meaningless — [start, end) is empty — so a partial
    # pair is normalized to "off" (both None) rather than stored inert.
    quiet_start = body.get("quiet_hours_start")
    quiet_end = body.get("quiet_hours_end")
    if quiet_start is not None and not (
        isinstance(quiet_start, int) and not isinstance(quiet_start, bool) and 0 <= quiet_start <= 23
    ):
        raise HTTPException(status_code=400, detail="quiet_hours_start must be an hour 0-23")
    if quiet_end is not None and not (
        isinstance(quiet_end, int) and not isinstance(quiet_end, bool) and 0 <= quiet_end <= 23
    ):
        raise HTTPException(status_code=400, detail="quiet_hours_end must be an hour 0-23")
    if quiet_start is None or quiet_end is None:
        quiet_start = quiet_end = None

    db.execute(
        """UPDATE devices SET alert_phone=?, alert_email=?, alert_channels=?, enabled_types=?,
           quiet_hours_start=?, quiet_hours_end=? WHERE id=?""",
        (
            alert_phone,
            alert_email,
            alert_channels,
            enabled_types,
            quiet_start,
            quiet_end,
            device_id,
        ),
    )
    db.commit()

    log_audit(
        "device_alert_settings_updated",
        actor=auth,
        details=(
            f"Device: {device_id}, phone_set={'yes' if alert_phone else 'no'}, "
            f"email_set={'yes' if alert_email else 'no'}, "
            f"channels={alert_channels or 'all'}, types={enabled_types or 'all'}, "
            f"quiet={quiet_start is not None and f'{quiet_start}-{quiet_end}' or 'off'}"
        ),
    )

    return {
        "status": "ok",
        "alert_phone": alert_phone,
        "alert_email": alert_email,
        "alert_channels": _json.loads(alert_channels) if alert_channels else None,
        "enabled_types": _json.loads(enabled_types) if enabled_types else None,
        "quiet_hours_start": quiet_start,
        "quiet_hours_end": quiet_end,
    }


@router.delete("/api/dashboard/devices/{device_id}")
async def delete_device(
    device_id: str,
    body: dict = None,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Permanently delete a device and all of its data (locations, media,
    evidence, commands, alerts, guardian recovery requests, FCM tokens),
    gated by a STEP-UP PASSWORD (account password for users, master API key
    for the admin dashboard).

    This is the permanent-deletion path promised in the privacy policy:
    once deleted, the device and its history cannot be recovered. A stolen
    dashboard session alone must not be able to destroy a device's history,
    so the caller re-authenticates (see _verify_stepup_password).
    """
    _assert_device_access(db, device_id, auth)
    row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    _verify_stepup_password(db, auth, (body or {}).get("password"))

    delete_device_cascade(db, device_id)
    db.commit()

    # Clear the WebSocket owner cache so stale broadcasts don't leak.
    from websocket_manager import update_device_owner

    update_device_owner(device_id, None)

    log_audit("device_deleted", actor=auth, details=f"Device: {device_id} (permanent)")
    return {"status": "ok", "message": f"Device {device_id} permanently deleted"}


@router.post("/api/dashboard/devices/{device_id}/recover")
async def mark_device_recovered(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Mark a stolen device as recovered."""
    _assert_device_access(db, device_id, auth)
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "UPDATE devices SET is_stolen=0, operating_mode='normal', sentinel_score=0 WHERE id=?",
        (device_id,),
    )
    db.execute(
        "UPDATE evidence_cases SET status='closed' WHERE device_id=? AND status='active'",
        (device_id,),
    )
    db.commit()

    log_audit("device_recovered", actor=auth, details=f"Device: {device_id}")

    return {"status": "ok", "message": "Device marked as recovered", "timestamp": now}


@router.get("/api/dashboard/devices/{device_id}/history")
async def get_device_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get full device information including command and event history."""
    _assert_device_access(db, device_id, auth)
    device = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    location = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    cmd_stats = db.execute(
        "SELECT status, COUNT(*) as count FROM commands WHERE device_id=? GROUP BY status",
        (device_id,),
    ).fetchall()

    alert_count = db.execute("SELECT COUNT(*) as count FROM alerts WHERE device_id=?", (device_id,)).fetchone()[0]

    evidence = db.execute(
        "SELECT * FROM evidence_cases WHERE device_id=? ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    return {
        "device": dict(device),
        "latest_location": dict(location) if location else None,
        "command_stats": {r["status"]: r["count"] for r in cmd_stats},
        "total_alerts": alert_count,
        "active_evidence": dict(evidence) if evidence else None,
    }


# ─── Locations ───────────────────────────────────────────────────────────────


@router.get("/api/dashboard/locations/{device_id}")
async def get_locations(
    device_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get location history for a device."""
    _assert_device_access(db, device_id, auth)
    rows = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()

    return {"locations": [dict(r) for r in rows]}


@router.get("/api/dashboard/locations/{device_id}/live")
async def get_live_location(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get latest location for a device."""
    _assert_device_access(db, device_id, auth)
    row = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    return {"location": dict(row) if row else None}


@router.get("/api/dashboard/replay/{device_id}")
async def get_replay_data(
    device_id: str,
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get location data for trail replay."""
    _assert_device_access(db, device_id, auth)
    query = "SELECT * FROM locations WHERE device_id=?"
    params = [device_id]

    if from_time:
        query += " AND server_timestamp >= ?"
        params.append(from_time)
    if to_time:
        query += " AND server_timestamp <= ?"
        params.append(to_time)

    query += " ORDER BY server_timestamp ASC"

    rows = db.execute(query, params).fetchall()
    return {"locations": [dict(r) for r in rows]}


# ─── Media ───────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/media/{device_id}")
async def get_media_list(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get media list (thumbnails) for a device."""
    _assert_device_access(db, device_id, auth)
    rows = db.execute(
        "SELECT id, device_id, type, timestamp, lat, lng FROM media WHERE device_id=? ORDER BY timestamp DESC",
        (device_id,),
    ).fetchall()

    return {"media": [dict(r) for r in rows]}


@router.get("/api/dashboard/media/file/{media_id}")
async def get_media_file(
    media_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get full media file with data."""
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    _assert_device_access(db, row["device_id"], auth)

    return {
        "id": row["id"],
        "type": row["type"],
        "data_b64": row["data_b64"],
        "timestamp": row["timestamp"],
        "lat": row["lat"],
        "lng": row["lng"],
        "sha256_hash": row["sha256_hash"],
    }


@router.post("/api/dashboard/media/{media_id}/delete")
async def delete_media(
    media_id: int,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Delete a media item, gated by a step-up password.

    Destructive and privacy-sensitive, so the caller must re-authenticate with
    their account password (user mode) or the master API key (admin mode) — a
    stolen dashboard session alone is NOT enough to destroy evidence. Attempts
    are rate-limited per actor and audit-logged.
    """
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    _assert_device_access(db, row["device_id"], auth)

    _verify_stepup_password(db, auth, body.get("password"))

    # Remove the media row, then fix up the evidence-case counters it
    # contributed (a deleted item must not leave stale counts).
    if row["evidence_case_id"]:
        db.execute(
            """UPDATE evidence_cases
               SET photo_count = MAX(0, photo_count - ?),
                   audio_count = MAX(0, audio_count - ?)
               WHERE id=?""",
            (
                1 if row["type"] == "photo" else 0,
                1 if row["type"] == "audio" else 0,
                row["evidence_case_id"],
            ),
        )
    db.execute("DELETE FROM media WHERE id=?", (media_id,))
    db.commit()

    log_audit(
        "media_deleted",
        actor=auth,
        details=f"Media: {media_id}, device: {row['device_id']}, type: {row['type']}",
    )

    return {"status": "ok", "deleted_id": media_id}


# ─── Commands (Dashboard Issue) ──────────────────────────────────────────────


@router.post("/api/dashboard/command")
async def issue_command(
    cmd: CommandRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Issue a command to a device."""
    _assert_device_access(db, cmd.device_id, auth)
    if not check_command_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    if cmd.command == "wipe":
        if cmd.params != "CONFIRMED_WIPE":
            raise HTTPException(status_code=400, detail="Wipe requires params='CONFIRMED_WIPE'")

    # Unacknowledged commands auto-expire: 5 minutes for sensitive ones
    # (wipe/lock/alarm), 30 minutes for everything else — a stale PENDING
    # must never linger on the dashboard or execute long after the operator
    # gave up on it.
    expires_minutes = 5 if cmd.command in ("wipe", "lock", "alarm") else 30
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()

    cur = db.execute(
        "INSERT INTO commands (device_id, command, params, priority, issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (cmd.device_id, cmd.command, cmd.params, cmd.priority, now, expires_at),
    )
    db.commit()

    command_id = cur.lastrowid
    log_audit(
        "command_issued",
        actor=auth,
        details=f"Command: {cmd.command} to {cmd.device_id}",
    )

    return {"status": "queued", "command_id": command_id}


@router.get("/api/dashboard/commands/{device_id}")
async def get_command_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get command history for a device."""
    _assert_device_access(db, device_id, auth)

    # Commands never acknowledged within their expiry window are marked
    # 'expired' so the operator sees EXPIRED (grey) instead of a stale PENDING
    # that misleads. datetime() normalizes both the ISO-8601 and SQLite-space
    # formats the DB has accumulated; the device-side poll uses the same
    # normalization so expired commands are never delivered.
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
    """Delete a single command from history, gated by a step-up password.

    Commands are an audit trail (they can include wipe/lock/alarm), so a
    dashboard session alone must not erase them — the caller re-authenticates
    with the step-up password (account password for users, master API key for
    admins), the same contract as media/device deletion. Ownership is checked
    BEFORE the password so a non-owner never reaches the verify step.
    """
    row = db.execute("SELECT device_id FROM commands WHERE id=?", (command_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Command not found")
    _assert_device_access(db, row["device_id"], auth)

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
    """Delete command history for a device, gated by a step-up password.

    only_finished=true (default) removes executed/failed/expired commands
    while KEEPING pending ones — an in-flight wipe/lock/alarm must never be
    erased mid-delivery. only_finished=false clears the entire history
    (including pending, which effectively cancels queued commands).
    """
    _assert_device_access(db, device_id, auth)

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


# ─── Evidence ────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/evidence/{device_id}")
async def get_evidence(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get evidence case for a device."""
    _assert_device_access(db, device_id, auth)
    case = db.execute(
        "SELECT * FROM evidence_cases WHERE device_id=? ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    if not case:
        return {"case_id": None, "status": "none"}

    return {
        "case_id": case["id"],
        "status": case["status"],
        "item_counts": {
            "locations": case["location_count"],
            "photos": case["photo_count"],
            "audio": case["audio_count"],
        },
        "sha256_chain": case["sha256_chain"],
        "created_at": case["created_at"],
        "theft_time": case["theft_time"],
    }


@router.post("/api/dashboard/evidence/{device_id}/generate-pdf")
async def generate_evidence_pdf(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Generate a forensic PDF evidence report for a device."""
    _assert_device_access(db, device_id, auth)
    from fastapi.responses import Response

    case = db.execute(
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    if not case:
        case_id = evidence_builder.create_case(device_id)
    else:
        case_id = case["id"]

    # Generate actual PDF using ReportLab
    from evidence_pdf import generate_evidence_pdf as generate_pdf

    pdf_bytes = generate_pdf(case_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="No evidence data found")

    # Mark case as PDF-generated
    db.execute("UPDATE evidence_cases SET pdf_generated=1 WHERE id=?", (case_id,))
    db.commit()

    log_audit(
        "evidence_pdf_generated",
        actor=auth,
        details=f"Case: {case_id}, Device: {device_id}",
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Magneetar-Evidence-{case_id}.pdf"',
        },
    )


# ─── Alerts ──────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/alerts/{device_id}")
async def get_alerts(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get alert history for a device."""
    _assert_device_access(db, device_id, auth)
    rows = db.execute(
        "SELECT * FROM alerts WHERE device_id=? ORDER BY sent_at DESC LIMIT 50",
        (device_id,),
    ).fetchall()

    return {"alerts": [dict(r) for r in rows]}


# ─── Geofences ───────────────────────────────────────────────────────────────


@router.post("/api/dashboard/geofence")
async def create_geofence(
    fence: GeofenceRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Create a geofence for a device."""
    _assert_device_access(db, fence.device_id, auth)
    cur = db.execute(
        (
            "INSERT INTO geofences (device_id, name, center_lat, center_lng, "
            "radius_meters, is_safe_zone) VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            fence.device_id,
            fence.name,
            fence.center_lat,
            fence.center_lng,
            fence.radius_meters,
            fence.is_safe_zone,
        ),
    )
    db.commit()

    return {"status": "ok", "geofence_id": cur.lastrowid}


@router.delete("/api/dashboard/geofence/{geofence_id}")
async def delete_geofence(
    geofence_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Delete a geofence."""
    fence = db.execute("SELECT device_id FROM geofences WHERE id=?", (geofence_id,)).fetchone()
    if fence:
        _assert_device_access(db, fence["device_id"], auth)
    db.execute("DELETE FROM geofences WHERE id=?", (geofence_id,))
    db.commit()
    return {"status": "ok"}


@router.get("/api/dashboard/geofences/{device_id}")
async def list_geofences(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """List geofences for a device."""
    _assert_device_access(db, device_id, auth)
    rows = db.execute("SELECT * FROM geofences WHERE device_id=? AND active=1", (device_id,)).fetchall()

    return {"geofences": [dict(r) for r in rows]}


# ─── Stats ───────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/stats")
async def get_stats(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get dashboard statistics. Users see stats scoped to their own devices.

    NOTE: this endpoint reads the SAME SQLite data plane as every other
    endpoint. The previous PostgreSQL branch was removed — in the Docker
    deployment MT_DATABASE_URL points at a Postgres that sits EMPTY while the
    live data plane is SQLite (/app/data/magneetar.db), so the counters read
    0/0/0 even with registered devices.

    Timestamps are normalized with datetime() because the DB has accumulated
    both ISO-8601 ("2026-08-01T20:34:00.123456+00:00") and SQLite-space
    ("2026-08-01 20:34:00") formats — a raw string comparison is wrong ('T'
    sorts after ' ', so ISO timestamps always appear newer).
    """
    user_id = _resolve_user_id(auth)

    if user_id:
        total_devices = db.execute("SELECT COUNT(*) FROM devices WHERE owner_id=?", (user_id,)).fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE owner_id=? AND datetime(last_seen) > datetime('now', '-5 minutes')",
            (user_id,),
        ).fetchone()[0]
        stolen_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE is_stolen=1 AND owner_id=?", (user_id,)
        ).fetchone()[0]
        total_locations = db.execute(
            "SELECT COUNT(*) FROM locations l JOIN devices d ON l.device_id=d.id WHERE d.owner_id=?",
            (user_id,),
        ).fetchone()[0]
        total_media = db.execute(
            "SELECT COUNT(*) FROM media m JOIN devices d ON m.device_id=d.id WHERE d.owner_id=?",
            (user_id,),
        ).fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = db.execute(
            "SELECT COUNT(*) FROM alerts a JOIN devices d ON a.device_id=d.id WHERE d.owner_id=? AND a.sent_at > ?",
            (user_id, today),
        ).fetchone()[0]
    else:
        total_devices = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE datetime(last_seen) > datetime('now', '-5 minutes')"
        ).fetchone()[0]
        stolen_devices = db.execute("SELECT COUNT(*) FROM devices WHERE is_stolen=1").fetchone()[0]
        total_locations = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        total_media = db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = db.execute("SELECT COUNT(*) FROM alerts WHERE sent_at > ?", (today,)).fetchone()[0]

    return {
        "total_devices": total_devices,
        "active_devices": active_devices,
        "stolen_devices": stolen_devices,
        "recovered_devices": 0,
        "total_locations": total_locations,
        "total_media": total_media,
        "alerts_today": alerts_today,
    }


# ─── Error Log ──────────────────────────────────────────────────────────────


@router.get("/api/dashboard/errors")
async def list_errors(
    limit: int = Query(50, ge=1, le=500),
    unresolved_only: bool = Query(False),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """List server errors with optional filter for unresolved only. Admin-only."""
    if _resolve_user_id(auth) is not None:
        raise HTTPException(status_code=403, detail="Admin access required")
    if unresolved_only:
        rows = db.execute(
            "SELECT * FROM error_log WHERE resolved=0 ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM error_log ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()

    count_row = db.execute("SELECT COUNT(*) as cnt FROM error_log WHERE resolved=0").fetchone()

    return {
        "errors": [dict(r) for r in rows],
        "unresolved_count": count_row["cnt"] if count_row else 0,
        "total_count": db.execute("SELECT COUNT(*) FROM error_log").fetchone()[0],
    }


@router.patch("/api/dashboard/errors/{error_id}/resolve")
async def resolve_error(
    error_id: int,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Mark an error as resolved. Admin-only."""
    if _resolve_user_id(auth) is not None:
        raise HTTPException(status_code=403, detail="Admin access required")
    now = datetime.now(timezone.utc).isoformat()
    notes = body.get("notes", "")

    db.execute(
        "UPDATE error_log SET resolved=1, resolved_at=?, resolved_by=?, notes=? WHERE id=?",
        (now, auth, notes, error_id),
    )
    db.commit()

    log_audit("error_resolved", actor=auth, details=f"Error #{error_id}: {notes}")

    return {"status": "ok", "message": f"Error #{error_id} marked as resolved"}
