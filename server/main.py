"""
Magneetar Server — Application Setup
Thin app initialization with middleware, lifespan, and route registration.
All API endpoints have been extracted into route modules under routes/.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re
import time
import traceback as tb
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from alerts import normalize_phone_to_e164  # noqa: E402  (SMS inbound webhook)
from archive_monitor import archive_stale_devices_loop
from auth import decode_token, user_id_from_subject
from config import settings
from database import DB_PATH, check_rate_limit, ensure_initialized, get_db_context, log_error
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from leader_lock import acquire_task_lock, release_task_lock
from logging_config import get_logger
from models import ConfigResponse, HealthResponse
from offline_monitor import check_offline_devices_loop
from sms_relay import parse_ack_sms  # noqa: E402  (SMS inbound webhook)
from websocket_manager import (
    ADMIN_OWNER,
    MAX_DASHBOARD_CONNECTIONS,
    active_dashboard_connections,
    add_connection,
    broadcast_to_dashboards,
    can_accept_new_connection,
    close_lowest_priority_connection,
    record_pong,
    redis_broadcast_listener,
    remove_websocket,
    start_connection_heartbeat,
    update_device_owner,
)
from write_queue import start_write_queue, stop_write_queue, write_queue_enabled

logger = get_logger("magneetar")


class _TokenRedactingFilter(logging.Filter):
    """Strip query-string credentials from any uvicorn log record.

    uvicorn logs WebSocket handshakes through its own loggers with the full
    request line — the dashboard's realtime token travels as `?token=<JWT>`
    in the WS URL, so those INFO lines write live bearer credentials to
    disk. `--no-access-log` (Dockerfile) only silences uvicorn's HTTP access
    log; the websocket protocol logs its own "accepted"/"closed" lines
    with the path + query string. This filter rewrites the record so the
    emitted text carries `token=[REDACTED]` instead, attached to every
    uvicorn logger so the guard holds whichever one emits.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "token=" in msg:
            record.msg = re.sub(r"token=[^&\s\"]{8,}", "token=[REDACTED]", msg)
            record.args = ()
        return True


def _install_credential_log_filter() -> None:
    filt = _TokenRedactingFilter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addFilter(filt)


