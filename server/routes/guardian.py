"""
Magneetar Guardian Network — Community Recovery Routes

When a device is stolen, its owner can launch a *recovery request*. Opt-in
"guardians" near the device's last known location see an anonymized, blurred
announcement (device model + approximate area — never the owner's identity or
exact coordinates) and can report sightings. Sightings stream to the owner in
real time via WebSocket; the owner closes the request when the device is
recovered.

Privacy & abuse controls (per the product spec):
  - Guardians see a BLURRED location (~5km grid) and the device model only.
  - Guardian identity is limited to the public handle they chose at opt-in.
  - Only the device owner can launch/close a request, and only for a device
    that is actually marked stolen.
  - Sighting reports are rate-limited per guardian to prevent spam.
"""

import math
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from auth import check_rate_limit, get_current_device_or_key, get_current_user
from database import get_db, log_audit
from encryption import decrypt_location_row
from fastapi import APIRouter, Depends, HTTPException, Query
from logging_config import get_logger
from models import GuardianOptIn, GuardianProfile, RecoveryRequestCreate, RecoverySightingCreate
from websocket_manager import broadcast_to_dashboards, update_device_owner

logger = get_logger("magneetar")

router = APIRouter()

# Blur radius for guardian-facing locations (~5km at the equator). Coordinates
# are rounded to this grid so guardians get a neighborhood, never a street.
BLUR_DEGREES = 0.05

# Guardians may report at most this many sightings per hour.
SIGHTING_RATE_MAX = 10
SIGHTING_RATE_WINDOW_MINUTES = 60


def _require_real_user(user_id: str) -> str:
    """Guardian features need a real user account.

    Rejects the shared API key AND admin dashboard tokens (subject
    'dashboard:<hash>'), which get_current_user passes through as-is — neither
    is a recoverable user identity.
    """
    if user_id == "api_key_user" or not user_id.startswith("usr-"):
        raise HTTPException(status_code=401, detail="User account authentication required")
    return user_id


def _blur(value: Optional[float]) -> Optional[float]:
    """Round a coordinate to the guardian-facing blur grid."""
    if value is None:
        return None
    return round(round(value / BLUR_DEGREES) * BLUR_DEGREES, 4)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two coordinates."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _device_last_location(db, device_id: str) -> tuple[Optional[float], Optional[float]]:
    """Return (lat, lng) of the device's most recent location, or (None, None)."""
    row = db.execute(
        "SELECT device_id, lat, lng, location_encrypted, location_data FROM locations "
        "WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    if not row:
        return None, None
    # At-rest encryption: the recovery-request snapshot stores the real
    # coordinates (encrypted rows carry 0.0 placeholders in lat/lng).
    return decrypt_location_row(row)


def _request_dict(db, row) -> dict:
    """Serialize a recovery request row with sighting count + last sighting."""
    sightings = db.execute(
        "SELECT * FROM recovery_sightings WHERE request_id=? ORDER BY created_at DESC LIMIT 50",
        (row["id"],),
    ).fetchall()
    count = db.execute("SELECT COUNT(*) as cnt FROM recovery_sightings WHERE request_id=?", (row["id"],)).fetchone()[
        "cnt"
    ]
    # Privacy contract: the owner sees each guardian's PUBLIC handle and the
    # sighting details, never the guardian's raw account id. Strip guardian_id.
    sighting_list = []
    for s in sightings:
        sighting_list.append(
            {
                "id": s["id"],
                "guardian_handle": s["guardian_handle"],
                "lat": s["lat"],
                "lng": s["lng"],
                "note": s["note"],
                # Offline Device Network relay metadata — the owner sees
                # "seen directly" (0/false) vs "relayed by N guardians".
                "hop_count": s["hop_count"] if "hop_count" in s.keys() else 0,
                "relayed": bool(s["relayed"]) if "relayed" in s.keys() else False,
                "created_at": s["created_at"],
            }
        )

    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "status": row["status"],
        "description": row["description"],
        "created_at": row["created_at"],
        "closed_at": row["closed_at"],
        "closed_reason": row["closed_reason"],
        "sighting_count": count,
        "sightings": sighting_list,
    }


