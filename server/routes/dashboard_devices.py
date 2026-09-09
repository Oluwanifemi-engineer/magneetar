"""
Magneetar Dashboard Device Routes (extracted from routes/dashboard.py — Phase 0).

Device CRUD endpoints for the web dashboard:
- Device listing with live location
- Device claim by pairing code
- Device alias, alert settings, SMS settings
- Cell-tower location resolution
- Device deletion (single + bulk archived)
- Device recovery
- Device sharing (grant, list, revoke)
- Device history

Extracted from dashboard.py (was 1,935 lines) to reduce it to ~700 lines
while keeping all device management in one focused module.

Shared helpers (RBAC, constants, utility functions) live in dashboard_helpers.py.
"""

import hmac
import json
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from analytics import track
from auth import check_rate_limit, require_dashboard_auth
from config import settings
from database import delete_device_cascade, get_db, log_audit
from encryption import decrypt_location, decrypt_location_row
from fastapi import APIRouter, Depends, HTTPException
from logging_config import get_logger
from models import DeviceClaimByPairingRequest, ShareRequest
from routes.dashboard_helpers import (
    LIVE_FIX_ORDER_SQL,
    _assert_device_access,
    _parse_int,
    _parse_json_list,
    _resolve_user_id,
    _verify_stepup_password,
)
from routes.devices import _enforce_device_limit, _user_exists

logger = get_logger("magneetar")

