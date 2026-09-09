"""
Sharing & Circles Domain

Owns: Device sharing between users, family circles, role-based access
      (owner/viewer/device_only), sharing invitations, access revocation.

Data tables: device_shares, circles, circle_members
Extracted from: routes/circles.py

Domain Events Published:
  - device_shared          {device_id, grantor_id, grantee_id, role}
  - sharing_revoked        {device_id, grantor_id, grantee_id}
  - circle_created         {circle_id, owner_id, name}
  - circle_member_added    {circle_id, user_id, role}
  - circle_member_removed  {circle_id, user_id}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from auth import _user_exists
from database import log_audit
from logging_config import get_logger

logger = get_logger("magneetar.sharing")

# ─── Device sharing ────────────────────────────────────────────────────────────


def share_device(
    conn: sqlite3.Connection,
    device_id: str,
    grantee_user_id: str,
    grantor_user_id: str,
    role: str = "viewer",
) -> dict:
    """Grant another user access to a device.

    Role options: 'device_only' (status glance), 'viewer' (read), 'admin'
    (control). Only the device owner can grant/revoke (enforced here).

    Idempotent: re-inviting the same account upgrades/downgrades the role in
    place (UNIQUE(device_id, grantee_user_id)).
    """
    _assert_device_owner(conn, device_id, grantor_user_id)

    if not _user_exists(conn, grantee_user_id):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Recipient account not found",
        )

    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO device_shares (id, device_id, grantee_user_id,
           role, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(device_id, grantee_user_id)
           DO UPDATE SET role=excluded.role, created_by=excluded.created_by""",
        (
            f"share_{device_id}_{grantee_user_id}",
            device_id,
            grantee_user_id,
            role,
            grantor_user_id,
            now,
        ),
    )
    conn.commit()

    log_audit(
        "device_shared",
        actor=grantor_user_id,
        details=f"Device: {device_id}, Grantee: {grantee_user_id}, Role: {role}",
    )

    return {
        "status": "ok",
        "share_id": cur.lastrowid or f"share_{device_id}_{grantee_user_id}",
        "device_id": device_id,
        "grantee_user_id": grantee_user_id,
        "role": role,
    }


def revoke_device_share(
    conn: sqlite3.Connection,
    device_id: str,
    grantee_user_id: str,
    grantor_user_id: str,
) -> dict:
    """Revoke a user's access to a device. Only the device owner can revoke."""
    _assert_device_owner(conn, device_id, grantor_user_id)

    cur = conn.execute(
        """DELETE FROM device_shares
           WHERE device_id=? AND grantee_user_id=?""",
        (device_id, grantee_user_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail="Share not found",
        )

    log_audit(
        "sharing_revoked",
        actor=grantor_user_id,
        details=f"Device: {device_id}, Revoked: {grantee_user_id}",
    )

    return {
        "status": "ok",
        "device_id": device_id,
        "grantee_user_id": grantee_user_id,
    }


def get_device_shares(
    conn: sqlite3.Connection,
    device_id: str,
    user_id: str,
    min_role: str = "viewer",
) -> list[dict]:
    """List all users who have access to a device (including the owner).

    Requires the caller to have at least 'viewer' role on the device.
    """
    from routes.dashboard_helpers import _assert_device_access

    _assert_device_access(conn, device_id, user_id, min_role=min_role)

    rows = conn.execute(
        """SELECT ds.id, ds.device_id, ds.grantee_user_id, ds.role,
                  ds.created_by, ds.created_at,
                  u.email, u.display_name
           FROM device_shares ds
           LEFT JOIN users u ON u.id = ds.grantee_user_id
           WHERE ds.device_id=?
           ORDER BY ds.created_at DESC""",
        (device_id,),
    ).fetchall()

    return [dict(r) for r in rows]


def _assert_device_owner(conn: sqlite3.Connection, device_id: str, user_id: str) -> None:
    """Raise HTTPException(403) if the user is not the device owner."""
    owner = conn.execute(
        "SELECT owner_id FROM devices WHERE id=?",
        (device_id,),
    ).fetchone()
    if not owner or owner["owner_id"] != user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Only the device owner can perform this action",
        )


# ─── Circles (group sharing) ───────────────────────────────────────────────────


def create_circle(
    conn: sqlite3.Connection,
    owner_id: str,
    name: str,
) -> dict:
    """Create a new circle (group). The creator is the admin."""
    import secrets

    circle_id = f"circle_{secrets.token_hex(8)}"
    invite_code = secrets.token_hex(3).upper()
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO circles (id, name, owner_id, invite_code, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (circle_id, name, owner_id, invite_code, now),
    )
    conn.commit()

    log_audit(
        "circle_created",
        actor=owner_id,
        details=f"Circle: {circle_id}, Name: {name}",
    )

    return {
        "status": "ok",
        "circle_id": circle_id,
        "name": name,
        "owner_id": owner_id,
        "invite_code": invite_code,
    }


