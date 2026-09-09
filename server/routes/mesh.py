"""
Magneetar BLE Mesh — Offline Device Finding.

When a phone is stolen and goes offline, other Magneetar phones nearby
can detect its BLE beacon and report the sighting to the server. The
owner sees the location on their dashboard even though the stolen phone
has no internet.

How it works:
1. Stolen phone broadcasts a BLE beacon (its device_id + encrypted token)
2. Nearby Magneetar phones detect the beacon
3. They report the sighting to this endpoint
4. Owner sees the sighting on their dashboard

Privacy:
- Beacons are only active when the owner requests recovery
- Sighting reports contain only the finder's device_id and approximate location
- The stolen device's exact identity is hidden from finders
"""

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from auth import get_current_device_or_key, get_current_user
from database import get_db
from fastapi import APIRouter, Depends, HTTPException
from logging_config import get_logger
from pydantic import BaseModel
from websocket_manager import broadcast_to_dashboards

logger = get_logger("magneetar")
router = APIRouter()


# ─── Recovery Sighting Alias ─────────────────────────────────────────────────
# The Android GuardianBeaconScanner sends to /api/recovery/sightings with
# user auth (Bearer token). Route it to the same handler as /api/mesh/sighting.
# This alias exists for backward compatibility — the canonical path is
# /api/mesh/sighting (device auth via x-device-key).


# ─── Beacon Registration ────────────────────────────────────────────────────


class BeaconRegistration(BaseModel):
    device_id: str
    beacon_token: str  # Short-lived token proving recovery is active
    active: bool = True


