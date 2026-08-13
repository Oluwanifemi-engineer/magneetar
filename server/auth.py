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

# Module-level imports ONLY — under full-suite collection test_e2e evicts
# database/auth from sys.modules and re-imports them with ITS env. A
# function-local `from database import ...` in a dependency would resolve the
# post-eviction module (different DB_PATH), so the lookup would hit a
# different DB than the one the app's routes write to (the documented
# full-suite order hazard — see routes/dashboard.py _verify_stepup_password).
from database import check_rate_limit, get_db_context, log_audit
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from memory_rate_limit import check_memory_rate_limit

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
    # Preserve the actor's token type so refreshed credentials still pass the
    # type checks: user: and dashboard: subjects get "dashboard" (dashboard +
    # WebSocket routes), anything else (device ids) gets "device". The old
    # one-liner minted "device" tokens for user subjects, which would be
    # rejected by /ws/dashboard's mandatory type check.
    if subject.startswith("user:") or subject.startswith("dashboard:"):
        token_type = "dashboard"
    else:
        token_type = "device"

    # Issue new pair
    access = create_token(subject, token_type, timedelta(hours=24))
    new_refresh = create_token(subject, "refresh", timedelta(days=90))

    return {
        "token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "expires_in": 86400,
    }


def _key_matches(candidate: str, expected: str) -> bool:
    """Constant-time equality against a single expected key.

    hmac.compare_digest runs in constant time for equal-length inputs, so a
    timing side-channel can't help guess a key over many requests. A
    TypeError (e.g. non-ASCII key) is treated as a mismatch — a clean reject,
    never a 500.
    """
    if not expected:
        return False
    try:
        return hmac.compare_digest(candidate, expected)
    except TypeError:
        return False


