"""
Magneetar HTTP Middleware (extracted from main.py — Phase 0).

All FastAPI middleware that applies to every request. Registered via
register_all_middleware(app) in main.py using @app.middleware("http").

Separating middleware from the app init file means:
- main.py stays focused on app creation, lifespan, and route registration
- Middleware can be tested independently
- Each middleware has a single, clear responsibility
"""

import asyncio
import logging
import re
import time
import traceback as tb

from config import settings
from database import log_error
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from feature_flags import flags as feature_flags
from logging_config import get_logger

logger = get_logger("magneetar")


# ─── Credential Log Redaction ────────────────────────────────────────────────
# Applied at module-import time (before any uvicorn logger emits). This is
# NOT a middleware — it's a logging filter installed once at startup to
# prevent JWT tokens from leaking into uvicorn's WebSocket handshake logs.


class TokenRedactingFilter(logging.Filter):
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


def install_credential_log_filter() -> None:
    """Attach the token-redacting filter to all uvicorn loggers.

    Called once at module import time. Safe to call multiple times (filters
    are deduplicated by Python's logging module).
    """
    filt = TokenRedactingFilter()
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addFilter(filt)


# Install immediately on import — this must run before uvicorn starts logging.
install_credential_log_filter()


# ─── Request Timing & Server Start ───────────────────────────────────────────

SERVER_START = time.time()
"""Process start time — used by monitor_request_time to compute uptime."""

REQUEST_TIMEOUT_SECONDS = settings.REQUEST_TIMEOUT_SECONDS
"""Cached from config to avoid attribute lookup on every request."""


# ─── Helper: Client IP Extraction ────────────────────────────────────────────


def extract_client_ip(request: Request) -> str:
    """Extract the real client IP from request headers.

    Checks CF-Connecting-IP (Cloudflare), X-Forwarded-For, then falls back
    to the direct connection IP. Used by multiple route handlers.
    """
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    if cf_ip:
        return cf_ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─── Middleware Registration ─────────────────────────────────────────────────
# Uses @app.middleware("http") decorator pattern — the only pattern supported
# by FastAPI for function-based middleware. Called once in main.py after the
# app instance is created.


def register_all_middleware(app: FastAPI) -> None:
    """Register all HTTP middleware on the FastAPI app.

    Execution order is REVERSE of registration order (Starlette behavior).
    The last middleware registered runs first. Order:
      1. monitor_request_time  (outermost — catches all exceptions + timing)
      2. timeout_middleware     (enforces request deadline)
      3. access_log_middleware  (logs method + path + status)
      4. security_headers_middleware (adds HSTS, CSP, etc.)
      5. api_version_mw         (injects version headers)
      6. maintenance_mode_middleware (blocks traffic during maintenance)
    """

    # ─── 6. Maintenance Mode (registered first → runs last) ──────────────
    # When maintenance_mode flag is enabled, all non-health/device/config
    # endpoints return 503. Device endpoints stay alive (phones keep
    # tracking), and the health/config endpoints are needed by dashboards
    # to detect maintenance.
    MAINTENANCE_WHITELIST = {"/health", "/api/config", "/api/device"}

    @app.middleware("http")
    async def maintenance_mode_middleware(request: Request, call_next):
        """Block non-essential traffic when maintenance_mode flag is enabled."""
        if feature_flags.is_enabled("maintenance_mode"):
            path = request.url.path
            if (
                any(path.startswith(prefix) for prefix in MAINTENANCE_WHITELIST)
                or path.startswith("/_next")
                or path.startswith("/static")
            ):
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "System is under maintenance. Please try again later.",
                    "maintenance": True,
                },
            )
        return await call_next(request)

    # ─── 5. API Version ──────────────────────────────────────────────────
    @app.middleware("http")
    async def api_version_mw(request: Request, call_next):
        """Thin wrapper around api_versioning.api_version_middleware."""
        from api_versioning import api_version_middleware

        return await api_version_middleware(request, call_next)

    # ─── 4. Security Headers ─────────────────────────────────────────────
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        """Set baseline security headers on every response."""
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # ─── 3. Access Log ───────────────────────────────────────────────────
    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        """Structured access log WITHOUT query strings.

        Dashboard tokens travel in the WebSocket URL (?token=...) and
        uvicorn's default access log records the full request line — writing
        JWTs to disk. Uvicorn's access log is disabled (--no-access-log)
        and this middleware logs method + path + status only.
        """
        response = await call_next(request)
        if request.url.path != "/health":
            extra_data = {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
            }
            client = request.headers.get("X-Magneetar-Client", "")
            if client:
                extra_data["client"] = client
            logger.info(
                "access",
                extra={"extra_data": extra_data},
            )
        return response

    # ─── 2. Request Timeout ──────────────────────────────────────────────
    @app.middleware("http")
    async def timeout_middleware(request: Request, call_next):
        """Enforce a maximum request duration to prevent hanging connections."""
        try:
            return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(
                "Request timed out",
                extra={
                    "extra_data": {
                        "method": request.method,
                        "path": request.url.path,
                        "timeout": REQUEST_TIMEOUT_SECONDS,
                    }
                },
            )
            return JSONResponse(
                status_code=504,
                content={
                    "detail": "Request timed out",
                    "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
                },
            )

    # ─── 1. Request Timing & Error Tracking (registered last → runs first) ─
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

            cf_ip = request.headers.get("CF-Connecting-IP", "")
            forwarded = request.headers.get("X-Forwarded-For", "")
            if cf_ip:
                client_ip = cf_ip
            elif forwarded:
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown"

            log_error(
                level=("CRITICAL" if getattr(e, "status_code", 500) >= 500 else "ERROR"),
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
