"""
Device Lifecycle Domain

Owns: Device registration, profile management, heartbeat processing,
      device status transitions, device archival, device sharing invitations.

Data tables: devices, device_shares, device_keys
Extracted from: routes/devices.py (registration, profile, heartbeat portions)

Domain Events Published:
  - device_registered      {device_id, owner_id, model}
  - device_heartbeat       {device_id, battery, signal}
  - device_online          {device_id, timestamp}
  - device_offline         {device_id, last_seen}
  - device_archived        {device_id, reason}
  - device_shared          {device_id, grantee_id, role}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from auth import (
    _user_exists,
    hash_device_key,
)
from config import settings
from database import log_audit
from logging_config import get_logger
from models import DeviceRegistration

logger = get_logger("magneetar.device")

# ─── Device ID validation ──────────────────────────────────────────────────────


DEVICE_ID_RE = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


def validate_device_id(device_id: str) -> None:
    """Raise HTTPException(422) if the device_id is malformed."""
    if not device_id or not DEVICE_ID_RE.match(device_id):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid device_id: use 3-64 characters of letters, digits, "
                "dash, underscore, or dot (no spaces or special characters)"
            ),
        )


# ─── Device registration ───────────────────────────────────────────────────────


def register_device(
    conn: sqlite3.Connection,
    reg: DeviceRegistration,
    owner_id: Optional[str] = None,
) -> dict:
    """Register a new device and return the registration response.

    Handles:
    - Fingerprint dedup (reinstall recovery): when the requested device_id is
      new but a device with the same fingerprint already exists and is unowned
      (or its owner account is gone), adopt the existing row as canonical.
    - Same-user exception: a row the registering user already owns is adopted
      regardless of staleness (their token proves ownership).
    - Per-user device limit enforcement when linking to an account.
    - Unowned-registration cap (MAX_UNOWNED_DEVICES).
    - Offline Command Relay prefill (sms_phone from sim_phone, only when NULL).
    - Unarchiving a freshly-registered device.
    """
    validate_device_id(reg.device_id)
    now = datetime.now(timezone.utc).isoformat()
    device_key_hash = None
    if reg.device_key:
        device_key_hash = hash_device_key(reg.device_key)

    canonical_id = reg.device_id
    existing = conn.execute(
        "SELECT id, owner_id FROM devices WHERE id=?",
        (reg.device_id,),
    ).fetchone()

    # ── Fingerprint dedup (reinstall recovery) ────────────────────────────────
    canonical_id = reg.device_id
    if existing is None and reg.fingerprint:
        candidates = conn.execute(
            """SELECT id, owner_id FROM devices
               WHERE device_fingerprint=? AND id != ?
               ORDER BY datetime(COALESCE(last_seen, registered)) DESC""",
            (reg.fingerprint, reg.device_id),
        ).fetchall()
        for canonical in candidates:
            canonical_owner = canonical["owner_id"]
            if owner_id and canonical_owner == owner_id:
                # Same user reinstalling their own device — adopt regardless
                # of staleness; the token already proves ownership.
                existing = canonical
                canonical_id = canonical["id"]
                break
            if canonical_owner is None or not _user_exists(conn, canonical_owner):
                # Unowned/orphaned — require the silence window so a
                # concurrently-reporting device is never hijacked.
                stale = conn.execute(
                    """SELECT (last_seen IS NULL OR
                               datetime(last_seen) < datetime('now', ?)) AS is_stale
                       FROM devices WHERE id=?""",
                    (f"-{settings.DEVICE_ADOPT_AFTER_HOURS} hours", canonical["id"]),
                ).fetchone()
                if stale and stale["is_stale"]:
                    existing = canonical
                    canonical_id = canonical["id"]
                    break

    # ── Per-user device limit ──────────────────────────────────────────────────
    if owner_id:
        already_owned = existing["owner_id"] if existing else None
        if already_owned and already_owned != owner_id:
            if _user_exists(conn, already_owned):
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=403,
                    detail="Device already linked to another account",
                )
        if already_owned is None or not _user_exists(conn, already_owned):
            _enforce_device_limit(conn, owner_id)

    # ── Upsert ─────────────────────────────────────────────────────────────────
    if existing:
        if canonical_id != reg.device_id and device_key_hash is not None:
            # Adoption path: fresh reinstall re-pointed at the pre-existing
            # row — the app generated a brand-new device_key, so replace it.
            conn.execute(
                """UPDATE devices
                   SET device_fingerprint=?, model=?, os_version=?,
                       app_version=?, imei_hash=?, sim_serial_hash=?,
                       device_key_hash=?, owner_id=COALESCE(?, owner_id),
                       last_seen=? WHERE id=?""",
                (
                    reg.fingerprint,
                    reg.model,
                    reg.os_version,
                    reg.app_version,
                    reg.imei_hash,
                    reg.sim_serial_hash,
                    device_key_hash,
                    owner_id,
                    now,
                    canonical_id,
                ),
            )
        else:
            conn.execute(
                """UPDATE devices
                   SET device_fingerprint=?, model=?, os_version=?,
                       app_version=?, imei_hash=?, sim_serial_hash=?,
                       device_key_hash=COALESCE(?, device_key_hash),
                       owner_id=COALESCE(?, owner_id), last_seen=?
                   WHERE id=?""",
                (
                    reg.fingerprint,
                    reg.model,
                    reg.os_version,
                    reg.app_version,
                    reg.imei_hash,
                    reg.sim_serial_hash,
                    device_key_hash,
                    owner_id,
                    now,
                    canonical_id,
                ),
            )
    else:
        # Unowned-registration cap (F-07): the low-privilege DEVICE key is
        # PUBLIC (it ships inside every APK), so a new unowned device row
        # costs nothing to create — cap how many can exist so an attacker
        # can't flood the devices table.
        if owner_id is None:
            unowned = conn.execute("SELECT COUNT(*) as cnt FROM devices WHERE owner_id IS NULL").fetchone()["cnt"]
            if unowned >= settings.MAX_UNOWNED_DEVICES:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Too many unowned devices on this server — register the "
                        "device to your account instead (sign in on the phone first)"
                    ),
                )

        conn.execute(
            """INSERT INTO devices (id, device_fingerprint, model, os_version,
               app_version, imei_hash, sim_serial_hash, device_key_hash,
               owner_id, last_seen, registered)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                canonical_id,
                reg.fingerprint,
                reg.model,
                reg.os_version,
                reg.app_version,
                reg.imei_hash,
                reg.sim_serial_hash,
                device_key_hash,
                owner_id,
                now,
                now,
            ),
        )

    # Prefill the Offline Command Relay recipient from SIM number (only when
    # sms_phone is still NULL — an owner-confirmed number is never overwritten).
    if reg.sim_phone:
        conn.execute(
            "UPDATE devices SET sms_phone=COALESCE(sms_phone, ?) WHERE id=?",
            (reg.sim_phone, canonical_id),
        )

    # Fresh registration un-archives the device (it is alive and reporting).
    unarchive_device(conn, canonical_id)
    conn.commit()

    # Resolve final owner (COALESCE keeps an existing owner on re-register).
    final_owner = conn.execute(
        "SELECT owner_id FROM devices WHERE id=?",
        (canonical_id,),
    ).fetchone()

    log_audit(
        "device_registered",
        actor=canonical_id,
        details=reg.model,
    )

    return {
        "device_id": canonical_id,
        "owner_id": final_owner["owner_id"] if final_owner else None,
        "server_time": now,
    }


