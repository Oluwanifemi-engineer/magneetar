"""
Magneetar Developer API Keys (spec: docs/developer-api.md)
───────────────────────────────────────────────────────────
Per-account, scoped, revocable API keys for third-party integrations
(resellers, alerting scripts, custom dashboards). Two families of routes:

1. `/api/account/api-keys/*` — key MANAGEMENT (create / list / revoke /
   rotate), gated by a USER dashboard JWT + step-up password, exactly like
   2FA enable and device deletion. The full key is returned ONCE at
   creation; the server stores only a 12-char prefix + SHA-256 hash.

2. `/api/v1/*` — the DATA surface. Authenticated with
   `Authorization: Bearer mtk_...` via auth.get_api_key_actor. The key
   resolves to the OWNING ACCOUNT, so all existing RBAC/share rules apply
   (a viewer-shared device stays read-only through the key too), and each
   route enforces the key's scopes via require_api_key_scope.

Security model:
- Keys are a DATA-PLANE credential. Dashboard/auth/metrics/key-management
  routes use their own JWT-only dependencies, so a leaked developer key can
  never reach them (same guarantee as the APK device key vs admin — F-02).
- Management routes are USER-account-only: operator/dashboard (API-key
  admin) sessions have no account to own keys and are rejected with 403.
- Step-up password re-authentication (rate-limited) on create/revoke/rotate
  so a stolen dashboard session alone cannot mint or destroy credentials.
- The raw key never appears in logs, audit rows, or the DB (prefix + hash
  only). Per-key rate limit 120 req/min enforced in get_api_key_actor.
"""

import uuid
from datetime import datetime, timezone

from auth import (
    ApiKeyActor,
    check_command_rate_limit,
    check_password_verify_rate_limit,
    generate_api_key,
    get_current_user,
    hash_device_key,
    require_api_key_scope,
    verify_password,
)
from database import get_db, get_db_context, log_audit
from encryption import decrypt_location, decrypt_location_row
from fastapi import APIRouter, Depends, HTTPException
from models import ApiKeyActionRequest, ApiKeyCreateRequest
from pydantic import BaseModel

router = APIRouter()


# ─── Step-up helpers ─────────────────────────────────────────────────────────


def _require_user_actor(auth: str) -> str:
    """Developer keys are a USER-account feature — operator/dashboard
    sessions (subject 'dashboard:<hash>') have no account to own keys and
    are rejected, mirroring user_security._require_user_actor.

    get_current_user already strips the 'user:' prefix, so auth is the bare
    user id for accounts (e.g. 'usr-abc123') and the raw subject for
    operators ('dashboard:<hash>') — never re-parse it."""
    if auth == "api_key_user" or auth.startswith("dashboard:"):
        raise HTTPException(status_code=403, detail="Developer API keys are a user-account feature")
    return auth


def _user_exists(user_id: str) -> bool:
    with get_db_context() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    return row is not None


def _verify_user_stepup(user_id: str, raw_password) -> None:
    """Re-verify the account password (rate-limited) before creating,
    revoking, or rotating keys — a stolen session alone must never mint or
    destroy long-lived credentials. Same contract as 2FA enable/disable."""
    if not check_password_verify_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="Too many verification attempts")
    password = raw_password if isinstance(raw_password, str) else ""
    if not password:
        raise HTTPException(status_code=400, detail="Password required")
    with get_db_context() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid password")


def _insert_key(db, user_id: str, name: str, scopes: list, expires_at) -> dict:
    """Mint a key, store prefix+hash, return the full key + metadata (the
    full key is returned to the caller exactly once)."""
    raw = generate_api_key()
    key_id = f"ak-{uuid.uuid4().hex[:12]}"
    prefix = raw[:12]
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO api_keys (id, user_id, name, key_prefix, key_hash, scopes, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key_id, user_id, name, prefix, hash_device_key(raw), ",".join(scopes), now, expires_at),
    )
    db.commit()
    return {
        "id": key_id,
        "name": name,
        "key": raw,
        "key_prefix": prefix,
        "scopes": scopes,
        "created_at": now,
        "expires_at": expires_at,
    }


# ─── Key management (user JWT + step-up) ─────────────────────────────────────


