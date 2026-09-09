"""
Magneetar Server — Application Setup

Thin app initialization with middleware, lifespan, and route registration.

All HTTP middleware lives in infrastructure/middleware.py.
APK distribution routes live in infrastructure/routes.py.
Lifespan (startup/shutdown) lives in infrastructure/lifespan.py.
WebSocket handlers live in infrastructure/websocket_handlers.py.
SMS inbound webhook lives in routes/sms.py.
Domain-specific routes live under routes/ and will move to domains/ later.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from api_versioning import customize_openapi_schema  # noqa: F401
from auth import hash_device_key
from config import settings
from database import get_db_context
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from feature_flags import flags as feature_flags
from logging_config import get_logger
from models import ConfigResponse, HealthResponse

logger = get_logger("magneetar")

# ── Backward-compatible re-exports ──────────────────────────────────────────
# Tests import these from main; they now live in infrastructure/ or routes/.
# Re-export here so existing test imports keep working during migration.
from infrastructure.middleware import TokenRedactingFilter as _TokenRedactingFilter  # noqa: F401, E402
from infrastructure.routes import _apk_checksum_cache, _get_apk_checksum, _sign_apk_ticket  # noqa: F401, E402
from infrastructure.websocket_handlers import _is_pong_message  # noqa: F401, E402


# ── Version (single source of truth) ─────────────────────────────────────────
def _get_version() -> str:
    """Read project version from VERSION file."""
    import os

    version_path = os.path.join(os.path.dirname(__file__), "VERSION")
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


# ─── App Setup ───────────────────────────────────────────────────────────────

from infrastructure.lifespan import create_lifespan  # noqa: E402

_prod = settings.ENVIRONMENT == "production"
app = FastAPI(
    title="Magneetar API",
    version=APP_VERSION,
    description="Anti-theft tracking system API",
    lifespan=create_lifespan(APP_VERSION),
    docs_url=None if _prod else "/docs",
    redoc_url=None if _prod else "/redoc",
    openapi_url=None if _prod else "/openapi.json",
    openapi_tags=[
        {"name": "Authentication", "description": "User registration, login, and token management"},
        {"name": "Device", "description": "Device registration, location, media, and commands"},
        {"name": "Dashboard", "description": "Web dashboard operations"},
        {"name": "Security", "description": "2FA, password reset, email verification"},
        {"name": "Monitoring", "description": "Metrics, health checks, and observability"},
    ],
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

# ─── Register Middleware ─────────────────────────────────────────────────────
# Late imports are intentional: app + middleware bootstrap must exist first.
from infrastructure.middleware import register_all_middleware  # noqa: E402

register_all_middleware(app)


# ─── Register HTTP Routers ──────────────────────────────────────────────────
from infrastructure.router_registry import register_all_routers  # noqa: E402

register_all_routers(app)

# ─── Register WebSocket Routes ───────────────────────────────────────────────
from infrastructure.websocket_handlers import register_websocket_routes  # noqa: E402

register_websocket_routes(app)


# ─── Core Endpoints (health, config) ────────────────────────────────────────
# These stay in main.py because they're thin, app-level, and don't belong
# to any specific domain. They will move to domains/ in later phases.


@app.get("/health", response_model=HealthResponse)
async def health():
    """Public health endpoint with dependency checks."""
    db_ok = False
    try:
        with get_db_context() as conn:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
    except Exception:
        pass

    status = "online" if db_ok else "degraded"

    if not db_ok:
        try:
            from health_webhook import send_health_alert

            asyncio.create_task(send_health_alert("down", "Magneetar API is DEGRADED — database unreachable."))
        except Exception:
            pass
    else:
        try:
            from health_webhook import send_health_alert

            asyncio.create_task(send_health_alert("recovery", "Magneetar API recovered — database is healthy."))
        except Exception:
            pass

    return HealthResponse(
        status=status,
        version=APP_VERSION,
        server_time=datetime.now(timezone.utc).isoformat(),
        database=db_ok,
    )


@app.get("/api/config", response_model=ConfigResponse)
async def get_config(x_device_key: Optional[str] = Header(None)):
    """Public config endpoint for mobile apps."""
    relay_number = ""
    if x_device_key:
        key_hash = hash_device_key(x_device_key)
        with get_db_context() as conn:
            row = conn.execute("SELECT 1 FROM devices WHERE device_key_hash=?", (key_hash,)).fetchone()
            if row:
                relay_number = settings.TWILIO_SMS_FROM
    return ConfigResponse(
        app_version=APP_VERSION,
        sms_relay_number=relay_number,
        feature_flags=feature_flags.get_all(),
    )


# ─── OpenAPI Schema Customization ────────────────────────────────────────────
if not _prod:
    customize_openapi_schema(app)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
