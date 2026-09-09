"""
Privacy & Compliance Domain

Owns: Consent tracking (GDPR), data retention enforcement, data export,
      right-to-erasure processing, cookie consent, privacy policy compliance.

Data tables: consent_records, data_export_jobs
Extracted from: routes/consent.py, data retention logic in main.py

Domain Events Published:
  - consent_recorded       {user_id, purpose, granted, timestamp}
  - consent_withdrawn      {user_id, purpose, timestamp}
  - data_export_requested  {user_id, request_id, format}
  - data_export_ready      {user_id, request_id, download_url}
  - data_deletion_requested {user_id, request_id}
  - data_deletion_completed {user_id, request_id}
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from database import log_audit
from logging_config import get_logger

logger = get_logger("magneetar.privacy")

# ─── Consent tracking (GDPR/NDPR) ──────────────────────────────────────────────


def record_tracking_consent(
    conn: sqlite3.Connection,
    device_id: str,
    grantee_user_id: str,
    grantor_user_id: str,
    consent_given: bool = True,
    consent_method: str = "explicit_grant",
) -> dict:
    """Record a tracking consent decision for a device share.

    consent_given=True: the device owner has explicitly granted tracking.
    consent_given=False: the device owner has withdrawn tracking consent.

    Each consent record is immutable — a withdrawal creates a new record with
    consent_given=False and a revocation timestamp.
    """
    now = datetime.now(timezone.utc).isoformat()
    consent_id = f"tc_{device_id}_{grantee_user_id}_{now.replace(':', '').replace('-', '')}"

    # Insert the consent record.
    conn.execute(
        """INSERT INTO tracking_consents
           (id, device_id, grantee_user_id, grantor_user_id,
            consent_given, consent_timestamp, consent_method)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            consent_id,
            device_id,
            grantee_user_id,
            grantor_user_id,
            1 if consent_given else 0,
            now,
            consent_method,
        ),
    )

    if not consent_given:
        # Revoke any prior active consent (soft revoke + timestamp).
        conn.execute(
            """UPDATE tracking_consents
               SET revoked=1, revocation_timestamp=?, revocation_method=?
               WHERE device_id=? AND grantee_user_id=? AND revoked=0""",
            (now, consent_method, device_id, grantee_user_id),
        )

    conn.commit()

    log_audit(
        action="consent_recorded",
        actor=grantor_user_id,
        details=(
            f"Device: {device_id}, Grantee: {grantee_user_id}, " f"Granted: {consent_given}, Method: {consent_method}"
        ),
    )

    return {
        "status": "ok",
        "consent_id": consent_id,
        "device_id": device_id,
        "grantee_user_id": grantee_user_id,
        "consent_given": consent_given,
        "consent_timestamp": now,
    }


def get_tracking_consent(
    conn: sqlite3.Connection,
    device_id: str,
    grantee_user_id: str,
) -> Optional[dict]:
    """Get the current tracking consent state for a device + grantee pair.

    Returns the most recent consent record (active or revoked).
    """
    row = conn.execute(
        """SELECT * FROM tracking_consents
           WHERE device_id=? AND grantee_user_id=?
           ORDER BY consent_timestamp DESC LIMIT 1""",
        (device_id, grantee_user_id),
    ).fetchone()
    return dict(row) if row else None


def is_tracking_allowed(
    conn: sqlite3.Connection,
    device_id: str,
    grantee_user_id: str,
) -> bool:
    """Check whether tracking is currently allowed for a device + grantee pair.

    Returns False if there is no consent record or the most recent record is
    revoked/ rejected.
    """
    consent = get_tracking_consent(conn, device_id, grantee_user_id)
    if not consent:
        return False
    return bool(consent["consent_given"]) and not bool(consent["revoked"])


# ─── Privacy consents (user-level) ─────────────────────────────────────────────


def record_privacy_consent(
    conn: sqlite3.Connection,
    user_id: str,
    consent_type: str,
    consent_given: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Record a user-level privacy consent (GDPR/NDPR).

    consent_type examples: 'privacy_policy', 'terms_of_service', 'marketing',
    'data_processing'.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO privacy_consents
           (user_id, consent_type, consent_given, consent_timestamp,
            ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            consent_type,
            1 if consent_given else 0,
            now,
            ip_address,
            user_agent,
        ),
    )
    conn.commit()

    log_audit(
        action="consent_recorded",
        actor=user_id,
        details=f"Type: {consent_type}, Granted: {consent_given}",
    )

    return {
        "status": "ok",
        "user_id": user_id,
        "consent_type": consent_type,
        "consent_given": consent_given,
        "consent_timestamp": now,
    }