def join_circle(
    conn: sqlite3.Connection,
    circle_id: str,
    user_id: str,
    invite_code: str,
) -> dict:
    """Join a circle via its invite code. Any member can join (the invite code
    is the only gate)."""
    circle = conn.execute(
        "SELECT id, owner_id, invite_code FROM circles WHERE id=?",
        (circle_id,),
    ).fetchone()
    if not circle:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Circle not found")
    if circle["invite_code"] != invite_code:
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Invalid invite code")

    # Check if already a member.
    existing = conn.execute(
        "SELECT 1 FROM circle_members WHERE circle_id=? AND user_id=?",
        (circle_id, user_id),
    ).fetchone()
    if existing:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail="Already a member of this circle",
        )

    now = datetime.now(timezone.utc).isoformat()
    member_id = f"cm_{circle_id}_{user_id}"
    conn.execute(
        """INSERT INTO circle_members (id, circle_id, user_id, role, joined_at)
           VALUES (?, ?, ?, 'member', ?)""",
        (member_id, circle_id, user_id, now),
    )
    conn.commit()

    log_audit(
        "circle_member_added",
        actor=user_id,
        details=f"Circle: {circle_id}",
    )

    return {
        "status": "ok",
        "circle_id": circle_id,
        "user_id": user_id,
        "role": "member",
    }


def leave_circle(
    conn: sqlite3.Connection,
    circle_id: str,
    user_id: str,
) -> dict:
    """Leave a circle. The owner must transfer ownership first or delete the
    circle."""
    circle = conn.execute(
        "SELECT owner_id FROM circles WHERE id=?",
        (circle_id,),
    ).fetchone()
    if not circle:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Circle not found")
    if circle["owner_id"] == user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Owner must transfer ownership or delete the circle first",
        )

    cur = conn.execute(
        "DELETE FROM circle_members WHERE circle_id=? AND user_id=?",
        (circle_id, user_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not a member of this circle")

    log_audit(
        "circle_member_removed",
        actor=user_id,
        details=f"Circle: {circle_id}",
    )

    return {"status": "ok", "circle_id": circle_id, "user_id": user_id}


def delete_circle(
    conn: sqlite3.Connection,
    circle_id: str,
    user_id: str,
) -> dict:
    """Delete a circle. Only the owner can delete."""
    circle = conn.execute(
        "SELECT owner_id FROM circles WHERE id=?",
        (circle_id,),
    ).fetchone()
    if not circle:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Circle not found")
    if circle["owner_id"] != user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Only the circle owner can delete it",
        )

    conn.execute("DELETE FROM circle_members WHERE circle_id=?", (circle_id,))
    conn.execute("DELETE FROM circle_devices WHERE circle_id=?", (circle_id,))
    conn.execute("DELETE FROM circles WHERE id=?", (circle_id,))
    conn.commit()

    log_audit(
        "circle_deleted",
        actor=user_id,
        details=f"Circle: {circle_id}",
    )

    return {"status": "ok", "circle_id": circle_id}


def get_circle(
    conn: sqlite3.Connection,
    circle_id: str,
) -> Optional[dict]:
    """Fetch a circle by id (owner info included)."""
    row = conn.execute(
        """SELECT c.id, c.name, c.owner_id, c.invite_code, c.created_at,
                  u.email as owner_email, u.display_name as owner_name
           FROM circles c
           LEFT JOIN users u ON u.id = c.owner_id
           WHERE c.id=?""",
        (circle_id,),
    ).fetchone()
    return dict(row) if row else None


def list_circles_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """List all circles a user is a member of."""
    rows = conn.execute(
        """SELECT c.id, c.name, c.owner_id, c.invite_code, c.created_at,
                  cm.role, cm.joined_at
           FROM circles c
           JOIN circle_members cm ON cm.circle_id = c.id
           WHERE cm.user_id=?
           ORDER BY c.created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_device_to_circle(
    conn: sqlite3.Connection,
    circle_id: str,
    device_id: str,
    user_id: str,
) -> dict:
    """Add a device to a circle (auto-shared by members). Only the circle owner
    or a device owner can add a device."""
    circle = conn.execute(
        "SELECT owner_id FROM circles WHERE id=?",
        (circle_id,),
    ).fetchone()
    if not circle:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Circle not found")

    # Device owner or circle owner can add.
    device_owner = conn.execute(
        "SELECT owner_id FROM devices WHERE id=?",
        (device_id,),
    ).fetchone()
    if not device_owner:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Device not found")

    if circle["owner_id"] != user_id and device_owner["owner_id"] != user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Only the circle owner or device owner can add a device",
        )

    now = datetime.now(timezone.utc).isoformat()
    entry_id = f"cd_{circle_id}_{device_id}"
    conn.execute(
        """INSERT INTO circle_devices (id, circle_id, device_id, shared_by, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(circle_id, device_id) DO NOTHING""",
        (entry_id, circle_id, device_id, user_id, now),
    )
    conn.commit()

    log_audit(
        "circle_device_added",
        actor=user_id,
        details=f"Circle: {circle_id}, Device: {device_id}",
    )

    return {
        "status": "ok",
        "circle_id": circle_id,
        "device_id": device_id,
    }


def remove_device_from_circle(
    conn: sqlite3.Connection,
    circle_id: str,
    device_id: str,
    user_id: str,
) -> dict:
    """Remove a device from a circle. Only the circle owner can remove."""
    circle = conn.execute(
        "SELECT owner_id FROM circles WHERE id=?",
        (circle_id,),
    ).fetchone()
    if not circle:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Circle not found")
    if circle["owner_id"] != user_id:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="Only the circle owner can remove devices",
        )

    cur = conn.execute(
        "DELETE FROM circle_devices WHERE circle_id=? AND device_id=?",
        (circle_id, device_id),
    )
    conn.commit()

    if cur.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Device not in circle")

    log_audit(
        "circle_device_removed",
        actor=user_id,
        details=f"Circle: {circle_id}, Device: {device_id}",
    )

    return {
        "status": "ok",
        "circle_id": circle_id,
        "device_id": device_id,
    }