def api_key_is_authorized(x_api_key: str) -> bool:
    """True when x-api-key is a credential valid for DEVICE-SCOPE auth.

    Accepts: the master key (operator bootstrap, back-compat) or the
    low-privilege device key (embedded in the public APK). The pre-split
    master key grace credential (MT_LEGACY_DEVICE_KEY) was retired on
    2026-08-10 — it is no longer accepted for any scope.

    IMPORTANT: this grants access to DEVICE endpoints only. Dashboard admin
    login (routes/dashboard.py) and admin-mode step-up compare against the
    master key ALONE, so the APK-embedded keys can never mint admin
    credentials.
    """
    return _key_matches(x_api_key, settings.API_KEY) or _key_matches(x_api_key, settings.DEVICE_KEY)


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify an x-api-key for DEVICE-SCOPE auth (master or device key).
    Returns the key if valid.

    NOTE: this dependency gates device endpoints (register etc.). The
    dashboard admin login and step-up paths are gated on the master key
    alone, so a key extracted from the public APK can never reach them.
    """
    if not settings.API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    if not api_key_is_authorized(x_api_key):
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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Verify a device JWT token. Returns the device id.

    Note: this helper is currently unused by routes (devices use
    get_current_device_or_key), but it must not carry the old x-api-key
    -> api_key_user admin fallback (F-02), so it is JWT-only.
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload.get("type") in ("device", "access"):
            return payload["sub"]

    raise HTTPException(status_code=401, detail="Valid authorization required")


def require_dashboard_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Dashboard endpoints require a valid dashboard/access JWT.

    Security (F-02): the APK embeds a LOW-PRIVILEGE device key, not the
    master key, so an extracted APK key must never grant dashboard access.
    Accepting any x-api-key here would hand the platform to anyone with an
    APK. Only JWTs minted by /api/auth/login or a user login are accepted.
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        if payload.get("type") in ("dashboard", "access"):
            return payload["sub"]

    raise HTTPException(status_code=401, detail="Dashboard authorization required")


def check_login_rate_limit(ip_address: str) -> bool:
    """Check login rate limit: 5 attempts per 10 minutes per IP."""
    return check_rate_limit(
        f"login:{ip_address}", "login", settings.RATE_LOGIN_ATTEMPTS, settings.RATE_LOGIN_WINDOW_MINUTES
    )


def check_location_rate_limit(device_id: str) -> bool:
    """Check device location report rate limit: 30/min per device.

    In-memory (memory_rate_limit) — this runs on EVERY location ping and the
    DB-backed limiter's write-per-call was the telemetry hot-path bottleneck.
    Semantics are identical (30 per rolling 60s).
    """
    return check_memory_rate_limit(f"location:{device_id}", 30, 60)


def check_command_rate_limit(actor: str) -> bool:
    """Check command issuance rate limit: 20 commands per minute per dashboard user."""
    return check_rate_limit(f"command:{actor}", "command", settings.RATE_COMMAND_PER_MINUTE, 1)


def check_password_verify_rate_limit(actor: str) -> bool:
    """Check step-up (password re-verification) rate limit: 10 attempts per
    minute per actor. Destructive actions (media deletion, account deletion)
    that re-authenticate with a password must not be brute-forced."""
    return check_rate_limit(f"stepup:{actor}", "stepup", 10, 1)


def check_media_rate_limit(device_id: str) -> bool:
    """Check media upload rate limit: 10 uploads per minute per device.

    In-memory (memory_rate_limit) — hot path (every media upload).
    """
    return check_memory_rate_limit(f"media:{device_id}", settings.RATE_MEDIA_PER_MINUTE, 60)


def check_heartbeat_rate_limit(device_id: str) -> bool:
    """Check heartbeat rate limit: 10 heartbeats per minute per device.

    In-memory (memory_rate_limit) — hot path (every heartbeat).
    """
    return check_memory_rate_limit(f"heartbeat:{device_id}", settings.RATE_HEARTBEAT_PER_MINUTE, 60)


def check_command_poll_rate_limit(device_id: str) -> bool:
    """Check command poll rate limit: 30 polls per minute per device.

    In-memory (memory_rate_limit) — hot path (every command poll).
    """
    return check_memory_rate_limit(f"command_poll:{device_id}", settings.RATE_COMMAND_POLL_PER_MINUTE, 60)


# ─── Developer API Keys (docs/developer-api.md) ─────────────────────────────
# Per-account, scoped, revocable keys for third-party integrations. The key
# format is mtk_<env>_<32 url-safe chars>; only a 12-char prefix + SHA-256 hash
# are stored. The key actor resolves to the OWNING ACCOUNT, so every existing
# RBAC/share rule applies automatically (a viewer-shared device stays
# read-only through the key too). Keys are a DATA-PLANE credential: they are
# never accepted on /api/auth/*, dashboard, metrics, or key-management routes.

VALID_API_KEY_SCOPES = frozenset({"devices:read", "devices:write", "alerts:read", "media:read"})


class ApiKeyActor:
    """A successfully authenticated developer API key.

    Carries the owning account id + granted scopes so data routes can treat
    the key as that user (filtered by scopes and per-device share roles).
    """

    __slots__ = ("user_id", "scopes", "key_prefix")

    def __init__(self, user_id: str, scopes: list, key_prefix: str):
        self.user_id = user_id
        self.scopes = scopes
        self.key_prefix = key_prefix

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    @property
    def subject(self) -> str:
        """Audit identity: 'key:<prefix>' — never the raw key."""
        return f"key:{self.key_prefix}"


def generate_api_key(env: str = "live") -> str:
    """Mint a new developer API key: mtk_<env>_<32 url-safe chars>.

    token_urlsafe(24) yields 32 url-safe characters. The full key is shown to
    the creator EXACTLY once — the server stores only the prefix + hash.
    """
    if env not in ("live", "test"):
        env = "live"
    return f"mtk_{env}_{secrets.token_urlsafe(24)}"


def get_api_key_actor(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> ApiKeyActor:
    """Authenticate a developer API key presented as `Authorization: Bearer
    mtk_...` and resolve it to its owning account + scopes.

    Lookup is by the 12-char prefix (indexed), then a constant-time SHA-256
    comparison against the stored hash — the raw key is never stored, logged,
    or compared in plaintext. Rejects: missing/malformed keys, revoked keys,
    expired keys, and keys whose owning account was deleted/deactivated.

    Security (F-02 family): this dependency is used ONLY by the /api/v1/*
    developer surface. Dashboard/auth/metrics/key-management routes use their
    own JWT-only dependencies, so a leaked developer key can never reach
    them — exactly like the APK-embedded device key can never mint dashboard
    credentials.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")
    presented = credentials.credentials or ""
    if not presented.startswith("mtk_"):
        raise HTTPException(status_code=401, detail="Invalid API key")

    prefix = presented[:12]
    key_hash = hash_device_key(presented)

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT id, user_id, key_hash, scopes, expires_at, revoked_at FROM api_keys WHERE key_prefix=?",
            (prefix,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")
        # Constant-time comparison — a timing side-channel must never help
        # guess a 32-char key from many requests.
        if not hmac.compare_digest(row["key_hash"], key_hash):
            raise HTTPException(status_code=401, detail="Invalid API key")
        if row["revoked_at"]:
            raise HTTPException(status_code=401, detail="API key has been revoked")
        if row["expires_at"]:
            try:
                if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
                    raise HTTPException(status_code=401, detail="API key has expired")
            except (ValueError, TypeError):
                raise HTTPException(status_code=401, detail="Invalid API key")
        # The owning account must still exist and be active — a key must not
        # outlive the account that issued it.
        user = conn.execute("SELECT is_active FROM users WHERE id=?", (row["user_id"],)).fetchone()
        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="Account no longer active")

        scopes = [s for s in (row["scopes"] or "").split(",") if s in VALID_API_KEY_SCOPES]

        # Per-key rate limit (120 req/min) — a leaked or shared key cannot
        # hammer the data plane. DB-backed like the other alert/command
        # limiters; checked BEFORE the request does any work.
        if not check_rate_limit(f"apikey:{prefix}", "apikey", 120, 1):
            raise HTTPException(status_code=429, detail="API key rate limit exceeded")

        # Best-effort last-used stamp + audit. Wrapped in try/except so a
        # failure to record usage never fails the request.
        try:
            conn.execute(
                "UPDATE api_keys SET last_used_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(), row["id"]),
            )
            conn.commit()
            log_audit("api_key_used", actor=f"key:{prefix}")
        except Exception:
            pass

    return ApiKeyActor(row["user_id"], scopes, prefix)


def require_api_key_scope(scope: str):
    """Dependency factory: authenticate a developer key AND require a scope.

    Usage: `actor: ApiKeyActor = Depends(require_api_key_scope("devices:read"))`
    Raises 403 when the key lacks the scope (least privilege: a key can never
    exceed its granted scopes, and scopes are intersected with the owning
    account's own rights by each data route).
    """

    def _dependency(actor: ApiKeyActor = Depends(get_api_key_actor)) -> ApiKeyActor:
        if not actor.has_scope(scope):
            raise HTTPException(
                status_code=403,
                detail=f"API key lacks the '{scope}' scope",
            )
        return actor

    return _dependency


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
    3. x-api-key header (shared API key: master or device key)
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

    # Method 3: shared x-api-key (master / device key).
    # The returned 'api_key_user' identity is DEVICE-scope only — it is used
    # by device routes (register, location, media, fcm, command poll) and is
    # NEVER a dashboard/admin credential, which is minted exclusively by the
    # master-key dashboard login.
    if x_api_key and api_key_is_authorized(x_api_key):
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
        # Constant-time comparison: hmac.compare_digest prevents timing
        # side-channels where an attacker measures response time to guess
        # the hash character-by-character.
        return hmac.compare_digest(check.hex(), h)
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


def create_two_factor_token(user_id: str) -> str:
    """Short-lived single-purpose JWT proving the password half of a 2FA
    login. Issued when a 2FA-enabled user logs in with the correct password;
    exchanged for real tokens only after a valid TOTP code is submitted.

    The type '2fa' is rejected by every other auth dependency (device,
    dashboard, user), so a stolen 2FA token is useless outside this flow.
    """
    return create_token(f"user:{user_id}", "2fa", timedelta(minutes=5))


def user_id_from_subject(subject: str) -> Optional[str]:
    """Extract the user id from a JWT subject like 'user:usr-xxx'.

    Returns None when the subject is not a user token (e.g. admin/api-key
    subjects like 'dashboard:<hash>' or 'api_key_user').
    """
    if subject.startswith("user:"):
        return subject[len("user:") :]
    return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    Extract user_id from a JWT token. Dashboard/operator JWTs (subject
    'dashboard:<hash>') pass through so admin-only endpoints can detect them.

    Security (F-02): the APK embeds a LOW-PRIVILEGE device key, not the
    master key, and shared keys must not grant user-route access. The
    x-api-key -> 'api_key_user' fallback has been removed; only real JWTs
    are accepted.

    Type check (v1.4): a `user:` subject alone is NOT enough — the 2FA
    challenge JWT (type '2fa') also carries a user: subject and must never
    act as a session. Only tokens minted as real session tokens
    (dashboard/access) pass.
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        sub = payload.get("sub", "")
        user_id = user_id_from_subject(sub)
        if user_id:
            if payload.get("type") in ("dashboard", "access"):
                return user_id
            raise HTTPException(status_code=401, detail="Invalid token type")
        if payload.get("type") in ("dashboard", "access"):
            return sub

    raise HTTPException(status_code=401, detail="Authorization required")