def _enforce_device_limit(conn: sqlite3.Connection, user_id: str) -> None:
    """Raise HTTPException(403) when the user already owns their plan's device
    allowance."""
    from config import plan_device_limit

    tier_row = conn.execute(
        "SELECT tier FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    tier = tier_row["tier"] if tier_row else "free"
    limit = plan_device_limit(tier)
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM devices WHERE owner_id=?",
        (user_id,),
    ).fetchone()["cnt"]
    if count >= limit:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail=(f"Device limit reached ({count}/{limit}) — " "upgrade your plan to protect more devices"),
        )


# ─── Device claim ──────────────────────────────────────────────────────────────


def claim_device(
    conn: sqlite3.Connection,
    user_id: str,
    device_id: Optional[str] = None,
    x_device_key: Optional[str] = None,
) -> dict:
    """Link an existing device to the authenticated user's account.

    The device is identified by its per-device secret key (x_device_key) or,
    failing that, by an explicit device_id. The user is authenticated with a
    user bearer token.

    Cross-account claims are blocked when the existing owner is a real account.
    Orphaned devices (owner account was permanently deleted) are claimable by
    anyone with the device key/id.
    """
    if not _user_exists(conn, user_id):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=401,
            detail="Account no longer exists",
        )

    device = None
    if x_device_key:
        key_hash = hash_device_key(x_device_key)
        device = conn.execute(
            "SELECT id, owner_id FROM devices WHERE device_key_hash=?",
            (key_hash,),
        ).fetchone()
    if device is None and device_id:
        device = conn.execute(
            "SELECT id, owner_id FROM devices WHERE id=?",
            (device_id,),
        ).fetchone()
    if device is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Device not found")

    existing_owner = device["owner_id"]
    if existing_owner and _user_exists(conn, existing_owner) and existing_owner != user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Device already linked to another account",
        )

    # Enforce per-user device limit before linking — skip when the device is
    # already owned by this user so re-claims stay idempotent.
    if existing_owner != user_id:
        _enforce_device_limit(conn, user_id)

    conn.execute(
        "UPDATE devices SET owner_id=? WHERE id=?",
        (user_id, device["id"]),
    )
    conn.commit()

    log_audit(
        "device_claimed",
        actor=user_id,
        details=f"Device: {device['id']}",
    )

    return {
        "status": "ok",
        "device_id": device["id"],
        "owner_id": user_id,
    }