_install_credential_log_filter()


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
            "Sentry initialized for error tracking",
            extra={"extra_data": {"environment": settings.ENVIRONMENT}},
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

    # ── Batched telemetry writes (opt-in, MT_WRITE_BATCH_MS) ──────────────
    # One dedicated writer connection per worker commits hot-path location
    # writes in batches, removing SQLite's single-writer lock from the
    # request path (measured: sync commits cap the server at ~370 req/s with
    # 3s p50 latency; batching lifts that ceiling 5-10x). No-op unless
    # MT_WRITE_BATCH_MS>0, so default behavior is unchanged. SQLite-only by
    # design — in PostgreSQL mode (MT_DATABASE_URL set) the facade pool
    # handles writes and the batch queue is skipped.
    if write_queue_enabled() and not settings.DATABASE_URL:
        await start_write_queue(DB_PATH)

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

    # ── PostgreSQL Setup (optional, storage facade — ADR-0005 Phase 2a) ──
    # When MT_DATABASE_URL is set, get_db()/get_db_context() return the
    # PgStore sync facade (storage.py) and every route reads/writes Postgres.
    # The SQL portability pass (Phase 2b, docs/postgres-migration.md §6.4) is
    # the remaining work before production cutover — dialect gaps like
    # datetime('now', ?) and INSERT OR REPLACE still live in route SQL. Any
    # setup failure falls back to SQLite so the server always boots.
    pg_connected = False
    if settings.DATABASE_URL:
        try:
            from storage import init_pg_store

            if init_pg_store():
                pg_connected = True
                logger.info(
                    "PostgreSQL wired via the storage facade (ADR-0005 Phase 2a): "
                    "routes read/write Postgres. Phase 2b (SQL portability pass, "
                    "docs/postgres-migration.md §6.4) is the remaining work before "
                    "production cutover."
                )
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
                    logger.info(
                        f"Data retention cleanup: {total_purged} records purged",
                        extra={"extra_data": result},
                    )
        except Exception as e:
            logger.warning(f"Data retention cleanup skipped: {e}")

    asyncio.create_task(run_cleanup())

    # ── WebSocket Connection Heartbeat (every 30s) ───────────────────
    heartbeat_task = asyncio.create_task(start_connection_heartbeat(interval=30))

    # ── Multi-worker broadcast listener (Redis pub/sub) ─────────────────
    # With --workers > 1 each worker owns its own WebSocket registry; this
    # task subscribes to the shared channel and forwards messages to THIS
    # worker's connections so every dashboard stays live regardless of which
    # worker handled the originating request. No-op when MT_REDIS_URL unset.
    redis_task = asyncio.create_task(redis_broadcast_listener())
    if settings.REDIS_URL:
        logger.info(
            "Realtime broadcast: Redis pub/sub enabled",
            extra={"extra_data": {"channel": "magneetar:ws"}},
        )
    else:
        logger.info("Realtime broadcast: local (single-worker mode)")

    # ── Offline Monitor (every 60s) ──────────────────────────────────
    # Alerts owners once per incident when a device stops reporting. Safe on
    # restarts: dedup is persisted in the alerts table (see offline_monitor.py).
    offline_task = asyncio.create_task(check_offline_devices_loop(interval_seconds=60))

    # ── Stale-Device Archive (every 6h) ───────────────────────────────
    # Soft-archives devices silent beyond MT_ARCHIVE_AFTER_DAYS (default 30)
    # so long-dead rows stop cluttering the dashboard. Any fresh telemetry
    # clears the flag automatically (see archive_monitor.py).
    archive_task = asyncio.create_task(archive_stale_devices_loop(interval_seconds=6 * 3600))

    # ── Scheduled Rate Limit Cleanup (every 6 hours) ────────────────────
    async def periodic_rate_limit_cleanup():
        """Background task to clean up stale rate limit entries.

        Runs under the leader lock: the purge is idempotent but running it
        in every worker (--workers > 1) is wasted DB churn, and the in-memory
        limiter sweep should run once."""
        while True:
            try:
                await asyncio.sleep(6 * 3600)  # 6 hours
                won, token = await acquire_task_lock("rate_limit_cleanup", ttl=6 * 3600 + 60)
                if not won:
                    continue  # another worker is the leader this cycle
                try:
                    use_pg = False
                    try:
                        from database_postgres import (
                            get_postgres_db,
                            is_postgres_configured,
                        )

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

                    # In-memory telemetry limiter (memory_rate_limit): drop
                    # keys whose windows have fully aged out (keeps it bounded
                    # even before the 50k-key opportunistic sweep kicks in).
                    from memory_rate_limit import sweep

                    swept = sweep()
                    if swept:
                        logger.info(f"Rate limit cleanup (in-memory): swept {swept} idle device keys")
                finally:
                    await release_task_lock("rate_limit_cleanup", token)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Rate limit cleanup failed: {e}")

    cleanup_task = asyncio.create_task(periodic_rate_limit_cleanup())
    yield
    cleanup_task.cancel()
    heartbeat_task.cancel()
    redis_task.cancel()
    offline_task.cancel()
    archive_task.cancel()

    logger.info("Magneetar server shutting down")

    # Flush any pending batched telemetry writes before the DB goes away.
    if write_queue_enabled():
        await stop_write_queue()

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

    # ── Close the PostgreSQL facade pool (only when wired) ─────────────────
    if settings.DATABASE_URL:
        try:
            from storage import close_pg_store

            close_pg_store()
        except Exception:
            logger.warning("PostgreSQL pool close failed (process exit continues)")


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
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Device-Key",
            "X-Request-ID",
        ],
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

# User account security routes (2FA, password reset, email verification)
from user_security import router as user_security_router  # noqa: E402

app.include_router(user_security_router)

# Device-facing routes (registration, location, media, commands, heartbeats)
from routes.devices import router as device_router  # noqa: E402

app.include_router(device_router)

# Dashboard-facing routes (admin UI, stats, errors, evidence, geofences)
from routes.dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)

# Guardian Network routes (community recovery)
from routes.guardian import router as guardian_router  # noqa: E402

app.include_router(guardian_router)

# Metrics and observability endpoints
from routes.metrics import router as metrics_router  # noqa: E402

app.include_router(metrics_router)

# User data routes (GDPR export, deletion, retention)
from routes.user_data import router as user_data_router  # noqa: E402

app.include_router(user_data_router)

# Developer API keys (management + /api/v1 data surface, docs/developer-api.md)
from routes.api_keys import router as api_keys_router  # noqa: E402

