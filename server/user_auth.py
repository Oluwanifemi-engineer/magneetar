"""
Magneetar User Authentication Endpoints
Registration, login, and user management.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from database import get_db_context, log_audit, check_rate_limit
from auth import (
    hash_password, verify_password, create_user_tokens,
    get_current_user, check_login_rate_limit, refresh_access_token
)
from models import (
    UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse, RefreshRequest
)
from config import settings

router = APIRouter()


@router.post("/api/auth/register", response_model=TokenResponse)
async def register_user(req: UserRegisterRequest, request: Request):
    """Register a new user account."""
    # Rate limit: 3 registrations per 10 minutes per IP
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown"))

    if not check_rate_limit(f"register:{client_ip}", "register", 3, 10):
        raise HTTPException(status_code=429, detail="Too many registration attempts")

    # Check if email already exists
    with get_db_context() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE email=?", (req.email,)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        # Create user
        user_id = f"usr-{uuid.uuid4().hex[:12]}"
        password_hashed = hash_password(req.password)
        now = datetime.now(timezone.utc).isoformat()

        db.execute(
            """INSERT INTO users (id, email, password_hash, display_name, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, req.email, password_hashed, req.display_name, now)
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
    client_ip = cf_ip or (forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown"))

    if not check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts")

    with get_db_context() as db:
        user = db.execute(
            "SELECT id, password_hash, is_active FROM users WHERE email=?",
            (req.email,)
        ).fetchone()

        # Always run verify_password to prevent timing attacks
        if not user:
            dummy_hash = "00000000000000000000000000000000:0000000000000000000000000000000000000000000000000000000000000000"
            verify_password(req.password, dummy_hash)
            log_audit("login_failed", ip_address=client_ip, details=req.email)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not verify_password(req.password, user["password_hash"]):
            log_audit("login_failed", ip_address=client_ip, details=req.email)
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account is deactivated")

        # Update last login
        db.execute(
            "UPDATE users SET last_login=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), user["id"])
        )
        db.commit()

        log_audit("user_login", actor=user["id"], ip_address=client_ip)

    tokens = create_user_tokens(user["id"])
    return TokenResponse(**tokens)


@router.get("/api/auth/me", response_model=UserResponse)
async def get_me(user_id: str = Depends(get_current_user)):
    """Get current user profile."""
    if user_id == "api_key_user":
        # API key users get a default profile
        return UserResponse(
            id="api_key_user",
            email="admin@magneetar.local",
            display_name="Administrator",
            tier="admin",
            is_active=True,
            device_count=0,
            max_devices=999
        )

    with get_db_context() as db:
        user = db.execute(
            "SELECT id, email, display_name, tier, is_active, created_at FROM users WHERE id=?",
            (user_id,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        device_count = db.execute(
            "SELECT COUNT(*) as cnt FROM devices WHERE owner_id=?",
            (user_id,)
        ).fetchone()["cnt"]

        max_devices = settings.MAX_DEVICES_PER_USER if user["tier"] == "free" else 999

        return UserResponse(
            id=user["id"],
            email=user["email"],
            display_name=user["display_name"],
            tier=user["tier"],
            is_active=user["is_active"],
            created_at=user["created_at"],
            device_count=device_count,
            max_devices=max_devices
        )


@router.post("/api/auth/user/refresh", response_model=TokenResponse)
async def refresh_user_token(req: RefreshRequest):
    """Refresh user JWT tokens."""
    return refresh_access_token(req.refresh_token)
