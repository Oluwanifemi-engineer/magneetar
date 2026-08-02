"""
Magneetar Authentication
JWT tokens for device and dashboard authentication.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from config import settings
from database import check_rate_limit, log_audit
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def create_token(subject: str, token_type: str = "access", expires_delta: timedelta = None) -> str:
    """
    Create a JWT token.
    token_type: "access", "refresh", "device", "dashboard"
    """
    if expires_delta is None:
        if token_type == "refresh":
            expires_delta = timedelta(days=settings.JWT_REFRESH_EXPIRY_DAYS)
        elif token_type == "device":
            expires_delta = timedelta(days=30)  # Device tokens live longer
        else:
            expires_delta = timedelta(hours=settings.JWT_ACCESS_EXPIRY_HOURS)

    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": secrets.token_hex(16),  # Unique token ID for revocation
    }

    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


# In-memory cache for revoked JTIs (TTL: 1 hour)
_revoked_cache: dict[str, float] = {}  # jti -> expiry timestamp


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Checks revocation list with in-memory cache."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])

        # Check if token has been revoked (with in-memory cache)
        jti = payload.get("jti")
        if jti:
            now = time.time()

            # Check cache first (avoids DB query on every request)
            cached_expiry = _revoked_cache.get(jti)
            if cached_expiry and cached_expiry > now:
                raise HTTPException(status_code=401, detail="Token has been revoked")
            elif cached_expiry:
                del _revoked_cache[jti]

            # Cache miss — check DB
            from database import get_db_context

            with get_db_context() as conn:
                revoked = conn.execute("SELECT jti FROM revoked_tokens WHERE jti=?", (jti,)).fetchone()
                if revoked:
                    _revoked_cache[jti] = now + 3600  # Cache for 1 hour
                    raise HTTPException(status_code=401, detail="Token has been revoked")

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_device_tokens(device_id: str) -> dict:
    """Create access + refresh token pair for a device."""
    access = create_token(device_id, "device", timedelta(hours=24))
    refresh = create_token(device_id, "refresh", timedelta(days=90))
    return {
        "token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def create_dashboard_tokens(api_key: str) -> dict:
    """Create access + refresh token pair for dashboard."""
    # Hash the API key as the subject (never store raw key in token)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    access = create_token(f"dashboard:{key_hash}", "dashboard", timedelta(hours=24))
    refresh = create_token(f"dashboard:{key_hash}", "refresh", timedelta(days=90))
    return {
        "token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def refresh_access_token(refresh_token: str) -> dict:
    """Rotate refresh token and issue new access token."""
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token type")

    # Revoke the old refresh token
    jti = payload.get("jti")
    if jti:
        from database import get_db_context

        with get_db_context() as conn:
            conn.execute("INSERT OR IGNORE INTO revoked_tokens (jti, reason) VALUES (?, ?)", (jti, "rotated"))
            conn.commit()

    subject = payload["sub"]
    token_type = "device" if not subject.startswith("dashboard:") else "dashboard"

    # Issue new pair
    access = create_token(subject, token_type, timedelta(hours=24))
    new_refresh = create_token(subject, "refresh", timedelta(days=90))

    return {
        "token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify the master API key. Returns the key if valid."""
    if not settings.API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    # Constant-time comparison. The master key is the bootstrap credential
    # embedded in every device build, so a timing side-channel on the plain
    # != comparison could in principle help an attacker guess it over many
    # requests. hmac.compare_digest runs in constant time for equal-length
    # inputs. (FastAPI enforces the header via Header(...), so x_api_key is
    # always a str here.) A TypeError (e.g. non-ASCII key) is treated as a
    # mismatch — a clean 401, never a 500.
    try:
        matches = hmac.compare_digest(x_api_key, settings.API_KEY)
    except TypeError:
        matches = False
    if not matches:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


