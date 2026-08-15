"""
Magneetar Dashboard-Facing API Routes
All endpoints for the web dashboard (devices, locations, commands, evidence, etc.)
"""

import base64
import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from auth import (
    check_command_rate_limit,
    check_login_rate_limit,
    check_password_verify_rate_limit,
    create_dashboard_tokens,
    refresh_access_token,
    require_dashboard_auth,
    user_id_from_subject,
    verify_password,
)
from config import settings
from database import check_rate_limit, delete_device_cascade, get_db, get_db_context, log_audit
from encryption import decrypt_location, decrypt_location_row
from evidence import evidence_builder

# Imported at MODULE level (not inside the route): under full-suite collection
# test_e2e evicts modules from sys.modules; a function-local `from evidence_pdf
# import ...` would resolve the post-eviction module at request time, whose
# evidence_builder binds a different database module than this router's — the
# PDF then compiles from a different DB than create_case wrote to (404
# 'No evidence data found' / FK failures). Same pattern as the FCM tests.
from evidence_pdf import generate_evidence_pdf as _generate_evidence_pdf_doc
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from logging_config import get_logger
from models import (
    CommandRequest,
    DeviceClaimByPairingRequest,
    GeofenceRequest,
    LoginRequest,
    RefreshRequest,
    ShareRequest,
    TokenResponse,
)

# Shared device helpers live in routes/devices.py; importing them here is
# cycle-safe (devices.py never imports routes/dashboard). Module-level (NOT
# function-local) on purpose: test_e2e/test_sim_change evict routes.* from
# sys.modules at import time, and a function-local import would resolve the
# post-eviction module at request time — whose `settings` is a fresh config
# singleton, so monkeypatched limits (e.g. MAX_DEVICES_PER_USER) and other
# config mutations would silently not apply (order-dependent flakes).
from routes.devices import _enforce_device_limit, _user_exists  # noqa: E402

logger = get_logger("magneetar")

router = APIRouter()

# ─── Live-location quality gate ─────────────────────────────────────────────
# The device reports a fix every ~3s. When GPS is unavailable (indoors,
# pocket, car), Android falls back to cell-tower fixes whose accuracy is
# 200-700m — and the cell centroid can be KILOMETRES from the true position.
# The dashboard's live pin used to be the newest fix regardless of quality,
# so a degraded fix landing right after a good GPS fix teleported the map to
# a misleading location (G1 field finding 2026-08-15: pin jumped 3.5km to a
# cell centroid while the device sat still).
#
# Rule: the live position is the most recent fix that is GOOD — HIGH/MEDIUM
# confidence or <100m accuracy — within a freshness window. A degraded fix
# only takes over after the window expires (so a genuinely moving device in
# a GPS-denied area still advances, just with an honest accuracy circle).
# The window ALSO bounds how far back we'll resurrect a stale good fix: a
# 3-hour-old GPS fix is not where the device is anymore.
LIVE_FIX_GOOD_ACCURACY_M = 100
LIVE_FIX_FRESH_WINDOW_MINUTES = 15

LIVE_FIX_ORDER_SQL = f"""
    CASE WHEN (confidence_level IN ('HIGH','MEDIUM')
               OR (accuracy_horizontal IS NOT NULL AND accuracy_horizontal < {LIVE_FIX_GOOD_ACCURACY_M}))
               AND julianday(server_timestamp) >= julianday('now', '-{LIVE_FIX_FRESH_WINDOW_MINUTES} minutes')
          THEN 0 ELSE 1 END,
    server_timestamp DESC
"""


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


# ─── Device Sharing / RBAC (roadmap Milestone 2 P1) ─────────────────────────
# Role hierarchy: owner > admin > viewer > device_only. Shares only ever grant
# admin/viewer/device_only — "owner" is implicit (the account the device is
# linked to). device_only is a privacy tier: status glance only, no location,
# evidence, or command access. Operator/dashboard (admin) sessions rank as
# owner so the existing admin surface keeps working unchanged.
ROLE_RANK = {"device_only": 0, "viewer": 1, "admin": 2, "owner": 3}


def _resolve_device_role(db, device_id: str, auth: str) -> Optional[str]:
    """Return the caller's effective role for a device, or None if they have
    no access at all.

    Existence is verified for EVERY scope BEFORE the admin shortcut: a
    nonexistent device must resolve to None so _assert_device_access can 404
    cleanly (the admin branch returning 'owner' first would let admin-scope
    writes blow up on downstream FK constraints instead of 404ing)."""
    row = db.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return None
    user_id = _resolve_user_id(auth)
    if user_id is None:
        return "owner"  # operator/dashboard session — full access
    if row["owner_id"] == user_id:
        return "owner"
    share = db.execute(
        "SELECT role FROM device_shares WHERE device_id=? AND grantee_user_id=?",
        (device_id, user_id),
    ).fetchone()
    return share["role"] if share else None


