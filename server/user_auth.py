"""
Magneetar User Authentication Endpoints
Registration, login, and user management.
"""

import uuid
from datetime import datetime, timezone

from auth import (
    check_login_rate_limit,
    create_user_tokens,
    get_current_user,
    hash_password,
    refresh_access_token,
    verify_password,
)
from config import plan_device_limit
from database import check_rate_limit, delete_device_cascade, get_db_context, log_audit
from fastapi import APIRouter, Depends, HTTPException, Request
from models import PlanUpdateRequest, RefreshRequest, TokenResponse, UserLoginRequest, UserRegisterRequest, UserResponse

router = APIRouter()


@router.post("/api/auth/register", response_model=TokenResponse)
async def register_user(req: UserRegisterRequest, request: Request):
    """Register a new user account."""
    # Rate limit: 3 registrations per 10 minutes per IP
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    if not check_rate_limit(f"register:{client_ip}", "register", 3, 10):
        raise HTTPException(status_code=429, detail="Too many registration attempts")

    # Check if email already exists
    with get_db_context() as db:
        existing = db.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        # Create user
        user_id = f"usr-{uuid.uuid4().hex[:12]}"
        password_hashed = hash_password(req.password)
        now = datetime.now(timezone.utc).isoformat()

        db.execute(
            """INSERT INTO users (id, email, password_hash, display_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, req.email, password_hashed, req.display_name, now),
        )
        db.commit()

        log_audit("user_registered", actor=user_id, ip_address=client_ip, details=req.email)

    # Issue tokens
    tokens = create_user_tokens(user_id)
    return TokenResponse(**tokens)


@router.post("/api/auth/user/login", response_model=TokenResponse)
async def login_user(req: UserLoginRequest, request: Request):
    """Login with email and password."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    if not check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    with get_db_context() as db:
        user = db.execute("SELECT id, password_hash, is_active FROM users WHERE email=?", (req.email,)).fetchone()

        # Always run verify_password to prevent timing attacks
        if not user:
            dummy_hash = (
                "00000000000000000000000000000000:0000000000000000000000000000000000000000000000000000000000000000"
            )
            verify_password(req.password, dummy_hash)
            log_audit("login_failed", ip_address=client_ip, details=req.email)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not verify_password(req.password, user["password_hash"]):
            log_audit("login_failed", ip_address=client_ip, details=req.email)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        # Update last login
        db.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), user["id"]))
        db.commit()

        log_audit("user_login", actor=user["id"], ip_address=client_ip)

    tokens = create_user_tokens(user["id"])
    return TokenResponse(**tokens)


@router.get("/api/auth/me", response_model=UserResponse)
async def get_me(user_id: str = Depends(get_current_user)):
    """Get current user profile."""
    if user_id == "api_key_user" or user_id.startswith("dashboard:"):
        # Operator/dashboard (or legacy API-key) sessions get the admin profile.
        # The dashboard JWT is minted by /api/auth/login with the master key,
        # so its subject is 'dashboard:<hash>' — resolve it to the admin view.
        return UserResponse(
            id=user_id,
            email="admin@magneetar.local",
            display_name="Administrator",
            tier="admin",
            is_active=True,
            device_count=0,
            max_devices=999,
        )

    with get_db_context() as db:
        user = db.execute(
            "SELECT id, email, display_name, tier, is_active, created_at FROM users WHERE id=?", (user_id,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        device_count = db.execute("SELECT COUNT(*) as cnt FROM devices WHERE owner_id=?", (user_id,)).fetchone()["cnt"]

        max_devices = plan_device_limit(user["tier"])

        return UserResponse(
            id=user["id"],
            email=user["email"],
            display_name=user["display_name"],
            tier=user["tier"],
            is_active=user["is_active"],
            created_at=user["created_at"],
            device_count=device_count,
            max_devices=max_devices,
        )


@router.post("/api/auth/user/refresh", response_model=TokenResponse)
async def refresh_user_token(req: RefreshRequest):
    """Refresh user JWT tokens."""
    return refresh_access_token(req.refresh_token)


@router.put("/api/auth/plan")
async def update_user_plan(req: PlanUpdateRequest, user_id: str = Depends(get_current_user)):
    """Set a user's plan tier. Admin only (dashboard/API-key auth).

    This is the manual upgrade path until self-serve payments land: an
    operator upgrades an account after payment, and plan_device_limit()
    immediately gates how many devices it may own.
    """
    is_admin = user_id == "api_key_user" or user_id.startswith("dashboard:")
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    with get_db_context() as db:
        user = db.execute("SELECT id FROM users WHERE email=?", (req.email,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db.execute("UPDATE users SET tier=? WHERE id=?", (req.tier, user["id"]))
        db.commit()
        log_audit("plan_updated", actor=user_id, details=f"{req.email} → {req.tier}")

    return {"status": "ok", "email": req.email, "tier": req.tier}


@router.delete("/api/auth/user/account")
async def delete_user_account(user_id: str = Depends(get_current_user)):
    """Permanently delete the user account, all owned devices, and all data.

    This is the permanent-deletion path promised in the privacy policy:
    deleting the account removes the user, their devices, locations, media,
    evidence, commands, alerts, guardian profiles, and recovery requests.
    This action cannot be undone.
    """
    if user_id == "api_key_user":
        raise HTTPException(status_code=401, detail="User authentication required")

    with get_db_context() as db:
        user = db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Cascade-delete every device owned by this user (device rows first,
        # then their child data, then the devices themselves), and clear the
        # WebSocket owner cache so a deleted user's token can't keep receiving
        # broadcasts for those devices.
        device_ids = [r["id"] for r in db.execute("SELECT id FROM devices WHERE owner_id=?", (user_id,)).fetchall()]
        for device_id in device_ids:
            delete_device_cascade(db, device_id)
            from websocket_manager import update_device_owner

            update_device_owner(device_id, None)

        # Guardian profile + sightings reference the user, not the device.
        db.execute("DELETE FROM recovery_sightings WHERE guardian_id=?", (user_id,))
        db.execute("DELETE FROM guardian_profiles WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM users WHERE id=?", (user_id,))
        db.commit()

        log_audit(
            "user_deleted",
            actor=user_id,
            details=f"Account permanently deleted with {len(device_ids)} device(s)",
        )

    return {"status": "ok", "message": "Account permanently deleted", "devices_removed": len(device_ids)}
