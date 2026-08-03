"""
Magneetar Server — Application Setup
Thin app initialization with middleware, lifespan, and route registration.
All API endpoints have been extracted into route modules under routes/.
"""

import asyncio
import hashlib
import hmac
import os
import time
import traceback as tb
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from auth import decode_token, user_id_from_subject
from config import settings
from database import check_rate_limit, ensure_initialized, log_error
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from logging_config import get_logger
from models import ConfigResponse, HealthResponse
from offline_monitor import check_offline_devices_loop
from websocket_manager import (
    ADMIN_OWNER,
    active_dashboard_connections,
    add_connection,
    broadcast_to_dashboards,
    can_accept_new_connection,
    close_lowest_priority_connection,
    record_pong,
    remove_websocket,
    start_connection_heartbeat,
    update_device_owner,
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

    # ── Offline Monitor (every 60s) ──────────────────────────────────
    # Alerts owners once per incident when a device stops reporting. Safe on
    # restarts: dedup is persisted in the alerts table (see offline_monitor.py).
    offline_task = asyncio.create_task(check_offline_devices_loop(interval_seconds=60))

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
    offline_task.cancel()

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

# Docs & OpenAPI schema are an attacker's blueprint (F-04): every endpoint,
# model, and auth scheme is laid out at /docs and /openapi.json. Enable them
# only outside production (dev/staging for API testing).
_prod = settings.ENVIRONMENT == "production"
app = FastAPI(
    title="Magneetar API",
    version=APP_VERSION,
    description="Anti-theft tracking system API",
    lifespan=lifespan,
    docs_url=None if _prod else "/docs",
    redoc_url=None if _prod else "/redoc",
    openapi_url=None if _prod else "/openapi.json",
)

# CORS — permissive in dev, strict in production (also serves as the
# authenticated-browser protection: only the known origins may read responses)
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
from user_auth import router as user_auth_router  # noqa: E402

app.include_router(user_auth_router)

# Device-facing routes (registration, location, media, commands, heartbeats)
from routes.devices import router as device_router  # noqa: E402

app.include_router(device_router)

# Dashboard-facing routes (admin UI, stats, errors, evidence, geofences)
from routes.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)

# Guardian Network routes (community recovery)
from routes.guardian import router as guardian_router  # noqa: E402

app.include_router(guardian_router)


# ─── Request Timeout Middleware ───────────────────────────────────────────


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Set baseline security headers on every response.

    HSTS tells browsers to only ever use HTTPS for this origin (the tunnel
    terminates TLS in front of us); frame-ancestors/X-Frame-Options stop the
    API from being embedded anywhere; nosniff blocks MIME-sniffing; and
    Referrer-Policy keeps tokens out of cross-origin referrers.
    """
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """Structured access log WITHOUT query strings.

    Dashboard tokens travel in the WebSocket URL (?token=...) and uvicorn's
    default access log records the full request line — writing JWTs to disk
    for anyone with log access to harvest. Uvicorn's access log is therefore
    disabled (Dockerfile --no-access-log) and this middleware logs method +
    path + status only, so credentials never land in logs.
    """
    response = await call_next(request)
    if request.url.path != "/health":  # keep health-check polling out of logs
        logger.info(
            "access",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                }
            },
        )
    return response


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


# ─── APK Download Gating (short-lived signed tickets) ───────────────────────
# /apk/download used to be anonymous: anyone could hotlink the binary and
# scrape the whole APK/CDN bandwidth. Downloads now require a short-lived
# HMAC-signed ticket minted by /apk/ticket (rate-limited per IP). The signing
# key is DERIVED FROM THE JWT SECRET, never MT_API_KEY — that key ships inside
# every APK, so using it would let anyone mint their own tickets.

APK_TICKET_TTL_SECONDS = 600  # 10 minutes — short enough that a leaked URL dies fast


def _apk_ticket_key() -> bytes:
    """HMAC key for APK download tickets (server-only JWT secret, domain-separated)."""
    return hmac.new(settings.JWT_SECRET.encode(), b"magneetar:apk-ticket:v1", hashlib.sha256).digest()


def _sign_apk_ticket(expires_epoch: int) -> str:
    """HMAC-SHA256 signature over 'download|<expires>'."""
    msg = f"download|{expires_epoch}".encode()
    return hmac.new(_apk_ticket_key(), msg, hashlib.sha256).hexdigest()


def _verify_apk_ticket(expires_epoch: int, sig: str) -> bool:
    """True when the signature matches AND the URL is still inside its TTL.

    The far-future check (expires - now <= TTL) makes a signed URL that was
    leaked from logs useless once its window closes — a stolen URL cannot be
    replayed for weeks by bumping nothing.
    """
    if not sig:
        return False
    now = int(time.time())
    expected = _sign_apk_ticket(expires_epoch)
    return hmac.compare_digest(expected, sig) and now <= expires_epoch and expires_epoch - now <= APK_TICKET_TTL_SECONDS


@app.get("/apk/ticket")
async def apk_ticket(request: Request):
    """Mint a short-lived signed download URL for the current release APK.

    Rate-limited per IP (20 tickets / 10 min) so the binary can't be scraped
    in bulk, while the landing page's download button just works for humans.
    """
    if _resolve_apk() is None:
        raise HTTPException(status_code=404, detail="APK not found on server")

    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    if cf_ip:
        client_ip = cf_ip
    elif forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(f"apk_ticket:{client_ip}", "apk_ticket", 20, 10):
        raise HTTPException(status_code=429, detail="Too many download requests — try again shortly")

    expires = int(time.time()) + APK_TICKET_TTL_SECONDS
    sig = _sign_apk_ticket(expires)
    return {
        "url": f"/apk/download?expires={expires}&sig={sig}",
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
    }


# ─── APK Resolution (shared by /apk/download + /apk/checksum) ───────────────


def _apk_candidates():
    """APK paths in order of preference — a version bump never breaks a link."""
    apk_dir = os.path.join(os.path.dirname(__file__), "static", "apk")
    yield os.path.join(apk_dir, f"magneetar-v{APP_VERSION}-release.apk")
    yield os.path.join(apk_dir, "magneetar-latest.apk")
    try:
        apks = sorted(
            (f for f in os.listdir(apk_dir) if f.endswith(".apk") and f.startswith("magneetar-")),
            key=lambda f: os.path.getmtime(os.path.join(apk_dir, f)),
            reverse=True,
        )
    except OSError:
        apks = []
    for name in apks:
        yield os.path.join(apk_dir, name)


def _resolve_apk():
    """Return the path of the APK that /apk/download would serve, or None."""
    for path in _apk_candidates():
        if os.path.exists(path):
            return path
    return None


def _sha256_file(path: str) -> str:
    """Streaming SHA-256 of a file without loading it into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# path -> (mtime, size, sha256) — invalidated when the file changes