app.include_router(api_keys_router)


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
        extra_data = {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
        }
        # In-app self-updater marks its own APK pulls (checksum/ticket/
        # download) so an upgrade can be told apart from a web download in
        # the logs — the G1 signal that a device self-updated.
        client = request.headers.get("X-Magneetar-Client", "")
        if client:
            extra_data["client"] = client
        logger.info(
            "access",
            extra={"extra_data": extra_data},
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
            content={
                "detail": "Request timed out",
                "timeout_seconds": settings.REQUEST_TIMEOUT_SECONDS,
            },
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


# Where a browser lands when it follows a stale/expired download link. The
# download page re-mints a fresh ticket on load, so a dead link self-heals
# instead of dead-ending on a raw 403 JSON body. Configurable for self-hosters
# whose dashboard lives elsewhere; the trailing '/download' is the page that
# mints tickets (see dashboard/src/app/download/page.tsx).
def _apk_download_page() -> str:
    base = settings.DASHBOARD_URL.strip().rstrip("/")
    # Defensive: an empty base degrades to a same-host relative redirect (a
    # 404 on the API host) rather than a malformed URL — never a crash.
    return base + "/download" if base else "/download"


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
    by /apk/ticket. A missing/expired ticket is redirected to the download
    page (302), which mints a fresh one — anonymous/hotlinked downloads never
    receive bytes.

    Resolves in order of preference so a version bump never breaks the link:
    1. magneetar-v{APP_VERSION}-release.apk  (the release built for this version)
    2. magneetar-latest.apk                  (the always-current pointer)
    3. the newest magneetar-*.apk on disk     (last resort)
    """
    if not _verify_apk_ticket(expires, sig):
        # A stale/expired link must not dead-end on raw JSON: the download page
        # mints a fresh ticket on load, so bounce the browser there (302 — the
        # ticket itself is still REQUIRED to receive bytes, so the anti-scrape
        # gate is unchanged; only the error UX changed).
        return RedirectResponse(
            _apk_download_page(),
            status_code=302,
        )
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
    return ConfigResponse(
        app_version=APP_VERSION,
        # Offline Command Relay: the number command SMS are sent FROM. The
        # Android app allowlists it as the only command-issuing sender (along
        # with the Termii alphanumeric "Magneetar"), so a leaked pairing code
        # alone can't be replayed from a random number. Empty when the server
        # has no SMS sender configured — the app then falls back to code-only.
        sms_relay_number=settings.TWILIO_SMS_FROM,
    )


@app.post("/api/sms/inbound")
async def sms_inbound_webhook(request: Request):
    """Twilio inbound-SMS webhook — the SMS reply return channel.

    When a phone executes a command that arrived over SMS and CAN send SMS
    (default SMS app / SMS_MANAGER role), the app SMS-replies
    "MT-ACK #<id> <status>" to the relay number. Twilio forwards that inbound
    message to this webhook, which applies the ack server-side — so an
    offline command can be acknowledged without waiting for the network
    outbox. The network outbox remains the reliable default; this is the
    instant path when available.

    Security:
    - X-Twilio-Signature is verified with the account auth token (HMAC-SHA1
      over the canonical URL + body params), so only genuine Twilio traffic
      can drive acks. Without a configured TWILIO_AUTH_TOKEN the endpoint is
      inert (403) — no signature, no processing.
    - The reply is applied ONLY when the From number matches the device's
      registered sms_phone (E.164-normalized), so a stranger's SMS can never
      ack (or forge) another device's commands.
    - The ack is limited to marking the command executed/failed; it can never
      issue new commands.
    """
    import base64 as _b64
    import urllib.parse as _urlparse

    # NOTE: get_db_context / normalize_phone_to_e164 / parse_ack_sms are
    # imported at MODULE level (top of this file) — under full-suite
    # collection test_e2e evicts modules from sys.modules; a function-local
    # `from database import get_db_context` would resolve the post-eviction
    # module whose DB_PATH points elsewhere, so the command lookup below would
    # 404 as 'unknown_command' (same bug class as the evidence PDF / step-up
    # password evictions documented in routes/dashboard.py).
    signature = request.headers.get("X-Twilio-Signature", "")
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not signature or not auth_token:
        raise HTTPException(status_code=403, detail="SMS inbound webhook not configured")

    form = dict(await request.form())
    from_number = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()

    # Twilio signature: base64(HMAC-SHA1(auth_token, url + urlencoded_params))
    # where params are the POST body, sorted by key. The URL must match the
    # one configured in the Twilio console exactly (scheme + host + path).
    canonical_url = str(request.url)
    sorted_params = _urlparse.urlencode(sorted(form.items()))
    expected = _b64.b64encode(
        hmac.new(
            auth_token.encode(),
            f"{canonical_url}{sorted_params}".encode(),
            hashlib.sha1,
        ).digest()
    ).decode()
    if not hmac.compare_digest(expected, signature):
        logger.warning("SMS inbound: Twilio signature mismatch — rejecting")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    parsed = parse_ack_sms(body)
    if not parsed:
        # Not an MT-ACK (e.g. a stray message to the relay number) — 200 so
        # Twilio doesn't retry; nothing to do.
        return {"status": "ignored"}
    command_id, ack_status = parsed

    # Per-sender rate limit (defense in depth): even with a valid signature,
    # bulk-replaying acks would write to the DB on every hit. Cap at 10
    # webhook acks per sender per minute.
    if not check_rate_limit(f"sms_inbound:{from_number}", "sms_inbound", 10, 1):
        logger.warning(f"SMS inbound: rate limited for sender {from_number}")
        raise HTTPException(status_code=429, detail="SMS inbound rate limit exceeded")

    with get_db_context() as conn:
        # Only acks for SMS-DELIVERED commands are accepted — a poll-delivered
        # command's lifecycle is fully handled by the network ack, so this
        # webhook must never interfere with it (scope tightness).
        row = conn.execute(
            "SELECT c.device_id, c.status, d.sms_phone FROM commands c "
            "JOIN devices d ON c.device_id=d.id WHERE c.id=? AND c.delivery_channel='sms'",
            (command_id,),
        ).fetchone()
        if not row:
            return {"status": "unknown_command"}
        if row["status"] != "pending":
            return {"status": "already_acknowledged"}

        # From must match the device's registered SMS number — a different
        # number must never ack this device's commands.
        device_phone = (row["sms_phone"] or "").strip()
        if not device_phone:
            return {"status": "no_phone_configured"}
        if normalize_phone_to_e164(from_number, settings.PHONE_COUNTRY_CODE) != normalize_phone_to_e164(
            device_phone, settings.PHONE_COUNTRY_CODE
        ):
            logger.warning(f"SMS inbound: ack for command {command_id} from non-owner number {from_number} — rejecting")
            return {"status": "sender_mismatch"}

        from datetime import datetime as _dt
        from datetime import timezone as _tz

        conn.execute(
            "UPDATE commands SET status=?, executed_at=? WHERE id=?",
            (ack_status, _dt.now(_tz.utc).isoformat(), command_id),
        )
        conn.commit()

    logger.info(
        "SMS inbound ack applied",
        extra={
            "extra_data": {
                "command_id": command_id,
                "status": ack_status,
                "device_id": row["device_id"],
            }
        },
    )
    return {"status": "acknowledged", "command_id": command_id}


# ─── WebSocket ───────────────────────────────────────────────────────────────


def _is_pong_message(data: str) -> bool:
    """True when a client keepalive message is a pong.

    The dashboard client sends a JSON pong (`{"type":"pong"}`) via
    JSON.stringify; older clients sent the bare string "pong". Both are
    accepted. JSON whitespace is normalized so a differently-spaced
    serialization can never make a live client look dead to the 90s
    stale-prune heartbeat.
    """
    if data == "pong":
        return True
    return data.replace(" ", "") == '{"type":"pong"}'


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
    device_ids = None  # user connections: allowed device ids (owned + shared)
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
            # dashboards receive broadcasts immediately (survives restarts),
            # and snapshot the full allowed-device set (owned + SHARED via
            # device_shares — Milestone 2 P1) so shared users receive live
            # updates for granted devices too. The snapshot is taken at
            # connect time; reconnecting picks up grant/revoke changes.
            try:
                from database import get_db_context

                with get_db_context() as conn:
                    owned = conn.execute("SELECT id FROM devices WHERE owner_id=?", (owner,)).fetchall()
                    for row in owned:
                        update_device_owner(row["id"], owner)
                    # device_only shares are the privacy tier: REST strips their
                    # coordinates, so the WS feed must NOT leak live lat/lng to
                    # them either — only viewer/admin grants join the set.
                    shared = conn.execute(
                        "SELECT device_id AS id FROM device_shares "
                        "WHERE grantee_user_id=? AND role != 'device_only'",
                        (owner,),
                    ).fetchall()
                    device_ids = {row["id"] for row in owned} | {row["id"] for row in shared}
            except Exception:
                pass  # fall back to owner-only scoping (safe default)
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
                    "max": MAX_DASHBOARD_CONNECTIONS,
                }
            },
        )
        await close_lowest_priority_connection()

    add_connection(websocket, owner, device_ids)  # register + scope + pong init
    logger.info(
        "WebSocket connected",
        extra={
            "extra_data": {
                "total": len(active_dashboard_connections),
                "max": MAX_DASHBOARD_CONNECTIONS,
            }
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif _is_pong_message(data):
                record_pong(websocket)
    except WebSocketDisconnect:
        remove_websocket(websocket)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
