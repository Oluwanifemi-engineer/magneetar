"""
Magneetar Dashboard-Facing API Routes
All endpoints for the web dashboard (devices, locations, commands, evidence, etc.)
"""
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
import sqlite3

from config import settings
from database import get_db, log_audit, log_error
from models import (
    LoginRequest, RefreshRequest, CommandRequest, GeofenceRequest,
    TokenResponse, Command,
)
from auth import (
    create_dashboard_tokens, refresh_access_token,
    require_dashboard_auth, check_login_rate_limit,
    check_command_rate_limit, decode_token,
)
from evidence import evidence_builder
from logging_config import get_logger
from websocket_manager import active_dashboard_connections

logger = get_logger("magneetar")

router = APIRouter()


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
    auth: str = Depends(require_dashboard_auth)
):
    """List all devices with latest location."""
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

        result.append({
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
        })

    return {"devices": result}


@router.patch("/api/dashboard/devices/{device_id}/alias")
async def update_device_alias(
    device_id: str,
    body: dict,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Update device alias/name."""
    alias = body.get("alias", "").strip()
    if not alias:
        raise HTTPException(status_code=400, detail="Alias is required")

    db.execute("UPDATE devices SET alias=? WHERE id=?", (alias, device_id))
    db.commit()
    log_audit("device_alias_updated", actor=auth, details=f"Device: {device_id}, Alias: {alias}")

    return {"status": "ok", "alias": alias}


@router.post("/api/dashboard/devices/{device_id}/recover")
async def mark_device_recovered(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Mark a stolen device as recovered."""
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "UPDATE devices SET is_stolen=0, operating_mode='normal', sentinel_score=0 WHERE id=?",
        (device_id,)
    )
    db.execute(
        "UPDATE evidence_cases SET status='closed' WHERE device_id=? AND status='active'",
        (device_id,)
    )
    db.commit()

    log_audit("device_recovered", actor=auth, details=f"Device: {device_id}")

    return {"status": "ok", "message": "Device marked as recovered", "timestamp": now}


@router.get("/api/dashboard/devices/{device_id}/history")
async def get_device_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get full device information including command and event history."""
    device = db.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    location = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,)
    ).fetchone()

    cmd_stats = db.execute(
        "SELECT status, COUNT(*) as count FROM commands WHERE device_id=? GROUP BY status",
        (device_id,)
    ).fetchall()

    alert_count = db.execute(
        "SELECT COUNT(*) as count FROM alerts WHERE device_id=?", (device_id,)
    ).fetchone()[0]

    evidence = db.execute(
        "SELECT * FROM evidence_cases WHERE device_id=? ORDER BY created_at DESC LIMIT 1",
        (device_id,)
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
    auth: str = Depends(require_dashboard_auth)
):
    """Get location history for a device."""
    rows = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT ?",
        (device_id, limit)
    ).fetchall()

    return {"locations": [dict(r) for r in rows]}


@router.get("/api/dashboard/locations/{device_id}/live")
async def get_live_location(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get latest location for a device."""
    row = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,)
    ).fetchone()

    return {"location": dict(row) if row else None}


