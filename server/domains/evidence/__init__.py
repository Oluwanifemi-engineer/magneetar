"""
Evidence & Forensics Domain

Owns: Auto-photo capture, audio recording, media storage/retrieval,
      evidence packaging for police reports, IMEI vault.

Data tables: evidence, media_files
Extracted from: routes/evidence.py, routes/devices.py (media portions)

Media Storage:
  - Phase 0 (current): files in static/evidence/ on local disk
  - Phase 2: migrate to S3/R2 object storage via infrastructure/storage.py

Domain Events Published:
  - evidence_captured      {device_id, evidence_id, type, timestamp}
  - evidence_uploaded      {device_id, evidence_id, storage_url}
  - police_report_generated {device_id, report_id, format}
"""

from __future__ import annotations

import base64
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from database import log_audit
from logging_config import get_logger
from media_store import (
    MediaValidationError,
    delete_media_file,
    media_bytes_for_row,
    save_media,
)

logger = get_logger("magneetar.evidence")

# ─── Evidence case management ──────────────────────────────────────────────────


def create_evidence_case(conn: sqlite3.Connection, device_id: str) -> dict:
    """Create a new evidence case for a device (theft investigation).

    Returns the new case id.
    """
    import secrets

    case_id = f"MGT-{datetime.now(timezone.utc).year}-{secrets.token_hex(2).upper()}"
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO evidence_cases (id, device_id, created_at, theft_time, status)
           VALUES (?, ?, ?, NULL, 'active')""",
        (case_id, device_id, now),
    )
    conn.commit()

    log_audit(
        action="evidence_case_created",
        actor=device_id,
        details=f"Case: {case_id}",
    )

    logger.info(
        "evidence_case_created",
        extra={
            "extra_data": {
                "case_id": case_id,
                "device_id": device_id,
            }
        },
    )

    return {
        "status": "ok",
        "case_id": case_id,
        "device_id": device_id,
        "created_at": now,
    }


def get_evidence_case(
    conn: sqlite3.Connection,
    device_id: str,
) -> Optional[dict]:
    """Get the active evidence case for a device (most recent)."""
    row = conn.execute(
        """SELECT * FROM evidence_cases
           WHERE device_id=? AND status='active'
           ORDER BY created_at DESC LIMIT 1""",
        (device_id,),
    ).fetchone()
    return dict(row) if row else None


def get_evidence_case_by_id(conn: sqlite3.Connection, case_id: str) -> Optional[dict]:
    """Get an evidence case by its id."""
    row = conn.execute(
        "SELECT * FROM evidence_cases WHERE id=?",
        (case_id,),
    ).fetchone()
    return dict(row) if row else None


def close_evidence_case(
    conn: sqlite3.Connection,
    case_id: str,
    closed_reason: str = "",
) -> dict:
    """Close an evidence case (theft resolved, investigation closed, etc.)."""
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """UPDATE evidence_cases
           SET status='closed', closed_at=?, closed_reason=?
           WHERE id=?""",
        (now, closed_reason, case_id),
    )
    conn.commit()

    log_audit(
        action="evidence_case_closed",
        actor="system",
        details=f"Case: {case_id}, Reason: {closed_reason}",
    )

    return {
        "status": "ok",
        "case_id": case_id,
        "closed_at": now,
        "closed_reason": closed_reason,
    }


def reopen_evidence_case(
    conn: sqlite3.Connection,
    case_id: str,
) -> dict:
    """Reopen a closed evidence case (new evidence has come to light)."""
    now = datetime.now(timezone.utc).isoformat()

    cur = conn.execute(
        """UPDATE evidence_cases
           SET status='active', closed_at=NULL, closed_reason=NULL
           WHERE id=?""",
        (case_id,),
    )
    conn.commit()

    if cur.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Evidence case not found")

    return {"status": "ok", "case_id": case_id, "reopened_at": now}


# ─── Media (evidence photos/audio) ─────────────────────────────────────────────


def add_media_to_case(
    conn: sqlite3.Connection,
    case_id: str,
    media_type: str,
    data_b64: str,
) -> dict:
    """Add media (photo/audio) to an evidence case.

    Validates and stores the media file on disk, then updates the case's
    item counts.
    """

    # Store the media file.
    try:
        stored = save_media("evidence", media_type, data_b64)
    except MediaValidationError as e:
        raise ValueError(str(e))

    # Update case counts.
    if media_type == "photo":
        conn.execute(
            "UPDATE evidence_cases SET photo_count = photo_count + 1 WHERE id=?",
            (case_id,),
        )
    elif media_type in ("audio", "audio_capture"):
        conn.execute(
            "UPDATE evidence_cases SET audio_count = audio_count + 1 WHERE id=?",
            (case_id,),
        )
    else:
        # Unknown type — still count it as a generic media item.
        pass

    conn.commit()

    logger.info(
        "evidence_media_added",
        extra={
            "extra_data": {
                "case_id": case_id,
                "media_type": media_type,
                "file_path": stored.get("file_path"),
            }
        },
    )

    return {
        "status": "ok",
        "case_id": case_id,
        "media_type": media_type,
        "file_path": stored.get("file_path"),
        "file_size": stored.get("file_size"),
    }


def get_media_list(
    conn: sqlite3.Connection,
    device_id: str,
) -> list[dict]:
    """Get the list of media items for a device (metadata only, no blobs)."""
    rows = conn.execute(
        """SELECT id, device_id, type, timestamp, lat, lng
           FROM media WHERE device_id=?
           ORDER BY timestamp DESC""",
        (device_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_media_file(
    conn: sqlite3.Connection,
    media_id: int,
) -> Optional[dict]:
    """Get a media file's full data (including the blob/file reference)."""
    row = conn.execute(
        "SELECT * FROM media WHERE id=?",
        (media_id,),
    ).fetchone()
    if not row:
        return None

    try:
        data_b64 = base64.b64encode(media_bytes_for_row(dict(row))).decode("ascii")
    except (FileNotFoundError, ValueError):
        return None

    return {
        "id": row["id"],
        "type": row["type"],
        "data_b64": data_b64,
        "timestamp": row["timestamp"],
        "lat": row["lat"],
        "lng": row["lng"],
        "sha256_hash": row["sha256_hash"],
        "file_size": row["file_size"] if "file_size" in row.keys() else None,
    }


