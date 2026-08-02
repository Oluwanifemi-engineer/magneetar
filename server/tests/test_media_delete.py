"""
Magneetar Media Deletion Tests

Covers the step-up (password re-verification) gate on destructive media
deletion: user mode verifies the account password, admin mode verifies the
master API key. A stolen dashboard session alone must NEVER be enough to
destroy evidence, and brute-forcing must be rate-limited.
"""

import os
import secrets
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "media-del-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "media-del-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from auth import create_dashboard_tokens  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY
TEST_USER_EMAIL = "media-owner@example.com"
TEST_USER_PASSWORD = "StrongPass1"


def register_user(email: str, password: str = TEST_USER_PASSWORD) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert resp.status_code == 200, f"register_user failed: {resp.text}"
    return resp.json()


def user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def admin_headers() -> dict:
    tokens = create_dashboard_tokens(TEST_API_KEY)
    return {"Authorization": f"Bearer {tokens['token']}"}


def seed_media(device_id: str, media_type: str = "photo", case_id: str = None) -> int:
    """Insert a media row directly (FK to device must exist). Returns media id."""
    with database.get_db_context() as conn:
        cur = conn.execute(
            "INSERT INTO media (device_id, type, data_b64, timestamp, evidence_case_id) "
            "VALUES (?, ?, 'QUJD', datetime('now'), ?)",
            (device_id, media_type, case_id),
        )
        conn.commit()
        return cur.lastrowid


def seed_device(device_id: str, user_token: str = None) -> dict:
    """Register a device, optionally linked to a user account."""
    headers = {"x-api-key": TEST_API_KEY}
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{device_id}",
            "model": "Media Test Device",
            "os_version": "Android 14",
            "app_version": "1.1.0",
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"seed_device failed: {resp.text}"
    return resp.json()


@pytest.fixture(autouse=True)
def reset_db_state():
    with database.get_db_context() as conn:
        for table in (
            "media",
            "locations",
            "commands",
            "evidence_cases",
            "alerts",
            "heartbeats",
            "geofences",
            "recovery_sightings",
            "recovery_requests",
            "devices",
            "users",
            "audit_log",
            "rate_limits",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    yield


def teardown_module(module):
    try:
        os.remove(test_db_path)
    except OSError:
        pass


# ─── Admin / API-key mode ────────────────────────────────────────────────────


class TestAdminMediaDelete:
    def test_admin_can_delete_with_master_api_key(self):
        seed_device("admin-del-device")
        media_id = seed_media("admin-del-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": TEST_API_KEY},
            headers=admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted_id"] == media_id

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM media WHERE id=?", (media_id,)).fetchone()[0] == 0

    def test_admin_wrong_password_rejected(self):
        seed_device("admin-wrong-device")
        media_id = seed_media("admin-wrong-device")

        resp = client.post(
            "/api/dashboard/media/{}/delete".format(media_id),
            json={"password": "not-the-key"},
            headers=admin_headers(),
        )
        assert resp.status_code == 401

        # Media still present
        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM media WHERE id=?", (media_id,)).fetchone()[0] == 1

    def test_missing_password_rejected(self):
        seed_device("admin-nopass-device")
        media_id = seed_media("admin-nopass-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={},
            headers=admin_headers(),
        )
        assert resp.status_code == 400

    def test_rate_limited_after_repeated_attempts(self):
        seed_device("admin-rl-device")
        media_id = seed_media("admin-rl-device")
        # Brute-force attempts: 10 allowed, 11th blocked.
        for _ in range(10):
            client.post(
                f"/api/dashboard/media/{media_id}/delete",
                json={"password": "wrong"},
                headers=admin_headers(),
            )

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": "wrong"},
            headers=admin_headers(),
        )
        assert resp.status_code == 429

    def test_unknown_media_404(self):
        resp = client.post(
            "/api/dashboard/media/999999/delete",
            json={"password": TEST_API_KEY},
            headers=admin_headers(),
        )
        assert resp.status_code == 404


# ─── User mode ───────────────────────────────────────────────────────────────


class TestUserMediaDelete:
    def test_user_can_delete_own_media_with_account_password(self):
        user = register_user(TEST_USER_EMAIL)
        seed_device("user-del-device", user_token=user["token"])
        media_id = seed_media("user-del-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM media WHERE id=?", (media_id,)).fetchone()[0] == 0

    def test_user_wrong_password_rejected(self):
        user = register_user(TEST_USER_EMAIL)
        seed_device("user-wrong-device", user_token=user["token"])
        media_id = seed_media("user-wrong-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": "WrongPass1"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 401

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM media WHERE id=?", (media_id,)).fetchone()[0] == 1

    def test_non_owner_denied(self):
        owner = register_user("media-owner-a@example.com")
        intruder = register_user("media-intruder@example.com")
        seed_device("user-guarded-device", user_token=owner["token"])
        media_id = seed_media("user-guarded-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": "AnyPass1"},
            headers=user_headers(intruder["token"]),
        )
        assert resp.status_code == 403

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM media WHERE id=?", (media_id,)).fetchone()[0] == 1


# ─── Evidence case counter consistency ───────────────────────────────────────


class TestEvidenceCounters:
    def test_delete_photo_decrements_case_count(self):
        user = register_user("media-evidence@example.com")
        seed_device("evidence-device", user_token=user["token"])
        # Create an active case + a linked photo.
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO evidence_cases (id, device_id, theft_time, status, photo_count, audio_count) "
                "VALUES ('case-media-del', 'evidence-device', datetime('now'), 'active', 1, 0)"
            )
            conn.commit()
        media_id = seed_media("evidence-device", media_type="photo", case_id="case-media-del")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text

        with database.get_db_context() as conn:
            case = conn.execute(
                "SELECT photo_count, audio_count FROM evidence_cases WHERE id='case-media-del'"
            ).fetchone()
        assert case["photo_count"] == 0
        assert case["audio_count"] == 0

    def test_delete_audio_decrements_audio_count(self):
        user = register_user("media-evidence-audio@example.com")
        seed_device("evidence-audio-device", user_token=user["token"])
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO evidence_cases (id, device_id, theft_time, status, photo_count, audio_count) "
                "VALUES ('case-media-audio', 'evidence-audio-device', datetime('now'), 'active', 0, 1)"
            )
            conn.commit()
        media_id = seed_media("evidence-audio-device", media_type="audio", case_id="case-media-audio")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text

        with database.get_db_context() as conn:
            case = conn.execute(
                "SELECT photo_count, audio_count FROM evidence_cases WHERE id='case-media-audio'"
            ).fetchone()
        assert case["audio_count"] == 0

    def test_delete_unlinked_media_leaves_case_untouched(self):
        """Media without an evidence_case_id must not break the counter path."""
        user = register_user("media-evidence-unlinked@example.com")
        seed_device("evidence-unlinked-device", user_token=user["token"])
        media_id = seed_media("evidence-unlinked-device")

        resp = client.post(
            f"/api/dashboard/media/{media_id}/delete",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
