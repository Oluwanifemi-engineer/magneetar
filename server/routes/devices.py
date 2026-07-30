"""
Magneetar Device-Facing API Routes
All endpoints for device communication (registration, location, media, commands, etc.)
"""

import asyncio
import base64
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from alerts import alert_engine
from auth import (
    check_command_poll_rate_limit,
    check_heartbeat_rate_limit,
    check_location_rate_limit,
    check_media_rate_limit,
    create_device_tokens,
    get_current_device_or_key,
    hash_device_key,
    refresh_access_token,
    verify_api_key,
)
from config import settings
from database import get_db, log_audit
from evidence import evidence_builder
from fastapi import APIRouter, Depends, HTTPException
from logging_config import get_logger
from models import (
    CommandAck,
    CommandRequest,
    ConfigResponse,
    DeviceRegistration,
    HealthResponse,
    HeartbeatPacket,
    LocationReport,
    MediaReport,
    OfflineQueueUpload,
    RefreshRequest,
    TelemetryPing,
)
from pydantic import BaseModel
from sentinel import sentinel
from websocket_manager import broadcast_to_dashboards

logger = get_logger("magneetar")

router = APIRouter()


# ─── Device Registration ─────────────────────────────────────────────────────


@router.post("/api/device/register")
async def register_device(
    reg: DeviceRegistration, db: sqlite3.Connection = Depends(get_db), x_api_key: str = Depends(verify_api_key)
):
    """Register a new device and get JWT tokens. Requires API key."""
    now = datetime.now(timezone.utc).isoformat()
    device_key_hash = None
    if reg.device_key:
        device_key_hash = hash_device_key(reg.device_key)

    existing = db.execute("SELECT id FROM devices WHERE id=?", (reg.device_id,)).fetchone()

    if existing:
        db.execute(
            """UPDATE devices
               SET device_fingerprint=?, model=?, os_version=?,
                   app_version=?, imei_hash=?, sim_serial_hash=?,
                   device_key_hash=COALESCE(?, device_key_hash), last_seen=?
               WHERE id=?""",
            (
                reg.fingerprint,
                reg.model,
                reg.os_version,
                reg.app_version,
                reg.imei_hash,
                reg.sim_serial_hash,
                device_key_hash,
                now,
                reg.device_id,
            ),
        )
    else:
        db.execute(
            """INSERT INTO devices (id, device_fingerprint, model, os_version,
               app_version, imei_hash, sim_serial_hash, device_key_hash, last_seen, registered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reg.device_id,
                reg.fingerprint,
                reg.model,
                reg.os_version,
                reg.app_version,
                reg.imei_hash,
                reg.sim_serial_hash,
                device_key_hash,
                now,
                now,
            ),
        )

    db.commit()
    tokens = create_device_tokens(reg.device_id)
    log_audit("device_registered", actor=reg.device_id, details=reg.model)

    return {
        **tokens,
        "has_device_key": device_key_hash is not None,
        "server_time": now,
    }


# ─── Location Reports ────────────────────────────────────────────────────────


@router.post("/api/device/location")
async def post_location(
    report: TelemetryPing, db: sqlite3.Connection = Depends(get_db), device_id: str = Depends(get_current_device_or_key)
):
    """Receive telemetry ping from device."""
    if report.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    if not check_location_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    is_valid, reason = sentinel.validate_report(report, None)
    if not is_valid:
        log_audit("invalid_location_report", actor=device_id, details=reason)

    now = datetime.now(timezone.utc).isoformat()
    ts = report.device_timestamp or now

    history = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10", (device_id,)
    ).fetchall()

    history_dicts = [dict(h) for h in history]
    score, threat_level, anomalies = sentinel.compute_score(report, history_dicts)

    db.execute(
        """INSERT INTO locations (device_id, lat, lng, altitude, accuracy_horizontal,
           accuracy_vertical, confidence_level, speed, bearing, activity_type,
           step_count, provider, gps_satellite_count, wifi_bssids, cell_tower_ids,
           ble_devices_nearby, battery_percent, is_charging, network_type,
           signal_strength_dbm, is_location_enabled, is_airplane_mode,
           sim_changed, sim_serial_hash, sentinel_score, threat_level, anomalies,
           device_timestamp, server_timestamp, was_queued, queued_at,
           queue_position, ping_sequence)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            device_id,
            report.lat,
            report.lng,
            report.altitude,
            report.accuracy_horizontal,
            report.accuracy_vertical,
            report.confidence_level,
            report.speed,
            report.bearing,
            report.activity_type,
            report.step_count,
            report.provider,
            report.gps_satellite_count,
            json.dumps(report.wifi_bssids or []),
            json.dumps(report.cell_tower_ids or []),
            report.ble_devices_nearby,
            report.battery_percent,
            report.is_charging,
            report.network_type,
            report.signal_strength_dbm,
            report.is_location_enabled,
            report.is_airplane_mode,
            report.sim_changed,
            report.sim_serial_hash,
            score,
            threat_level,
            json.dumps(anomalies or []),
            ts,
            now,
            report.was_queued,
            report.queued_at,
            report.queue_position,
            report.ping_sequence,
        ),
    )

    db.execute("UPDATE devices SET last_seen=?, sentinel_score=? WHERE id=?", (now, score, device_id))
    db.commit()

    if score >= settings.THEFT_SCORE_THRESHOLD:
        sentinel.auto_activate_theft_mode(device_id, score)
        await alert_engine.send_all(
            device_id, "theft_detected", {"location": f"{report.lat},{report.lng}", "time": now, "score": score}
        )

    geofences = db.execute("SELECT * FROM geofences WHERE device_id=? AND active=1", (device_id,)).fetchall()

    if geofences:
        triggered = sentinel.check_geofences(report, [dict(g) for g in geofences])
        for event in triggered:
            if event["event"] == "exited" and not event["is_safe_zone"]:
                await alert_engine.send_all(
                    device_id,
                    "geofence_exit",
                    {"zone_name": event["name"], "location": f"{report.lat},{report.lng}", "time": now},
                )

    await broadcast_to_dashboards(
        {
            "type": "location",
            "data": {
                "device_id": device_id,
                "lat": report.lat,
                "lng": report.lng,
                "speed": report.speed,
                "battery": report.battery_percent,
                "sentinel_score": score,
                "threat_level": threat_level,
                "timestamp": now,
            },
        }
    )

    commands = db.execute(
        "SELECT id, command, params, priority FROM commands WHERE device_id=? AND status='pending' ORDER BY priority",
        (device_id,),
    ).fetchall()

    return {
        "status": "ok",
        "commands_pending": len(commands),
        "server_time": now,
    }


