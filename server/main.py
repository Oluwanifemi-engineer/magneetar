"""
Magneetar Server — Complete API
All endpoints for device communication and dashboard control.
"""
from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import json
import asyncio
from datetime import datetime, timezone, timedelta
import hashlib
import time
from config import settings
from database import get_db, log_audit, check_rate_limit, log_error
from models import (
    DeviceRegistration, TelemetryPing, LocationReport, OfflineQueueUpload,
    MediaReport, CommandRequest, CommandAck, HeartbeatPacket,
    LoginRequest, RefreshRequest, GeofenceRequest, AlertSettings,
    HealthResponse, ConfigResponse, DashboardStats, TokenResponse,
    DeviceResponse, Command, MediaItem, Alert, EvidenceCase, Geofence
)
from auth import (
    create_device_tokens, create_dashboard_tokens, refresh_access_token,
    verify_api_key, get_current_device, get_current_dashboard,
    require_dashboard_auth, check_login_rate_limit, check_location_rate_limit,
    check_command_rate_limit, check_media_rate_limit,
    check_heartbeat_rate_limit, check_command_poll_rate_limit,
    get_current_device_or_key, hash_device_key, decode_token
)
from encryption import get_encryption
from sentinel import sentinel
from alerts import alert_engine
from evidence import evidence_builder
from user_auth import router as user_auth_router
from contextlib import asynccontextmanager
from logging_config import get_logger

logger = get_logger("magneetar")

# ── Sentry Initialization (optional) ────────────────────────────────────────
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            traces_sample_rate=0.2 if settings.ENVIRONMENT == "production" else 0.0,
            profiles_sample_rate=0.1 if settings.ENVIRONMENT == "production" else 0.0,
            integrations=[
                FastApiIntegration(),
                LoggingIntegration(level=None, event_level=None),
            ],
            send_default_pii=False,
            release="magneetar@1.0.0",
        )
        logger.info("Sentry initialized for error tracking", extra={"extra_data": {"environment": settings.ENVIRONMENT}})
except ImportError:
    pass
except Exception as e:
    logger.warning(f"Sentry initialization failed: {e}")

# ─── Lifespan Handler ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown."""
    # ── Validate configuration on startup ──────────────────────────────────
    config_errors = settings.validate()
    if config_errors:
        logger.error("FATAL: Configuration errors detected:")
        for err in config_errors:
            logger.error(f"  ❌ {err}")
        logger.error("")
        logger.error("Fix: Run './scripts/generate-env.sh' to generate secure secrets,")
        logger.error("     then edit server/.env with your alert service credentials.")
        raise RuntimeError(f"Server cannot start: {len(config_errors)} configuration errors")

    logger.info(
        "Magneetar server starting",
        extra={"extra_data": {
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "host": settings.HOST,
            "port": settings.PORT,
            "database": "PostgreSQL" if settings.DATABASE_URL else "SQLite",
            "retention_days": settings.DATA_RETENTION_DAYS,
            "max_devices": settings.MAX_DEVICES_PER_USER,
        }}
    )

    # ── PostgreSQL Setup (optional) ────────────────────────────────────────
    pg_connected = False
    if settings.DATABASE_URL:
        try:
            from database_postgres import get_postgres_db, is_postgres_configured
            if is_postgres_configured():
                pg = await get_postgres_db()
                if pg.is_connected:
                    pg_connected = True
                    logger.info("PostgreSQL connected and schema initialized")
        except Exception as e:
            logger.warning(f"PostgreSQL setup failed, falling back to SQLite: {e}")

    if not pg_connected:
        logger.info(f"Using SQLite database: {settings.DB_PATH}")

    # ── Data Retention Cleanup (non-blocking) ──────────────────────────────
    async def run_cleanup():
        try:
            if pg_connected:
                from database_postgres import get_postgres_db
                pg = await get_postgres_db()
                result = await pg.purge_old_data(settings.DATA_RETENTION_DAYS)
                logger.info(f"Data retention cleanup: {result}")
            else:
                from database import purge_old_data
                result = await asyncio.to_thread(purge_old_data, settings.DATA_RETENTION_DAYS)
                if result:
                    total_purged = sum(result.values())
                    logger.info(f"Data retention cleanup: {total_purged} records purged", extra={"extra_data": result})
        except Exception as e:
            logger.warning(f"Data retention cleanup skipped: {e}")

    asyncio.create_task(run_cleanup())

    # ── Scheduled Rate Limit Cleanup (every 6 hours) ────────────────────
    async def periodic_rate_limit_cleanup():
        """Background task to clean up stale rate limit entries."""
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6 hours
                # Check PostgreSQL availability dynamically (handles connection failures)
                use_pg = False
                try:
                    from database_postgres import get_postgres_db, is_postgres_configured
                    if is_postgres_configured():
                        pg = await get_postgres_db()
                        if pg.is_connected:
                            use_pg = True
                except Exception:
                    pass

                if use_pg:
                    await pg.execute("DELETE FROM rate_limits WHERE timestamp < NOW() - interval '7 days'")
                    logger.info("Rate limit cleanup (PostgreSQL): purged entries older than 7 days")
                else:
                    from database import get_db_context
                    with get_db_context() as conn:
                        conn.execute("DELETE FROM rate_limits WHERE timestamp < datetime('now', '-7 days')")
                        conn.commit()
                    logger.info("Rate limit cleanup (SQLite): purged entries older than 7 days")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Rate limit cleanup failed: {e}")

    cleanup_task = asyncio.create_task(periodic_rate_limit_cleanup())
    yield
    cleanup_task.cancel()

    logger.info("Magneetar server shutting down")

    # Cleanup PostgreSQL connection if active
    try:
        from database_postgres import close_postgres_db
        await close_postgres_db()
    except:
        pass

    active_dashboard_connections.clear()


# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Magneetar API",
    version="1.0.0",
    description="Anti-theft tracking system API",
    lifespan=lifespan
)

# CORS — permissive in dev, strict in production
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            # Production domains
            "https://magneetar.me",
            "https://app.magneetar.me",
            "https://api.magneetar.me",
            # Localhost for development
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Device-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Track server start time
SERVER_START = time.time()

# Active WebSocket connections
active_dashboard_connections: list[WebSocket] = []

# Include user auth routes
app.include_router(user_auth_router)


# ─── Request Timing & Error Tracking Middleware ────────────────────────────

@app.middleware("http")
async def monitor_request_time(request: Request, call_next):
    """Log request duration and catch unhandled exceptions for dashboard."""
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        duration = time.time() - start_time
        
        # Log slow requests (>1s)
        if duration > 1.0:
            logger.warning(
                "Slow request detected",
                extra={"extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 1),
                    "status_code": response.status_code,
                }}
            )
        
        # Add server timing header
        response.headers["X-Process-Time-Ms"] = str(round(duration * 1000, 1))
        
        return response
        
    except Exception as e:
        # Catch unhandled exceptions and log to database
        import traceback as tb
        duration = time.time() - start_time
        error_tb = "".join(tb.format_exception(type(e), e, e.__traceback__))
        
        # Get client IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        cf_ip = request.headers.get("CF-Connecting-IP", "")
        if cf_ip:
            client_ip = cf_ip
        elif forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        # Store in database
        log_error(
            level="CRITICAL" if getattr(e, "status_code", 500) >= 500 else "ERROR",
            message=f"{type(e).__name__}: {str(e)}",
            source="middleware",
            traceback=error_tb,
            request_method=request.method,
            request_path=request.url.path,
            request_ip=client_ip,
            user_agent=request.headers.get("User-Agent", ""),
        )
        
        # Log to server logs
        logger.error(
            f"Unhandled error: {type(e).__name__}: {e}",
            extra={"extra_data": {
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration * 1000, 1),
            }}
        )
        
        # Re-raise for FastAPI to handle (returns 500)
        raise


# ─── WebSocket Manager ──────────────────────────────────────────────────────