def delete_media_item(
    conn: sqlite3.Connection,
    media_id: int,
    user_id: str,
    min_role: str = "admin",
) -> dict:
    """Delete a media item (gated by dashboard admin role).

    Deletes the file from disk and removes the DB row. Updates the parent
    evidence case's item counts if applicable.
    """
    from routes.dashboard_helpers import _assert_device_access

    row = conn.execute(
        "SELECT * FROM media WHERE id=?",
        (media_id,),
    ).fetchone()
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Media not found")

    _assert_device_access(conn, row["device_id"], user_id, min_role=min_role)

    # Update evidence case counts.
    if row["evidence_case_id"]:
        if row["type"] == "photo":
            conn.execute(
                """UPDATE evidence_cases
                   SET photo_count = MAX(0, photo_count - 1)
                   WHERE id=?""",
                (row["evidence_case_id"],),
            )
        elif row["type"] in ("audio", "audio_capture"):
            conn.execute(
                """UPDATE evidence_cases
                   SET audio_count = MAX(0, audio_count - 1)
                   WHERE id=?""",
                (row["evidence_case_id"],),
            )

    # Delete the file from disk.
    file_path = row["file_path"] if "file_path" in row.keys() else None
    if file_path:
        delete_media_file(file_path)

    # Delete the DB row.
    conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    conn.commit()

    log_audit(
        action="media_deleted",
        actor=user_id,
        details=(f"Media: {media_id}, Device: {row['device_id']}, " f"Type: {row['type']}"),
    )

    return {"status": "ok", "deleted_id": media_id}


def get_media_sha256(
    conn: sqlite3.Connection,
    media_id: int,
) -> Optional[str]:
    """Get the SHA-256 hash of a media file (for integrity verification)."""
    row = conn.execute(
        "SELECT sha256_hash FROM media WHERE id=?",
        (media_id,),
    ).fetchone()
    return row["sha256_hash"] if row else None
