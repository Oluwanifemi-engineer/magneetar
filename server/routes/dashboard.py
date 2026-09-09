"""
Magneetar Dashboard-Facing API Routes

Remaining endpoints after extraction:
- Auth (login, refresh)
- Locations (history, live, export, replay)
- Media (list, file, delete)
- Evidence (case, generate PDF)
- Alerts (history)
- Geofences (CRUD)
- Stats, Errors, Analytics

Extracted to separate modules:
- Device CRUD + Sharing → routes/dashboard_devices.py
- Commands → routes/dashboard_commands.py
- Shared helpers (RBAC, constants) → routes/dashboard_helpers.py
"""

import base64
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from analytics import track
from auth import (
    check_login_rate_limit,
    create_dashboard_tokens,
    refresh_access_token,
    require_dashboard_auth,
)
from config import settings
from database import get_db, log_audit
from encryption import decrypt_location_row
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
    GeofenceRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from routes.dashboard_helpers import (
    LIVE_FIX_ORDER_SQL,
    _assert_device_access,
    _resolve_user_id,
    _verify_stepup_password,
)

logger = get_logger("magneetar")

router = APIRouter()

# ─── Include Extracted Route Modules ─────────────────────────────────────────
# These routers register their own endpoints on the same /api/dashboard path.
# They are included HERE (not in main.py) because dashboard.py is the
# canonical owner of the /api/dashboard/* namespace.

from routes.dashboard_commands import router as commands_router  # noqa: E402
from routes.dashboard_devices import router as devices_router  # noqa: E402

router.include_router(devices_router)
router.include_router(commands_router)


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
        "SELECT * FROM locations WHERE device_id=? " "ORDER BY server_timestamp DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()

    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
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
    """Export a device's location history as CSV."""
    import csv as _csv
    import io as _io

    from fastapi.responses import Response

    _assert_device_access(db, device_id, auth, min_role="viewer")
    rows = db.execute(
        "SELECT device_id, server_timestamp, device_timestamp, lat, lng, "
        "location_encrypted, location_data, accuracy_horizontal, altitude, "
        "speed, bearing, provider, battery_percent, threat_level, "
        "sentinel_score, was_queued FROM locations "
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
            "Content-Disposition": (f'attachment; filename="magneetar-locations-{device_id}.csv"'),
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
    row = db.execute(
        f"SELECT * FROM locations WHERE device_id=? " f"ORDER BY {LIVE_FIX_ORDER_SQL} LIMIT 1",
        (device_id,),
    ).fetchone()

    if not row:
        return {"location": None}
    loc = dict(row)
    loc["lat"], loc["lng"] = decrypt_location_row(loc)
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
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
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
        "SELECT id, device_id, type, timestamp, lat, lng " "FROM media WHERE device_id=? ORDER BY timestamp DESC",
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
    """Delete a media item, gated by a step-up password."""
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    _assert_device_access(db, row["device_id"], auth, min_role="admin")

    _verify_stepup_password(db, auth, body.get("password"))

    from media_store import delete_media_file

    delete_media_file(row["file_path"] if "file_path" in row.keys() else None)

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
        details=(f"Media: {media_id}, device: {row['device_id']}, " f"type: {row['type']}"),
    )

    return {"status": "ok", "deleted_id": media_id}


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
        "SELECT * FROM evidence_cases WHERE device_id=? " "ORDER BY created_at DESC LIMIT 1",
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
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' " "ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    if not case:
        case_id = evidence_builder.create_case(device_id)
    else:
        case_id = case["id"]

    pdf_bytes = _generate_evidence_pdf_doc(case_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="No evidence data found")

    db.execute("UPDATE evidence_cases SET pdf_generated=1 WHERE id=?", (case_id,))
    db.commit()

    log_audit(
        "evidence_pdf_generated",
        actor=auth,
        details=f"Case: {case_id}, Device: {device_id}",
    )
    track("evidence_exported", device_id=device_id, case_id=case_id)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (f'attachment; filename="Magneetar-Evidence-{case_id}.pdf"'),
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
        "INSERT INTO geofences "
        "(device_id, name, center_lat, center_lng, radius_meters, "
        "is_safe_zone, auto_action) VALUES (?, ?, ?, ?, ?, ?, ?)",
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
    rows = db.execute(
        "SELECT * FROM geofences WHERE device_id=? AND active=1",
        (device_id,),
    ).fetchall()

    return {"geofences": [dict(r) for r in rows]}


# ─── Stats ───────────────────────────────────────────────────────────────────


@router.get("/api/dashboard/stats")
async def get_stats(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """Get dashboard statistics. Users see stats scoped to their own devices."""
    user_id = _resolve_user_id(auth)

    if user_id:
        total_devices = db.execute("SELECT COUNT(*) FROM devices WHERE owner_id=?", (user_id,)).fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE owner_id=? AND " "datetime(last_seen) > datetime('now', '-5 minutes')",
            (user_id,),
        ).fetchone()[0]
        stolen_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE is_stolen=1 AND owner_id=?",
            (user_id,),
        ).fetchone()[0]
        total_locations = db.execute(
            "SELECT COUNT(*) FROM locations l " "JOIN devices d ON l.device_id=d.id WHERE d.owner_id=?",
            (user_id,),
        ).fetchone()[0]
        total_media = db.execute(
            "SELECT COUNT(*) FROM media m " "JOIN devices d ON m.device_id=d.id WHERE d.owner_id=?",
            (user_id,),
        ).fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = db.execute(
            "SELECT COUNT(*) FROM alerts a "
            "JOIN devices d ON a.device_id=d.id "
            "WHERE d.owner_id=? AND a.sent_at > ?",
            (user_id, today),
        ).fetchone()[0]
    else:
        total_devices = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE " "datetime(last_seen) > datetime('now', '-5 minutes')"
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
            "SELECT * FROM error_log WHERE resolved=0 " "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM error_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()

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
        "UPDATE error_log SET resolved=1, resolved_at=?, " "resolved_by=?, notes=? WHERE id=?",
        (now, auth, notes, error_id),
    )
    db.commit()

    log_audit("error_resolved", actor=auth, details=f"Error #{error_id}: {notes}")

    return {
        "status": "ok",
        "message": f"Error #{error_id} marked as resolved",
    }


# ─── Analytics (MVP Metrics) ─────────────────────────────────────────────────


@router.get("/api/dashboard/analytics")
async def get_analytics(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth),
):
    """MVP analytics for the dashboard."""
    active_devices = db.execute(
        """SELECT date(server_timestamp) as day,
                  COUNT(DISTINCT device_id) as count
           FROM locations
           WHERE server_timestamp > datetime('now', '-7 days')
           GROUP BY date(server_timestamp) ORDER BY day"""
    ).fetchall()

    command_stats = db.execute("SELECT status, COUNT(*) as count FROM commands GROUP BY status").fetchall()

    total_devices = db.execute("SELECT COUNT(*) as cnt FROM devices").fetchone()["cnt"]

    total_locations = db.execute("SELECT COUNT(*) as cnt FROM locations").fetchone()["cnt"]

    return {
        "active_devices_7d": [dict(r) for r in active_devices],
        "command_stats": {r["status"]: r["count"] for r in command_stats},
        "total_devices": total_devices,
        "total_locations": total_locations,
    }
