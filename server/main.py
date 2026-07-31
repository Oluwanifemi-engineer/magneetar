"""
Magneetar Server — Application Setup
Thin app initialization with middleware, lifespan, and route registration.
All API endpoints have been extracted into route modules under routes/.
"""

import asyncio
import os
import time
import traceback as tb
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from auth import decode_token
from config import settings
from database import ensure_initialized, log_error
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from logging_config import get_logger
from models import ConfigResponse, HealthResponse
from websocket_manager import (
    active_dashboard_connections,
    add_connection,
    broadcast_to_dashboards,
    can_accept_new_connection,
    close_lowest_priority_connection,
    record_pong,
    remove_websocket,
    start_connection_heartbeat,
)

logger = get_logger("magneetar")


# ── Version (single source of truth) ─────────────────────────────────────────
def _get_version() -> str:
    """Read project version from VERSION file."""
    version_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
    try:
        with open(version_path) as f:
            return f.read().strip()
    except Exception:
        return "1.0.0"


APP_VERSION = _get_version()


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
            release=f"magneetar@{APP_VERSION}",
        )
        logger.info(
            "Sentry initialized for error tracking", extra={"extra_data": {"environment": settings.ENVIRONMENT}}
        )
except ImportError:
    pass
except Exception as e:
    logger.warning(f"Sentry initialization failed: {e}")


# ─── Lifespan Handler ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown."""
    # ── Initialize database (safe, idempotent) ───────────────────────────
    ensure_initialized()

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

    # ── Optional integrations: warn (non-fatal) ────────────────────────────
    # Misconfigured optional services (e.g. a bad Twilio SID) must not take
    # down the server — alerts degrade gracefully via the circuit breaker.
    for warn in settings.validate_optional():
        logger.warning(f"⚠️  Optional configuration: {warn}")

    logger.info(
        "Magneetar server starting",
        extra={
            "extra_data": {
                "version": APP_VERSION,
                "environment": settings.ENVIRONMENT,
                "host": settings.HOST,
                "port": settings.PORT,
                "database": "PostgreSQL" if settings.DATABASE_URL else "SQLite",
                "retention_days": settings.DATA_RETENTION_DAYS,
                "max_devices": settings.MAX_DEVICES_PER_USER,
            }
        },
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

    # ── WebSocket Connection Heartbeat (every 30s) ───────────────────
    heartbeat_task = asyncio.create_task(start_connection_heartbeat(interval=30))

    # ── Scheduled Rate Limit Cleanup (every 6 hours) ────────────────────
    async def periodic_rate_limit_cleanup():
        """Background task to clean up stale rate limit entries."""
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6 hours
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
    heartbeat_task.cancel()

    logger.info("Magneetar server shutting down")

    try:
        from database_postgres import close_postgres_db

        await close_postgres_db()
    except Exception:
        pass

    # Notify dashboard WebSocket clients before shutdown (fire-and-forget with timeout)
    if active_dashboard_connections:
        logger.info(f"Notifying {len(active_dashboard_connections)} dashboard client(s) of shutdown...")
        try:
            await asyncio.wait_for(
                broadcast_to_dashboards(
                    {
                        "type": "shutdown",
                        "message": "Server is shutting down",
                        "reconnect": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                timeout=0.5,
            )
        except (asyncio.TimeoutError, Exception):
            logger.warning("Shutdown notification timed out or failed")

    active_dashboard_connections.clear()


# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Magneetar API",
    version=APP_VERSION,
    description="Anti-theft tracking system API",
    lifespan=lifespan,
)

# CORS — permissive in dev, strict in production
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://magneetar.me",
            "https://app.magneetar.me",
            "https://api.magneetar.me",
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


# ─── Include Route Modules ───────────────────────────────────────────────────

# User auth routes (sign-up, sign-in, profile)
from user_auth import router as user_auth_router

app.include_router(user_auth_router)

# Device-facing routes (registration, location, media, commands, heartbeats)
from routes.devices import router as device_router

app.include_router(device_router)

# Dashboard-facing routes (admin UI, stats, errors, evidence, geofences)
from routes.dashboard import router as dashboard_router

app.include_router(dashboard_router)


# ─── Request Timeout Middleware ───────────────────────────────────────────


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    """Enforce a maximum request duration to prevent hanging connections."""
    try:
        return await asyncio.wait_for(call_next(request), timeout=settings.REQUEST_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "Request timed out",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "timeout": settings.REQUEST_TIMEOUT_SECONDS,
                }
            },
        )
        return JSONResponse(
            status_code=504,
            content={"detail": "Request timed out", "timeout_seconds": settings.REQUEST_TIMEOUT_SECONDS},
        )


