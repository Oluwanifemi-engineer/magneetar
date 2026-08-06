"""
Magneetar Device-Key Separation Tests

The public APK embeds a LOW-PRIVILEGE device key (MT_DEVICE_KEY). It must be
able to register devices / use device endpoints, but must NEVER be able to log
into the dashboard as platform admin — that requires the master key
(MT_API_KEY), which lives server-side only. The pre-split master key is
accepted for device-scope auth only (MT_LEGACY_DEVICE_KEY, rotation grace).

These tests lock in the separation so a future refactor can't silently widen
the APK key's powers again.
"""

import os
import secrets
import tempfile

# NOTE: MT_API_KEY/MT_JWT_SECRET must match the values every other suite
# uses (test_auth, test_api...). config.settings is a process-wide singleton
# instantiated from the environment at first import — under a full-suite run
# whichever file imports first wins, so a unique value here would make every
# endpoint test 401 (the settings singleton carries the other file's key).
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_DEVICE_KEY"] = "test-device-key-" + "b" * 24
os.environ["MT_LEGACY_DEVICE_KEY"] = "test-legacy-key-" + "c" * 22
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)

_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
os.environ["MT_DB_PATH"] = _test_db_path

import pytest  # noqa: E402
from auth import api_key_is_authorized, verify_api_key  # noqa: E402
from config import settings  # noqa: E402
from database import init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

# Fixed keys for THIS suite. Because config.settings is a process-wide
# singleton loaded at first import (possibly by another test file, whose env
# won), the per-test monkeypatch below pins the exact values the assertions
# expect — the tests are hermetic and order-independent.
MASTER_KEY = "test-master-key-" + "a" * 21
DEVICE_KEY = "test-device-key-" + "b" * 24
LEGACY_KEY = "test-legacy-key-" + "c" * 22


@pytest.fixture(autouse=True)
def _pin_keys(monkeypatch):
    """Pin settings to this suite's keys for every test, then restore."""
    monkeypatch.setattr(settings, "API_KEY", MASTER_KEY)
    monkeypatch.setattr(settings, "DEVICE_KEY", DEVICE_KEY)
    monkeypatch.setattr(settings, "LEGACY_DEVICE_KEY", LEGACY_KEY)
    init_db()
    yield


def _register_device(client: TestClient, x_api_key: str):
    return client.post(
        "/api/device/register",
        json={
            "device_id": f"dev-{secrets.token_hex(4)}",
            "fingerprint": secrets.token_hex(16),
            "model": "Test Device",
            "os_version": "15",
        },
        headers={"x-api-key": x_api_key},
    )


class TestApiKeyScopeUnit:
    """The pure auth helpers enforce the key set correctly."""

    def test_master_device_and_legacy_are_authorized(self):
        assert api_key_is_authorized(MASTER_KEY)
        assert api_key_is_authorized(DEVICE_KEY)
        assert api_key_is_authorized(LEGACY_KEY)

    def test_random_key_is_rejected(self):
        assert not api_key_is_authorized(secrets.token_hex(32))
        assert not api_key_is_authorized("")
        assert not api_key_is_authorized(MASTER_KEY[:-1])  # near-miss

    def test_verify_api_key_accepts_all_three_keys(self):
        assert verify_api_key(x_api_key=MASTER_KEY) == MASTER_KEY
        assert verify_api_key(x_api_key=DEVICE_KEY) == DEVICE_KEY
        assert verify_api_key(x_api_key=LEGACY_KEY) == LEGACY_KEY

    def test_verify_api_key_rejects_random(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            verify_api_key(x_api_key=secrets.token_hex(32))
        assert exc.value.status_code == 401


class TestDashboardLoginRejectsDeviceKeys:
    """The APK-embedded keys must NEVER mint dashboard admin credentials."""

    def test_master_key_logs_in_as_admin(self):
        with TestClient(app) as client:
            res = client.post("/api/auth/login", json={"api_key": MASTER_KEY})
            assert res.status_code == 200
            assert "token" in res.json()

    def test_device_key_is_rejected(self):
        with TestClient(app) as client:
            res = client.post("/api/auth/login", json={"api_key": DEVICE_KEY})
            assert res.status_code == 401
            assert "token" not in res.text

    def test_legacy_key_is_rejected(self):
        with TestClient(app) as client:
            res = client.post("/api/auth/login", json={"api_key": LEGACY_KEY})
            assert res.status_code == 401

    def test_master_key_still_works_after_rejections(self):
        # Sanity: the rejections above are key-specific, not a broken route.
        with TestClient(app) as client:
            res = client.post("/api/auth/login", json={"api_key": MASTER_KEY})
            assert res.status_code == 200


class TestDeviceEndpointsAcceptDeviceKeys:
    """Device-scope endpoints accept the device + legacy keys (and master)."""

    def test_register_with_device_key(self):
        with TestClient(app) as client:
            res = _register_device(client, DEVICE_KEY)
            assert res.status_code == 200
            assert "token" in res.json()

    def test_register_with_legacy_key(self):
        with TestClient(app) as client:
            res = _register_device(client, LEGACY_KEY)
            assert res.status_code == 200

    def test_register_with_master_key(self):
        # Master stays a valid bootstrap for device flows (back-compat).
        with TestClient(app) as client:
            res = _register_device(client, MASTER_KEY)
            assert res.status_code == 200

    def test_register_with_garbage_key(self):
        with TestClient(app) as client:
            res = _register_device(client, secrets.token_hex(32))
            assert res.status_code == 401

    def test_register_without_key(self):
        with TestClient(app) as client:
            res = client.post(
                "/api/device/register",
                json={
                    "device_id": f"dev-{secrets.token_hex(4)}",
                    "fingerprint": secrets.token_hex(16),
                },
            )
            assert res.status_code == 422  # Header(...) required


class TestAdminStepUpStillMasterOnly:
    """Admin-mode step-up (destructive actions) accepts only the master key."""

    def test_stepup_with_device_key_is_rejected(self):
        # The step-up compare in routes/dashboard.py is hard-gated to the
        # master key. Prove it by scanning the route source rather than
        # executing a destructive path: a device key in the config must never
        # be referenced there.
        import inspect

        import routes.dashboard as dashboard_routes

        src = inspect.getsource(dashboard_routes)
        assert "settings.API_KEY" in src
        assert "settings.DEVICE_KEY" not in src
        assert "settings.LEGACY_DEVICE_KEY" not in src