async def broadcast_to_dashboards(message: dict):
    """Send message to all connected dashboard clients."""
    dead = []
    for ws in active_dashboard_connections:
        try:
            await ws.send_json(message)
        except:
            dead.append(ws)
    for ws in dead:
        active_dashboard_connections.remove(ws)


# ─── Health & Config ────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health():
    """Public health endpoint."""
    return HealthResponse(
        status="online",
        version="1.0.0",
        uptime=time.time() - SERVER_START,
        server_time=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Public config endpoint for mobile apps."""
    return ConfigResponse()


# ─── Device Registration ─────────────────────────────────────────────────────

@app.post("/api/device/register")
async def register_device(
    reg: DeviceRegistration,
    db: sqlite3.Connection = Depends(get_db),
    x_api_key: str = Depends(verify_api_key)
):
    """Register a new device and get JWT tokens. Requires API key.
    The device can optionally provide a device_key — a unique secret generated
    by the device itself. The server stores only its SHA-256 hash.
    All subsequent calls can use x-device-key header for auth instead of
    the shared API key.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Hash the device key if provided (unique per-device secret)
    device_key_hash = None
    if reg.device_key:
        device_key_hash = hash_device_key(reg.device_key)

    # Check if device already exists
    existing = db.execute("SELECT id FROM devices WHERE id=?", (reg.device_id,)).fetchone()

    if existing:
        # Update existing device
        db.execute(
            """UPDATE devices 
               SET device_fingerprint=?, model=?, os_version=?, 
                   app_version=?, imei_hash=?, sim_serial_hash=?, 
                   device_key_hash=COALESCE(?, device_key_hash), last_seen=?
               WHERE id=?""",
            (reg.fingerprint, reg.model, reg.os_version, reg.app_version,
             reg.imei_hash, reg.sim_serial_hash, device_key_hash, now, reg.device_id)
        )
    else:
        # Register new device
        db.execute(
            """INSERT INTO devices (id, device_fingerprint, model, os_version, 
               app_version, imei_hash, sim_serial_hash, device_key_hash, last_seen, registered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (reg.device_id, reg.fingerprint, reg.model, reg.os_version,
             reg.app_version, reg.imei_hash, reg.sim_serial_hash,
             device_key_hash, now, now)
        )

    db.commit()

    # Generate tokens
    tokens = create_device_tokens(reg.device_id)

    log_audit("device_registered", actor=reg.device_id, details=reg.model)

    return {
        **tokens,
        "has_device_key": device_key_hash is not None,
        "server_time": now,
    }


# ─── Device Location ────────────────────────────────────────────────────────

@app.post("/api/device/location")
async def post_location(
    report: TelemetryPing,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Receive telemetry ping from device."""
    # Verify device_id matches token
    if report.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    # Rate limit check
    if not check_location_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Validate report
    is_valid, reason = sentinel.validate_report(report, None)
    if not is_valid:
        log_audit("invalid_location_report", actor=device_id, details=reason)
        # Still store but flag it

    now = datetime.now(timezone.utc).isoformat()
    ts = report.device_timestamp or now

    # Get recent history for Sentinel
    history = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10",
        (device_id,)
    ).fetchall()

    # Run Sentinel (convert Row objects to dicts for sentinel engine)
    history_dicts = [dict(h) for h in history]
    score, threat_level, anomalies = sentinel.compute_score(report, history_dicts)

    # Store location
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
            device_id, report.lat, report.lng, report.altitude,
            report.accuracy_horizontal, report.accuracy_vertical,
            report.confidence_level, report.speed, report.bearing,
            report.activity_type, report.step_count, report.provider,
            report.gps_satellite_count, json.dumps(report.wifi_bssids),
            json.dumps(report.cell_tower_ids), report.ble_devices_nearby,
            report.battery_percent, report.is_charging, report.network_type,
            report.signal_strength_dbm, report.is_location_enabled,
            report.is_airplane_mode, report.sim_changed, report.sim_serial_hash,
            score, threat_level, json.dumps(anomalies),
            ts, now, report.was_queued, report.queued_at,
            report.queue_position, report.ping_sequence
        )
    )

    # Update device (auto_activate_theft_mode handles 'stolen' mode)
    db.execute(
        """UPDATE devices 
           SET last_seen=?, sentinel_score=?
           WHERE id=?""",
        (now, score, device_id)
    )

    db.commit()

    # Auto-activate theft mode if needed (sets operating_mode='stolen')
    if score >= settings.THEFT_SCORE_THRESHOLD:
        sentinel.auto_activate_theft_mode(device_id, score)
        # Send theft alerts
        await alert_engine.send_all(
            device_id, "theft_detected",
            {"location": f"{report.lat},{report.lng}", "time": now, "score": score}
        )

    # Check geofences
    geofences = db.execute(
        "SELECT * FROM geofences WHERE device_id=? AND active=1",
        (device_id,)
    ).fetchall()

    if geofences:
        triggered = sentinel.check_geofences(report, [dict(g) for g in geofences])
        for event in triggered:
            if event["event"] == "exited" and not event["is_safe_zone"]:
                # Alert owner
                await alert_engine.send_all(
                    device_id, "geofence_exit",
                    {"zone_name": event["name"], "location": f"{report.lat},{report.lng}",
                     "time": now}
                )

    # Broadcast to dashboards
    await broadcast_to_dashboards({
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
        }
    })

    # Get pending commands
    commands = db.execute(
        "SELECT id, command, params, priority FROM commands WHERE device_id=? AND status='pending' ORDER BY priority",
        (device_id,)
    ).fetchall()

    return {
        "status": "ok",
        "commands_pending": len(commands),
        "server_time": now,
    }


