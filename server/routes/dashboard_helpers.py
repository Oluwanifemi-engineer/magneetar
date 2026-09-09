"""
Magneetar Dashboard Helpers (extracted from routes/dashboard.py — Phase 0).

Shared constants, RBAC functions, and utility functions used by multiple
dashboard route modules. Extracted to avoid duplication when dashboard.py
is split into domain-specific route modules.

Contains:
- LIVE_FIX_ORDER_SQL (quality gate for device location queries)
- ROLE_RANK and RBAC helpers (_resolve_device_role, _assert_device_access)
- _verify_stepup_password (re-authentication for destructive actions)
- _resolve_user_id, _parse_json_list, _parse_int (utility functions)
"""

import hmac
from typing import Optional

from auth import check_password_verify_rate_limit, verify_password
from config import settings
from database import get_db_context
from fastapi import HTTPException
from logging_config import get_logger

logger = get_logger("magneetar")

# ─── Live-location quality gate ─────────────────────────────────────────────
# The device reports a fix every ~3s. When GPS is unavailable (indoors,
# pocket, car), Android falls back to cell-tower fixes whose accuracy is
# 200-700m — and the cell centroid can be KILOMETRES from the true position.
# The dashboard's live pin used to be the newest fix regardless of quality,
# so a degraded fix landing right after a good GPS fix teleported the map to
# a misleading location (G1 field finding 2026-08-15: pin jumped 3.5km to a
# cell centroid while the device sat still).
#
# Rule: the live position is the most recent fix that is GOOD — HIGH/MEDIUM
# confidence or <100m accuracy — within a freshness window. A degraded fix
# only takes over after the window expires (so a genuinely moving device in
# a GPS-denied area still advances, just with an honest accuracy circle).
# The window ALSO bounds how far back we'll resurrect a stale good fix: a
# 3-hour-old GPS fix is not where the device is anymore.
LIVE_FIX_GOOD_ACCURACY_M = 100
LIVE_FIX_FRESH_WINDOW_MINUTES = 15

LIVE_FIX_ORDER_SQL = f"""
    CASE WHEN (confidence_level IN ('HIGH','MEDIUM')
               OR (accuracy_horizontal IS NOT NULL AND accuracy_horizontal < {LIVE_FIX_GOOD_ACCURACY_M}))
               AND julianday(server_timestamp) >= julianday('now', '-{LIVE_FIX_FRESH_WINDOW_MINUTES} minutes')
          THEN 0 ELSE 1 END,
    server_timestamp DESC
"""


# ─── Device Sharing / RBAC ──────────────────────────────────────────────────
# Role hierarchy: owner > admin > viewer > device_only. Shares only ever grant
# admin/viewer/device_only — "owner" is implicit (the account the device is
# linked to). device_only is a privacy tier: status glance only, no location,
# evidence, or command access. Operator/dashboard (admin) sessions rank as
# owner so the existing admin surface keeps working unchanged.
ROLE_RANK = {"device_only": 0, "viewer": 1, "admin": 2, "owner": 3}


def _resolve_user_id(auth: str) -> Optional[str]:
    """Return the user id if the auth subject is a user token, else None (admin)."""
    from auth import user_id_from_subject

    return user_id_from_subject(auth)


def _parse_json_list(raw) -> Optional[list]:
    """Parse a JSON-TEXT list column; None for NULL or invalid."""
    if raw is None:
        return None
    import json as _json

    try:
        parsed = _json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        return None


def _parse_int(raw) -> Optional[int]:
    """Coerce an hour column to int; None for NULL or unparseable.

    Quiet hours added by the pre-v1.2 migration were ALTERed with TEXT
    affinity, so values on upgraded DBs arrive as strings ('22').
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


def _resolve_device_role(db, device_id: str, auth: str) -> Optional[str]:
    """Return the caller's effective role for a device, or None if they have
    no access at all.

    Existence is verified for EVERY scope BEFORE the admin shortcut: a
    nonexistent device must resolve to None so _assert_device_access can 404
    cleanly (the admin branch returning 'owner' first would let admin-scope
    writes blow up on downstream FK constraints instead of 404ing)."""
    row = db.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return None
    user_id = _resolve_user_id(auth)
    if user_id is None:
        return "owner"  # operator/dashboard session — full access
    if row["owner_id"] == user_id:
        return "owner"
    share = db.execute(
        "SELECT role FROM device_shares WHERE device_id=? AND grantee_user_id=?",
        (device_id, user_id),
    ).fetchone()
    return share["role"] if share else None


def _assert_device_access(db, device_id: str, auth: str, min_role: str = "device_only"):
    """Verify the caller can access a device at or above min_role.

    Roles: owner > admin > viewer > device_only (see _resolve_device_role).
    Existence is verified for EVERY scope: a nonexistent device must be a
    clean 404, never a 500 from a downstream FOREIGN KEY constraint (the
    admin scope historically skipped the existence check, so admin-scope
    writes like command/geofence blew up with an unhandled IntegrityError).
    min_role semantics:
      device_only — status-level visibility (default; any access grants it)
      viewer      — full read access (locations, media, evidence)
      admin       — control (commands, geofences, alert/sms settings)
      owner       — destructive/management actions (delete, share grant/revoke)
    Returns the caller's role so endpoints can branch on it (e.g. hide
    device_only users' coordinates in the device list).
    """
    role = _resolve_device_role(db, device_id, auth)
    if role is None:
        row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        raise HTTPException(
            status_code=403,
            detail="Access denied: device not linked to your account",
        )
    if ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: the '{role}' role cannot perform this action",
        )
    return role


def _verify_stepup_password(db, auth: str, raw_password) -> None:
    """Re-authenticate a destructive action with a step-up password.

    Destructive, privacy-sensitive actions (media/device deletion) must not
    succeed on a stolen dashboard session alone — the caller re-authenticates
    with their account password (user mode) or the master API key itself
    (admin mode). Attempts are rate-limited per actor; raises HTTPException
    (400 missing / 401 wrong / 429 throttled).

    NOTE: check_password_verify_rate_limit / verify_password are imported at
    MODULE level, never inside this function — under full-suite collection
    test_e2e evicts auth/database from sys.modules, so a function-local
    import would resolve the post-eviction chain (different DB_PATH) and the
    step-up bucket would be written to a different DB than the one the test
    fixtures clear (sporadic 429s under full-suite runs only).
    """
    if not check_password_verify_rate_limit(auth):
        raise HTTPException(status_code=429, detail="Too many verification attempts")

    password = raw_password if isinstance(raw_password, str) else ""
    if not password:
        raise HTTPException(status_code=400, detail="Password required")

    user_id = _resolve_user_id(auth)
    if user_id is not None:
        # User mode — verify the account password (bcrypt / PBKDF2).
        with get_db_context() as conn:
            user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")
    else:
        # Admin / API-key mode — re-verify the master API key itself.
        if not hmac.compare_digest(password, settings.API_KEY):
            raise HTTPException(status_code=401, detail="Invalid password")