def _assert_device_access(db, device_id: str, auth: str, min_role: str = "device_only"):
    """Verify the caller can access a device at or above min_role.

    Roles: owner > admin > viewer > device_only (see _resolve_device_role).
    Existence is verified for EVERY scope: a nonexistent device must be a
    clean 404, never a 500 from a downstream FOREIGN KEY constraint (the
    admin scope historically skipped the existence check, so admin-scope
    writes like command/geofence blew up with an unhandled IntegrityError).
    min_role semantics:
      device_only — status-level visibility (default; any access grants it)
      viewer      — full read access (locations, media, evidence)
      admin       — control (commands, geofences, alert/sms settings)
      owner       — destructive/management actions (delete, share grant/revoke)
    Returns the caller's role so endpoints can branch on it (e.g. hide
    device_only users' coordinates in the device list).
    """
    role = _resolve_device_role(db, device_id, auth)
    if role is None:
        row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        raise HTTPException(status_code=403, detail="Access denied: device not linked to your account")
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: the '{role}' role cannot perform this action",
        )
    return role


def _verify_stepup_password(db, auth: str, raw_password) -> None:
    """Re-authenticate a destructive action with a step-up password.

    Destructive, privacy-sensitive actions (media/device deletion) must not
    succeed on a stolen dashboard session alone — the caller re-authenticates
    with their account password (user mode) or the master API key itself
    (admin mode). Attempts are rate-limited per actor; raises HTTPException
    (400 missing / 401 wrong / 429 throttled).

    NOTE: check_password_verify_rate_limit / verify_password are imported at
    MODULE level, never inside this function — under full-suite collection
    test_e2e evicts auth/database from sys.modules, so a function-local
    import would resolve the post-eviction chain (different DB_PATH) and the
    step-up bucket would be written to a different DB than the one the test
    fixtures clear (sporadic 429s under full-suite runs only).
    """
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
    """List devices with latest location. Users see their own devices PLUS
    devices shared with them (each tagged with the caller's access_role:
    owner/admin/viewer/device_only — see _resolve_device_role)."""
    user_id = _resolve_user_id(auth)
    # location_encrypted/location_data ride along so each device's last fix
    # can be decrypted below (v1.5 at-rest encryption — encrypted rows carry
    # 0.0 placeholders in lat/lng). access_role/is_owner tag the caller's
    # grant per row (device_shares LEFT JOIN — the COALESCE only kicks in for
    # the owner's own rows where ds is NULL).
    # The device's "latest" fix is the most recent GOOD fix (HIGH/MEDIUM
    # confidence or <100m accuracy) within the staleness window, falling back
    # to the newest fix — see LIVE_FIX_ORDER_SQL. Without this, a degraded
    # cell-tower fix (200-700m, sometimes km off) landing right after a good
    # GPS fix teleported the sidebar/map to a misleading position (G1
    # finding 2026-08-15: pin jumped 3.5km to a cell centroid).
    if user_id:
        devices = db.execute(
            f"""SELECT d.*,
                      l.lat, l.lng, l.location_encrypted, l.location_data,
                      l.battery_percent, l.sentinel_score, l.threat_level,
                      CASE WHEN d.owner_id = ? THEN 'owner'
                           ELSE COALESCE(ds.role, 'viewer') END AS access_role,
                      (d.owner_id = ?) AS is_owner
               FROM devices d
               LEFT JOIN device_shares ds
                      ON ds.device_id = d.id AND ds.grantee_user_id = ?
               LEFT JOIN locations l ON d.id = l.device_id
                   AND l.id = (SELECT id FROM locations WHERE device_id = d.id
                               ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1)
               WHERE d.owner_id = ? OR ds.grantee_user_id IS NOT NULL
               ORDER BY d.last_seen DESC""",
            (user_id, user_id, user_id, user_id),
        ).fetchall()
    else:
        devices = db.execute(
            f"""SELECT d.*,
                      l.lat, l.lng, l.location_encrypted, l.location_data,
                      l.battery_percent, l.sentinel_score, l.threat_level,
                      'owner' AS access_role,
                      1 AS is_owner
               FROM devices d
               LEFT JOIN locations l ON d.id = l.device_id
                   AND l.id = (SELECT id FROM locations WHERE device_id = d.id
                               ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1)
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
        # At-rest encryption: decrypt the last fix (encrypted rows carry 0.0
        # placeholders in lat/lng; plaintext legacy rows pass through).
        lat, lng = decrypt_location(
            d["lat"],
            d["lng"],
            bool(d["location_encrypted"]),
            d["location_data"],
            d["id"],
        )
        access_role = d["access_role"] if "access_role" in d.keys() else "owner"
        is_owner = bool(d["is_owner"]) if "is_owner" in d.keys() else True
        if access_role == "device_only":
            # Privacy tier: status glance only — strip coordinates and PII
            # (alert recipients, SMS relay number) before anything leaves.
            lat, lng = None, None

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
                "lat": lat,
                "lng": lng,
                "battery_percent": d["battery_percent"],
                "location_encrypted": bool(d["location_encrypted"]),
                "is_online": is_online,
                # Milestone 2 P1 RBAC: how the caller may use this device
                # (owner/admin/viewer/device_only) + whether they own it.
                "access_role": access_role,
                "is_owner": is_owner,
                "capture_armed": (
                    bool(d["capture_armed"]) if "capture_armed" in d.keys() and d["capture_armed"] is not None else None
                ),
                "archived_at": d["archived_at"] if "archived_at" in d.keys() else None,
                "alert_phone": (
                    d["alert_phone"] if "alert_phone" in d.keys() and access_role != "device_only" else None
                ),
                "alert_email": (
                    d["alert_email"] if "alert_email" in d.keys() and access_role != "device_only" else None
                ),
                # Per-device prefs stored as JSON TEXT — parse for the client;
                # NULL (no override) stays None so the UI shows global defaults.
                "alert_channels": (
                    _parse_json_list(d["alert_channels"])
                    if "alert_channels" in d.keys() and access_role != "device_only"
                    else None
                ),
                "enabled_types": (
                    _parse_json_list(d["enabled_types"])
                    if "enabled_types" in d.keys() and access_role != "device_only"
                    else None
                ),
                "quiet_hours_start": (
                    _parse_int(d["quiet_hours_start"])
                    if "quiet_hours_start" in d.keys() and access_role != "device_only"
                    else None
                ),
                "quiet_hours_end": (
                    _parse_int(d["quiet_hours_end"])
                    if "quiet_hours_end" in d.keys() and access_role != "device_only"
                    else None
                ),
                # Offline Command Relay (SMS) — the number commands are SMSed to
                # when the device is offline, and the opt-in toggle.
                "sms_phone": (d["sms_phone"] if "sms_phone" in d.keys() and access_role != "device_only" else None),
                "sms_commands_enabled": (
                    bool(d["sms_commands_enabled"]) if "sms_commands_enabled" in d.keys() else False
                ),
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
    _assert_device_access(db, device_id, auth, min_role="admin")
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
    _assert_device_access(db, device_id, auth, min_role="admin")
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


@router.patch("/api/dashboard/devices/{device_id}/sms-settings")
async def update_device_sms_settings(
    device_id: str,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Configure the Offline Command Relay for a device.

    When a device is OFFLINE (no data), the dashboard can still reach it by
    SMS: the server texts the command to the phone's SIM number and the app
    executes it locally. This endpoint sets the recipient number (E.164) and
    the opt-in toggle.

    Security & cost:
    - The owner must EXPLICITLY enable SMS commands (Twilio costs money per
      message, and an SMS command is a real attack surface). The toggle
      defaults to OFF.
    - The phone number must be E.164 (starts with '+') so Twilio/Termii can
      route it; empty string clears the number (disables the relay).
    - The Android app reports its SIM number best-effort; the server prefills
      sms_phone on registration only when it is still NULL so an owner-set
      value is never overwritten.
    """
    _assert_device_access(db, device_id, auth, min_role="admin")
    row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    sms_phone = (body.get("sms_phone") or "").strip()
    enabled = bool(body.get("sms_commands_enabled", False))

    if sms_phone and not sms_phone.startswith("+"):
        raise HTTPException(
            status_code=400,
            detail="SMS phone must be in E.164 format starting with '+'",
        )
    if enabled and not sms_phone:
        raise HTTPException(
            status_code=400,
            detail="Enable Offline SMS commands requires a phone number (E.164, e.g. +2348081234567)",
        )

    db.execute(
        "UPDATE devices SET sms_phone=?, sms_commands_enabled=? WHERE id=?",
        (sms_phone or None, 1 if enabled else 0, device_id),
    )
    db.commit()
    log_audit(
        "device_sms_settings_updated",
        actor=auth,
        details=f"Device: {device_id}, sms_commands_enabled={enabled}, sms_phone={'set' if sms_phone else 'cleared'}",
    )
    return {
        "status": "ok",
        "sms_phone": sms_phone or None,
        "sms_commands_enabled": enabled,
    }


@router.post("/api/dashboard/cell-locate")
async def resolve_cell_location(
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Resolve a cell-tower fingerprint to approximate coordinates.

    The offline command relay captures the device's surrounding cell towers
    (MCC/MNC/TAC/CID) — which works with ZERO internet — and this endpoint
    turns that fingerprint into a coarse position (~50-200m in cities) using
    a pluggable provider (Unwired Labs when MT_CELL_LOOKUP_API_KEY is set).
    Results are cached in cell_location_cache so a fingerprint is looked up
    at most once.

    Graceful degradation: an unconfigured provider (or a fingerprint the
    provider can't resolve) returns {"resolved": false} with the fingerprint
    echoed — the caller still stores the raw fingerprint for a future lookup.

    Body: {"cell_tower_ids": ["lte:621:20:30544:123456", ...]}
    """
    tower_ids = body.get("cell_tower_ids") or []
    if not isinstance(tower_ids, list) or not tower_ids:
        raise HTTPException(status_code=400, detail="cell_tower_ids must be a non-empty list")
    if not all(isinstance(t, str) and ":" in t for t in tower_ids):
        raise HTTPException(status_code=400, detail="Each tower id must be 'type:mcc:mnc:tac:cid'")

    fingerprint = ",".join(sorted(set(tower_ids)))

    # 1) Cache hit — a fingerprint resolves to the same place every time.
    cached = db.execute(
        "SELECT lat, lng, accuracy_meters, provider FROM cell_location_cache WHERE fingerprint=?",
        (fingerprint,),
    ).fetchone()
    if cached:
        return {
            "resolved": True,
            "lat": cached["lat"],
            "lng": cached["lng"],
            "accuracy_meters": cached["accuracy_meters"],
            "provider": cached["provider"],
            "cached": True,
        }

    # 2) Provider not configured — degrade gracefully, never fail the caller.
    if not settings.CELL_LOOKUP_API_KEY:
        return {
            "resolved": False,
            "reason": "no_provider_configured",
            "cell_tower_ids": tower_ids,
        }

    # 3) Ask the provider (Unwired Labs format).
    import httpx

    parsed = []
    for t in tower_ids:
        parts = t.split(":")
        if len(parts) < 5:
            continue
        tower_type, mcc, mnc, tac, cid = (
            parts[0],
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
            int(parts[4]),
        )
        key = {"lte": "lte", "gsm": "gsm", "wcdma": "wcdma", "nr": "nr"}.get(tower_type, "lte")
        entry = {"radio": key, "mcc": mcc, "mnc": mnc, "lac": tac, "cid": cid}
        if tower_type in ("lte", "nr"):
            entry["tac"] = tac
        parsed.append(entry)
    if not parsed:
        return {
            "resolved": False,
            "reason": "unparseable_fingerprint",
            "cell_tower_ids": tower_ids,
        }

    try:
        with httpx.Client(timeout=8) as client:
            resp = client.post(
                settings.CELL_LOOKUP_URL,
                json={"token": settings.CELL_LOOKUP_API_KEY, "cells": parsed},
            )
            data = resp.json()
        if data.get("status") == "ok" and data.get("lat") is not None and data.get("lon") is not None:
            lat, lng = float(data["lat"]), float(data["lon"])
            accuracy = data.get("accuracy")
            db.execute(
                "INSERT OR REPLACE INTO cell_location_cache (fingerprint, lat, lng, accuracy_meters, provider) "
                "VALUES (?, ?, ?, ?, ?)",
                (fingerprint, lat, lng, accuracy, "unwiredlabs"),
            )
            db.commit()
            return {
                "resolved": True,
                "lat": lat,
                "lng": lng,
                "accuracy_meters": accuracy,
                "provider": "unwiredlabs",
                "cached": False,
            }
        return {
            "resolved": False,
            "reason": "provider_no_fix",
            "cell_tower_ids": tower_ids,
        }
    except Exception as e:
        logger.warning(f"Cell lookup failed: {e}")
        return {
            "resolved": False,
            "reason": "provider_error",
            "cell_tower_ids": tower_ids,
        }


# NOTE: /archived is a STATIC path and MUST be registered before
# /{device_id} — FastAPI matches routes in registration order, so the
# parameterized route below would otherwise capture "archived" as a
# device_id and 404 instead of bulk-deleting.
@router.delete("/api/dashboard/devices/archived")
async def delete_archived_devices(
    body: dict = None,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Bulk-delete all ARCHIVED (stale) devices, gated by a step-up password.

    Devices silent beyond the archive threshold (MT_ARCHIVE_AFTER_DAYS,
    default 30) are soft-flagged with archived_at and dimmed in the sidebar.
    This endpoint permanently removes every archived device the caller can
    access — users get their own archived devices, admins get all — and
    re-authenticates with the step-up password (account password for users,
    master API key for admins), the same contract as single-device deletion.
    Rate-limited per actor via _verify_stepup_password.
    """
    _verify_stepup_password(db, auth, (body or {}).get("password"))

    user_id = _resolve_user_id(auth)
    if user_id:
        rows = db.execute(
            "SELECT id FROM devices WHERE archived_at IS NOT NULL AND owner_id=?",
            (user_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT id FROM devices WHERE archived_at IS NOT NULL").fetchall()

    deleted = []
    for row in rows:
        device_id = row["id"]
        delete_device_cascade(db, device_id)
        deleted.append(device_id)
        # Clear the WebSocket owner cache so stale broadcasts don't leak.
        from websocket_manager import update_device_owner

        update_device_owner(device_id, None)

    db.commit()
    log_audit(
        "archived_devices_bulk_deleted",
        actor=auth,
        details=f"{len(deleted)} archived device(s): {', '.join(deleted) or 'none'}",
    )

    return {"status": "ok", "deleted": deleted, "count": len(deleted)}


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
    _assert_device_access(db, device_id, auth, min_role="owner")
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
    _assert_device_access(db, device_id, auth, min_role="admin")
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


# ─── Device Sharing (roadmap Milestone 2 P1) ────────────────────────────────
# Grant another account (family member, partner) access to a device. Only the
# device OWNER can grant, change, or revoke shares; grantees are ranked
# admin > viewer > device_only (see _resolve_device_role).


@router.post("/api/dashboard/devices/{device_id}/shares")
async def grant_device_share(
    device_id: str,
    body: ShareRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Grant (or update) another account's access to a device.

    Account OWNERS only — mirroring claim-by-pairing, sharing is a user
    action: an operator (API-key/dashboard) session has no account to share
    FROM, and a grant it creates would carry created_by=None plus skip the
    self-share check. The grantee is found by email; re-inviting the same
    account with a different role upgrades/downgrades the grant in place
    (UNIQUE device_id+grantee, id kept stable so the returned share_id is
    always the row's real id). A grantee is never the owner themselves — you
    cannot "share" a device you own.
    """
    _assert_device_access(db, device_id, auth, min_role="owner")
    owner_id = _resolve_user_id(auth)
    if owner_id is None:
        raise HTTPException(status_code=403, detail="Sharing is a user-account action")

    grantee = db.execute("SELECT id FROM users WHERE email=? AND is_active=1", (body.email,)).fetchone()
    if not grantee:
        raise HTTPException(status_code=404, detail="No account found with that email")
    if grantee["id"] == owner_id:
        raise HTTPException(status_code=400, detail="You already own this device")

    share_id = uuid4().hex
    db.execute(
        """INSERT INTO device_shares (id, device_id, grantee_user_id, role, created_by)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(device_id, grantee_user_id)
           DO UPDATE SET id=excluded.id, role=excluded.role, created_by=excluded.created_by""",
        (share_id, device_id, grantee["id"], body.role, owner_id),
    )
    db.commit()
    log_audit(
        "device_share_granted",
        actor=auth,
        details=f"Device: {device_id}, Grantee: {body.email}, Role: {body.role}",
    )
    return {
        "status": "ok",
        "share_id": share_id,
        "device_id": device_id,
        "grantee_user_id": grantee["id"],
        "role": body.role,
    }


@router.get("/api/dashboard/devices/{device_id}/shares")
async def list_device_shares(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """List who has access to a device and with which role (owner + admins)."""
    _assert_device_access(db, device_id, auth, min_role="admin")
    rows = db.execute(
        """SELECT ds.id, ds.device_id, ds.grantee_user_id, ds.role, ds.created_at,
                  u.email, u.display_name
           FROM device_shares ds
           JOIN users u ON u.id = ds.grantee_user_id
           WHERE ds.device_id = ?
           ORDER BY ds.created_at DESC""",
        (device_id,),
    ).fetchall()
    return {"shares": [dict(r) for r in rows]}


@router.delete("/api/dashboard/devices/{device_id}/shares/{share_id}")
async def revoke_device_share(
    device_id: str,
    share_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Revoke an account's access to a device (account owner only — operator
    sessions have no account, mirroring the grant endpoint)."""
    _assert_device_access(db, device_id, auth, min_role="owner")
    if _resolve_user_id(auth) is None:
        raise HTTPException(status_code=403, detail="Sharing is a user-account action")
    row = db.execute("SELECT id FROM device_shares WHERE id=? AND device_id=?", (share_id, device_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Share not found")
    db.execute("DELETE FROM device_shares WHERE id=?", (share_id,))
    db.commit()
    log_audit(
        "device_share_revoked",
        actor=auth,
        details=f"Device: {device_id}, Share: {share_id}",
    )
    return {"status": "ok", "share_id": share_id}


@router.get("/api/dashboard/devices/{device_id}/history")
async def get_device_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get full device information including command and event history."""
    _assert_device_access(db, device_id, auth, min_role="viewer")
    device = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Quality-gated live fix (same rule as the devices list) — the newest
    # row is often a degraded cell-tower fix that would mislead the caller.
    location = db.execute(
        f"SELECT * FROM locations WHERE device_id=? ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1",
        (device_id,),
    ).fetchone()

    # At-rest encryption: decrypt the latest fix before serializing it.
    # location_data is the raw ciphertext — never ship it to the client.
    latest_location = dict(location) if location else None
    if latest_location:
        latest_location["lat"], latest_location["lng"] = decrypt_location_row(latest_location)
        latest_location.pop("location_data", None)

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
        "latest_location": latest_location,
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
    _assert_device_access(db, device_id, auth, min_role="viewer")
    rows = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()

    # At-rest encryption: decrypt every ping so the map renders real coords.
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
        # location_data is the raw ciphertext — never ship it to the client.
        loc.pop("location_data", None)
        locations.append(loc)
    return {"locations": locations}


@router.get("/api/dashboard/locations/{device_id}/export/csv")
async def export_locations_csv(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
    limit: int = Query(10000, ge=1, le=50000),
):
    """Export a device's location history as CSV (Prey-parity: portable history
    for law-enforcement handover, insurance claims, or local analysis).

    Same ownership gate as every other dashboard endpoint. Timestamps sort
    oldest-first; coordinates are decrypted from the at-rest ciphertext
    before export (encrypted rows carry 0.0 placeholders in lat/lng, and
    shipping those would poison the file). The response carries a UTF-8 BOM
    so Excel opens the file with correct encoding, and an attachment
    Content-Disposition so browsers download rather than render it.

    The endpoint caps at `limit` rows (default 10,000) so a long-lived
    device can't balloon memory on one request.
    """
    import csv as _csv
    import io as _io

    from fastapi.responses import Response

    _assert_device_access(db, device_id, auth, min_role="viewer")
    rows = db.execute(
        "SELECT device_id, server_timestamp, device_timestamp, lat, lng, location_encrypted, location_data, "
        "accuracy_horizontal, altitude, speed, bearing, provider, battery_percent, "
        "threat_level, sentinel_score, was_queued FROM locations "
        "WHERE device_id=? ORDER BY server_timestamp ASC LIMIT ?",
        (device_id, limit),
    ).fetchall()

    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(
        [
            "server_timestamp",
            "device_timestamp",
            "lat",
            "lng",
            "accuracy_m",
            "altitude_m",
            "speed_ms",
            "bearing_deg",
            "provider",
            "battery_percent",
            "threat_level",
            "sentinel_score",
            "was_queued",
        ]
    )
    for r in rows:
        row = dict(r)
        lat, lng = decrypt_location_row(row)
        writer.writerow(
            [
                row["server_timestamp"],
                row.get("device_timestamp"),
                lat,
                lng,
                row.get("accuracy_horizontal"),
                row.get("altitude"),
                row.get("speed"),
                row.get("bearing"),
                row.get("provider"),
                row.get("battery_percent"),
                row.get("threat_level"),
                row.get("sentinel_score"),
                row.get("was_queued"),
            ]
        )

    csv_text = "\ufeff" + buf.getvalue()  # UTF-8 BOM for Excel
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="magneetar-locations-{device_id}.csv"',
        },
    )


@router.get("/api/dashboard/locations/{device_id}/live")
async def get_live_location(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get latest location for a device."""
    _assert_device_access(db, device_id, auth, min_role="viewer")
    # Quality-gated live fix (same rule as the devices list) — see
    # LIVE_FIX_ORDER_SQL. The newest row is often a degraded cell fix that
    # can be kilometres off the true position.
    row = db.execute(
        f"SELECT * FROM locations WHERE device_id=? ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1",
        (device_id,),
    ).fetchone()

    if not row:
        return {"location": None}
    loc = dict(row)
    loc["lat"], loc["lng"] = decrypt_location_row(loc)
    # location_data is the raw ciphertext — never ship it to the client.
    loc.pop("location_data", None)
    return {"location": loc}


@router.get("/api/dashboard/replay/{device_id}")
async def get_replay_data(
    device_id: str,
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get location data for trail replay."""
    _assert_device_access(db, device_id, auth, min_role="viewer")
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
    # At-rest encryption: decrypt each ping for the trail.
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
        # location_data is the raw ciphertext — never ship it to the client.
        loc.pop("location_data", None)
        locations.append(loc)
    return {"locations": locations}


# ─── Media ───────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/media/{device_id}")
async def get_media_list(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get media list (thumbnails) for a device."""
    _assert_device_access(db, device_id, auth, min_role="viewer")
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
    _assert_device_access(db, row["device_id"], auth, min_role="viewer")

    # Media storage refactor (v1.4): bytes live on disk (file_path) for new
    # rows; legacy rows keep base64 in data_b64. Both are served in the same
    # legacy wire format so old dashboard builds keep working unchanged.
    from media_store import media_bytes_for_row

    try:
        data_b64 = base64.b64encode(media_bytes_for_row(row)).decode("ascii")
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Media file missing on server")

    return {
        "id": row["id"],
        "type": row["type"],
        "data_b64": data_b64,
        "timestamp": row["timestamp"],
        "lat": row["lat"],
        "lng": row["lng"],
        "sha256_hash": row["sha256_hash"],
        "file_size": row["file_size"] if "file_size" in row.keys() else None,
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
    _assert_device_access(db, row["device_id"], auth, min_role="admin")

    _verify_stepup_password(db, auth, body.get("password"))

    # Remove the media file from disk alongside the DB row (best-effort).
    from media_store import delete_media_file

    delete_media_file(row["file_path"] if "file_path" in row.keys() else None)

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
    _assert_device_access(db, cmd.device_id, auth, min_role="admin")
    if not check_command_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    if cmd.command == "wipe":
        if cmd.params != "CONFIRMED_WIPE":
            raise HTTPException(status_code=400, detail="Wipe requires params='CONFIRMED_WIPE'")
        # Wipe is a factory reset — the most destructive command on the
        # platform. Like device/media deletion, it re-authenticates with the
        # step-up password (account password for users, master API key for the
        # admin dashboard) so a stolen dashboard session alone can never wipe
        # a device. Ownership is checked above via _assert_device_access.
        _verify_stepup_password(db, auth, cmd.password)

    # ── Offline Command Relay (SMS) ──────────────────────────────────────
    # When the device is offline (no data) but the owner enabled SMS commands
    # with a confirmed SIM number, deliver the command over the cellular SMS
    # channel as well — the app executes it locally on receipt. The normal
    # poll is skipped for SMS-delivered commands (delivery_channel='sms'), so
    # an offline phone that comes back online later does NOT double-execute a
    # command it already ran from the SMS. The SMS path only fires when the
    # device's last_seen is stale (it is offline) — an online device uses the
    # free, fast poll channel.
    device = db.execute(
        "SELECT sms_phone, sms_commands_enabled, device_key_hash, last_seen FROM devices WHERE id=?",
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

    # Only route via SMS when the device has a device_key_hash — the MAGNET
    # SMS carries the pairing code derived from it, so a keyless device (e.g.
    # an API-key-only legacy registration) could never verify the command
    # on-device. A relay to a keyless device would be silently ignored and the
    # command stranded (SMS channel excludes it from the poll), so guard it.
    has_device_key = bool(device and device["device_key_hash"])
    if sms_enabled and sms_phone and device_offline and has_device_key:
        # Per-device SMS cap: each relay costs real money (Twilio) and each
        # message is a real attack surface, so a single device can only relay
        # 5 SMS commands per minute. The shared command-issuance rate limit
        # (20/min per dashboard user) is NOT enough — one user could otherwise
        # fire 20 SMS/min to one number (~28k/day) through the relay.
        if not check_rate_limit(f"sms:{cmd.device_id}", "sms_command", 5, 1):
            raise HTTPException(
                status_code=429,
                detail="SMS command relay rate limit exceeded — try again in a minute",
            )
        delivery_channel = "sms"

    # Unacknowledged commands auto-expire: 5 minutes for sensitive ones
    # (wipe/lock/alarm), 30 minutes for everything else — a stale PENDING
    # must never linger on the dashboard or execute long after the operator
    # gave up on it. SMS-delivered commands get a LONGER window (24h): the
    # phone executes on SMS receipt but its ack can only travel over the
    # network when connectivity returns, so a short expiry would mark a
    # successfully-executed command 'expired' before the ack lands.
    # (Computed for BOTH channels up-front: a failed SMS send falls back to
    # the poll channel and must re-stamp the poll expiry, not keep 24h.)
    sms_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=24 * 60)).isoformat()
    # Expiry policy: wipe/lock/alarm are sensitive and fast-acting (5 min);
    # lost_mode gets a FULL 24h window — a lost phone is exactly the scenario
    # where it may be offline/stolen longer than 30 minutes, and the command
    # must survive until the device next polls (the SMS relay path already
    # gets 24h for the same reason). Everything else: 30 min.
    poll_expires_minutes = (
        5 if cmd.command in ("wipe", "lock", "alarm") else (24 * 60 if cmd.command == "lost_mode" else 30)
    )
    poll_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=poll_expires_minutes)).isoformat()
    expires_at = sms_expires_at if delivery_channel == "sms" else poll_expires_at

    # Urgent commands jump the queue: the device poll orders by priority ASC,
    # so wipe/lock/alarm/capture get priority 1 (executed first) while
    # ping/burst stay at the default 5. An explicit caller priority is honored
    # only when it is already more urgent than the forced value.
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
        "INSERT INTO commands (device_id, command, params, priority, issued_at, expires_at, delivery_channel) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
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

    # Now that the command id exists, actually send the SMS (best-effort).
    sms_delivered = False
    if delivery_channel == "sms":
        from sms_relay import command_sms_body, send_command_sms

        sms_body = command_sms_body(device["device_key_hash"], command_id, cmd.command, cmd.params or "")
        sms_delivered = send_command_sms(sms_phone, sms_body)
        log_audit(
            "command_sms_relay",
            actor=auth,
            details=(
                f"Command: {cmd.command} #{command_id} to {cmd.device_id} via SMS "
                f"to {sms_phone} → {'delivered' if sms_delivered else 'SEND FAILED'}"
            ),
        )

        # SMS SEND FAILURE → fall back to the poll channel. A command stamped
        # delivery_channel='sms' is excluded from the device poll forever, so
        # a failed SMS would strand it — never executable, never retryable by
        # the normal channel. Re-stamp it as poll (with the poll expiry) so it
        # stays deliverable the moment the device returns; the response's
        # sms_delivered=false already tells the operator the SMS failed.
        if not sms_delivered:
            db.execute(
                "UPDATE commands SET delivery_channel='poll', expires_at=? WHERE id=?",
                (poll_expires_at, command_id),
            )
            db.commit()
            delivery_channel = "poll"

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
    }


@router.get("/api/dashboard/commands/{device_id}")
async def get_command_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get command history for a device."""
    _assert_device_access(db, device_id, auth, min_role="viewer")

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
    """Delete command history for a device, gated by a step-up password.

    only_finished=true (default) removes executed/failed/expired commands
    while KEEPING pending ones — an in-flight wipe/lock/alarm must never be
    erased mid-delivery. only_finished=false clears the entire history
    (including pending, which effectively cancels queued commands).
    """
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


# ─── Evidence ────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/evidence/{device_id}")
async def get_evidence(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get evidence case for a device."""
    _assert_device_access(db, device_id, auth, min_role="viewer")
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
    _assert_device_access(db, device_id, auth, min_role="viewer")
    from fastapi.responses import Response

    case = db.execute(
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    if not case:
        case_id = evidence_builder.create_case(device_id)
    else:
        case_id = case["id"]

    # Generate actual PDF using ReportLab (module-level binding, see import
    # note above — never import evidence_pdf inside the request path).
    pdf_bytes = _generate_evidence_pdf_doc(case_id)
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
    _assert_device_access(db, device_id, auth, min_role="viewer")
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
    _assert_device_access(db, fence.device_id, auth, min_role="admin")
    cur = db.execute(
        (
            "INSERT INTO geofences (device_id, name, center_lat, center_lng, "
            "radius_meters, is_safe_zone, auto_action) VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            fence.device_id,
            fence.name,
            fence.center_lat,
            fence.center_lng,
            fence.radius_meters,
            fence.is_safe_zone,
            fence.auto_action,
        ),
    )
    db.commit()

    return {
        "status": "ok",
        "geofence_id": cur.lastrowid,
        "auto_action": fence.auto_action,
    }


@router.delete("/api/dashboard/geofence/{geofence_id}")
async def delete_geofence(
    geofence_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Delete a geofence."""
    fence = db.execute("SELECT device_id FROM geofences WHERE id=?", (geofence_id,)).fetchone()
    if fence:
        _assert_device_access(db, fence["device_id"], auth, min_role="admin")
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
    _assert_device_access(db, device_id, auth, min_role="viewer")
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
