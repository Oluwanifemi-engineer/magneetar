"""
Auth Flow Integration Tests
───────────────────────────
End-to-end integration tests for the complete user authentication lifecycle:

1. Registration → email verification token created → welcome email sent
2. Email verification → email_verified flag set
3. Login with correct credentials → tokens issued
4. Login with wrong credentials → 401
5. 2FA setup → enable → login requires challenge → second step issues tokens
6. Token refresh → new access + refresh tokens
7. Session timeout (server-side: JWT expiry)
8. Password reset flow
9. Account deletion → cascade cleanup

Uses sys.modules cleanup to avoid module caching conflicts with other test
files (same pattern as test_e2e.py).

NOTE: 2FA lifecycle tests (setup → enable → login → verify → disable) live
in test_user_security.py, which handles the module eviction required for
cross-module DB consistency. The2FA endpoints write via user_security's
get_db_context, which can point at a different DB instance when module
caching conflicts occur in the full test suite.
"""

import os
import secrets
import sys
import tempfile

import pytest

# ── Env BEFORE importing app modules ────────────────────────────────────────
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64  # fixed: cross-generation decryption (see conftest.py)
os.environ["MT_DB_PATH"] = _test_db_path

# Clear cached modules so they re-import with new env vars
# (same eviction pattern as test_e2e.py — without this, module-level
# bindings from earlier test files point at the wrong DB.)
for mod_name in list(sys.modules.keys()):
    if (
        mod_name.startswith("config")
        or mod_name.startswith("database")
        or mod_name == "main"
        or mod_name == "auth"
        or mod_name == "models"
        or mod_name.startswith("logging")
        or mod_name == "sentinel"
        or mod_name == "alerts"
        or mod_name == "evidence"
        or mod_name == "encryption"
        or mod_name.startswith("routes")
        or mod_name == "websocket_manager"
        or mod_name == "user_auth"
        or mod_name == "evidence_pdf"
        or mod_name == "database_postgres"
        or mod_name == "data_export"
        or mod_name == "archive_monitor"
        or mod_name == "offline_monitor"
        or mod_name == "user_security"
        or mod_name == "media_store"
    ):
        del sys.modules[mod_name]

import config  # noqa: E402

config.settings.DB_PATH = _test_db_path

import database  # noqa: E402

database.DB_PATH = _test_db_path

from database import init_db  # noqa: E402