_apk_checksum_cache: dict[str, tuple[int, int, str]] = {}


def _get_apk_checksum(path: str) -> tuple[str, int]:
    """(sha256, size_bytes) of an APK file, cached per (mtime, size) so
    repeated requests don't re-hash multi-MB files. Replaced files yield fresh
    digests. One stat feeds both the cache key and the reported size, so a
    checksum response can never pair a size from one version of a file with a
    hash from another."""
    stat = os.stat(path)
    cached = _apk_checksum_cache.get(path)
    if cached is not None and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
        return cached[2], stat.st_size
    digest = _sha256_file(path)
    _apk_checksum_cache[path] = (stat.st_mtime, stat.st_size, digest)
    return digest, stat.st_size


@app.get("/apk/download")
async def download_apk(expires: int = 0, sig: str = ""):
    """Download the latest Magneetar release APK.

    Requires a short-lived signed ticket (?expires=<epoch>&sig=<hmac>) minted
    by /apk/ticket — anonymous/hotlinked downloads are rejected with 403.

    Resolves in order of preference so a version bump never breaks the link:
    1. magneetar-v{APP_VERSION}-release.apk  (the release built for this version)
    2. magneetar-latest.apk                  (the always-current pointer)
    3. the newest magneetar-*.apk on disk     (last resort)
    """
    if not _verify_apk_ticket(expires, sig):
        raise HTTPException(status_code=403, detail="Missing or expired download ticket — request one from /apk/ticket")
    path = _resolve_apk()
    if path is None:
        raise HTTPException(status_code=404, detail="APK not found on server")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=f"Magneetar-v{APP_VERSION}-release.apk",
    )


@app.get("/apk/checksum")
async def apk_checksum():
    """SHA-256 checksum + size for the exact bytes /apk/download serves.

    Lets sideloaders verify a downloaded file byte-for-byte against the
    official build before installing. The hash is computed once per file
    change (cache keyed on mtime + size) so repeated hits stay cheap.
    """
    path = _resolve_apk()
    if path is None:
        raise HTTPException(status_code=404, detail="APK not found on server")

    digest, size_bytes = await asyncio.to_thread(_get_apk_checksum, path)

    return {
        # Same display name /apk/download hands the browser, so users can
        # match the file they saved against the checksum page 1:1.
        "filename": f"Magneetar-v{APP_VERSION}-release.apk",
        "version": APP_VERSION,
        "sha256": digest,
        "size_bytes": size_bytes,
    }


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
    # app_version must match /health (single source: VERSION file). A stale
    # hardcoded value here broke the Android "update available" nudge.
    return ConfigResponse(app_version=APP_VERSION)


# ─── WebSocket ───────────────────────────────────────────────────────────────


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    """WebSocket for real-time dashboard updates.

    REQUIRES a valid ?token= (dashboard/access JWT). Anonymous connections
    are rejected — the old behaviour of accepting everyone and treating
    tokenless connections as admin leaked every device's live location to
    the internet (F-01).

    Connection limits are enforced per IP to prevent resource exhaustion.
    A max of MAX_DASHBOARD_CONNECTIONS (100) concurrent connections is allowed.
    """
    await websocket.accept()

    # ── Authentication (mandatory) ────────────────────────────────────
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4408, reason="Authentication required")
        return

    owner = None  # resolved below; never register unauthenticated
    try:
        payload = decode_token(token)
        if payload.get("type") not in ("dashboard", "access"):
            await websocket.close(code=4001, reason="Invalid token type")
            return
        sub = payload.get("sub", "")
        user_id = user_id_from_subject(sub)
        if user_id:
            owner = user_id
            # Hydrate the in-memory device→owner cache so this user's
            # dashboards receive broadcasts immediately (survives restarts).
            try:
                from database import get_db_context

                with get_db_context() as conn:
                    rows = conn.execute("SELECT id FROM devices WHERE owner_id=?", (owner,)).fetchall()
                    for row in rows:
                        update_device_owner(row["id"], owner)
            except Exception:
                pass
        elif sub.startswith("dashboard:"):
            # Authenticated operator/dashboard token — explicit admin scope.
            owner = ADMIN_OWNER
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if owner is None:
        # Valid signature but unrecognized subject shape — deny rather than
        # default to admin (defense in depth, same bug class as F-01).
        await websocket.close(code=4001, reason="Invalid token subject")
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

    add_connection(websocket, owner)  # register + initialize pong timestamp
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