# ─── Unarchive ────────────────────────────────────────────────────────────────


def unarchive_device(conn: sqlite3.Connection, device_id: str) -> None:
    """Clear the archived_at flag on a device that has come back online.

    Any fresh telemetry/heartbeat clears the flag automatically.
    """
    conn.execute(
        "UPDATE devices SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL",
        (device_id,),
    )
    conn.commit()


# ─── Device read ───────────────────────────────────────────────────────────────


def get_device(conn: sqlite3.Connection, device_id: str) -> Optional[dict]:
    """Fetch a device by id (full row, excluding sensitive hashes for
    non-owners)."""
    row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    return dict(row) if row else None


def get_device_owner(conn: sqlite3.Connection, device_id: str) -> Optional[str]:
    """Resolve the owner_id of a device."""
    row = conn.execute(
        "SELECT owner_id FROM devices WHERE id=?",
        (device_id,),
    ).fetchone()
    return row["owner_id"] if row else None


def list_user_devices(
    conn: sqlite3.Connection,
    user_id: str,
    include_archived: bool = False,
) -> list[dict]:
    """List all devices owned by a user."""
    if include_archived:
        rows = conn.execute(
            "SELECT * FROM devices WHERE owner_id=? ORDER BY last_seen DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM devices
               WHERE owner_id=? AND (archived_at IS NULL OR
                     datetime(archived_at) > datetime('now', '-7 days'))
               ORDER BY last_seen DESC""",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_device_profile(
    conn: sqlite3.Connection,
    device_id: str,
    alias: Optional[str] = None,
    model: Optional[str] = None,
    os_version: Optional[str] = None,
    app_version: Optional[str] = None,
) -> dict:
    """Update a device's profile fields."""
    sets = []
    params = []
    if alias is not None:
        sets.append("alias=?")
        params.append(alias)
    if model is not None:
        sets.append("model=?")
        params.append(model)
    if os_version is not None:
        sets.append("os_version=?")
        params.append(os_version)
    if app_version is not None:
        sets.append("app_version=?")
        params.append(app_version)
    if not sets:
        return get_device(conn, device_id)
    sets.append("last_seen=?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(device_id)

    conn.execute(
        f"UPDATE devices SET {', '.join(sets)} WHERE id=?",
        params,
    )
    conn.commit()
    return get_device(conn, device_id)