@router.get("/api/dashboard/replay/{device_id}")
async def get_replay_data(
    device_id: str,
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get location data for trail replay."""
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
    auth: str = Depends(require_dashboard_auth)
):
    """Get media list (thumbnails) for a device."""
    rows = db.execute(
        "SELECT id, device_id, type, timestamp, lat, lng FROM media WHERE device_id=? ORDER BY timestamp DESC",
        (device_id,)
    ).fetchall()

    return {"media": [dict(r) for r in rows]}


@router.get("/api/dashboard/media/file/{media_id}")
async def get_media_file(
    media_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get full media file with data."""
    row = db.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")

    return {
        "id": row["id"],
        "type": row["type"],
        "data_b64": row["data_b64"],
        "timestamp": row["timestamp"],
        "lat": row["lat"],
        "lng": row["lng"],
        "sha256_hash": row["sha256_hash"],
    }


# ─── Commands (Dashboard Issue) ──────────────────────────────────────────────

@router.post("/api/dashboard/command")
async def issue_command(
    cmd: CommandRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Issue a command to a device."""
    if not check_command_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    if cmd.command == "wipe":
        if cmd.params != "CONFIRMED_WIPE":
            raise HTTPException(
                status_code=400,
                detail="Wipe requires params='CONFIRMED_WIPE'"
            )

    expires_minutes = 5 if cmd.command in ('wipe', 'lock', 'alarm') else 60
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()

    cur = db.execute(
        "INSERT INTO commands (device_id, command, params, priority, issued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (cmd.device_id, cmd.command, cmd.params, cmd.priority, now, expires_at)
    )
    db.commit()

    command_id = cur.lastrowid
    log_audit("command_issued", actor=auth, details=f"Command: {cmd.command} to {cmd.device_id}")

    return {"status": "queued", "command_id": command_id}


@router.get("/api/dashboard/commands/{device_id}")
async def get_command_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get command history for a device."""
    rows = db.execute(
        "SELECT * FROM commands WHERE device_id=? ORDER BY issued_at DESC LIMIT 50",
        (device_id,)
    ).fetchall()

    return {"commands": [dict(r) for r in rows]}


# ─── Evidence ────────────────────────────────────────────────────────────────

@router.get("/api/dashboard/evidence/{device_id}")
async def get_evidence(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get evidence case for a device."""
    case = db.execute(
        "SELECT * FROM evidence_cases WHERE device_id=? ORDER BY created_at DESC LIMIT 1",
        (device_id,)
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
    auth: str = Depends(require_dashboard_auth)
):
    """Generate a forensic PDF evidence report for a device."""
    from fastapi.responses import Response

    case = db.execute(
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (device_id,)
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
    db.execute(
        "UPDATE evidence_cases SET pdf_generated=1 WHERE id=?",
        (case_id,)
    )
    db.commit()

    log_audit("evidence_pdf_generated", actor=auth, details=f"Case: {case_id}, Device: {device_id}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="Magneetar-Evidence-{case_id}.pdf"',
        }
    )


# ─── Alerts ──────────────────────────────────────────────────────────────────

@router.get("/api/dashboard/alerts/{device_id}")
async def get_alerts(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get alert history for a device."""
    rows = db.execute(
        "SELECT * FROM alerts WHERE device_id=? ORDER BY sent_at DESC LIMIT 50",
        (device_id,)
    ).fetchall()

    return {"alerts": [dict(r) for r in rows]}


# ─── Geofences ───────────────────────────────────────────────────────────────

@router.post("/api/dashboard/geofence")
async def create_geofence(
    fence: GeofenceRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Create a geofence for a device."""
    cur = db.execute(
        "INSERT INTO geofences (device_id, name, center_lat, center_lng, radius_meters, is_safe_zone) VALUES (?, ?, ?, ?, ?, ?)",
        (fence.device_id, fence.name, fence.center_lat, fence.center_lng, fence.radius_meters, fence.is_safe_zone)
    )
    db.commit()

    return {"status": "ok", "geofence_id": cur.lastrowid}


@router.delete("/api/dashboard/geofence/{geofence_id}")
async def delete_geofence(
    geofence_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Delete a geofence."""
    db.execute("DELETE FROM geofences WHERE id=?", (geofence_id,))
    db.commit()
    return {"status": "ok"}


@router.get("/api/dashboard/geofences/{device_id}")
async def list_geofences(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """List geofences for a device."""
    rows = db.execute(
        "SELECT * FROM geofences WHERE device_id=? AND active=1",
        (device_id,)
    ).fetchall()

    return {"geofences": [dict(r) for r in rows]}


# ─── Stats ───────────────────────────────────────────────────────────────────

@router.get("/api/dashboard/stats")
async def get_stats(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get dashboard statistics."""
    pg_available = False
    try:
        from database_postgres import get_postgres_db, is_postgres_configured
        if is_postgres_configured():
            pg = await get_postgres_db()
            if pg.is_connected:
                pg_available = True
    except Exception:
        pass

    if pg_available:
        from database_postgres import get_postgres_db
        pg = await get_postgres_db()

        rows = await pg.fetch_all("""
            SELECT
                (SELECT COUNT(*) FROM devices) AS total_devices,
                (SELECT COUNT(*) FROM devices WHERE last_seen > NOW() - interval '5 minutes') AS active_devices,
                (SELECT COUNT(*) FROM devices WHERE is_stolen = TRUE) AS stolen_devices,
                (SELECT COUNT(*) FROM locations) AS total_locations,
                (SELECT COUNT(*) FROM media) AS total_media,
                (SELECT COUNT(*) FROM alerts WHERE sent_at > CURRENT_DATE) AS alerts_today
        """)
        row = rows[0] if rows else {}
        return {
            "total_devices": row.get("total_devices", 0),
            "active_devices": row.get("active_devices", 0),
            "stolen_devices": row.get("stolen_devices", 0),
            "recovered_devices": 0,
            "total_locations": row.get("total_locations", 0),
            "total_media": row.get("total_media", 0),
            "alerts_today": row.get("alerts_today", 0),
        }
    else:
        total_devices = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE last_seen > datetime('now', '-5 minutes')"
        ).fetchone()[0]
        stolen_devices = db.execute("SELECT COUNT(*) FROM devices WHERE is_stolen=1").fetchone()[0]
        total_locations = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        total_media = db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE sent_at > ?", (today,)
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


# ─── Error Log ──────────────────────────────────────────────────────────────

@router.get("/api/dashboard/errors")
async def list_errors(
    limit: int = Query(50, ge=1, le=500),
    unresolved_only: bool = Query(False),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """List server errors with optional filter for unresolved only."""
    if unresolved_only:
        rows = db.execute(
            "SELECT * FROM error_log WHERE resolved=0 ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM error_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
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
    auth: str = Depends(require_dashboard_auth)
):
    """Mark an error as resolved."""
    now = datetime.now(timezone.utc).isoformat()
    notes = body.get("notes", "")

    db.execute(
        "UPDATE error_log SET resolved=1, resolved_at=?, resolved_by=?, notes=? WHERE id=?",
        (now, auth, notes, error_id)
    )
    db.commit()

    log_audit("error_resolved", actor=auth, details=f"Error #{error_id}: {notes}")

    return {"status": "ok", "message": f"Error #{error_id} marked as resolved"}