def withdraw_privacy_consent(
    conn: sqlite3.Connection,
    user_id: str,
    consent_type: str,
) -> dict:
    """Withdraw a user-level privacy consent."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE privacy_consents
           SET revoked=1, revocation_timestamp=?
           WHERE user_id=? AND consent_type=? AND revoked=0""",
        (now, user_id, consent_type),
    )
    conn.commit()

    log_audit(
        action="consent_withdrawn",
        actor=user_id,
        details=f"Type: {consent_type}",
    )

    return {
        "status": "ok",
        "user_id": user_id,
        "consent_type": consent_type,
        "withdrawn_at": now,
    }


def get_user_consent_history(
    conn: sqlite3.Connection,
    user_id: str,
) -> list[dict]:
    """Get all privacy consent records for a user."""
    rows = conn.execute(
        """SELECT * FROM privacy_consents
           WHERE user_id=? ORDER BY consent_timestamp DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Data export (GDPR right to portability) ──────────────────────────────────


# Thread-safe counter for export request IDs (simple, no external deps).
_export_counter_lock = threading.Lock()
_export_counter = 0


def _next_export_id() -> str:
    global _export_counter
    with _export_counter_lock:
        _export_counter += 1
        return f"exp_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{_export_counter:04d}"


def request_data_export(
    conn: sqlite3.Connection,
    user_id: str,
    export_format: str = "json",
) -> dict:
    """Request a data export for a user (GDPR right to portability).

    Creates an export request record. The actual export is generated
    asynchronously (in production, this would be a background job).
    """
    request_id = _next_export_id()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO data_export_requests
           (id, user_id, status, requested_at, download_url, expires_at)
           VALUES (?, ?, 'pending', ?, NULL, ?)""",
        (request_id, user_id, now, (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=7)).isoformat()),
    )
    conn.commit()

    log_audit(
        action="data_export_requested",
        actor=user_id,
        details=f"Request: {request_id}, Format: {export_format}",
    )

    return {
        "status": "ok",
        "request_id": request_id,
        "user_id": user_id,
        "format": export_format,
        "requested_at": now,
        "expires_at": (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=7)).isoformat(),
    }


def get_export_request(
    conn: sqlite3.Connection,
    request_id: str,
    user_id: str,
) -> Optional[dict]:
    """Get the status of a data export request."""
    row = conn.execute(
        """SELECT * FROM data_export_requests
           WHERE id=? AND user_id=?""",
        (request_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_export_requests(
    conn: sqlite3.Connection,
    user_id: str,
) -> list[dict]:
    """List all data export requests for a user."""
    rows = conn.execute(
        """SELECT * FROM data_export_requests
           WHERE user_id=? ORDER BY requested_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ─── Right to erasure (GDPR/NDPR deletion) ────────────────────────────────────


def request_data_deletion(
    conn: sqlite3.Connection,
    user_id: str,
) -> dict:
    """Request permanent deletion of a user's data (GDPR/NDPR right to erasure).

    Creates a deletion request record. The actual deletion is performed
    asynchronously (in production, this would be a background job with a
    confirmation period). Returns the request id for tracking.
    """
    import secrets

    request_id = f"del_{secrets.token_hex(8)}"
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO data_export_requests
           (id, user_id, status, requested_at, download_url, expires_at)
           VALUES (?, ?, 'deletion_pending', ?, NULL, ?)""",
        (
            request_id,
            user_id,
            now,
            (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=30)).isoformat(),
        ),
    )
    conn.commit()

    log_audit(
        action="data_deletion_requested",
        actor=user_id,
        details=f"Request: {request_id}",
    )

    return {
        "status": "ok",
        "request_id": request_id,
        "user_id": user_id,
        "requested_at": now,
        "scheduled_deletion": (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=30)).isoformat(),
    }


def get_deletion_request(
    conn: sqlite3.Connection,
    request_id: str,
    user_id: str,
) -> Optional[dict]:
    """Get the status of a data deletion request."""
    row = conn.execute(
        """SELECT * FROM data_export_requests
           WHERE id=? AND user_id=?
             AND status IN ('deletion_pending', 'deleting', 'completed')""",
        (request_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def cancel_deletion_request(
    conn: sqlite3.Connection,
    request_id: str,
    user_id: str,
) -> dict:
    """Cancel a pending data deletion request (before it is executed)."""
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """UPDATE data_export_requests
           SET status='cancelled', completed_at=?
           WHERE id=? AND user_id=? AND status='deletion_pending'""",
        (now, request_id, user_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Deletion request not found or already processed",
        )

    log_audit(
        action="data_deletion_cancelled",
        actor=user_id,
        details=f"Request: {request_id}",
    )

    return {
        "status": "ok",
        "request_id": request_id,
        "cancelled_at": now,
    }