@router.post("/api/device/location/simple")
async def post_location_simple(
    report: LocationReport,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Simplified location report for basic tracking."""
    now = datetime.now(timezone.utc).isoformat()
    ts = report.timestamp or now

    db.execute(
        "INSERT INTO locations (device_id, lat, lng, accuracy, provider, device_timestamp, server_timestamp) VALUES (?,?,?,?,?,?,?)",
        (device_id, report.lat, report.lng, report.accuracy, report.provider, ts, now),
    )
    db.execute("UPDATE devices SET last_seen=? WHERE id=?", (now, device_id))
    db.commit()

    return {"status": "ok", "server_time": now}


# ─── Media Uploads ───────────────────────────────────────────────────────────


@router.post("/api/device/media")
async def post_media(
    report: MediaReport, db: sqlite3.Connection = Depends(get_db), device_id: str = Depends(get_current_device_or_key)
):
    """Upload media (photo/audio) from device."""
    if report.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    if not check_media_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Media upload rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()
    ts = report.timestamp or now

    data = base64.b64decode(report.data_b64)
    sha256_hash = hashlib.sha256(data).hexdigest()

    case = db.execute(
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()

    case_id = case["id"] if case else None

    db.execute(
        """INSERT INTO media (device_id, type, data_b64, lat, lng, timestamp,
           evidence_case_id, sha256_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, report.type, report.data_b64, report.lat, report.lng, ts, case_id, sha256_hash),
    )
    db.commit()

    media_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    if case_id:
        evidence_builder.add_media_to_case(case_id, report.type, report.data_b64)

    await broadcast_to_dashboards(
        {
            "type": "media",
            "data": {
                "device_id": device_id,
                "media_id": media_id,
                "type": report.type,
                "timestamp": ts,
            },
        }
    )

    return {
        "status": "ok",
        "media_id": media_id,
        "evidence_case_id": case_id,
    }


# ─── Commands (Device Polling) ───────────────────────────────────────────────


@router.get("/api/device/commands/{device_id}")
async def get_device_commands(
    device_id: str, db: sqlite3.Connection = Depends(get_db), token_device_id: str = Depends(get_current_device_or_key)
):
    """Poll for pending commands."""
    if device_id != token_device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    if not check_command_poll_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Command poll rate limit exceeded")

    rows = db.execute(
        """SELECT id, command, params, priority
           FROM commands
           WHERE device_id=? AND status='pending'
           AND (expires_at IS NULL OR expires_at > datetime('now'))
           ORDER BY priority ASC""",
        (device_id,),
    ).fetchall()

    return {"commands": [dict(r) for r in rows]}