# ─── Request Timing & Error Tracking Middleware ────────────────────────────


@app.middleware("http")
async def monitor_request_time(request: Request, call_next):
    """Log request duration and catch unhandled exceptions."""
    start_time = time.time()

    try:
        response = await call_next(request)

        duration = time.time() - start_time

        if duration > 1.0:
            logger.warning(
                "Slow request detected",
                extra={
                    "extra_data": {
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration * 1000, 1),
                        "status_code": response.status_code,
                    }
                },
            )

        response.headers["X-Process-Time-Ms"] = str(round(duration * 1000, 1))
        return response

    except Exception as e:
        duration = time.time() - start_time
        error_tb = "".join(tb.format_exception(type(e), e, e.__traceback__))

        forwarded = request.headers.get("X-Forwarded-For", "")
        cf_ip = request.headers.get("CF-Connecting-IP", "")
        if cf_ip:
            client_ip = cf_ip
        elif forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

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

        logger.error(
            f"Unhandled error: {type(e).__name__}: {e}",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 1),
                }
            },
        )

        raise


# ─── Health & Config (kept in main.py — core infrastructure) ─────────────────


@app.get("/health", response_model=HealthResponse)
async def health():
    """Public health endpoint with dependency checks."""
    db_ok = False
    try:
        from database import get_db_context

        with get_db_context() as conn:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="online" if db_ok else "degraded",
        version=APP_VERSION,
        uptime=time.time() - SERVER_START,
        server_time=datetime.now(timezone.utc).isoformat(),
        database=db_ok,
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Public config endpoint for mobile apps."""
    return ConfigResponse()


@app.get("/apk/download")
async def download_apk():
    """Download the latest Magneetar release APK."""
    apk_path = os.path.join(os.path.dirname(__file__), "static", "apk", f"magneetar-v{APP_VERSION}-release.apk")
    if not os.path.exists(apk_path):
        raise HTTPException(status_code=404, detail="APK not found on server")
    return FileResponse(
        apk_path, media_type="application/vnd.android.package-archive", filename=f"Magneetar-v{APP_VERSION}-release.apk"
    )


# ─── WebSocket ───────────────────────────────────────────────────────────────


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for real-time dashboard updates.

    Connection limits are enforced per IP to prevent resource exhaustion.
    A max of MAX_DASHBOARD_CONNECTIONS (100) concurrent connections is allowed.
    """
    await websocket.accept()

    # ── Authentication ─────────────────────────────────────────────────
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") not in ("dashboard", "access"):
                await websocket.close(code=4001, reason="Invalid token type")
                return
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

    # ── Enforce connection limit ────────────────────────────────────────
    if not can_accept_new_connection():
        # Evict oldest connection to make room — avoids silently dropping new clients
        logger.warning(
            "WebSocket at capacity — evicting oldest connection",
            extra={
                "extra_data": {
                    "active": len(active_dashboard_connections),
                    "max": 100,
                }
            },
        )
        await close_lowest_priority_connection()

    add_connection(websocket)  # register + initialize pong timestamp
    logger.info(
        "WebSocket connected",
        extra={
            "extra_data": {
                "total": len(active_dashboard_connections),
                "max": 100,
            }
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data in ("pong", '{"type": "pong"}'):
                record_pong(websocket)
    except WebSocketDisconnect:
        remove_websocket(websocket)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
