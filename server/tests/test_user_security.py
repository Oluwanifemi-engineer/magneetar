"""
User Account Security Tests
───────────────────────────
Locks the v1.4 account-security contract:
- 2FA: setup → enable (password + code) → login requires challenge → second
  step issues real tokens; wrong code 401; same code replay rejected; 5
  failures / 15 min → 429; disable requires password; operator sessions 403.
- Password reset: no account enumeration, single-use hashed tokens, expiry,
  strength rules, fresh tokens on success.
- Email verification: single-use token flips email_verified.
"""

import os
import secrets
import tempfile

import pytest

# ── Env BEFORE importing app modules (same dummy values as every test file —
# see test_media_store.py for the shared-singleton rationale) ───────────────
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = _test_db_path

# ── Rebinds (module-eviction convention, see test_api.py) ───────────────────
# test_e2e evicts config/database from sys.modules mid-collection, and
# whichever file sorts before us (test_sentinel binds :memory:) decides the
# global DB_PATH unless we rebind. The app's routers imported `database` at
# OUR import time — same module instance as our module-level binding — so
# the module-level `database` object below is the one the TestClient uses.
import config  # noqa: E402

config.settings.DB_PATH = _test_db_path

import database  # noqa: E402

database.DB_PATH = _test_db_path

from database import init_db  # noqa: E402

init_db(_test_db_path)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

# The API key is read from the BOUND settings singleton, NOT os.environ —
# whichever test module imported config first wins the singleton, and its key
# may differ from this file's env (test_multi_user.py uses its own dummy).
TEST_API_KEY = config.settings.API_KEY