@router.post("/api/device/commands/{command_id}/ack")
async def ack_command(
    command_id: int,
    ack: CommandAck,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Acknowledge command execution."""
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "UPDATE commands SET status=?, executed_at=? WHERE id=? AND device_id=?",
        (ack.status, now, command_id, device_id),
    )
    db.commit()

    await broadcast_to_dashboards(
        {
            "type": "command_ack",
            "data": {
                "command_id": command_id,
                "device_id": device_id,
                "status": ack.status,
            },
        }
    )

    return {"status": "ok"}


# ─── Heartbeat ───────────────────────────────────────────────────────────────


@router.post("/api/device/heartbeat")
async def post_heartbeat(
    hb: HeartbeatPacket, db: sqlite3.Connection = Depends(get_db), device_id: str = Depends(get_current_device_or_key)
):
    """Receive heartbeat from device."""
    if hb.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    if not check_heartbeat_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Heartbeat rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO heartbeats (device_id, timestamp, battery_percent, is_charging,
           network_type, device_admin_active, sim_hash, app_version, pending_evidence_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            device_id,
            now,
            hb.battery_percent,
            hb.is_charging,
            hb.network_type,
            hb.device_admin_active,
            hb.sim_hash,
            hb.app_version,
            hb.pending_evidence_count,
        ),
    )

    db.execute("UPDATE devices SET last_seen=?, app_version=? WHERE id=?", (now, hb.app_version, device_id))

    if hb.device_admin_active is False:
        sentinel.auto_activate_theft_mode(device_id, 40)

    db.commit()

    device = db.execute("SELECT operating_mode FROM devices WHERE id=?", (device_id,)).fetchone()

    return {
        "status": "ok",
        "operating_mode": device["operating_mode"] if device else "normal",
        "server_time": now,
    }


# ─── Token Refresh ───────────────────────────────────────────────────────────


@router.post("/api/device/refresh")
async def refresh_token(req: RefreshRequest):
    """Refresh JWT tokens."""
    return refresh_access_token(req.refresh_token)


# ─── Offline Queue ───────────────────────────────────────────────────────────


@router.post("/api/device/offline-queue")
async def upload_offline_queue(
    queue: OfflineQueueUpload,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key),
):
    """Batch upload of queued telemetry pings."""
    processed = 0

    for ping in queue.pings:
        if ping.device_id != device_id:
            continue

        now = datetime.now(timezone.utc).isoformat()
        ts = ping.device_timestamp or now

        history = db.execute(
            "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10", (device_id,)
        ).fetchall()
        history_dicts = [dict(h) for h in history]
        score, threat_level, anomalies = sentinel.compute_score(ping, history_dicts)

        db.execute(
            """INSERT INTO locations (device_id, lat, lng, altitude, accuracy_horizontal,
               confidence_level, speed, bearing, activity_type, provider,
               battery_percent, is_charging, network_type, sentinel_score,
               threat_level, anomalies, device_timestamp, server_timestamp, was_queued,
               queued_at, queue_position, ping_sequence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                device_id,
                ping.lat,
                ping.lng,
                ping.altitude,
                ping.accuracy_horizontal,
                ping.confidence_level,
                ping.speed,
                ping.bearing,
                ping.activity_type,
                ping.provider,
                ping.battery_percent,
                ping.is_charging,
                ping.network_type,
                score,
                threat_level,
                json.dumps(anomalies or []),
                ts,
                now,
                True,
                ping.queued_at,
                ping.queue_position,
                ping.ping_sequence,
            ),
        )
        processed += 1

    db.execute("UPDATE devices SET last_seen=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), device_id))
    db.commit()

    return {"status": "ok", "processed": processed}


# ─── FCM Token Registration ─────────────────────────────────────────────────


class FCMTokenRequest(BaseModel):
    fcm_token: str
    device_id: str = ""
    platform: Optional[str] = "android"


@router.post("/api/device/fcm-token")
async def register_fcm_token(
    req: FCMTokenRequest,
    db: sqlite3.Connection = Depends(get_db),
    resolved_device_id: str = Depends(get_current_device_or_key),
):
    """Register an FCM push notification token for a device."""
    now = datetime.now(timezone.utc).isoformat()

    device_id = resolved_device_id
    if device_id == "api_key_user" or not device_id:
        device_id = req.device_id.strip() if req.device_id else ""
    if not device_id:
        device_id = "broadcast"

    existing = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not existing:
        db.execute(
            """INSERT INTO devices (id, device_fingerprint, model, platform, registered, last_seen)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (device_id, f"fcm_{device_id}", "FCM Relay", "push_service", now, now),
        )
        db.commit()

    db.execute(
        """INSERT INTO fcm_tokens (device_id, fcm_token, platform, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(device_id, fcm_token) DO UPDATE SET updated_at=?""",
        (device_id, req.fcm_token, req.platform, now, now),
    )
    db.commit()

    logger.info("FCM token registered", extra={"extra_data": {"device_id": device_id, "platform": req.platform}})

    return {"status": "ok", "message": "FCM token registered", "device_id": device_id}
