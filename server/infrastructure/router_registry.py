"""
Magneetar Route Registration (extracted from main.py — Phase 0).

Single place that registers every HTTP router on the FastAPI app, so adding or
removing a domain is one obvious change. Imported by main.py and called once
after the app instance is created.

Each router is imported from its canonical module and included with its default
prefix + tags. The list is deliberately flat — no indirection, no auto-discovery
— so the set of active routes is readable at a glance and diffs cleanly.
"""

from fastapi import FastAPI


def register_all_routers(app: FastAPI) -> None:
    """Include every application router on `app`.

    Order is not significant for route matching (FastAPI collects routes by
    prefix), but it is kept stable so ``git diff`` stays readable when a router
    is added or removed.
    """
    # ── Authentication & security ─────────────────────────────────────────────
    from user_auth import router as user_auth_router
    from user_security import router as user_security_router

    app.include_router(user_auth_router)
    app.include_router(user_security_router)

    # ── Device lifecycle (location, media, commands, heartbeats) ─────────────
    from routes.devices import router as device_router

    app.include_router(device_router)

    # ── Web dashboard operations ──────────────────────────────────────────────
    from routes.dashboard import router as dashboard_router

    app.include_router(dashboard_router)

    # ── Observability ─────────────────────────────────────────────────────────
    from routes.metrics import router as metrics_router

    app.include_router(metrics_router)

    # ── Offline / low-connectivity channels ───────────────────────────────────
    from routes.mesh import router as mesh_router
    from routes.sms import router as sms_router
    from routes.ussd import router as ussd_router
    from routes.whatsapp import router as whatsapp_router

    app.include_router(ussd_router)
    app.include_router(whatsapp_router)
    app.include_router(mesh_router)
    app.include_router(sms_router)

    # ── Group sharing & consent ───────────────────────────────────────────────
    from routes.circles import router as circles_router
    from routes.consent import router as consent_router

    app.include_router(circles_router)
    app.include_router(consent_router)

    # ── Payments ──────────────────────────────────────────────────────────────
    from routes.payments import router as payments_router

    app.include_router(payments_router)

    # ── APK distribution (infrastructure, not a domain) ───────────────────────
    from infrastructure.routes import router as apk_router

    app.include_router(apk_router)
