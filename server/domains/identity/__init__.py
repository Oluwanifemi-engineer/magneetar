"""
Identity & Access Domain

Owns: User registration, authentication, JWT tokens, 2FA, password reset,
      email verification, API key management, device key authentication.

Data tables: users, user_sessions, user_2fa, api_keys
Extracted from: user_auth.py, user_security.py

Domain Events Published:
  - user_registered        {user_id, email, method}
  - user_authenticated     {user_id, method, ip}
  - user_2fa_enabled       {user_id, method}
  - user_password_reset    {user_id, method}
  - api_key_created        {user_id, key_id}
  - device_key_registered  {device_id, owner_id}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from auth import (
    create_dashboard_tokens,
    create_device_tokens,
    decode_token,
    refresh_access_token,
    user_id_from_subject,
)
from database import log_audit
from encryption import decrypt_totp_secret, encrypt_totp_secret
from logging_config import get_logger
from models import TokenResponse

logger = get_logger("magneetar.identity")

# ─── Token helpers (re-export from auth for domain consumers) ─────────────────


def dashboard_tokens_from_key(api_key: str) -> TokenResponse:
    """Mint dashboard access + refresh tokens from the master API key."""
    return create_dashboard_tokens(api_key)


def device_tokens_from_id(device_id: str) -> TokenResponse:
    """Mint device-scoped access + refresh tokens from a device id."""
    return create_device_tokens(device_id)


def refresh_dashboard_token(refresh_token: str) -> TokenResponse:
    """Rotate a dashboard refresh token into a new access + refresh pair."""
    return refresh_access_token(refresh_token)


def resolve_user_id_from_token(bearer: str) -> Optional[str]:
    """Resolve a user id from a bearer JWT. Returns None if not a user token."""
    if not bearer:
        return None
    try:
        payload = decode_token(bearer)
    except Exception:
        return None
    return user_id_from_subject(payload.get("sub", ""))


# ─── User registration ─────────────────────────────────────────────────────────


def register_user(
    conn: sqlite3.Connection,
    email: str,
    password_hash: str,
    display_name: Optional[str] = None,
) -> str:
    """Register a new user account.

    Returns the new user id.
    """
    import secrets

    user_id = f"usr_{secrets.token_hex(16)}"
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO users (id, email, password_hash, display_name,
           tier, is_active, email_verified, created_at)
           VALUES (?, ?, ?, ?, 'free', 1, 0, ?)""",
        (user_id, email, password_hash, display_name, now),
    )
    conn.commit()

    log_audit(
        action="user_registered",
        actor=user_id,
        details=f"Email: {email}",
    )

    return user_id


def authenticate_user(
    conn: sqlite3.Connection,
    email: str,
    password_hash: str,
) -> Optional[dict]:
    """Authenticate a user by email + password hash.

    Returns the user row dict if credentials are valid, None otherwise.
    """
    row = conn.execute(
        """SELECT id, email, password_hash, tier, is_active,
           email_verified, totp_enabled, totp_secret_enc, totp_last_period
           FROM users WHERE email=?""",
        (email,),
    ).fetchone()
    if not row:
        return None
    if row["password_hash"] != password_hash:
        return None
    if not row["is_active"]:
        return None
    return dict(row)


# ─── 2FA (TOTP) ────────────────────────────────────────────────────────────────


def enable_2fa(
    conn: sqlite3.Connection,
    user_id: str,
    totp_secret: str,
    totp_provisioning_uri: str,
) -> dict:
    """Encrypt and store a user's TOTP secret. Called AFTER the user proves
    a valid code (so a mistyped secret during setup is rejected before it
    gets stored).

    Returns the provisioning URI so the dashboard can render the QR.
    """
    from pyotp import TOTP

    # Verify the secret is valid before storing.
    totp = TOTP(totp_secret)
    if not totp.verify(periods=1):
        raise ValueError("Invalid TOTP secret")

    encrypted = encrypt_totp_secret(totp_secret)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """UPDATE users SET totp_secret_enc=?, totp_enabled=1,
           totp_last_period=0, updated_at=? WHERE id=?""",
        (encrypted, now, user_id),
    )
    conn.commit()

    log_audit(
        action="user_2fa_enabled",
        actor=user_id,
        details="TOTP",
    )

    return {
        "provisioning_uri": totp_provisioning_uri,
        "user_id": user_id,
        "enabled": True,
    }


def disable_2fa(conn: sqlite3.Connection, user_id: str) -> dict:
    """Disable TOTP 2FA for a user (after they prove a valid code or the
    recovery code)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE users SET totp_secret_enc=NULL, totp_enabled=0,
           totp_last_period=0, updated_at=? WHERE id=?""",
        (now, user_id),
    )
    conn.commit()

    log_audit(
        action="user_2fa_disabled",
        actor=user_id,
        details="TOTP",
    )

    return {"user_id": user_id, "enabled": False}