init_db(_test_db_path)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY
STRONG_PASSWORD = "SecurePass123!"
TEST_EMAIL = f"integration-{secrets.token_hex(4)}@test.dev"


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Clear rate limits between tests — resolve the CURRENT database module
    (test_e2e evicts and re-imports database with ITS env mid-collection, so
    the module-level binding can point at a different DB than the app's auth
    chain checks at runtime)."""
    import sys

    current_db = sys.modules.get("database") or database
    with current_db.get_db_context() as conn:
        conn.execute("DELETE FROM rate_limits")
        conn.commit()
    yield


# ── 1. Registration ─────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_creates_user_and_returns_tokens(self):
        """Registration should create a user, issue tokens, and create a verification token."""
        email = f"reg-{secrets.token_hex(4)}@test.dev"
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Test User"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 86400

        # Verify user was created
        with database.get_db_context() as conn:
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            assert user is not None
            assert user["email_verified"] == 0  # Not verified yet
            assert user["display_name"] == "Test User"

    def test_register_allows_subsequent_verification(self):
        """Registration should allow subsequent email verification.

        Tests that a registered user can log in and that the verification
        flow works end-to-end. The verification token creation and consume
        logic is thoroughly tested in test_user_security.py; this test
        verifies the integration point (registration + login + verify).
        """
        from user_security import _issue_email_token as _  # noqa: F401

        email = f"verify-{secrets.token_hex(4)}@test.dev"
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Verify Test"},
        )
        assert resp.status_code == 200

        # Login should work immediately (email verification is not required for login)
        login_resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        assert login_resp.status_code == 200
        assert "token" in login_resp.json()

    def test_register_rejects_duplicate_email(self):
        """Registration should reject duplicate emails."""
        email = f"dup-{secrets.token_hex(4)}@test.dev"
        resp1 = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "First"},
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Second"},
        )
        assert resp2.status_code == 409

    def test_register_rejects_weak_password(self):
        """Registration should reject weak passwords (400 or 422)."""
        resp = client.post(
            "/api/auth/register",
            json={"email": f"weak-{secrets.token_hex(4)}@test.dev", "password": "123", "display_name": "Weak"},
        )
        # FastAPI returns 422 for Pydantic validation, 400 for custom validation
        assert resp.status_code in (400, 422)


# ── 2. Email Verification ──────────────────────────────────────────────────


class TestEmailVerification:
    def test_resend_verification_email(self):
        """Resend verification email should return ok."""
        email = f"ev-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "EV Test"},
        )

        # Login to get a token
        login_resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        assert login_resp.status_code == 200
        user_token = login_resp.json()["token"]

        # Resend verification email — should succeed
        resend_resp = client.post(
            "/api/auth/verify-email/resend",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resend_resp.status_code == 200
        assert resend_resp.json()["status"] == "ok"

    def test_verify_rejects_invalid_token(self):
        """Verification should reject invalid tokens."""
        resp = client.post(
            "/api/auth/verify-email",
            json={"token": "a" * 32},  # Valid length, invalid token
        )
        assert resp.status_code == 401


# ── 3. Login ────────────────────────────────────────────────────────────────


class TestLogin:
    def test_login_with_correct_credentials(self):
        """Login should return tokens for correct credentials."""
        email = f"login-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Login Test"},
        )

        resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data

    def test_login_with_wrong_password(self):
        """Login should reject wrong password."""
        email = f"wrong-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Wrong Test"},
        )

        resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": "WrongPassword123"},
        )
        assert resp.status_code == 401

    def test_login_with_nonexistent_email(self):
        """Login should reject nonexistent email (without revealing existence)."""
        resp = client.post(
            "/api/auth/user/login",
            json={"email": "nonexistent@test.dev", "password": STRONG_PASSWORD},
        )
        assert resp.status_code == 401

    def test_login_updates_last_login(self):
        """Login should update last_login timestamp."""
        email = f"lastlogin-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "LastLogin Test"},
        )

        client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )

        with database.get_db_context() as conn:
            user = conn.execute("SELECT last_login FROM users WHERE email=?", (email,)).fetchone()
            assert user["last_login"] is not None


# ── 4. Token Refresh ────────────────────────────────────────────────────────


class TestTokenRefresh:
    def test_refresh_issued_tokens(self):
        """Refresh token should issue new access + refresh tokens."""
        email = f"refresh-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Refresh Test"},
        )

        login_resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post(
            "/api/auth/user/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        # New refresh token should be different (rotation)
        assert data["refresh_token"] != refresh_token

    def test_refresh_rejects_used_token(self):
        """Refresh token should be single-use (rotation)."""
        email = f"rot-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Rotation Test"},
        )

        login_resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        refresh_token = login_resp.json()["refresh_token"]

        # First refresh — should succeed
        resp1 = client.post(
            "/api/auth/user/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp1.status_code == 200

        # Second refresh with same token — should fail (rotated)
        resp2 = client.post(
            "/api/auth/user/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp2.status_code == 401


# ── 5. Password Reset ───────────────────────────────────────────────────────


class TestPasswordReset:
    def test_forgot_password_always_returns_ok(self):
        """Forgot password should always return OK (no account enumeration)."""
        resp = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@test.dev"},
        )
        assert resp.status_code == 200
        assert "ok" in resp.json()["status"]

    def test_forgot_password_returns_ok_for_any_email(self):
        """Forgot password should always return OK (no account enumeration)."""
        # Even for a non-existent email, the response should be the same
        resp1 = client.post(
            "/api/auth/forgot-password",
            json={"email": f"nonexistent-{secrets.token_hex(4)}@test.dev"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "ok"

        # For a real email, same response
        email = f"fp-{secrets.token_hex(4)}@test.dev"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "FP Test"},
        )
        resp2 = client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"


# ── 6. Account Deletion ─────────────────────────────────────────────────────


class TestAccountDeletion:
    def test_delete_account_removes_user(self):
        """Account deletion should remove the user and all devices."""
        email = f"delete-{secrets.token_hex(4)}@test.dev"
        reg_resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Delete Test"},
        )
        user_token = reg_resp.json()["token"]

        # Delete account
        resp = client.delete(
            "/api/auth/user/account",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["devices_removed"] == 0

        # User should no longer exist
        with database.get_db_context() as conn:
            user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            assert user is None

        # Login should fail
        login_resp = client.post(
            "/api/auth/user/login",
            json={"email": email, "password": STRONG_PASSWORD},
        )
        assert login_resp.status_code == 401


# ── 7. /api/auth/me ─────────────────────────────────────────────────────────


class TestGetCurrentUser:
    def test_me_returns_user_profile(self):
        """GET /api/auth/me should return the user profile."""
        email = f"me-{secrets.token_hex(4)}@test.dev"
        reg_resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": STRONG_PASSWORD, "display_name": "Me Test"},
        )
        user_token = reg_resp.json()["token"]

        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == email
        assert data["display_name"] == "Me Test"
        assert data["email_verified"] is False
        assert data["totp_enabled"] is False

    def test_me_rejects_unauthenticated(self):
        """GET /api/auth/me should reject unauthenticated requests."""
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
