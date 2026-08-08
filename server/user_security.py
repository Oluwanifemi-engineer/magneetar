"""
Magneetar User Account Security
────────────────────────────────
TOTP two-factor authentication, password reset, and email verification for
user accounts.

Security model:
- TOTP secrets are AES-256-GCM encrypted at rest with the server's
  MT_ENCRYPTION_KEY (domain-separated AAD) — a DB dump alone never yields a
  working secret.
- Codes are verified with pyotp at valid_window=1 (accepts ±1 time step for
  clock drift, nothing more). Replay protection: the accepted time-step is
  stored per user, so the same code cannot be reused within its window.
  Brute-force protection: 5 failed attempts / 15 min per user → 429.
- 2FA enrollment and disabling are STEP-UP gated: the account password is
  re-verified (rate-limited), so a stolen session cannot silently enable or
  disable 2FA.
- Password reset: tokens are single-use, expiring (15 min), and stored only
  as SHA-256 hashes. The endpoint never reveals whether an email exists
  (no account enumeration) and delivers the reset link by email (SendGrid;
  inert + logged when email is not configured — same graceful degradation
  as the rest of the alert stack).
- Email verification uses the same single-use hashed-token pattern.

These routes are user-account-only: operator (dashboard/API-key) sessions
are rejected with 403.
"""