def verify_totp_code(
    conn: sqlite3.Connection,
    user_id: str,
    code: str,
) -> bool:
    """Verify a TOTP code for a user. Returns True if valid."""
    from pyotp import TOTP

    row = conn.execute(
        "SELECT totp_secret_enc, totp_last_period FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    if not row or not row["totp_secret_enc"]:
        return False

    secret = decrypt_totp_secret(row["totp_secret_enc"])
    totp = TOTP(secret)

    # Period-based replay protection: reject codes from the same time step
    # as the last accepted code.
    current_period = totp.time_counter()
    if current_period == row["totp_last_period"]:
        return False

    if totp.verify(code):
        conn.execute(
            "UPDATE users SET totp_last_period=? WHERE id=?",
            (current_period, user_id),
        )
        conn.commit()
        return True

    return False


# ─── Password reset ────────────────────────────────────────────────────────────


def create_password_reset_token(
    conn: sqlite3.Connection,
    user_id: str,
) -> str:
    """Create a single-use, expiring password reset token.

    Returns the raw token (sent to the user's email) — only the hash is
    stored.
    """
    import secrets

    raw_token = secrets.token_urlsafe(32)
    token_hash = __import__("hashlib").sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=1)

    conn.execute(
        """INSERT INTO password_reset_tokens
           (id, user_id, token_hash, expires_at, used, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (user_id, user_id, token_hash, expires_at.isoformat(), now.isoformat()),
    )
    conn.commit()

    log_audit(
        action="password_reset_requested",
        actor=user_id,
        details="Token created",
    )

    return raw_token


def consume_password_reset_token(
    conn: sqlite3.Connection,
    user_id: str,
    raw_token: str,
) -> bool:
    """Validate and consume a password reset token. Returns True if valid
    and not expired/used."""
    import hashlib

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    datetime.now(timezone.utc).isoformat()

    row = conn.execute(
        """SELECT id FROM password_reset_tokens
           WHERE user_id=? AND token_hash=? AND used=0
             AND datetime(expires_at) > datetime('now')""",
        (user_id, token_hash),
    ).fetchone()

    if not row:
        return False

    # Mark as used (single-use).
    conn.execute(
        "UPDATE password_reset_tokens SET used=1 WHERE id=?",
        (row["id"],),
    )
    conn.commit()

    log_audit(
        action="password_reset_consumed",
        actor=user_id,
        details="Token consumed",
    )

    return True


def reset_password(conn: sqlite3.Connection, user_id: str, new_password_hash: str) -> dict:
    """Reset a user's password after a valid reset token has been consumed."""
    conn.execute(
        "UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
        (new_password_hash, datetime.now(timezone.utc).isoformat(), user_id),
    )
    conn.commit()

    log_audit(
        action="password_reset_completed",
        actor=user_id,
        details="Password reset",
    )

    return {"user_id": user_id, "reset": True}


# ─── Email verification ─────────────────────────────────────────────────────────


def create_email_verify_token(
    conn: sqlite3.Connection,
    user_id: str,
) -> str:
    """Create a single-use, expiring email verification token.

    Returns the raw token (sent to the user's email) — only the hash is
    stored.
    """
    import secrets

    raw_token = secrets.token_urlsafe(32)
    token_hash = __import__("hashlib").sha256(raw_token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=24)

    conn.execute(
        """INSERT INTO email_verify_tokens
           (id, user_id, token_hash, expires_at, used, created_at)
           VALUES (?, ?, ?, ?, 0, ?)""",
        (user_id, user_id, token_hash, expires_at.isoformat(), now.isoformat()),
    )
    conn.commit()

    return raw_token


def consume_email_verify_token(
    conn: sqlite3.Connection,
    user_id: str,
    raw_token: str,
) -> bool:
    """Validate and consume an email verification token. Returns True if valid."""
    import hashlib

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = conn.execute(
        """SELECT id FROM email_verify_tokens
           WHERE user_id=? AND token_hash=? AND used=0
             AND datetime(expires_at) > datetime('now')""",
        (user_id, token_hash),
    ).fetchone()

    if not row:
        return False

    conn.execute(
        "UPDATE email_verify_tokens SET used=1 WHERE id=?",
        (row["id"],),
    )
    conn.execute(
        "UPDATE users SET email_verified=1 WHERE id=?",
        (user_id,),
    )
    conn.commit()

    return True


# ─── Account management ─────────────────────────────────────────────────────────


def get_user(conn: sqlite3.Connection, user_id: str) -> Optional[dict]:
    """Fetch a user by id (excluding password hash for privacy)."""
    row = conn.execute(
        """SELECT id, email, display_name, tier, is_active,
           email_verified, created_at, last_login, totp_enabled
           FROM users WHERE id=?""",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def update_user_profile(
    conn: sqlite3.Connection,
    user_id: str,
    display_name: Optional[str] = None,
    tier: Optional[str] = None,
) -> dict:
    """Update a user's display name and/or tier."""
    now = datetime.now(timezone.utc).isoformat()
    sets = []
    params = []
    if display_name is not None:
        sets.append("display_name=?")
        params.append(display_name)
    if tier is not None:
        sets.append("tier=?")
        params.append(tier)
    if not sets:
        return get_user(conn, user_id)
    sets.append("updated_at=?")
    params.append(now)
    params.append(user_id)

    conn.execute(
        f"UPDATE users SET {', '.join(sets)} WHERE id=?",
        params,
    )
    conn.commit()
    return get_user(conn, user_id)


def delete_user(conn: sqlite3.Connection, user_id: str) -> dict:
    """Permanently delete a user and all their data.

    This is the 'right to erasure' path — deletes the user row and all
    device/sharing/command/etc. data owned by the user.
    """
    from database import delete_device_cascade

    # Delete all devices owned by this user (cascades to locations, media,
    # commands, evidence, alerts, heartbeats, geofences, shares).
    devices = conn.execute(
        "SELECT id FROM devices WHERE owner_id=?",
        (user_id,),
    ).fetchall()
    for d in devices:
        delete_device_cascade(conn, d["id"])

    # Delete the user row.
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()

    log_audit(
        action="user_deleted",
        actor=user_id,
        details="Account permanently deleted",
    )

    return {"user_id": user_id, "deleted": True}