# ─── Guardian Profiles ──────────────────────────────────────────────────────


@router.get("/api/guardian/profile", response_model=GuardianProfile)
async def get_guardian_profile(db: sqlite3.Connection = Depends(get_db), user_id: str = Depends(get_current_user)):
    """Get the authenticated user's guardian profile (defaults to opted-out)."""
    user_id = _require_real_user(user_id)
    row = db.execute("SELECT * FROM guardian_profiles WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {
            "user_id": user_id,
            "opted_in": False,
            "radius_km": 20,
            "handle": None,
            "created_at": None,
            "updated_at": None,
        }
    # SQLite stores booleans as 0/1 integers — coerce to real booleans for JSON
    return {**dict(row), "opted_in": bool(row["opted_in"])}


@router.post("/api/guardian/opt-in", response_model=GuardianProfile)
async def guardian_opt_in(
    req: GuardianOptIn,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Opt in (or out) as a community guardian. Handle is the public identity
    guardians see on sightings — keep it an alias, never your full name."""
    user_id = _require_real_user(user_id)
    now = datetime.now(timezone.utc).isoformat()

    handle = (req.handle or "").strip()[:40] or None
    db.execute(
        """INSERT INTO guardian_profiles (user_id, opted_in, radius_km, handle, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               opted_in=excluded.opted_in,
               radius_km=excluded.radius_km,
               handle=excluded.handle,
               updated_at=excluded.updated_at""",
        (user_id, req.opted_in, req.radius_km, handle, now, now),
    )
    db.commit()
    log_audit("guardian_opt_in", actor=user_id, details=f"opted_in={req.opted_in}")

    row = db.execute("SELECT * FROM guardian_profiles WHERE user_id=?", (user_id,)).fetchone()
    return {**dict(row), "opted_in": bool(row["opted_in"])}


# ─── Recovery Requests (owner side) ─────────────────────────────────────────


@router.post("/api/recovery/requests")
async def launch_recovery_request(
    req: RecoveryRequestCreate,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Launch a community recovery request for a stolen device the user owns.

    The device must be marked stolen (operating_mode == 'stolen'). Only one
    active request may exist per device.
    """
    user_id = _require_real_user(user_id)

    device = db.execute(
        "SELECT id, owner_id, operating_mode, model FROM devices WHERE id=?", (req.device_id,)
    ).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Device not linked to your account")
    if device["operating_mode"] != "stolen":
        raise HTTPException(status_code=400, detail="Recovery requests can only be launched for stolen devices")

    active = db.execute(
        "SELECT id FROM recovery_requests WHERE device_id=? AND status='active'", (req.device_id,)
    ).fetchone()
    if active:
        raise HTTPException(status_code=409, detail="An active recovery request already exists for this device")

    if not check_rate_limit(f"recovery:{user_id}", "recovery_launch", 5, 24 * 60):
        raise HTTPException(status_code=429, detail="Too many recovery requests. Try again later.")

    request_id = f"rec-{secrets.token_hex(6)}"
    now = datetime.now(timezone.utc).isoformat()
    lat, lng = _device_last_location(db, req.device_id)

    # Find Network: an opaque per-request beacon token the stolen device
    # broadcasts over BLE. Guardians report the token back (never the request
    # id), so the request id stays off the air and the token is useless to a
    # random scanner that doesn't know the server-side mapping.
    beacon_token = secrets.token_hex(8)

    db.execute(
        """INSERT INTO recovery_requests
           (id, device_id, owner_id, status, description, last_lat, last_lng, created_at, beacon_token)
           VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?)""",
        (request_id, req.device_id, user_id, (req.description or "").strip()[:500], lat, lng, now, beacon_token),
    )
    db.commit()

    # Keep the WS owner cache in sync so sighting broadcasts reach this owner.
    update_device_owner(req.device_id, user_id)

    await broadcast_to_dashboards(
        {
            "type": "recovery_launched",
            "data": {
                "device_id": req.device_id,
                "request_id": request_id,
                "timestamp": now,
            },
        }
    )

    log_audit("recovery_request_launched", actor=user_id, details=f"Request: {request_id}")

    row = db.execute("SELECT * FROM recovery_requests WHERE id=?", (request_id,)).fetchone()
    return _request_dict(db, row)


@router.get("/api/device/recovery/beacon")
async def get_device_recovery_beacon(
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Find Network: the stolen device fetches its own active beacon token.

    The Android app calls this with device auth (its device JWT or
    x-device-key) to learn what to broadcast over BLE. The token is opaque
    and per-request; the response deliberately contains no request id, owner
    identity, or coordinates. Returns beacon_token: null when the device has
    no active recovery request (nothing to broadcast).
    """
    if device_id == "api_key_user":
        # The shared API key can't claim a specific device's beacon — that
        # would let anyone with the public key mint beacons for other phones.
        raise HTTPException(status_code=401, detail="Device authentication required")

    row = db.execute(
        "SELECT beacon_token FROM recovery_requests WHERE device_id=? AND status='active' "
        "ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    if not row or not row["beacon_token"]:
        return {"beacon_token": None}
    return {"beacon_token": row["beacon_token"]}


@router.get("/api/recovery/requests")
async def list_recovery_requests(db: sqlite3.Connection = Depends(get_db), user_id: str = Depends(get_current_user)):
    """List the authenticated user's recovery requests (most recent first)."""
    user_id = _require_real_user(user_id)
    rows = db.execute(
        "SELECT * FROM recovery_requests WHERE owner_id=? ORDER BY created_at DESC LIMIT 20",
        (user_id,),
    ).fetchall()
    return {"requests": [_request_dict(db, r) for r in rows]}


@router.post("/api/recovery/requests/{request_id}/close")
async def close_recovery_request(
    request_id: str,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Close a recovery request and mark the device recovered.

    Only the request's owner can close it. Closing also flips the device back
    to normal operating mode (the device has been found).
    """
    user_id = _require_real_user(user_id)
    row = db.execute("SELECT * FROM recovery_requests WHERE id=?", (request_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Recovery request not found")
    if row["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your recovery request")
    if row["status"] != "active":
        raise HTTPException(status_code=400, detail="Recovery request already closed")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE recovery_requests SET status='closed', closed_at=?, closed_reason='recovered' WHERE id=?",
        (now, request_id),
    )
    # Mark the device recovered too — this is the end of the theft incident.
    db.execute(
        "UPDATE devices SET is_stolen=0, operating_mode='normal', sentinel_score=0 WHERE id=?",
        (row["device_id"],),
    )
    db.execute(
        "UPDATE evidence_cases SET status='closed' WHERE device_id=? AND status='active'",
        (row["device_id"],),
    )
    db.commit()
    update_device_owner(row["device_id"], user_id)

    await broadcast_to_dashboards(
        {
            "type": "recovery_closed",
            "data": {"device_id": row["device_id"], "request_id": request_id, "timestamp": now},
        }
    )

    log_audit("recovery_request_closed", actor=user_id, details=f"Request: {request_id}")

    return {"status": "ok", "message": "Recovery request closed — device marked recovered", "request_id": request_id}


# ─── Guardian side: nearby requests & sightings ─────────────────────────────


@router.get("/api/recovery/nearby")
async def list_nearby_recovery_requests(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(20.0, gt=0, le=500),
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Guardian view: active recovery requests near a coordinate.

    Locations are BLURRED to the guardian grid and the owner's identity is
    never exposed. Only the device model, a description, the approximate
    area, and sighting counts are shared.
    """
    user_id = _require_real_user(user_id)

    # Light per-user throttle — repeated queries from many coordinates could
    # otherwise be used to triangulate a blurred location.
    if not check_rate_limit(f"nearby:{user_id}", "recovery_nearby", 60, 60):
        raise HTTPException(status_code=429, detail="Too many nearby queries. Try again later.")

    profile = db.execute("SELECT opted_in FROM guardian_profiles WHERE user_id=?", (user_id,)).fetchone()
    if not profile or not profile["opted_in"]:
        raise HTTPException(status_code=403, detail="Opt in as a guardian to see recovery requests")

    # Candidate requests: active, with a stored last-location snapshot.
    rows = db.execute(
        """SELECT r.*, d.model AS device_model
           FROM recovery_requests r JOIN devices d ON r.device_id = d.id
           WHERE r.status='active' AND r.last_lat IS NOT NULL AND r.last_lng IS NOT NULL
           ORDER BY r.created_at DESC
           LIMIT 100"""
    ).fetchall()

    nearby = []
    for r in rows:
        dist = _haversine_km(lat, lng, r["last_lat"], r["last_lng"])
        if dist > radius_km:
            continue
        sighting_count = db.execute(
            "SELECT COUNT(*) as cnt FROM recovery_sightings WHERE request_id=?", (r["id"],)
        ).fetchone()["cnt"]
        nearby.append(
            {
                "id": r["id"],
                "device_model": r["device_model"],
                "description": r["description"],
                "distance_km": round(dist, 1),
                "blurred_lat": _blur(r["last_lat"]),
                "blurred_lng": _blur(r["last_lng"]),
                "sighting_count": sighting_count,
                "created_at": r["created_at"],
            }
        )

    return {"requests": nearby, "guardian_user_id": user_id}


@router.post("/api/recovery/sightings")
async def report_sighting(
    req: RecoverySightingCreate,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """A guardian reports a sighting of a device on an active recovery request.

    The guardian must be opted in. Sightings are rate-limited to prevent spam.
    The owner receives the sighting instantly over WebSocket.
    """
    user_id = _require_real_user(user_id)
    profile = db.execute("SELECT opted_in, handle FROM guardian_profiles WHERE user_id=?", (user_id,)).fetchone()
    if not profile or not profile["opted_in"]:
        raise HTTPException(status_code=403, detail="Opt in as a guardian to report sightings")

    # Resolve the target request: by explicit request_id (dashboard flow) or
    # by the opaque beacon_token a Find Network guardian picked up over BLE
    # (the request id is never broadcast, so the server maps token -> request).
    if req.request_id:
        request = db.execute("SELECT * FROM recovery_requests WHERE id=?", (req.request_id,)).fetchone()
    elif req.beacon_token:
        request = db.execute(
            "SELECT * FROM recovery_requests WHERE beacon_token=? ORDER BY created_at DESC LIMIT 1",
            (req.beacon_token,),
        ).fetchone()
    else:
        raise HTTPException(status_code=422, detail="request_id or beacon_token is required")
    if not request:
        raise HTTPException(status_code=404, detail="Recovery request not found")
    if request["status"] != "active":
        raise HTTPException(status_code=400, detail="Recovery request is no longer active")

    if not check_rate_limit(f"sighting:{user_id}", "sighting", SIGHTING_RATE_MAX, SIGHTING_RATE_WINDOW_MINUTES):
        raise HTTPException(
            status_code=429,
            detail=f"Sighting limit reached ({SIGHTING_RATE_MAX} per hour)",
        )

    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO recovery_sightings (request_id, guardian_id, guardian_handle,
           lat, lng, note, hop_count, relayed, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            request["id"],
            user_id,
            profile["handle"] or "Guardian",
            req.lat,
            req.lng,
            (req.note or "").strip()[:300],
            req.hop_count if req.hop_count is not None else 0,
            1 if req.relayed else 0,
            now,
        ),
    )
    db.commit()

    # Deliver to the owner's open dashboards right away.
    await broadcast_to_dashboards(
        {
            "type": "recovery_sighting",
            "data": {
                "device_id": request["device_id"],
                "request_id": request["id"],
                "sighting_id": cur.lastrowid,
                "guardian_handle": profile["handle"] or "Guardian",
                "lat": req.lat,
                "lng": req.lng,
                "note": (req.note or "").strip()[:300],
                "timestamp": now,
            },
        }
    )

    log_audit("recovery_sighting", actor=user_id, details=f"Request: {req.request_id}")

    return {
        "status": "ok",
        "sighting_id": cur.lastrowid,
        "request_id": request["id"],
        "guardian_handle": profile["handle"] or "Guardian",
    }