# ─── Simple Location Report (backward compat) ────────────────────────────────

@app.post("/api/device/location/simple")
async def post_location_simple(
    report: LocationReport,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Simplified location report for basic tracking."""
    now = datetime.now(timezone.utc).isoformat()
    ts = report.timestamp or now

    db.execute(
        "INSERT INTO locations (device_id, lat, lng, accuracy, provider, device_timestamp, server_timestamp) VALUES (?,?,?,?,?,?,?)",
        (device_id, report.lat, report.lng, report.accuracy, report.provider, ts, now)
    )
    db.execute(
        "UPDATE devices SET last_seen=? WHERE id=?",
        (now, device_id)
    )
    db.commit()

    return {"status": "ok", "server_time": now}


# ─── Device Media Upload ─────────────────────────────────────────────────────

@app.post("/api/device/media")
async def post_media(
    report: MediaReport,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Upload media (photo/audio) from device."""
    if report.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    # Rate limit check
    if not check_media_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Media upload rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()
    ts = report.timestamp or now

    # Compute hash
    import base64
    data = base64.b64decode(report.data_b64)
    sha256_hash = hashlib.sha256(data).hexdigest()

    # Find or create evidence case
    case = db.execute(
        "SELECT id FROM evidence_cases WHERE device_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
        (device_id,)
    ).fetchone()

    case_id = case["id"] if case else None

    db.execute(
        """INSERT INTO media (device_id, type, data_b64, lat, lng, timestamp, 
           evidence_case_id, sha256_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, report.type, report.data_b64,
         report.lat, report.lng, ts, case_id, sha256_hash)
    )
    db.commit()

    media_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Update evidence case
    if case_id:
        evidence_builder.add_media_to_case(case_id, report.type, report.data_b64)

    # Broadcast to dashboards
    await broadcast_to_dashboards({
        "type": "media",
        "data": {
            "device_id": device_id,
            "media_id": media_id,
            "type": report.type,
            "timestamp": ts,
        }
    })

    return {
        "status": "ok",
        "media_id": media_id,
        "evidence_case_id": case_id,
    }


# ─── Device Commands ─────────────────────────────────────────────────────────

@app.get("/api/device/commands/{device_id}")
async def get_device_commands(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    token_device_id: str = Depends(get_current_device_or_key)
):
    """Poll for pending commands."""
    if device_id != token_device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    # Rate limit check
    if not check_command_poll_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Command poll rate limit exceeded")

    rows = db.execute(
        """SELECT id, command, params, priority 
           FROM commands 
           WHERE device_id=? AND status='pending' 
           AND (expires_at IS NULL OR expires_at > datetime('now'))
           ORDER BY priority ASC""",
        (device_id,)
    ).fetchall()

    return {"commands": [dict(r) for r in rows]}


@app.post("/api/device/commands/{command_id}/ack")
async def ack_command(
    command_id: int,
    ack: CommandAck,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Acknowledge command execution."""
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        "UPDATE commands SET status=?, executed_at=? WHERE id=? AND device_id=?",
        (ack.status, now, command_id, device_id)
    )
    db.commit()

    # Broadcast to dashboards
    await broadcast_to_dashboards({
        "type": "command_ack",
        "data": {
            "command_id": command_id,
            "device_id": device_id,
            "status": ack.status,
        }
    })

    return {"status": "ok"}


# ─── Device Heartbeat ────────────────────────────────────────────────────────

@app.post("/api/device/heartbeat")
async def post_heartbeat(
    hb: HeartbeatPacket,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Receive heartbeat from device."""
    if hb.device_id != device_id:
        raise HTTPException(status_code=403, detail="Device ID mismatch")

    # Rate limit check
    if not check_heartbeat_rate_limit(device_id):
        raise HTTPException(status_code=429, detail="Heartbeat rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO heartbeats (device_id, timestamp, battery_percent, is_charging,
           network_type, device_admin_active, sim_hash, app_version, pending_evidence_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, now, hb.battery_percent, hb.is_charging,
         hb.network_type, hb.device_admin_active, hb.sim_hash,
         hb.app_version, hb.pending_evidence_count)
    )

    # Update device
    db.execute(
        "UPDATE devices SET last_seen=?, app_version=? WHERE id=?",
        (now, hb.app_version, device_id)
    )

    # Check if device admin is disabled (theft signal)
    if hb.device_admin_active is False:
        # This is a serious theft indicator
        sentinel.auto_activate_theft_mode(device_id, 40)

    db.commit()

    # Get current operating mode
    device = db.execute(
        "SELECT operating_mode FROM devices WHERE id=?", (device_id,)
    ).fetchone()

    return {
        "status": "ok",
        "operating_mode": device["operating_mode"] if device else "normal",
        "server_time": now,
    }


# ─── Token Refresh ───────────────────────────────────────────────────────────

@app.post("/api/device/refresh")
async def refresh_token(req: RefreshRequest):
    """Refresh JWT tokens."""
    return refresh_access_token(req.refresh_token)


# ─── Offline Queue Upload ────────────────────────────────────────────────────

@app.post("/api/device/offline-queue")
async def upload_offline_queue(
    queue: OfflineQueueUpload,
    db: sqlite3.Connection = Depends(get_db),
    device_id: str = Depends(get_current_device_or_key)
):
    """Batch upload of queued telemetry pings."""
    processed = 0

    for ping in queue.pings:
        if ping.device_id != device_id:
            continue

        now = datetime.now(timezone.utc).isoformat()
        ts = ping.device_timestamp or now

        # Run Sentinel on each queued ping
        history = db.execute(
            "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10",
            (device_id,)
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
                device_id, ping.lat, ping.lng, ping.altitude,
                ping.accuracy_horizontal, ping.confidence_level,
                ping.speed, ping.bearing, ping.activity_type, ping.provider,
                ping.battery_percent, ping.is_charging, ping.network_type,
                score, threat_level, json.dumps(anomalies),
                ts, now, True, ping.queued_at, ping.queue_position, ping.ping_sequence
            )
        )
        processed += 1

    db.execute(
        "UPDATE devices SET last_seen=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), device_id)
    )
    db.commit()

    return {"status": "ok", "processed": processed}


# ─── Dashboard Auth ──────────────────────────────────────────────────────────

@app.post("/api/auth/login", response_model=TokenResponse)
async def dashboard_login(
    req: LoginRequest,
    request: Request
):
    """Dashboard login with API key. Rate-limited by real client IP."""
    # Get real client IP (supporting reverse proxy / Cloudflare)
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

    # Verify API key
    if req.api_key != settings.API_KEY:
        log_audit("login_failed", details=f"Invalid API key from IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    log_audit("dashboard_login", actor="dashboard")
    return create_dashboard_tokens(req.api_key)


@app.post("/api/auth/refresh", response_model=TokenResponse)
async def dashboard_refresh(req: RefreshRequest):
    """Refresh dashboard tokens."""
    return refresh_access_token(req.refresh_token)


# ─── Dashboard: Devices ──────────────────────────────────────────────────────

@app.get("/api/dashboard/devices")
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
        # Check if online (seen in last 5 minutes)
        is_online = False
        if d["last_seen"]:
            try:
                last_seen = datetime.fromisoformat(d["last_seen"])
                is_online = (datetime.now(timezone.utc) - last_seen).total_seconds() < 300
            except:
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


# ─── Dashboard: Locations ────────────────────────────────────────────────────

@app.get("/api/dashboard/locations/{device_id}")
async def get_locations(
    device_id: str,
    limit: int = Query(200, ge=1, le=1000),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get location history for a device."""
    rows = db.execute(
        """SELECT * FROM locations 
           WHERE device_id=? 
           ORDER BY server_timestamp DESC 
           LIMIT ?""",
        (device_id, limit)
    ).fetchall()

    return {"locations": [dict(r) for r in rows]}


@app.get("/api/dashboard/locations/{device_id}/live")
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


# ─── Dashboard: Media ────────────────────────────────────────────────────────

@app.get("/api/dashboard/media/{device_id}")
async def get_media_list(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get media list (thumbnails) for a device."""
    rows = db.execute(
        """SELECT id, device_id, type, timestamp, lat, lng 
           FROM media 
           WHERE device_id=? 
           ORDER BY timestamp DESC""",
        (device_id,)
    ).fetchall()

    return {"media": [dict(r) for r in rows]}


@app.get("/api/dashboard/media/file/{media_id}")
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


# ─── Dashboard: Commands ─────────────────────────────────────────────────────

@app.post("/api/dashboard/command")
async def issue_command(
    cmd: CommandRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Issue a command to a device."""
    # Rate limit check
    if not check_command_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    # Special handling for wipe command
    if cmd.command == "wipe":
        # Check for confirmation parameter
        if cmd.params != "CONFIRMED_WIPE":
            raise HTTPException(
                status_code=400,
                detail="Wipe requires params='CONFIRMED_WIPE'"
            )

    # Set expiry (1 hour for normal commands, 5 minutes for critical)
    expires_minutes = 5 if cmd.command in ('wipe', 'lock', 'alarm') else 60
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).isoformat()

    cur = db.execute(
        """INSERT INTO commands (device_id, command, params, priority, issued_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (cmd.device_id, cmd.command, cmd.params, cmd.priority, now, expires_at)
    )
    db.commit()

    command_id = cur.lastrowid

    log_audit(
        "command_issued",
        actor=auth,
        details=f"Command: {cmd.command} to {cmd.device_id}"
    )

    return {"status": "queued", "command_id": command_id}


@app.get("/api/dashboard/commands/{device_id}")
async def get_command_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get command history for a device."""
    rows = db.execute(
        """SELECT * FROM commands 
           WHERE device_id=? 
           ORDER BY issued_at DESC 
           LIMIT 50""",
        (device_id,)
    ).fetchall()

    return {"commands": [dict(r) for r in rows]}


# ─── Dashboard: Evidence ─────────────────────────────────────────────────────

@app.get("/api/dashboard/evidence/{device_id}")
async def get_evidence(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get evidence case for a device."""
    case = db.execute(
        """SELECT * FROM evidence_cases 
           WHERE device_id=? 
           ORDER BY created_at DESC 
           LIMIT 1""",
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


@app.post("/api/dashboard/evidence/{device_id}/generate-pdf")
async def generate_evidence_pdf(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Generate evidence PDF for a device."""
    case = db.execute(
        """SELECT id FROM evidence_cases 
           WHERE device_id=? AND status='active'
           ORDER BY created_at DESC LIMIT 1""",
        (device_id,)
    ).fetchone()

    if not case:
        # Create a new case
        case_id = evidence_builder.create_case(device_id)
    else:
        case_id = case["id"]

    # Get compiled evidence data
    pdf_data = evidence_builder.compile_pdf_data(case_id)
    if not pdf_data:
        raise HTTPException(status_code=404, detail="No evidence data found")

    # In production, generate actual PDF here
    # For now, return the compiled data
    return {
        "case_id": case_id,
        "status": "generated",
        "data": pdf_data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Dashboard: Alerts ───────────────────────────────────────────────────────

@app.get("/api/dashboard/alerts/{device_id}")
async def get_alerts(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get alert history for a device."""
    rows = db.execute(
        """SELECT * FROM alerts 
           WHERE device_id=? 
           ORDER BY sent_at DESC 
           LIMIT 50""",
        (device_id,)
    ).fetchall()

    return {"alerts": [dict(r) for r in rows]}


# ─── Dashboard: Geofences ────────────────────────────────────────────────────

@app.post("/api/dashboard/geofence")
async def create_geofence(
    fence: GeofenceRequest,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Create a geofence for a device."""
    cur = db.execute(
        """INSERT INTO geofences (device_id, name, center_lat, center_lng, 
           radius_meters, is_safe_zone)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (fence.device_id, fence.name, fence.center_lat, fence.center_lng,
         fence.radius_meters, fence.is_safe_zone)
    )
    db.commit()

    return {"status": "ok", "geofence_id": cur.lastrowid}


@app.delete("/api/dashboard/geofence/{geofence_id}")
async def delete_geofence(
    geofence_id: int,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Delete a geofence."""
    db.execute("DELETE FROM geofences WHERE id=?", (geofence_id,))
    db.commit()
    return {"status": "ok"}


@app.get("/api/dashboard/geofences/{device_id}")
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


# ─── Dashboard: Stats ────────────────────────────────────────────────────────

@app.get("/api/dashboard/stats")
async def get_stats(
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get dashboard statistics."""
    # Check if PostgreSQL is available
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
        # SQLite fallback
        total_devices = db.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        active_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE last_seen > datetime('now', '-5 minutes')"
        ).fetchone()[0]
        stolen_devices = db.execute(
            "SELECT COUNT(*) FROM devices WHERE is_stolen=1"
        ).fetchone()[0]
        total_locations = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        total_media = db.execute("SELECT COUNT(*) FROM media").fetchone()[0]
        today = datetime.now(timezone.utc).date().isoformat()
        alerts_today = db.execute(
            "SELECT COUNT(*) FROM alerts WHERE sent_at > ?",
            (today,)
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


# ─── Dashboard: Device Management ────────────────────────────────────────────

@app.patch("/api/dashboard/devices/{device_id}/alias")
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

    db.execute(
        "UPDATE devices SET alias=? WHERE id=?",
        (alias, device_id)
    )
    db.commit()

    log_audit("device_alias_updated", actor=auth, details=f"Device: {device_id}, Alias: {alias}")

    return {"status": "ok", "alias": alias}


@app.post("/api/dashboard/devices/{device_id}/recover")
async def mark_device_recovered(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Mark a stolen device as recovered."""
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """UPDATE devices 
           SET is_stolen=0, operating_mode='normal', sentinel_score=0
           WHERE id=?""",
        (device_id,)
    )

    # Close active evidence cases
    db.execute(
        """UPDATE evidence_cases 
           SET status='closed' 
           WHERE device_id=? AND status='active'""",
        (device_id,)
    )

    db.commit()

    log_audit("device_recovered", actor=auth, details=f"Device: {device_id}")

    return {"status": "ok", "message": "Device marked as recovered", "timestamp": now}


@app.get("/api/dashboard/devices/{device_id}/history")
async def get_device_history(
    device_id: str,
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """Get full device information including command and event history."""
    device = db.execute(
        "SELECT * FROM devices WHERE id=?", (device_id,)
    ).fetchone()

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Latest location
    location = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
        (device_id,)
    ).fetchone()

    # Command stats
    cmd_stats = db.execute(
        """SELECT status, COUNT(*) as count 
           FROM commands WHERE device_id=? 
           GROUP BY status""",
        (device_id,)
    ).fetchall()

    # Alert stats
    alert_count = db.execute(
        "SELECT COUNT(*) as count FROM alerts WHERE device_id=?",
        (device_id,)
    ).fetchone()[0]

    # Evidence case
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


# ─── Dashboard: Error Log ─────────────────────────────────────────────────

@app.get("/api/dashboard/errors")
async def list_errors(
    limit: int = Query(50, ge=1, le=500),
    unresolved_only: bool = Query(False),
    db: sqlite3.Connection = Depends(get_db),
    auth: str = Depends(require_dashboard_auth)
):
    """List server errors with optional filter for unresolved only."""
    if unresolved_only:
        rows = db.execute(
            """SELECT * FROM error_log 
               WHERE resolved=0
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT * FROM error_log 
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,)
        ).fetchall()

    # Count unresolved
    count_row = db.execute(
        "SELECT COUNT(*) as cnt FROM error_log WHERE resolved=0"
    ).fetchone()

    return {
        "errors": [dict(r) for r in rows],
        "unresolved_count": count_row["cnt"] if count_row else 0,
        "total_count": db.execute("SELECT COUNT(*) FROM error_log").fetchone()[0],
    }


@app.patch("/api/dashboard/errors/{error_id}/resolve")
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
        """UPDATE error_log 
           SET resolved=1, resolved_at=?, resolved_by=?, notes=?
           WHERE id=?""",
        (now, auth, notes, error_id)
    )
    db.commit()

    log_audit("error_resolved", actor=auth, details=f"Error #{error_id}: {notes}")

    return {"status": "ok", "message": f"Error #{error_id} marked as resolved"}


# ─── Dashboard: Replay ───────────────────────────────────────────────────────

@app.get("/api/dashboard/replay/{device_id}")
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


# ─── FCM Token Registration ────────────────────────────────────────────────

class FCMTokenRequest(BaseModel):
    fcm_token: str
    device_id: str = ""
    platform: Optional[str] = "android"


@app.post("/api/device/fcm-token")
async def register_fcm_token(
    req: FCMTokenRequest,
    db: sqlite3.Connection = Depends(get_db),
    _: str = Depends(get_current_device_or_key)
):
    """Register an FCM push notification token for a device.
    Called by the Android MagneetarMessagingService on new token.
    The Android app sends its device_id (from SharedPreferences) so
    alerts can be properly routed to the right notification devices.
    Falls back to 'broadcast' if no device_id provided.
    Auth: device key, JWT, or shared API key.
    """
    now = datetime.now(timezone.utc).isoformat()
    resolved_id = req.device_id.strip() if req.device_id else ""
    if not resolved_id:
        resolved_id = "broadcast"

    db.execute(
        """INSERT INTO fcm_tokens (device_id, fcm_token, platform, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(device_id, fcm_token) DO UPDATE SET updated_at=?""",
        (resolved_id, req.fcm_token, req.platform, now, now)
    )
    db.commit()

    logger.info("FCM token registered", extra={"extra_data": {"device_id": resolved_id, "platform": req.platform}})

    return {"status": "ok", "message": "FCM token registered"}


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for real-time dashboard updates."""
    await websocket.accept()

    # Authenticate via token in query
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") not in ("dashboard", "access"):
                await websocket.close(code=4001, reason="Invalid token type")
                return
        except:
            await websocket.close(code=4001, reason="Invalid token")
            return
    else:
        # Allow connection without token for demo
        pass

    active_dashboard_connections.append(websocket)

    try:
        while True:
            # Keep connection alive, receive any client messages
            data = await websocket.receive_text()
            # Client can send ping
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket in active_dashboard_connections:
            active_dashboard_connections.remove(websocket)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