@router.post("/api/mesh/beacon/register")
async def register_beacon(
    reg: BeaconRegistration,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Register a device as a BLE beacon for recovery.

    Called by the stolen device when recovery is activated.
    The beacon_token is a short-lived, rotating token that proves
    the owner requested recovery — finders validate this before
    reporting sightings.
    """
    if reg.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    now = datetime.now(timezone.utc).isoformat()

    # Upsert beacon registration
    existing = db.execute("SELECT id FROM mesh_beacons WHERE device_id=?", (device_id,)).fetchone()

    if existing:
        db.execute(
            "UPDATE mesh_beacons SET beacon_token=?, active=?, updated_at=? WHERE device_id=?",
            (reg.beacon_token, reg.active, now, device_id),
        )
    else:
        db.execute(
            "INSERT INTO mesh_beacons (device_id, beacon_token, active, registered_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (device_id, reg.beacon_token, reg.active, now, now),
        )

    db.commit()
    return {"status": "ok", "device_id": device_id, "active": reg.active}


@router.post("/api/mesh/beacon/deactivate")
async def deactivate_beacon(
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Deactivate BLE beacon (recovery complete or cancelled)."""
    db.execute(
        "UPDATE mesh_beacons SET active=0, updated_at=? WHERE device_id=?",
        (datetime.now(timezone.utc).isoformat(), device_id),
    )
    db.commit()
    return {"status": "ok"}


# ─── Sighting Reports ───────────────────────────────────────────────────────


class SightingReport(BaseModel):
    beacon_device_id: Optional[str] = None  # The stolen device we detected (new format)
    beacon_token: str  # Must match the registered token
    lat: float
    lng: float
    accuracy: Optional[float] = None  # Horizontal accuracy in meters
    rssi: Optional[int] = None  # BLE signal strength
    hop_count: Optional[int] = 0  # BLE mesh hop count
    relayed: Optional[bool] = False  # Was this beacon relayed through another phone?


@router.post("/api/mesh/sighting")
async def report_sighting(
    report: SightingReport,
    db: sqlite3.Connection = Depends(get_db),
    finder_device_id: str = Depends(get_current_device_or_key),
):
    """Report a BLE sighting of a stolen device.

    Called by finder phones when they detect a beacon.
    Validates the beacon_token to prevent false reports.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Validate beacon exists and is active
    beacon = db.execute(
        "SELECT device_id, beacon_token FROM mesh_beacons " "WHERE device_id=? AND active=1",
        (report.beacon_device_id,),
    ).fetchone()

    if not beacon:
        raise HTTPException(status_code=404, detail="No active beacon for this device")

    if beacon["beacon_token"] != report.beacon_token:
        raise HTTPException(status_code=403, detail="Invalid beacon token")

    # Resolve beacon_device_id from the token if not provided (Android sends token only)
    beacon_device_id = report.beacon_device_id or beacon["device_id"]

    # Don't let a device report itself
    if finder_device_id == beacon_device_id:
        raise HTTPException(status_code=400, detail="Cannot report own device")

    # Rate limit: max 1 sighting per finder per beacon per 5 minutes
    recent = db.execute(
        "SELECT 1 FROM mesh_sightings "
        "WHERE beacon_device_id=? AND finder_device_id=? "
        "AND datetime(reported_at) > datetime('now', '-5 minutes') LIMIT 1",
        (beacon_device_id, finder_device_id),
    ).fetchone()

    if recent:
        return {"status": "ok", "message": "Sighting already reported recently"}

    # Store sighting (with relay metadata if present)
    db.execute(
        "INSERT INTO mesh_sightings "
        "(beacon_device_id, finder_device_id, lat, lng, accuracy, rssi, hop_count, relayed, reported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            beacon_device_id,
            finder_device_id,
            report.lat,
            report.lng,
            report.accuracy,
            report.rssi,
            report.hop_count or 0,
            report.relayed or False,
            now,
        ),
    )

    # Update device location with the sighting (approximate, from finder)
    db.execute(
        "UPDATE devices SET last_seen=?, last_lat=?, last_lng=? WHERE id=?",
        (now, report.lat, report.lng, beacon_device_id),
    )

    db.commit()

    # Notify the owner via WebSocket
    await broadcast_to_dashboards(
        {
            "type": "mesh_sighting",
            "data": {
                "device_id": beacon_device_id,
                "lat": report.lat,
                "lng": report.lng,
                "finder": finder_device_id,
                "hop_count": report.hop_count or 0,
                "relayed": report.relayed or False,
                "timestamp": now,
            },
        }
    )

    logger.info(
        "BLE sighting reported",
        extra={
            "extra_data": {
                "beacon": beacon_device_id,
                "finder": finder_device_id,
                "lat": report.lat,
                "lng": report.lng,
                "hop": report.hop_count or 0,
            }
        },
    )

    return {"status": "ok", "message": "Sighting recorded"}


# ─── Sighting Query (for dashboard) ─────────────────────────────────────────


@router.get("/api/mesh/sightings/{device_id}")
async def get_sightings(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    limit: int = 20,
    user_id: str = Depends(get_current_device_or_key),
):
    """Get recent BLE sightings for a device (owner only)."""

    # Verify ownership
    device = db.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device["owner_id"] and device["owner_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your device")

    sightings = db.execute(
        "SELECT lat, lng, accuracy, rssi, finder_device_id, reported_at "
        "FROM mesh_sightings WHERE beacon_device_id=? "
        "ORDER BY reported_at DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()

    return {
        "device_id": device_id,
        "sightings": [dict(s) for s in sightings],
    }


# ─── Recovery Sighting Alias (user auth) ────────────────────────────────────
# The Android GuardianBeaconScanner sends to /api/recovery/sightings with
# a user Bearer token. This alias authenticates via user JWT, resolves the
# user's device, and delegates to the sighting logic.


@router.post("/api/recovery/sightings")
async def report_sighting_via_recovery(
    report: SightingReport,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Alias for /api/mesh/sighting — accepts user JWT auth.

    The Android GuardianBeaconScanner sends user auth (Bearer token),
    not device auth. This endpoint resolves the user's device and
    forwards to the same sighting logic.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Find the user's first registered device (guardian scans from their own phone)
    device = db.execute(
        "SELECT id FROM devices WHERE owner_id=? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="No device registered for this user")

    finder_device_id = device["id"]

    # Validate beacon exists and is active
    beacon = db.execute(
        "SELECT device_id, beacon_token FROM mesh_beacons " "WHERE active=1",
    ).fetchall()

    # Find the matching beacon by token
    matched_beacon = None
    for b in beacon:
        if b["beacon_token"] == report.beacon_token:
            matched_beacon = b
            break

    if not matched_beacon:
        raise HTTPException(status_code=404, detail="No active beacon for this token")

    beacon_device_id = report.beacon_device_id or matched_beacon["device_id"]

    # Don't let a device report itself
    if finder_device_id == beacon_device_id:
        raise HTTPException(status_code=400, detail="Cannot report own device")

    # Rate limit: max 1 sighting per finder per beacon per 5 minutes
    recent = db.execute(
        "SELECT 1 FROM mesh_sightings "
        "WHERE beacon_device_id=? AND finder_device_id=? "
        "AND datetime(reported_at) > datetime('now', '-5 minutes') LIMIT 1",
        (beacon_device_id, finder_device_id),
    ).fetchone()

    if recent:
        return {"status": "ok", "message": "Sighting already reported recently"}

    # Store sighting
    db.execute(
        "INSERT INTO mesh_sightings "
        "(beacon_device_id, finder_device_id, lat, lng, accuracy, rssi, hop_count, relayed, reported_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            beacon_device_id,
            finder_device_id,
            report.lat,
            report.lng,
            report.accuracy,
            report.rssi,
            report.hop_count or 0,
            report.relayed or False,
            now,
        ),
    )

    # Update device location with the sighting
    db.execute(
        "UPDATE devices SET last_seen=?, last_lat=?, last_lng=? WHERE id=?",
        (now, report.lat, report.lng, beacon_device_id),
    )

    db.commit()

    # Notify the owner via WebSocket
    await broadcast_to_dashboards(
        {
            "type": "mesh_sighting",
            "data": {
                "device_id": beacon_device_id,
                "lat": report.lat,
                "lng": report.lng,
                "finder": finder_device_id,
                "hop_count": report.hop_count or 0,
                "relayed": report.relayed or False,
                "timestamp": now,
            },
        }
    )

    logger.info(
        "BLE sighting reported (recovery alias)",
        extra={
            "extra_data": {
                "beacon": beacon_device_id,
                "finder": finder_device_id,
                "lat": report.lat,
                "lng": report.lng,
            }
        },
    )

    return {"status": "ok", "message": "Sighting recorded"}


# ─── Guardian Opt-in Profile ─────────────────────────────────────────────────
# The Android GuardianBeaconScanner calls this BEFORE it starts each scan
# cycle and only scans while the account's guardian profile says opted_in.
# Until a community-recovery opt-in flow ships (none exists today), no
# profile row is ever written — so this returns opted_in=false for every
# account, which is the truthful state: the scanner stays off and no
# volunteer sighting data is collected. When the opt-in UI ships, rows appear
# here and scanning activates for the users who chose it.


@router.get("/api/guardian/profile")
async def get_guardian_profile(
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Return the caller's guardian opt-in state (user JWT auth).

    Response shape matches what the Android GuardianBeaconScanner reads:
    opted_in (bool) is the gate; handle/radius_km are null until the
    volunteer flow exists.
    """
    row = db.execute(
        "SELECT opted_in, handle, radius_km FROM guardian_profiles WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if not row:
        return {"opted_in": False, "handle": None, "radius_km": None}
    return {
        "opted_in": bool(row["opted_in"]),
        "handle": row["handle"],
        "radius_km": row["radius_km"],
    }
