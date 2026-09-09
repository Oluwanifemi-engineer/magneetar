"""
Geospatial Domain

Owns: Geofence CRUD, point-in-polygon testing, geofence breach detection,
      auto-action triggers on geofence entry/exit.

Data tables: geofences, geofence_events
Extracted from: routes/dashboard.py (geofence portions)

Domain Events Published:
  - geofence_created       {user_id, geofence_id, name, shape}
  - geofence_breach        {device_id, geofence_id, action, lat, lon}
  - geofence_auto_action   {device_id, geofence_id, action_type, result}
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from logging_config import get_logger
from models import GeofenceRequest

logger = get_logger("magneetar.geospatial")

# ─── Geofence CRUD ─────────────────────────────────────────────────────────────


def create_geofence(
    conn: sqlite3.Connection,
    fence: GeofenceRequest,
    user_id: str,
    min_role: str = "admin",
) -> dict:
    """Create a geofence for a device.

    Requires the authenticated user to have at least 'admin' role on the
    device (owner or admin share).
    """
    from routes.dashboard_helpers import _assert_device_access

    _assert_device_access(conn, fence.device_id, user_id, min_role=min_role)

    cur = conn.execute(
        """INSERT INTO geofences
           (device_id, name, center_lat, center_lng, radius_meters,
            is_safe_zone, auto_action)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
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
    conn.commit()

    logger.info(
        "geofence_created",
        extra={
            "extra_data": {
                "geofence_id": cur.lastrowid,
                "device_id": fence.device_id,
                "name": fence.name,
                "user_id": user_id,
            }
        },
    )

    return {
        "status": "ok",
        "geofence_id": cur.lastrowid,
        "auto_action": fence.auto_action,
    }


def list_geofences(
    conn: sqlite3.Connection,
    device_id: str,
    user_id: str,
    min_role: str = "viewer",
) -> list[dict]:
    """List active geofences for a device."""
    from routes.dashboard_helpers import _assert_device_access

    _assert_device_access(conn, device_id, user_id, min_role=min_role)

    rows = conn.execute(
        "SELECT * FROM geofences WHERE device_id=? AND active=1",
        (device_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_geofence(conn: sqlite3.Connection, geofence_id: int) -> Optional[dict]:
    """Fetch a single geofence by id."""
    row = conn.execute(
        "SELECT * FROM geofences WHERE id=?",
        (geofence_id,),
    ).fetchone()
    return dict(row) if row else None


def delete_geofence(
    conn: sqlite3.Connection,
    geofence_id: int,
    user_id: str,
    min_role: str = "admin",
) -> dict:
    """Delete a geofence. Admin-only."""
    from routes.dashboard_helpers import _assert_device_access

    fence = conn.execute(
        "SELECT device_id FROM geofences WHERE id=?",
        (geofence_id,),
    ).fetchone()
    if fence:
        _assert_device_access(conn, fence["device_id"], user_id, min_role=min_role)
    conn.execute("DELETE FROM geofences WHERE id=?", (geofence_id,))
    conn.commit()

    logger.info(
        "geofence_deleted",
        extra={
            "extra_data": {
                "geofence_id": geofence_id,
                "user_id": user_id,
            }
        },
    )

    return {"status": "ok"}


def update_geofence(
    conn: sqlite3.Connection,
    geofence_id: int,
    name: Optional[str] = None,
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
    radius_meters: Optional[float] = None,
    is_safe_zone: Optional[bool] = None,
    auto_action: Optional[str] = None,
    user_id: str = "",
    min_role: str = "admin",
) -> dict:
    """Update a geofence's fields. Admin-only."""
    from routes.dashboard_helpers import _assert_device_access

    fence = conn.execute(
        "SELECT device_id FROM geofences WHERE id=?",
        (geofence_id,),
    ).fetchone()
    if not fence:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Geofence not found")
    _assert_device_access(conn, fence["device_id"], user_id, min_role=min_role)

    sets = []
    params = []
    if name is not None:
        sets.append("name=?")
        params.append(name)
    if center_lat is not None:
        sets.append("center_lat=?")
        params.append(center_lat)
    if center_lng is not None:
        sets.append("center_lng=?")
        params.append(center_lng)
    if radius_meters is not None:
        sets.append("radius_meters=?")
        params.append(radius_meters)
    if is_safe_zone is not None:
        sets.append("is_safe_zone=?")
        params.append(1 if is_safe_zone else 0)
    if auto_action is not None:
        sets.append("auto_action=?")
        params.append(auto_action)
    if not sets:
        return get_geofence(conn, geofence_id)
    params.append(geofence_id)

    conn.execute(
        f"UPDATE geofences SET {', '.join(sets)} WHERE id=?",
        params,
    )
    conn.commit()

    logger.info(
        "geofence_updated",
        extra={
            "extra_data": {
                "geofence_id": geofence_id,
                "user_id": user_id,
            }
        },
    )

    return get_geofence(conn, geofence_id)


def toggle_geofence_active(
    conn: sqlite3.Connection,
    geofence_id: int,
    active: bool,
    user_id: str,
    min_role: str = "admin",
) -> dict:
    """Toggle a geofence's active state."""
    from routes.dashboard_helpers import _assert_device_access

    fence = conn.execute(
        "SELECT device_id FROM geofences WHERE id=?",
        (geofence_id,),
    ).fetchone()
    if not fence:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Geofence not found")
    _assert_device_access(conn, fence["device_id"], user_id, min_role=min_role)

    conn.execute(
        "UPDATE geofences SET active=? WHERE id=?",
        (1 if active else 0, geofence_id),
    )
    conn.commit()

    return get_geofence(conn, geofence_id)
