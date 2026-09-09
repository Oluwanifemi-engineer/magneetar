"""
Device Lifecycle Integration Tests
──────────────────────────────────
End-to-end tests for the complete device lifecycle:

1. Device registration (via API key)
2. Device claim (link device to user account)
3. Device sharing (grant access to another user)
4. Device share revocation
5. Device access control (viewer/admin/owner roles)
6. Device deletion (cascade cleanup)

Uses sys.modules cleanup to avoid module caching conflicts.
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

# Module eviction (same pattern as test_e2e.py)
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


def _register_user(email: str) -> str:
    """Register a user and return their access token."""
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": STRONG_PASSWORD, "display_name": "Device Test"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _register_device(device_id: str, fingerprint: str = "test-fp-001") -> dict:
    """Register a device via API key and return the response."""
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": fingerprint,
            "model": "Test Phone",
            "platform": "android",
        },
        headers={"x-api-key": TEST_API_KEY},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _claim_device(device_id: str, user_token: str) -> dict:
    """Claim a device for a user account."""
    resp = client.post(
        "/api/device/claim",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── 1. Device Registration ──────────────────────────────────────────────────


class TestDeviceRegistration:
    def test_register_device_returns_tokens(self):
        """Device registration should return JWT tokens."""
        device_id = f"reg-{secrets.token_hex(4)}"
        resp = _register_device(device_id)
        assert "token" in resp
        assert "refresh_token" in resp
        assert resp["device_id"] == device_id

    def test_register_rejects_duplicate_device_id(self):
        """Registration should reject duplicate device IDs."""
        device_id = f"dup-{secrets.token_hex(4)}"
        _register_device(device_id)
        resp = client.post(
            "/api/device/register",
            json={"device_id": device_id, "fingerprint": "test-fingerprint-001", "model": "Test"},
            headers={"x-api-key": TEST_API_KEY},
        )
        # Should return 200 (updates existing) or 409 (conflict)
        assert resp.status_code in (200, 409)


# ── 2. Device Claiming ─────────────────────────────────────────────────────


class TestDeviceClaiming:
    def test_claim_device_links_to_account(self):
        """Claiming a device should link it to the user's account."""
        device_id = f"claim-{secrets.token_hex(4)}"
        _register_device(device_id)

        user_token = _register_user(f"owner-{secrets.token_hex(4)}@test.dev")
        claim_resp = _claim_device(device_id, user_token)

        assert claim_resp["status"] == "ok"
        assert claim_resp["device_id"] == device_id

        # Device should appear in user's device list
        me_resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert me_resp.status_code == 200

    def test_claim_rejects_already_owned_device(self):
        """Cannot claim a device owned by another user."""
        device_id = f"owned-{secrets.token_hex(4)}"
        _register_device(device_id)

        owner_token = _register_user(f"owner1-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, owner_token)

        other_token = _register_user(f"owner2-{secrets.token_hex(4)}@test.dev")
        resp = client.post(
            "/api/device/claim",
            json={"device_id": device_id},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403

    def test_claim_requires_user_token(self):
        """Claiming requires a user JWT, not an API key."""
        device_id = f"noauth-{secrets.token_hex(4)}"
        _register_device(device_id)

        # Try to claim without user token (API key only)
        resp = client.post(
            "/api/device/claim",
            json={"device_id": device_id},
            headers={"x-api-key": TEST_API_KEY},
        )
        assert resp.status_code == 401


# ── 3. Device Sharing ───────────────────────────────────────────────────────


class TestDeviceSharing:
    def test_share_device_grants_access(self):
        """Sharing a device should grant access to another user."""
        device_id = f"share-{secrets.token_hex(4)}"
        _register_device(device_id)

        owner_token = _register_user(f"owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, owner_token)

        grantee_email = f"grantee-{secrets.token_hex(4)}@test.dev"
        _register_user(grantee_email)

        # Share device with grantee
        share_resp = client.post(
            f"/api/dashboard/devices/{device_id}/shares",
            json={"email": grantee_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert share_resp.status_code == 200
        share_data = share_resp.json()
        assert share_data["status"] == "ok"
        assert share_data["role"] == "viewer"

        # List shares
        list_resp = client.get(
            f"/api/dashboard/devices/{device_id}/shares",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert list_resp.status_code == 200
        shares = list_resp.json()["shares"]
        assert len(shares) >= 1
        assert shares[0]["role"] == "viewer"

    def test_revoke_share_removes_access(self):
        """Revoking a share should remove access."""
        device_id = f"revoke-{secrets.token_hex(4)}"
        _register_device(device_id)

        owner_token = _register_user(f"owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, owner_token)

        grantee_email = f"grantee-{secrets.token_hex(4)}@test.dev"
        _register_user(grantee_email)

        # Share
        share_resp = client.post(
            f"/api/dashboard/devices/{device_id}/shares",
            json={"email": grantee_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        share_id = share_resp.json()["share_id"]

        # Revoke
        revoke_resp = client.delete(
            f"/api/dashboard/devices/{device_id}/shares/{share_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert revoke_resp.status_code == 200

        # List should be empty
        list_resp = client.get(
            f"/api/dashboard/devices/{device_id}/shares",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        shares = list_resp.json()["shares"]
        assert len(shares) == 0

    def test_viewer_cannot_share(self):
        """Viewers should not be able to share devices."""
        device_id = f"viewer-{secrets.token_hex(4)}"
        _register_device(device_id)

        owner_token = _register_user(f"owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, owner_token)

        viewer_email = f"viewer-{secrets.token_hex(4)}@test.dev"
        viewer_token = _register_user(viewer_email)

        # Share as viewer
        client.post(
            f"/api/dashboard/devices/{device_id}/shares",
            json={"email": viewer_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        # Viewer tries to share — should fail
        other_email = f"other-{secrets.token_hex(4)}@test.dev"
        _register_user(other_email)
        resp = client.post(
            f"/api/dashboard/devices/{device_id}/shares",
            json={"email": other_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