router = APIRouter()


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
                "access_role": access_role,
                "is_owner": is_owner,
                "capture_armed": (
                    bool(d["capture_armed"]) if "capture_armed" in d.keys() and d["capture_armed"] is not None else None
                ),
                "location_mode": (d["location_mode"] if "location_mode" in d.keys() else None),
                "archived_at": (d["archived_at"] if "archived_at" in d.keys() else None),
                "alert_phone": (
                    d["alert_phone"] if "alert_phone" in d.keys() and access_role != "device_only" else None
                ),
                "alert_email": (
                    d["alert_email"] if "alert_email" in d.keys() and access_role != "device_only" else None
                ),
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
    code shown in the Magneetar app on the phone."""
    if not check_rate_limit(f"claim_pairing:{auth}", "claim_pairing", 10, 10):
        raise HTTPException(status_code=429, detail="Too many claim attempts — try again shortly")

    user_id = _resolve_user_id(auth)
    if user_id is None:
        raise HTTPException(status_code=403, detail="User authentication required")

    if not _user_exists(db, user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")

    device = db.execute(
        "SELECT id, owner_id, device_key_hash FROM devices WHERE id=?",
        (req.device_id,),
    ).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    stored_hash = device["device_key_hash"] or ""
    if len(stored_hash) < 8 or not hmac.compare_digest(req.pairing_code, stored_hash[:8]):
        raise HTTPException(status_code=403, detail="Invalid pairing code")

    existing_owner = device["owner_id"]
    if existing_owner and existing_owner != user_id and _user_exists(db, existing_owner):
        raise HTTPException(status_code=403, detail="Device already linked to another account")

    if existing_owner != user_id:
        _enforce_device_limit(db, user_id)

    db.execute("UPDATE devices SET owner_id=? WHERE id=?", (user_id, req.device_id))
    db.commit()

    from websocket_manager import update_device_owner

    update_device_owner(req.device_id, user_id)
    log_audit(
        "device_claimed_by_pairing",
        actor=auth,
        details=f"Device: {req.device_id}",
    )
    track("device_claimed", device_id=req.device_id, user_id=user_id)

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

    from alerts import ALL_ALERT_TYPES, ALL_CHANNELS

    alert_phone = (body.get("alert_phone") or "").strip()
    alert_email = (body.get("alert_email") or "").strip()

    if alert_phone and not alert_phone.startswith("+"):
        raise HTTPException(
            status_code=400,
            detail="Alert phone must be in E.164 format starting with '+'",
        )
    if alert_email and "@" not in alert_email:
        raise HTTPException(status_code=400, detail="Invalid alert email address")

    alert_channels_raw = body.get("alert_channels")
    alert_channels = None
    if alert_channels_raw is not None:
        if not isinstance(alert_channels_raw, list):
            raise HTTPException(status_code=400, detail="alert_channels must be a list")
        invalid = set(alert_channels_raw) - set(ALL_CHANNELS)
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid channels: {sorted(invalid)}")
        alert_channels = json.dumps(list(dict.fromkeys(alert_channels_raw))) if alert_channels_raw else None

    enabled_raw = body.get("enabled_types")
    enabled_types = None
    if enabled_raw is not None:
        if not isinstance(enabled_raw, list):
            raise HTTPException(status_code=400, detail="enabled_types must be a list")
        invalid = set(enabled_raw) - set(ALL_ALERT_TYPES)
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert types: {sorted(invalid)}",
            )
        enabled_types = json.dumps(list(dict.fromkeys(enabled_raw))) if enabled_raw else None

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
        """UPDATE devices SET alert_phone=?, alert_email=?, alert_channels=?,
           enabled_types=?, quiet_hours_start=?, quiet_hours_end=? WHERE id=?""",
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
            f"channels={alert_channels or 'all'}, "
            f"types={enabled_types or 'all'}, "
            f"quiet={quiet_start is not None and f'{quiet_start}-{quiet_end}' or 'off'}"
        ),
    )

    return {
        "status": "ok",
        "alert_phone": alert_phone,
        "alert_email": alert_email,
        "alert_channels": json.loads(alert_channels) if alert_channels else None,
        "enabled_types": json.loads(enabled_types) if enabled_types else None,
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
    """Configure the Offline Command Relay for a device."""
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
            detail=("Enable Offline SMS commands requires a phone number " "(E.164, e.g. +2348081234567)"),
        )

    db.execute(
        "UPDATE devices SET sms_phone=?, sms_commands_enabled=? WHERE id=?",
        (sms_phone or None, 1 if enabled else 0, device_id),
    )
    db.commit()
    log_audit(
        "device_sms_settings_updated",
        actor=auth,
        details=(
            f"Device: {device_id}, sms_commands_enabled={enabled}, " f"sms_phone={'set' if sms_phone else 'cleared'}"
        ),
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
    """Resolve a cell-tower fingerprint to approximate coordinates."""
    tower_ids = body.get("cell_tower_ids") or []
    if not isinstance(tower_ids, list) or not tower_ids:
        raise HTTPException(status_code=400, detail="cell_tower_ids must be a non-empty list")
    if not all(isinstance(t, str) and ":" in t for t in tower_ids):
        raise HTTPException(
            status_code=400,
            detail="Each tower id must be 'type:mcc:mnc:tac:cid'",
        )

    fingerprint = ",".join(sorted(set(tower_ids)))

    cached = db.execute(
        "SELECT lat, lng, accuracy_meters, provider " "FROM cell_location_cache WHERE fingerprint=?",
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

    if not settings.CELL_LOOKUP_API_KEY:
        return {
            "resolved": False,
            "reason": "no_provider_configured",
            "cell_tower_ids": tower_ids,
        }

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
                "INSERT OR REPLACE INTO cell_location_cache "
                "(fingerprint, lat, lng, accuracy_meters, provider) "
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
    """Bulk-delete all ARCHIVED (stale) devices, gated by a step-up password."""
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
    """Permanently delete a device and all of its data, gated by step-up password."""
    _assert_device_access(db, device_id, auth, min_role="owner")
    row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    _verify_stepup_password(db, auth, (body or {}).get("password"))

    delete_device_cascade(db, device_id)
    db.commit()

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
        "UPDATE devices SET is_stolen=0, operating_mode='normal', " "sentinel_score=0 WHERE id=?",
        (device_id,),
    )
    db.execute(
        "UPDATE evidence_cases SET status='closed' " "WHERE device_id=? AND status='active'",
        (device_id,),
    )
    db.commit()

    log_audit("device_recovered", actor=auth, details=f"Device: {device_id}")

    return {
        "status": "ok",
        "message": "Device marked as recovered",
        "timestamp": now,
    }


# ─── Device Sharing (roadmap Milestone 2 P1) ────────────────────────────────


@router.post("/api/dashboard/devices/{device_id}/shares")
async def grant_device_share(
    device_id: str,
    body: ShareRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Grant (or update) another account's access to a device."""
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
        """INSERT INTO device_shares
           (id, device_id, grantee_user_id, role, created_by)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(device_id, grantee_user_id)
           DO UPDATE SET id=excluded.id, role=excluded.role,
                         created_by=excluded.created_by""",
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
    """List who has access to a device and with which role."""
    _assert_device_access(db, device_id, auth, min_role="admin")
    rows = db.execute(
        """SELECT ds.id, ds.device_id, ds.grantee_user_id, ds.role,
                  ds.created_at, u.email, u.display_name
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
    """Revoke an account's access to a device."""
    _assert_device_access(db, device_id, auth, min_role="owner")
    if _resolve_user_id(auth) is None:
        raise HTTPException(status_code=403, detail="Sharing is a user-account action")
    row = db.execute(
        "SELECT id FROM device_shares WHERE id=? AND device_id=?",
        (share_id, device_id),
    ).fetchone()
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


# ─── Device History ──────────────────────────────────────────────────────────


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

    location = db.execute(
        f"SELECT * FROM locations WHERE device_id=? " f"ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1",
        (device_id,),
    ).fetchone()

    latest_location = dict(location) if location else None
    if latest_location:
        latest_location["lat"], latest_location["lng"] = decrypt_location_row(latest_location)
        latest_location.pop("location_data", None)

    cmd_stats = db.execute(
        "SELECT status, COUNT(*) as count FROM commands " "WHERE device_id=? GROUP BY status",
        (device_id,),
    ).fetchall()

    alert_count = db.execute(
        "SELECT COUNT(*) as count FROM alerts WHERE device_id=?",
        (device_id,),
    ).fetchone()[0]

    evidence = db.execute(
        "SELECT * FROM evidence_cases WHERE device_id=? " "ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    return {
        "device": dict(device),
        "latest_location": latest_location,
        "command_stats": {r["status"]: r["count"] for r in cmd_stats},
        "total_alerts": alert_count,
        "active_evidence": dict(evidence) if evidence else None,
    }