def get_current_device(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Extract and validate device ID from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_token(credentials.credentials)

    if payload.get("type") not in ("device", "access"):
        raise HTTPException(status_code=401, detail="Invalid token type for device")

    return payload["sub"]


def get_current_dashboard(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """Extract and validate dashboard session from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization required")

    payload = decode_token(credentials.credentials)

    if payload.get("type") not in ("dashboard", "access"):
        raise HTTPException(status_code=401, detail="Invalid token type for dashboard")

    return payload["sub"]


def verify_device_or_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), x_api_key: Optional[str] = Header(None)
) -> str:
    """
    Verify either a device JWT token or the master API key.
    Returns the device_id or "api_key_user" as the actor.
    """
    # Try JWT first
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload.get("type") in ("device", "access"):
            return payload["sub"]

    # Fall back to API key
    if x_api_key and x_api_key == settings.API_KEY:
        log_audit("api_key_auth", actor="api_key_user")
        return "api_key_user"

    raise HTTPException(status_code=401, detail="Valid authorization required")


def require_dashboard_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), x_api_key: Optional[str] = Header(None)
) -> str:
    """
    Dashboard endpoints accept either:
    1. JWT token from dashboard login
    2. Master API key (for API testing)
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload.get("type") in ("dashboard", "access"):
            return payload["sub"]

    if x_api_key and x_api_key == settings.API_KEY:
        return "api_key_user"

    raise HTTPException(status_code=401, detail="Dashboard authorization required")


def check_login_rate_limit(ip_address: str) -> bool:
    """Check login rate limit: 5 attempts per 10 minutes per IP."""
    return check_rate_limit(
        f"login:{ip_address}", "login", settings.RATE_LOGIN_ATTEMPTS, settings.RATE_LOGIN_WINDOW_MINUTES
    )


def check_location_rate_limit(device_id: str) -> bool:
    """Check device location report rate limit."""
    return check_rate_limit(
        f"location:{device_id}", "location", 30, 1  # 30 requests  # per minute (effectively 1 per 2 seconds)
    )


def check_command_rate_limit(actor: str) -> bool:
    """Check command issuance rate limit: 20 commands per minute per dashboard user."""
    return check_rate_limit(f"command:{actor}", "command", settings.RATE_COMMAND_PER_MINUTE, 1)


def check_password_verify_rate_limit(actor: str) -> bool:
    """Check step-up (password re-verification) rate limit: 10 attempts per
    minute per actor. Destructive actions (media deletion, account deletion)
    that re-authenticate with a password must not be brute-forced."""
    return check_rate_limit(f"stepup:{actor}", "stepup", 10, 1)


def check_media_rate_limit(device_id: str) -> bool:
    """Check media upload rate limit: 10 uploads per minute per device."""
    return check_rate_limit(f"media:{device_id}", "media", settings.RATE_MEDIA_PER_MINUTE, 1)


def check_heartbeat_rate_limit(device_id: str) -> bool:
    """Check heartbeat rate limit: 10 heartbeats per minute per device."""
    return check_rate_limit(f"heartbeat:{device_id}", "heartbeat", settings.RATE_HEARTBEAT_PER_MINUTE, 1)


def check_command_poll_rate_limit(device_id: str) -> bool:
    """Check command poll rate limit: 30 polls per minute per device."""
    return check_rate_limit(f"command_poll:{device_id}", "command_poll", settings.RATE_COMMAND_POLL_PER_MINUTE, 1)


# ─── Device Key Authentication ────────────────────────────────────────────────


def hash_device_key(key: str) -> str:
    """SHA-256 hash of a device key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def get_current_device_or_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_device_key: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> str:
    """
    Combined device authentication — tries three methods in order:
    1. JWT Bearer token (from existing sessions)
    2. x-device-key header (per-device unique key)
    3. x-api-key header (legacy shared API key)
    Returns the device_id (or 'api_key_user' for API key fallback).
    """
    # Method 1: JWT token
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") in ("device", "access"):
                return payload["sub"]
        except HTTPException:
            pass  # Fall through to next method

    # Method 2: Device key (unique per-device secret)
    if x_device_key:
        key_hash = hash_device_key(x_device_key)
        from database import get_db_context

        with get_db_context() as conn:
            row = conn.execute("SELECT id FROM devices WHERE device_key_hash=?", (key_hash,)).fetchone()
            if row:
                return row["id"]

    # Method 3: Legacy shared API key
    if x_api_key and x_api_key == settings.API_KEY:
        log_audit("api_key_auth", actor="api_key_user")
        return "api_key_user"

    raise HTTPException(status_code=401, detail="Device authorization required")


# ─── User Authentication ─────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.
    Falls back to PBKDF2-SHA256 if bcrypt is not installed.
    """
    try:
        import bcrypt

        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except ImportError:
        # Fallback for environments without bcrypt
        import hashlib

        salt = secrets.token_hex(16)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
        return f"pbkdf2:{salt}:{h.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.
    Supports both bcrypt (preferred) and PBKDF2-SHA256 (fallback) formats.
    """
    try:
        # Try bcrypt first (format: $2b$... or $2a$...)
        if password_hash.startswith("$"):
            import bcrypt

            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ImportError:
        pass
    except Exception:
        return False

    # Fallback: PBKDF2-SHA256 (format: pbkdf2:salt:hash)
    try:
        import hashlib

        parts = password_hash.split(":")
        if len(parts) < 3 or parts[0] != "pbkdf2":
            return False
        salt = parts[1]
        h = parts[2]
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600000)
        return check.hex() == h
    except Exception:
        return False


def create_user_tokens(user_id: str) -> dict:
    """Create access + refresh token pair for a user."""
    access = create_token(f"user:{user_id}", "dashboard", timedelta(hours=24))
    refresh = create_token(f"user:{user_id}", "refresh", timedelta(days=90))
    return {
        "token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def user_id_from_subject(subject: str) -> Optional[str]:
    """Extract the user id from a JWT subject like 'user:usr-xxx'.

    Returns None when the subject is not a user token (e.g. admin/api-key
    subjects like 'dashboard:<hash>' or 'api_key_user').
    """
    if subject.startswith("user:"):
        return subject[len("user:") :]
    return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security), x_api_key: Optional[str] = Header(None)
) -> str:
    """
    Extract user_id from JWT token or fall back to API key auth.
    Returns user_id string (or 'api_key_user' for backward compat).
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        sub = payload.get("sub", "")
        user_id = user_id_from_subject(sub)
        if user_id:
            return user_id
        if payload.get("type") in ("dashboard", "access"):
            return sub

    if x_api_key and x_api_key == settings.API_KEY:
        return "api_key_user"

    raise HTTPException(status_code=401, detail="Authorization required")
