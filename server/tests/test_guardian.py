"""
Magneetar Guardian Network Tests
Community recovery: guardian opt-in, recovery request launch/close,
blurred nearby listing for guardians, and rate-limited sightings.
"""

import os
import secrets
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "guardian-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "guardian-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from auth import create_dashboard_tokens, create_device_tokens  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY
TEST_USER_PASSWORD = "StrongPass1"


def register_user(email: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_USER_PASSWORD, "display_name": "Test User"},
    )
    assert resp.status_code == 200, f"register_user failed: {resp.text}"
    return resp.json()


def user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device(device_id: str, user_token: str = None) -> dict:
    headers = api_key_headers()
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{device_id}",
            "model": "Guardian Test Phone",
            "os_version": "Android 14",
            "app_version": "1.1.0",
            "device_key": f"devicekey-{device_id}",
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"register_device failed: {resp.text}"
    return resp.json()


def set_device_stolen(device_id: str):
    """Flip a device into stolen mode directly (as Sentinel would)."""
    with database.get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET is_stolen=1, operating_mode='stolen', sentinel_score=90 WHERE id=?",
            (device_id,),
        )
        conn.execute(
            "INSERT INTO evidence_cases (id, device_id, theft_time, status) VALUES (?, ?, datetime('now'), 'active')",
            (f"case-{device_id}", device_id),
        )
        conn.execute(
            "INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES (?, ?, ?, datetime('now'))",
            (device_id, 9.0820, 8.6753),
        )
        conn.commit()


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset the shared test DB between tests."""
    with database.get_db_context() as conn:
        for table in (
            "recovery_sightings",
            "recovery_requests",
            "guardian_profiles",
            "locations",
            "media",
            "commands",
            "evidence_cases",
            "alerts",
            "heartbeats",
            "geofences",
            "fcm_tokens",
            "devices",
            "users",
            "audit_log",
            "rate_limits",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()

    import websocket_manager

    websocket_manager._device_owners.clear()
    websocket_manager._connection_owners.clear()
    yield


def teardown_module(module):
    try:
        os.remove(test_db_path)
    except OSError:
        pass


# ─── Schema migration (existing DBs must gain new tables) ────────────────────


class TestSchemaMigration:
    def test_ensure_initialized_migrates_existing_db(self, monkeypatch):
        """An existing database (created before the Guardian tables) must be
        migrated forward by ensure_initialized() on server startup."""
        fd, old_db_path = tempfile.mkstemp(suffix="-old.db")
        os.close(fd)

        # Simulate a DB created by an older release: devices table only.
        conn = sqlite3.connect(old_db_path)
        conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        # Point the database module at the old file and run the startup check.
        monkeypatch.setattr(database, "DB_PATH", old_db_path)
        assert database.ensure_initialized() is True

        conn = sqlite3.connect(old_db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()

        assert "guardian_profiles" in tables
        assert "recovery_requests" in tables
        assert "recovery_sightings" in tables
        assert "devices" in tables
        os.remove(old_db_path)

    def test_ensure_initialized_noop_when_current(self, monkeypatch):
        """A fully-migrated DB should not be rewritten on every startup."""
        fd, fresh_db_path = tempfile.mkstemp(suffix="-fresh.db")
        os.close(fd)
        monkeypatch.setattr(database, "DB_PATH", fresh_db_path)

        assert database.ensure_initialized() is True  # created it
        assert database.ensure_initialized() is False  # no-op on second call
        os.remove(fresh_db_path)


# ─── Guardian opt-in ─────────────────────────────────────────────────────────


class TestGuardianOptIn:
    def test_opt_in_creates_profile(self):
        user = register_user("guardian@example.com")
        resp = client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 30, "handle": "NightWatch"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["opted_in"] is True
        assert resp.json()["handle"] == "NightWatch"
        assert resp.json()["radius_km"] == 30

    def test_opt_out(self):
        user = register_user("optout@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 10, "handle": "Ghost"},
            headers=user_headers(user["token"]),
        )
        resp = client.post(
            "/api/guardian/opt-in",
            json={"opted_in": False},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["opted_in"] is False

    def test_profile_defaults_opted_out(self):
        user = register_user("fresh@example.com")
        resp = client.get("/api/guardian/profile", headers=user_headers(user["token"]))
        assert resp.status_code == 200
        assert resp.json()["opted_in"] is False

    def test_opt_in_requires_real_user(self):
        resp = client.post("/api/guardian/opt-in", json={"opted_in": True}, headers=api_key_headers())
        assert resp.status_code == 401

    def test_profile_requires_auth(self):
        resp = client.get("/api/guardian/profile")
        assert resp.status_code == 401


# ─── Recovery request launch / list / close ──────────────────────────────────


class TestRecoveryRequests:
    def _setup_stolen_device(self, email="owner@example.com"):
        user = register_user(email)
        device = register_device("stolen-phone", user_token=user["token"])
        set_device_stolen("stolen-phone")
        return user, device

    def test_launch_requires_stolen_device(self):
        user = register_user("normal@example.com")
        register_device("normal-phone", user_token=user["token"])
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "normal-phone", "description": "Not stolen"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 400

    def test_launch_success(self):
        user, _ = self._setup_stolen_device()
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Grey Pixel 8, lost near the mall"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "active"
        assert body["device_id"] == "stolen-phone"
        assert body["id"].startswith("rec-")
        assert body["sighting_count"] == 0

    def test_launch_non_owner_403(self):
        owner = register_user("owner-a@example.com")
        intruder = register_user("owner-b@example.com")
        register_device("stolen-phone", user_token=owner["token"])
        set_device_stolen("stolen-phone")
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(intruder["token"]),
        )
        assert resp.status_code == 403

    def test_launch_duplicate_409(self):
        user, _ = self._setup_stolen_device()
        client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "First"},
            headers=user_headers(user["token"]),
        )
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Second"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 409

    def test_list_only_own_requests(self):
        user_a, _ = self._setup_stolen_device(email="owner-a@example.com")
        user_b = register_user("owner-b@example.com")
        client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(user_a["token"]),
        )
        resp_b = client.get("/api/recovery/requests", headers=user_headers(user_b["token"]))
        assert resp_b.status_code == 200
        assert resp_b.json()["requests"] == []

        resp_a = client.get("/api/recovery/requests", headers=user_headers(user_a["token"]))
        assert len(resp_a.json()["requests"]) == 1

    def test_close_marks_device_recovered(self):
        user, _ = self._setup_stolen_device()
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Help find it"},
            headers=user_headers(user["token"]),
        ).json()

        resp = client.post(
            f"/api/recovery/requests/{req['id']}/close",
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert "recovered" in resp.json()["message"]

        with database.get_db_context() as conn:
            device = conn.execute("SELECT is_stolen, operating_mode FROM devices WHERE id='stolen-phone'").fetchone()
            assert device["is_stolen"] == 0
            assert device["operating_mode"] == "normal"

        # Closing a closed request → 400
        resp = client.post(f"/api/recovery/requests/{req['id']}/close", headers=user_headers(user["token"]))
        assert resp.status_code == 400

    def test_close_non_owner_403(self):
        user, _ = self._setup_stolen_device()
        other = register_user("other@example.com")
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(user["token"]),
        ).json()
        resp = client.post(f"/api/recovery/requests/{req['id']}/close", headers=user_headers(other["token"]))
        assert resp.status_code == 403

    def test_close_unknown_404(self):
        user = register_user("close404@example.com")
        resp = client.post("/api/recovery/requests/rec-nonexistent/close", headers=user_headers(user["token"]))
        assert resp.status_code == 404


# ─── Guardian nearby view & sightings ────────────────────────────────────────


class TestNearbyAndSightings:
    def _setup(self):
        """Owner with a stolen device + an active request; a guardian nearby."""
        owner = register_user("owner@example.com")
        register_device("stolen-phone", user_token=owner["token"])
        set_device_stolen("stolen-phone")
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Find this Pixel"},
            headers=user_headers(owner["token"]),
        ).json()

        guardian = register_user("guardian@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "EagleEye"},
            headers=user_headers(guardian["token"]),
        )
        return owner, guardian, req

    def test_nearby_requires_opt_in(self):
        owner, _g, req = self._setup()
        stranger = register_user("stranger@example.com")
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(stranger["token"]),
        )
        assert resp.status_code == 403

    def test_nearby_shows_blurred_request(self):
        _o, guardian, _req = self._setup()
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200
        requests = resp.json()["requests"]
        assert len(requests) == 1
        r = requests[0]
        assert r["device_model"] == "Guardian Test Phone"
        assert r["distance_km"] <= 1.0
        # Location is blurred — must not be the exact device coordinate
        assert r["blurred_lat"] != 9.0820 or r["blurred_lng"] != 8.6753
        assert isinstance(r["blurred_lat"], float)

    def test_nearby_filters_by_distance(self):
        _o, guardian, _req = self._setup()
        # Far away (device at 9.08, 8.67 — asking from London)
        resp = client.get(
            "/api/recovery/nearby?lat=51.5074&lng=-0.1278&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["requests"] == []

    def test_report_sighting_requires_opt_in(self):
        owner, _g, req = self._setup()
        stranger = register_user("sight-stranger@example.com")
        resp = client.post(
            "/api/recovery/sightings",
            json={"request_id": req["id"], "lat": 9.083, "lng": 8.676, "note": "Saw it!"},
            headers=user_headers(stranger["token"]),
        )
        assert resp.status_code == 403

    def test_report_sighting_success_and_owner_sees_it(self):
        owner, guardian, req = self._setup()
        resp = client.post(
            "/api/recovery/sightings",
            json={"request_id": req["id"], "lat": 9.083, "lng": 8.676, "note": "Saw it near the bus stop"},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["guardian_handle"] == "EagleEye"

        # Owner's request detail now includes the sighting
        resp = client.get("/api/recovery/requests", headers=user_headers(owner["token"]))
        requests = resp.json()["requests"]
        assert len(requests) == 1
        assert requests[0]["sighting_count"] == 1
        assert requests[0]["sightings"][0]["guardian_handle"] == "EagleEye"
        assert requests[0]["sightings"][0]["note"] == "Saw it near the bus stop"

    def test_sighting_on_closed_request_400(self):
        owner, guardian, req = self._setup()
        client.post(f"/api/recovery/requests/{req['id']}/close", headers=user_headers(owner["token"]))
        resp = client.post(
            "/api/recovery/sightings",
            json={"request_id": req["id"], "lat": 9.083, "lng": 8.676, "note": "Too late"},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 400

    def test_sighting_rate_limited(self, monkeypatch):
        _o, guardian, req = self._setup()
        # Shrink the limit to make the test fast and deterministic
        import routes.guardian as guardian_routes

        monkeypatch.setattr(guardian_routes, "SIGHTING_RATE_MAX", 3)

        for i in range(3):
            resp = client.post(
                "/api/recovery/sightings",
                json={"request_id": req["id"], "lat": 9.083, "lng": 8.676, "note": f"Sighting {i}"},
                headers=user_headers(guardian["token"]),
            )
            assert resp.status_code == 200

        resp = client.post(
            "/api/recovery/sightings",
            json={"request_id": req["id"], "lat": 9.083, "lng": 8.676, "note": "Fourth"},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 429

    def test_guardian_cannot_see_owner_identity(self):
        _o, guardian, _req = self._setup()
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        body = resp.json()
        payload = str(body)
        assert "owner" not in payload.lower() or "owner_id" not in payload
        assert "owner_id" not in payload