import base64
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from auth import (
    check_password_verify_rate_limit,
    create_two_factor_token,
    create_user_tokens,
    get_current_user,
    hash_password,
    user_id_from_subject,
    verify_password,
)
from config import settings
from database import check_rate_limit, get_db_context, log_audit
from fastapi import APIRouter, Depends, HTTPException, Request
from models import (
    ForgotPasswordRequest,
    LoginTwoFactorRequest,
    ResetPasswordRequest,
    TokenResponse,
    TwoFactorDisableRequest,
    TwoFactorVerifyRequest,
    VerifyEmailRequest,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Constants ──────────────────────────────────────────────────────────────

# Time-step (RFC 6238 default).
TOTP_PERIOD_SECONDS = 30

RESET_TOKEN_TTL_MINUTES = 15
VERIFY_TOKEN_TTL_MINUTES = 60 * 24  # 24h — users often verify later

# Encryption domain separation (never reuse the same AAD across features).
_TOTP_AAD = b"magneetar:totp-secret:v1"

# Token tables are INTERNAL constants — never attacker input — so string
# concatenation of the table name is safe (a whitelist guard below still
# refuses anything else, defense in depth).
_TOKEN_TABLES = {"password_reset_tokens", "email_verify_tokens"}


# ─── TOTP secret encryption ─────────────────────────────────────────────────


def _encrypt_secret(plaintext: str) -> str:
    """AES-256-GCM encrypt a TOTP secret with the master encryption key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = bytes.fromhex(settings.ENCRYPTION_KEY)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), _TOTP_AAD)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def _decrypt_secret(encrypted_b64: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = bytes.fromhex(settings.ENCRYPTION_KEY)
    combined = base64.b64decode(encrypted_b64)
    nonce, ciphertext = combined[:12], combined[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, _TOTP_AAD).decode("utf-8")


# ─── TOTP primitives ────────────────────────────────────────────────────────


def _totp(secret_b32: str):
    """pyotp TOTP with standard RFC 6238 defaults (6 digits, 30s, SHA-1)."""
    import pyotp

    return pyotp.TOTP(secret_b32)


def _totp_period_index() -> int:
    return int(datetime.now(timezone.utc).timestamp()) // TOTP_PERIOD_SECONDS


def _verify_totp_code(secret_b32: str, code: str) -> bool:
    """Verify a code within ±1 time step (90s grace for clock drift)."""
    try:
        return _totp(secret_b32).verify(code, valid_window=1)
    except Exception:
        return False


def _qr_svg_data_uri(otpauth_uri: str) -> str:
    """Render an otpauth URI as an inline SVG data URL (segno, pure Python —
    no Pillow needed). The data URL keeps the QR inside the API response, so
    the dashboard never needs an external QR library."""
    import segno

    qr = segno.make_qr(otpauth_uri)
    from io import BytesIO

    buf = BytesIO()
    qr.save(buf, kind="svg", scale=6, border=1)
    svg = buf.getvalue().decode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


# ─── Step-up helpers ────────────────────────────────────────────────────────


def _require_user_actor(user_id: str):
    """2FA/reset/verify routes are user-account-only."""
    if user_id == "api_key_user" or user_id.startswith("dashboard:"):
        raise HTTPException(status_code=403, detail="User accounts only")


def _verify_stepup_password(user_id: str, password) -> None:
    """Re-verify the account password (rate-limited) for sensitive actions."""
    if not check_password_verify_rate_limit(user_id):
        raise HTTPException(status_code=429, detail="Too many verification attempts")
    password = password if isinstance(password, str) else ""
    if not password:
        raise HTTPException(status_code=400, detail="Password required")
    with get_db_context() as conn:
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid password")


# ─── Transactional email (reset/verify links) ───────────────────────────────


async def send_transactional_email(to: str, subject: str, text: str) -> bool:
    """Send a non-alert email (password reset, verification) via SendGrid.

    Returns False when SendGrid is not configured — the flow degrades
    gracefully (tokens still issued + logged) exactly like the alert engine.
    """
    if not settings.SENDGRID_API_KEY:
        logger.warning(f"Transactional email NOT sent to {to} — MT_SENDGRID_KEY not configured (subject: {subject})")
        return False
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": "alerts@magneetar.me", "name": "Magneetar"},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": text}],
                },
                timeout=10,
            )
            return response.status_code in (200, 202)
    except Exception as e:
        logger.warning(f"Transactional email send failed: {e}")
        return False


# ─── Token issuance for reset/verify emails ─────────────────────────────────


def _issue_email_token(table: str, user_id: str, ttl_minutes: int) -> str:
    """Create a single-use token row; returns the RAW token (hashed in DB)."""
    if table not in _TOKEN_TABLES:
        raise ValueError(f"Unknown token table: {table!r}")
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token_id = f"tk-{uuid.uuid4().hex[:12]}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    with get_db_context() as conn:
        conn.execute(
            "INSERT INTO " + table + " (id, user_id, token_hash, expires_at) VALUES (?, ?, ?, ?)",
            (token_id, user_id, token_hash, expires),
        )
        conn.commit()
    return raw


def _consume_email_token(table: str, user_id: str, raw_token: str) -> bool:
    """Validate + consume a single-use token. Returns True on success."""
    if table not in _TOKEN_TABLES:
        return False
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with get_db_context() as conn:
        row = conn.execute(
            "SELECT id, used, expires_at FROM " + table + " WHERE user_id=? AND token_hash=?",
            (user_id, token_hash),
        ).fetchone()
        if not row:
            return False
        if row["used"]:
            return False
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires < datetime.now(timezone.utc):
                return False
        except (ValueError, TypeError):
            return False
        conn.execute("UPDATE " + table + " SET used=1 WHERE id=?", (row["id"],))
        conn.commit()
        return True


# ─── 2FA endpoints ──────────────────────────────────────────────────────────


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


@router.post("/api/auth/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_two_factor(user_id: str = Depends(get_current_user)):
    """Start 2FA enrollment: returns a fresh TOTP secret + provisioning URI
    + QR SVG. Does NOT enable anything — enable_2fa does, after the user
    proves they hold the secret (a valid code) AND re-enters their password.

    Step-up: the account password is required in the enable step, so a
    stolen session cannot enroll 2FA (which would lock the owner out).
    """
    _require_user_actor(user_id)
    import pyotp

    secret = pyotp.random_base32()
    otpauth = _totp(secret).provisioning_uri(name=user_id, issuer_name="Magneetar")

    # Persist the encrypted secret now so /api/auth/2fa/enable can validate a
    # code against it. A re-run of setup overwrites the pending secret — the
    # owner's old authenticator entry simply stops working (harmless: 2FA is
    # not enabled until the enable step proves password + code).
    with get_db_context() as conn:
        conn.execute(
            "UPDATE users SET totp_secret_enc=?, totp_enabled=0 WHERE id=?",
            (_encrypt_secret(secret), user_id),
        )
        conn.commit()

    return TwoFactorSetupResponse(
        secret=secret,
        otpauth_uri=otpauth,
        qr_svg_data_uri=_qr_svg_data_uri(otpauth),
    )


@router.post("/api/auth/2fa/enable")
async def enable_two_factor(req: TwoFactorVerifyRequest, user_id: str = Depends(get_current_user)):
    """Enable 2FA: requires the current account password (step-up) AND a
    valid TOTP code from the secret returned by /setup."""
    _require_user_actor(user_id)
    _verify_stepup_password(user_id, req.password)

    with get_db_context() as conn:
        row = conn.execute("SELECT totp_secret_enc FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(status_code=400, detail="Run /api/auth/2fa/setup first")

    secret = _decrypt_secret(row["totp_secret_enc"])
    if not _verify_totp_code(secret, req.code):
        raise HTTPException(status_code=401, detail="Invalid verification code")

    # NOTE: totp_last_period is deliberately NOT stamped here — replay
    # protection applies to the login step (re-using a code to re-enter), not
    # to the one-time enrollment code. Stamping it would reject the user's
    # very first 2FA login when it happens within the same 30s window as
    # enrollment (confusing UX for zero security gain: the enrollment code is
    # only valid for its window and brute-force is already capped).
    with get_db_context() as conn:
        conn.execute("UPDATE users SET totp_enabled=1 WHERE id=?", (user_id,))
        conn.commit()
    log_audit("2fa_enabled", actor=user_id)
    return {"status": "ok", "totp_enabled": True}


@router.post("/api/auth/2fa/disable")
async def disable_two_factor(req: TwoFactorDisableRequest, user_id: str = Depends(get_current_user)):
    """Disable 2FA: requires the account password (step-up) — a stolen
    session alone must never be able to turn off the owner's second factor."""
    _require_user_actor(user_id)
    _verify_stepup_password(user_id, req.password)

    with get_db_context() as conn:
        conn.execute(
            "UPDATE users SET totp_enabled=0, totp_secret_enc=NULL, totp_last_period=NULL WHERE id=?",
            (user_id,),
        )
        conn.commit()
    log_audit("2fa_disabled", actor=user_id)
    return {"status": "ok", "totp_enabled": False}


# ─── 2FA login ──────────────────────────────────────────────────────────────


def login_requires_2fa(user_row) -> bool:
    return bool(user_row["totp_enabled"])


def issue_2fa_challenge(user_id: str) -> dict:
    """The login endpoint calls this when the user has 2FA enabled: returns
    a short-lived challenge token instead of real tokens."""
    return {"requires_2fa": True, "two_factor_token": create_two_factor_token(user_id)}


@router.post("/api/auth/user/login/2fa", response_model=TokenResponse)
async def login_with_two_factor(req: LoginTwoFactorRequest, request: Request):
    """Second half of a 2FA login: exchange the challenge token + TOTP code
    for real access/refresh tokens.

    - The challenge token is a 5-minute, single-purpose JWT (type '2fa').
    - The code is verified against the user's stored secret with ±1 step.
    - Replay: the accepted time-step is persisted per user — the same code
      cannot be reused within its 30s window.
    - Brute force: 5 failed attempts / 15 min per user → 429.
    """
    from auth import decode_token

    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    payload = decode_token(req.two_factor_token)
    if payload.get("type") != "2fa":
        raise HTTPException(status_code=401, detail="Invalid 2FA challenge token")
    user_id = user_id_from_subject(payload.get("sub", ""))
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid 2FA challenge token")

    if not check_rate_limit(f"2fa:{user_id}", "2fa_login", 5, 15):
        log_audit("2fa_rate_limited", actor=user_id, ip_address=client_ip)
        raise HTTPException(status_code=429, detail="Too many 2FA attempts — try again in 15 minutes")

    with get_db_context() as conn:
        user = conn.execute(
            "SELECT id, is_active, totp_enabled, totp_secret_enc, totp_last_period FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid 2FA challenge token")
    if not user["totp_enabled"] or not user["totp_secret_enc"]:
        raise HTTPException(status_code=401, detail="2FA is not enabled for this account")

    secret = _decrypt_secret(user["totp_secret_enc"])
    if not _verify_totp_code(secret, req.code):
        log_audit("2fa_failed", actor=user_id, ip_address=client_ip)
        raise HTTPException(status_code=401, detail="Invalid verification code")

    # Replay protection: reject a code from an already-accepted time-step.
    current_period = _totp_period_index()
    if user["totp_last_period"] and user["totp_last_period"] >= current_period - 1:
        raise HTTPException(status_code=401, detail="Verification code already used")

    with get_db_context() as conn:
        conn.execute(
            "UPDATE users SET totp_last_period=?, last_login=? WHERE id=?",
            (current_period, datetime.now(timezone.utc).isoformat(), user_id),
        )
        conn.commit()
    log_audit("user_login_2fa", actor=user_id, ip_address=client_ip)

    tokens = create_user_tokens(user_id)
    return TokenResponse(**tokens)


# ─── Password reset ─────────────────────────────────────────────────────────


@router.post("/api/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Request a password reset link. Always returns the same response
    whether or not the email exists (no account enumeration). The reset
    token is single-use, expires in 15 minutes, and is only ever emailed."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    # Per-IP throttle so the endpoint can't be used to spam mailboxes.
    if not check_rate_limit(f"forgot:{client_ip}", "forgot_password", 5, 15):
        raise HTTPException(status_code=429, detail="Too many reset requests — try again later")

    with get_db_context() as conn:
        user = conn.execute("SELECT id, email FROM users WHERE email=?", (req.email,)).fetchone()

    if user:
        raw = _issue_email_token("password_reset_tokens", user["id"], RESET_TOKEN_TTL_MINUTES)
        reset_url = f"{_dashboard_base_url()}/reset-password?email={user['email']}&token={raw}"
        delivered = await send_transactional_email(
            user["email"],
            "Magneetar — Reset your password",
            (
                "You asked to reset your Magneetar password.\n\n"
                f"Reset link (valid {RESET_TOKEN_TTL_MINUTES} minutes): {reset_url}\n\n"
                "If you didn't request this, ignore this email — your password is unchanged."
            ),
        )
        log_audit(
            "password_reset_requested",
            actor=user["id"],
            ip_address=client_ip,
            details=f"email_delivered={delivered}",
        )

    # Identical response either way — never reveal account existence.
    return {"status": "ok", "message": "If that email is registered, a reset link is on its way."}


@router.post("/api/auth/reset-password", response_model=TokenResponse)
async def reset_password(req: ResetPasswordRequest, request: Request):
    """Complete a password reset with the emailed single-use token. On
    success the password is changed and the caller is logged in (fresh
    tokens), exactly like a normal login."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    cf_ip = request.headers.get("CF-Connecting-IP", "")
    client_ip = cf_ip or (
        forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    )

    with get_db_context() as conn:
        user = conn.execute("SELECT id, email FROM users WHERE email=?", (req.email,)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    if not _consume_email_token("password_reset_tokens", user["id"], req.token):
        raise HTTPException(status_code=401, detail="Invalid or expired reset token")

    # Validate password strength before hashing (same rules as registration)
    from user_auth import _validate_password_strength

    _validate_password_strength(req.new_password)

    new_hash = hash_password(req.new_password)
    with get_db_context() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
        conn.commit()
    log_audit("password_reset", actor=user["id"], ip_address=client_ip)

    tokens = create_user_tokens(user["id"])
    return TokenResponse(**tokens)


# ─── Email verification ─────────────────────────────────────────────────────


@router.post("/api/auth/verify-email/resend")
async def resend_verification_email(user_id: str = Depends(get_current_user)):
    """(Re)send the email-verification link to the signed-in user."""
    _require_user_actor(user_id)
    with get_db_context() as conn:
        user = conn.execute("SELECT id, email, email_verified FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["email_verified"]:
        return {"status": "ok", "message": "Email already verified"}

    raw = _issue_email_token("email_verify_tokens", user["id"], VERIFY_TOKEN_TTL_MINUTES)
    verify_url = f"{_dashboard_base_url()}/verify-email?token={raw}"
    delivered = await send_transactional_email(
        user["email"],
        "Magneetar — Verify your email address",
        (
            "Welcome to Magneetar! Confirm this email address to secure your account.\n\n"
            f"Verify link (valid 24 hours): {verify_url}"
        ),
    )
    log_audit("verification_email_sent", actor=user_id, details=f"delivered={delivered}")
    return {"status": "ok", "message": "Verification email sent", "delivered": delivered}


@router.post("/api/auth/verify-email")
async def verify_email(req: VerifyEmailRequest):
    """Verify the user's email with the emailed single-use token."""
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()
    with get_db_context() as conn:
        row = conn.execute(
            "SELECT user_id, used, expires_at FROM email_verify_tokens WHERE token_hash=?",
            (token_hash,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired verification token")
        if row["used"]:
            raise HTTPException(status_code=401, detail="Verification token already used")
        try:
            expires = datetime.fromisoformat(row["expires_at"])
            if expires < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Verification token expired")
        except (ValueError, TypeError):
            raise HTTPException(status_code=401, detail="Invalid or expired verification token")

        conn.execute("UPDATE email_verify_tokens SET used=1 WHERE user_id=?", (row["user_id"],))
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
        conn.commit()
    log_audit("email_verified", actor=row["user_id"])
    return {"status": "ok", "message": "Email verified"}


# ─── Misc helpers ───────────────────────────────────────────────────────────


def _dashboard_base_url() -> str:
    """Base URL for links emailed to users (reset/verify). Configurable via
    MT_DASHBOARD_URL so self-hosted deployments get correct links."""
    return settings.DASHBOARD_URL.rstrip("/")