@router.post("/api/account/api-keys")
async def create_api_key(
    req: ApiKeyCreateRequest,
    db=Depends(get_db),
    auth: str = Depends(get_current_user),
):
    """Create a scoped developer API key. Requires the account password
    (step-up). Returns the FULL key exactly once — the server stores only
    the prefix + SHA-256 hash, so it cannot be recovered later."""
    user_id = _require_user_actor(auth)
    if not _user_exists(user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")
    _verify_user_stepup(user_id, req.password)

    result = _insert_key(db, user_id, req.name, req.scopes, req.expires_at)
    log_audit(
        "api_key_created",
        actor=user_id,
        details=f"key_prefix={result['key_prefix']} scopes={','.join(req.scopes)}",
    )
    return result


@router.get("/api/account/api-keys")
async def list_api_keys(auth: str = Depends(get_current_user)):
    """List the caller's keys — prefix + metadata only, never the hash or
    the full key. last_used_at lets the owner spot keys they forgot about."""
    user_id = _require_user_actor(auth)
    with get_db_context() as conn:
        rows = conn.execute(
            "SELECT id, name, key_prefix, scopes, created_at, last_used_at, expires_at, revoked_at "
            "FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    keys = []
    for r in rows:
        item = dict(r)
        item["scopes"] = [s for s in (item.get("scopes") or "").split(",") if s]
        keys.append(item)
    return {"api_keys": keys}


@router.delete("/api/account/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    body: ApiKeyActionRequest,
    auth: str = Depends(get_current_user),
):
    """Revoke a key immediately — every subsequent request with it gets 401.
    Soft-revoke (revoked_at stamp) keeps the audit trail intact. Step-up
    password required: a stolen session alone must not be able to kill
    credentials (nor, conversely, to keep keys alive after account theft)."""
    user_id = _require_user_actor(auth)
    if not _user_exists(user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")
    _verify_user_stepup(user_id, body.password)

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT key_prefix FROM api_keys WHERE id=? AND user_id=? AND revoked_at IS NULL",
            (key_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="API key not found")
        conn.execute(
            "UPDATE api_keys SET revoked_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), key_id),
        )
        conn.commit()
    log_audit("api_key_revoked", actor=user_id, details=f"key_prefix={row['key_prefix']}")
    return {"status": "ok", "id": key_id}


@router.post("/api/account/api-keys/{key_id}/rotate")
async def rotate_api_key(
    key_id: str,
    body: ApiKeyActionRequest,
    db=Depends(get_db),
    auth: str = Depends(get_current_user),
):
    """Revoke the old key and mint a fresh one with the same name/scopes/
    expiry — the standard response to a suspected leak. The old key dies
    instantly; the new full key is returned exactly once. Step-up gated."""
    user_id = _require_user_actor(auth)
    if not _user_exists(user_id):
        raise HTTPException(status_code=401, detail="Account no longer exists")
    _verify_user_stepup(user_id, body.password)

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT name, scopes, expires_at, key_prefix FROM api_keys "
            "WHERE id=? AND user_id=? AND revoked_at IS NULL",
            (key_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="API key not found")
        conn.execute(
            "UPDATE api_keys SET revoked_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), key_id),
        )
        conn.commit()

    name = row["name"]
    scopes = [s for s in (row["scopes"] or "").split(",") if s]
    expires_at = row["expires_at"]
    result = _insert_key(db, user_id, name, scopes, expires_at)
    log_audit(
        "api_key_rotated",
        actor=user_id,
        details=f"old_prefix={row['key_prefix']} new_prefix={result['key_prefix']}",
    )
    return result


# ─── Developer data surface (/api/v1/* — key auth + scopes + RBAC) ───────────


class V1CommandRequest(BaseModel):
    """Issue a command through a developer key. Same command set as the
    dashboard minus `wipe` (factory reset requires the dashboard step-up
    password — a key has no password, so wipe is deliberately rejected)."""

    command: str
    params: str = ""

    def model_post_init(self, __context) -> None:
        # Validated in the route to keep the project's single command
        # whitelist source (models.CommandRequest) authoritative.
        pass


def _role_for(db, device_id: str, user_id: str):
    """Effective role (owner/admin/viewer/device_only/None) for a user on a
    device — the key's data access is exactly the account's own RBAC rights."""
    row = db.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
    if not row:
        return None
    if row["owner_id"] == user_id:
        return "owner"
    share = db.execute(
        "SELECT role FROM device_shares WHERE device_id=? AND grantee_user_id=?",
        (device_id, user_id),
    ).fetchone()
    return share["role"] if share else None


_ROLE_RANK = {"device_only": 0, "viewer": 1, "admin": 2, "owner": 3}


def _assert_device_access(db, device_id: str, user_id: str, min_role: str) -> str:
    """Mirror of routes/dashboard._assert_device_access for the key actor:
    existence is verified first (clean 404), then role >= min_role (403)."""
    role = _role_for(db, device_id, user_id)
    if role is None:
        row = db.execute("SELECT id FROM devices WHERE id=?", (device_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Device not found")
        raise HTTPException(status_code=403, detail="Access denied: device not linked to your account")
    if _ROLE_RANK[role] < _ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: the '{role}' role cannot perform this action",
        )
    return role


@router.get("/api/v1/devices")
async def v1_list_devices(
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("devices:read")),
):
    """List the account's devices (owned + shared), each tagged with the
    caller's access_role. Coordinates are stripped for device_only shares
    (privacy tier), exactly like the dashboard list."""
    user_id = actor.user_id
    rows = db.execute(
        """SELECT d.*,
                  l.lat, l.lng, l.location_encrypted, l.location_data,
                  l.battery_percent, l.sentinel_score, l.threat_level,
                  CASE WHEN d.owner_id = ? THEN 'owner'
                       ELSE COALESCE(ds.role, 'viewer') END AS access_role
           FROM devices d
           LEFT JOIN device_shares ds
                  ON ds.device_id = d.id AND ds.grantee_user_id = ?
           LEFT JOIN locations l ON d.id = l.device_id
               AND l.id = (SELECT MAX(id) FROM locations WHERE device_id = d.id)
           WHERE d.owner_id = ? OR ds.grantee_user_id IS NOT NULL
           ORDER BY d.last_seen DESC""",
        (user_id, user_id, user_id),
    ).fetchall()

    result = []
    for d in rows:
        lat, lng = None, None
        if d["access_role"] != "device_only":
            # The joined row has no device_id key (device id lives in d.id) —
            # pass it explicitly, same as dashboard list_devices.
            lat, lng = decrypt_location(
                d["lat"],
                d["lng"],
                bool(d["location_encrypted"]),
                d["location_data"],
                d["id"],
            )
        result.append(
            {
                "id": d["id"],
                "alias": d["alias"],
                "model": d["model"],
                "os_version": d["os_version"],
                "app_version": d["app_version"],
                "last_seen": d["last_seen"],
                "registered": d["registered"],
                "is_stolen": bool(d["is_stolen"]),
                "operating_mode": d["operating_mode"],
                "sentinel_score": d["sentinel_score"] or 0,
                "lat": lat,
                "lng": lng,
                "battery_percent": d["battery_percent"],
                "access_role": d["access_role"],
            }
        )
    return {"devices": result}


@router.get("/api/v1/devices/{device_id}/locations")
async def v1_device_locations(
    device_id: str,
    limit: int = 200,
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("devices:read")),
):
    """Location history for one device (owner/viewer+; device_only shares
    cannot read coordinates). Rows are decrypted from at-rest ciphertext."""
    limit = max(1, min(limit, 1000))
    _assert_device_access(db, device_id, actor.user_id, min_role="viewer")
    rows = db.execute(
        "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
        loc.pop("location_data", None)  # raw ciphertext never leaves the server
        locations.append(loc)
    return {"device_id": device_id, "locations": locations}


@router.get("/api/v1/alerts")
async def v1_alerts(
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("alerts:read")),
):
    """Alert history for the account's owned + shared (viewer+) devices."""
    user_id = actor.user_id
    rows = db.execute(
        """SELECT a.id, a.device_id, a.alert_type, a.channel, a.recipient,
                  a.message, a.sent_at, a.delivered
           FROM alerts a
           JOIN devices d ON d.id = a.device_id
           LEFT JOIN device_shares ds
                  ON ds.device_id = d.id AND ds.grantee_user_id = ?
           WHERE d.owner_id = ? OR (ds.grantee_user_id IS NOT NULL AND ds.role != 'device_only')
           ORDER BY a.sent_at DESC
           LIMIT 500""",
        (user_id, user_id),
    ).fetchall()
    return {"alerts": [dict(r) for r in rows]}


@router.get("/api/v1/media/{device_id}")
async def v1_media_list(
    device_id: str,
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("media:read")),
):
    """Evidence media METADATA for a device. Owner only (per spec: viewers
    never see media through keys). Fetch bytes via
    /api/v1/media/{device_id}/file/{media_id}."""
    _assert_device_access(db, device_id, actor.user_id, min_role="owner")
    rows = db.execute(
        "SELECT id, device_id, type, timestamp, lat, lng, sha256_hash, file_size "
        "FROM media WHERE device_id=? ORDER BY timestamp DESC",
        (device_id,),
    ).fetchall()
    return {"device_id": device_id, "media": [dict(r) for r in rows]}


@router.get("/api/v1/media/{device_id}/file/{media_id}")
async def v1_media_file(
    device_id: str,
    media_id: int,
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("media:read")),
):
    """Fetch a media file's bytes (owner only). Served as base64 in the same
    wire format the dashboard uses, with the SHA-256 for integrity checks."""
    _assert_device_access(db, device_id, actor.user_id, min_role="owner")
    row = db.execute("SELECT * FROM media WHERE id=? AND device_id=?", (media_id, device_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Media not found")
    import base64

    from media_store import media_bytes_for_row

    try:
        data_b64 = base64.b64encode(media_bytes_for_row(row)).decode("ascii")
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Media file missing on server")
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "type": row["type"],
        "data_b64": data_b64,
        "timestamp": row["timestamp"],
        "lat": row["lat"],
        "lng": row["lng"],
        "sha256_hash": row["sha256_hash"],
        "file_size": row["file_size"] if "file_size" in row.keys() else None,
    }


@router.post("/api/v1/devices/{device_id}/commands")
async def v1_issue_command(
    device_id: str,
    req: V1CommandRequest,
    db=Depends(get_db),
    actor: ApiKeyActor = Depends(require_api_key_scope("devices:write")),
):
    """Queue a remote command through a developer key. Requires the
    devices:write scope AND admin-or-owner role on the device — a viewer
    share stays read-only even with a write-scoped key (least privilege:
    scopes are intersected with the account's own rights). The command is
    delivered via the normal device poll (the SMS relay is a dashboard-only
    owner feature). `wipe` is rejected — factory reset requires the
    dashboard step-up password, which a key cannot provide."""
    _assert_device_access(db, device_id, actor.user_id, min_role="admin")
    if not check_command_rate_limit(actor.subject):
        raise HTTPException(status_code=429, detail="Command rate limit exceeded")

    # Single authoritative command whitelist (models.CommandRequest) — kept
    # in sync with the Android app's TrackingService.handleCommand().
    from models import CommandRequest as _CommandWhitelist

    try:
        _CommandWhitelist(device_id=device_id, command=req.command, params=req.params)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if req.command == "wipe":
        raise HTTPException(
            status_code=400,
            detail="wipe requires dashboard step-up authentication — not available to API keys",
        )

    now = datetime.now(timezone.utc).isoformat()
    from datetime import timedelta

    # Same expiry policy as the dashboard: sensitive/fast-acting commands
    # expire in 5 min, lost_mode gets a full 24h window, everything else 30m.
    minutes = 5 if req.command in ("lock", "alarm") else (24 * 60 if req.command == "lost_mode" else 30)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()

    # Urgent commands jump the queue (priority 1), mirroring the dashboard.
    priority = (
        1
        if req.command in ("lock", "alarm", "capture_photo", "capture_photo_front", "capture_audio", "lost_mode")
        else 5
    )

    cur = db.execute(
        "INSERT INTO commands (device_id, command, params, priority, issued_at, expires_at, delivery_channel) "
        "VALUES (?, ?, ?, ?, ?, ?, 'poll')",
        (device_id, req.command, req.params, priority, now, expires_at),
    )
    db.commit()
    command_id = cur.lastrowid
    log_audit(
        "command_issued_via_api_key",
        actor=actor.subject,
        details=f"Device: {device_id}, Command: {req.command}",
    )
    return {"status": "ok", "command_id": command_id, "command": req.command}