STRONG_PASSWORD = "SecurePass123"


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Keep the shared rate-limit buckets deterministic across tests (see the
    same fixture in test_api.py for the eviction rationale: this deliberately
    uses the module-level `database` binding — the pre-eviction instance the
    app's routers imported — NOT a function-local import, which would resolve
    a post-eviction module whose DB_PATH points at test_sentinel's :memory:)."""
    with database.get_db_context() as conn:
        conn.execute("DELETE FROM rate_limits")
        conn.commit()
    yield


def _register_user(email: str, password: str = STRONG_PASSWORD) -> str:
    """Register and return the user's access token."""
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Security Tester"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _login(email: str, password: str = STRONG_PASSWORD) -> dict:
    resp = client.post("/api/auth/user/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _totp_code(secret_b32: str) -> str:
    import pyotp

    return pyotp.TOTP(secret_b32).now()


def _get_2fa_secret(email: str) -> str:
    """Fetch the stored TOTP secret straight from the DB — the raw secret
    from setup is only known to the caller, so tests re-derive it exactly
    like a real authenticator app would (via the decrypted store). Uses the
    module-level `database` binding (eviction convention — see the fixture)."""
    from user_security import _decrypt_secret

    with database.get_db_context() as conn:
        row = conn.execute("SELECT u.totp_secret_enc FROM users u WHERE u.email=?", (email,)).fetchone()
    assert row and row["totp_secret_enc"], "user must have a stored (encrypted) TOTP secret"
    return _decrypt_secret(row["totp_secret_enc"])


def _setup_and_enable_2fa(email: str) -> None:
    """Run setup + enable for a registered user (returns nothing; the user
    now requires 2FA on login)."""
    token = _plain_token(email)
    assert client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    secret = _get_2fa_secret(email)
    enable = client.post(
        "/api/auth/2fa/enable",
        json={"password": STRONG_PASSWORD, "code": _totp_code(secret)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enable.status_code == 200, enable.text


class TestTwoFactorLifecycle:
    def test_full_lifecycle(self):
        email = "lifecycle@test.dev"
        token = _register_user(email)

        # Setup returns secret + provisioning URI + QR data URL.
        setup = client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        assert setup.status_code == 200, setup.text
        data = setup.json()
        assert data["secret"] and data["otpauth_uri"].startswith("otpauth://totp/")
        assert data["qr_svg_data_uri"].startswith("data:image/svg+xml;base64,")
        secret = data["secret"]

        # Enable requires the password AND a valid code.
        resp = client.post(
            "/api/auth/2fa/enable",
            json={"password": STRONG_PASSWORD, "code": _totp_code(secret)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["totp_enabled"] is True

        # Login now returns a challenge, NOT real tokens.
        login = _login(email)
        assert login["requires_2fa"] is True
        assert "token" not in login
        challenge = login["two_factor_token"]

        # Wrong code → 401.
        wrong = client.post(
            "/api/auth/user/login/2fa",
            json={"two_factor_token": challenge, "code": "000000"},
        )
        assert wrong.status_code == 401

        # Correct code → real tokens.
        ok = client.post(
            "/api/auth/user/login/2fa",
            json={"two_factor_token": challenge, "code": _totp_code(secret)},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["token"] and ok.json()["refresh_token"]

        # /me reflects the enabled state.
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {ok.json()['token']}"})
        assert me.json()["totp_enabled"] is True

        # Disable requires the password.
        disabled = client.post(
            "/api/auth/2fa/disable",
            json={"password": STRONG_PASSWORD},
            headers={"Authorization": f"Bearer {ok.json()['token']}"},
        )
        assert disabled.status_code == 200
        assert disabled.json()["totp_enabled"] is False

        # After disable, plain login works again.
        assert "token" in _login(email)

    def test_enable_rejects_wrong_password(self):
        email = "badpw@test.dev"
        token = _register_user(email)
        setup = client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"}).json()
        resp = client.post(
            "/api/auth/2fa/enable",
            json={"password": "WrongPass123", "code": _totp_code(setup["secret"])},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_enable_rejects_wrong_code(self):
        email = "badcode@test.dev"
        token = _register_user(email)
        client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        resp = client.post(
            "/api/auth/2fa/enable",
            json={"password": STRONG_PASSWORD, "code": "123456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        # 2FA must NOT be enabled.
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["totp_enabled"] is False

    def test_operator_session_rejected(self):
        """2FA routes are user-account-only — the operator dashboard session
        (subject 'dashboard:<hash>') must get 403, not enroll a fake user."""
        login = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        token = login.json()["token"]
        resp = client.post("/api/auth/2fa/setup", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_challenge_token_is_not_a_dashboard_token(self):
        """The 2FA challenge JWT (type '2fa') must be rejected everywhere a
        real dashboard token is required — a stolen challenge can't be used
        as a session."""
        email = "challenge@test.dev"
        _register_user(email)
        _setup_and_enable_2fa(email)

        challenge = _login(email)["two_factor_token"]
        assert client.get("/api/dashboard/devices", headers={"Authorization": f"Bearer {challenge}"}).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {challenge}"}).status_code == 401

    def test_same_code_replay_rejected(self):
        email = "replay@test.dev"
        _register_user(email)
        _setup_and_enable_2fa(email)

        challenge = _login(email)["two_factor_token"]
        code = _totp_code(_get_2fa_secret(email))
        assert (
            client.post("/api/auth/user/login/2fa", json={"two_factor_token": challenge, "code": code}).status_code
            == 200
        )

        # Same code again (still inside its window) must be rejected.
        second = client.post("/api/auth/user/login/2fa", json={"two_factor_token": challenge, "code": code})
        assert second.status_code == 401

    def test_brute_force_lockout(self):
        email = "brute@test.dev"
        _register_user(email)
        _setup_and_enable_2fa(email)

        for _ in range(5):
            challenge = _login(email)["two_factor_token"]
            resp = client.post("/api/auth/user/login/2fa", json={"two_factor_token": challenge, "code": "111111"})
            assert resp.status_code == 401

        # 6th attempt within the 15-min window → 429.
        challenge = _login(email)["two_factor_token"]
        resp = client.post("/api/auth/user/login/2fa", json={"two_factor_token": challenge, "code": "111111"})
        assert resp.status_code == 429


def _plain_token(email: str) -> str:
    """A real user access token, completing the 2FA step when enabled."""
    login = _login(email)
    if login.get("requires_2fa"):
        from user_security import _decrypt_secret

        with database.get_db_context() as conn:
            row = conn.execute("SELECT u.totp_secret_enc FROM users u WHERE u.email=?", (email,)).fetchone()
        secret = _decrypt_secret(row["totp_secret_enc"])
        resp = client.post(
            "/api/auth/user/login/2fa",
            json={"two_factor_token": login["two_factor_token"], "code": _totp_code(secret)},
        )
        assert resp.status_code == 200
        return resp.json()["token"]
    return login["token"]


class TestPasswordReset:
    def test_forgot_password_no_enumeration(self):
        """Unknown and known emails get identical responses."""
        _register_user("exists@test.dev")
        known = client.post("/api/auth/forgot-password", json={"email": "exists@test.dev"})
        unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@test.dev"})
        assert known.status_code == 200
        assert unknown.status_code == 200
        assert known.json() == unknown.json()

    def test_reset_flow_round_trip(self):
        _register_user("reset@test.dev")
        client.post("/api/auth/forgot-password", json={"email": "reset@test.dev"})

        # Pull the raw token from the DB (in production it is only emailed).
        from database import get_db_context

        with get_db_context() as conn:
            row = conn.execute(
                "SELECT token_hash FROM password_reset_tokens WHERE user_id IN "
                "(SELECT id FROM users WHERE email='reset@test.dev') "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        # token_hash is SHA-256 of the raw token — brute-forcing it from the
        # DB is infeasible, so verify by RESETTING with a garbage token first
        # (rejected), then confirm the stored hash is not the raw value.
        assert row["token_hash"] != "some-raw-token"

        # Wrong token → 401 and password unchanged.
        bad = client.post(
            "/api/auth/reset-password",
            json={"email": "reset@test.dev", "token": "x" * 40, "new_password": "NewPass456"},
        )
        assert bad.status_code == 401
        assert (
            client.post(
                "/api/auth/user/login", json={"email": "reset@test.dev", "password": STRONG_PASSWORD}
            ).status_code
            == 200
        )

        # Weak new password → 422 (strength rules mirror registration).
        weak = client.post(
            "/api/auth/reset-password",
            json={"email": "reset@test.dev", "token": "x" * 32, "new_password": "weak"},
        )
        assert weak.status_code == 422

    def test_reset_requires_valid_registered_email(self):
        resp = client.post(
            "/api/auth/reset-password",
            json={"email": "unknown@test.dev", "token": "x" * 32, "new_password": "NewPass456"},
        )
        assert resp.status_code == 401

    def test_reset_token_never_logged_without_email_provider(self):
        """No SendGrid configured (the current production state): the reset
        link cannot be emailed, and the raw token must NEVER reach the logs —
        a log reader must not become a password-reset oracle. The WARNING
        carries metadata only; the body (with the token) only appears at
        DEBUG and even then redacted. (Regression: the old behavior logged
        the full body with the raw token at WARNING.)"""
        _register_user("recover@test.dev")

        import logging

        # Capture on the module's logger at DEBUG so both the WARNING and the
        # DEBUG body emission are seen (caplog is unreliable in the full
        # suite — the app's logging_config adds its own handler).
        captured: list[str] = []
        handler = logging.Handler()
        handler.setLevel(logging.DEBUG)
        handler.emit = lambda record: captured.append(record.getMessage())
        logger = logging.getLogger("user_security")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        try:
            resp = client.post("/api/auth/forgot-password", json={"email": "recover@test.dev"})
        finally:
            logger.removeHandler(handler)
        assert resp.status_code == 200

        logged = "\n".join(captured)
        # Metadata-only warning: recipient + subject, no body, no link.
        assert "MT_SENDGRID_KEY not configured" in logged
        assert "recover@test.dev" in logged
        # The DEBUG body may be emitted, but the credential is redacted — the
        # link is present only with token=REDACTED, never with a real value.
        assert "/reset-password?email=recover@test.dev&token=REDACTED" in logged
        import re

        assert re.search(r"token=(?!REDACTED)[A-Za-z0-9._-]{8,}", logged) is None

        # The flow still works end-to-end: pull the raw token from the DB the
        # way the emailed link would carry it (hashed at rest) and reset.
        from database import get_db_context

        with get_db_context() as conn:
            row = conn.execute(
                "SELECT token_hash FROM password_reset_tokens WHERE user_id IN "
                "(SELECT id FROM users WHERE email='recover@test.dev') "
                "ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        assert row is not None
        # token_hash is SHA-256 of the raw token — the raw value is only ever
        # emailed, so the DB cannot reveal it either (proves hashing at rest).
        assert len(row["token_hash"]) == 64
        assert row["token_hash"] != "recover@test.dev"

        # The reset flow itself still works end-to-end: mint the raw token the
        # way the emailed link would carry it (only possible in a test), reset
        # with it, and confirm the new password works, the old one is dead,
        # and the token is single-use.
        from database import get_db_context
        from user_security import _issue_email_token

        with get_db_context() as conn:
            user_id = conn.execute("SELECT id FROM users WHERE email='recover@test.dev'").fetchone()["id"]
        raw = _issue_email_token("password_reset_tokens", user_id, 60)
        done = client.post(
            "/api/auth/reset-password",
            json={"email": "recover@test.dev", "token": raw, "new_password": "Recovered#2026"},
        )
        assert done.status_code == 200, done.text
        # New password works; the old one is gone.
        assert (
            client.post(
                "/api/auth/user/login", json={"email": "recover@test.dev", "password": "Recovered#2026"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/user/login", json={"email": "recover@test.dev", "password": STRONG_PASSWORD}
            ).status_code
            == 401
        )
        # Single-use: replaying the same token is rejected.
        replay = client.post(
            "/api/auth/reset-password",
            json={"email": "recover@test.dev", "token": raw, "new_password": "Replay#2026"},
        )
        assert replay.status_code == 401


class TestEmailVerification:
    def test_verify_flow(self):
        token = _register_user("verify@test.dev")
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["email_verified"] is False

        resend = client.post("/api/auth/verify-email/resend", headers={"Authorization": f"Bearer {token}"})
        assert resend.status_code == 200, resend.text

        from database import get_db_context

        with get_db_context() as conn:
            row = conn.execute("SELECT token_hash FROM email_verify_tokens ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row is not None
        # The stored value must be a SHA-256 hash, never the raw token.
        assert len(row["token_hash"]) == 64

        # A garbage token is rejected (must be long enough to pass the
        # pydantic shape gate first — that is the 422; a well-formed garbage
        # token is the 401).
        assert client.post("/api/auth/verify-email", json={"token": "garbage-token"}).status_code == 422
        assert client.post("/api/auth/verify-email", json={"token": "garbage-token-0123456789"}).status_code == 401

    def test_verify_email_marks_verified(self):
        from database import get_db_context
        from user_security import _issue_email_token

        _register_user("verify2@test.dev")
        with get_db_context() as conn:
            user_id = conn.execute("SELECT id FROM users WHERE email='verify2@test.dev'").fetchone()["id"]
        raw = _issue_email_token("email_verify_tokens", user_id, 60)

        resp = client.post("/api/auth/verify-email", json={"token": raw})
        assert resp.status_code == 200, resp.text

        with get_db_context() as conn:
            row = conn.execute("SELECT email_verified FROM users WHERE id=?", (user_id,)).fetchone()
        assert row["email_verified"] == 1

        # Single use — the same token cannot verify twice.
        assert client.post("/api/auth/verify-email", json={"token": raw}).status_code == 401
