"""
Magneetar E2E Tests
Standalone integration tests. Uses sys.modules cleanup to avoid
module caching conflicts with other test files.
"""

import os
import secrets
import sys
import tempfile
import time

# Set test environment BEFORE any imports
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "e2e-test-key-" + "z" * 32
os.environ["MT_JWT_SECRET"] = "e2e-test-jwt-" + "y" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Clear cached modules so they re-import with new env vars
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
        # user_auth/evidence_pdf/database_postgres also bind config+settings;
        # leaving the stale copies in sys.modules makes later test modules
        # (test_multi_user, test_reliability) mix config A tokens with config
        # B decoding → "Invalid token", and write rate limits to the wrong DB.
        or mod_name == "user_auth"
        or mod_name == "evidence_pdf"
        or mod_name == "database_postgres"
    ):
        del sys.modules[mod_name]

import database as db_module  # noqa: E402 (env set above)
from config import settings  # noqa: E402

# Force settings to use test DB path
settings.DB_PATH = test_db_path
db_module.DB_PATH = test_db_path
db_module.init_db(test_db_path)

import main as main_module  # noqa: E402
from auth import create_dashboard_tokens, create_device_tokens  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main_module.app)

TEST_API_KEY = os.environ["MT_API_KEY"]


def get_dash_headers():
    tokens = create_dashboard_tokens(TEST_API_KEY)
    return {"Authorization": f"Bearer {tokens['token']}"}


def get_device_headers(device_id="e2e-test-device"):
    tokens = create_device_tokens(device_id)
    return {"Authorization": f"Bearer {tokens['token']}"}


def ensure_device(device_id="e2e-test-device"):
    """Register a device for testing. Returns True on success."""
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": "e2e-fingerprint",
            "model": "Test Phone",
            "os_version": "Android 14",
            "app_version": "1.0.0",
        },
        headers={"x-api-key": TEST_API_KEY},
    )
    return resp.status_code == 200


# ─── Device Management Endpoints ───────────────────────────────────────────


class TestDeviceManagement:
    def setup_method(self):
        assert ensure_device()

    def test_update_device_alias(self):
        headers = get_dash_headers()
        resp = client.patch("/api/dashboard/devices/e2e-test-device/alias", json={"alias": "My Phone"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["alias"] == "My Phone"

    def test_update_device_alias_empty_rejected(self):
        headers = get_dash_headers()
        resp = client.patch("/api/dashboard/devices/e2e-test-device/alias", json={"alias": ""}, headers=headers)
        assert resp.status_code == 400

    def test_mark_device_recovered(self):
        with db_module.get_db_context() as db:
            db.execute("UPDATE devices SET is_stolen=1, operating_mode='stolen' WHERE id=?", ("e2e-test-device",))
            db.commit()

        headers = get_dash_headers()
        resp = client.post("/api/dashboard/devices/e2e-test-device/recover", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        with db_module.get_db_context() as db:
            device = db.execute(
                "SELECT is_stolen, operating_mode FROM devices WHERE id=?", ("e2e-test-device",)
            ).fetchone()
            assert device["is_stolen"] == 0
            assert device["operating_mode"] == "normal"

    def test_get_device_history(self):
        headers = get_dash_headers()
        resp = client.get("/api/dashboard/devices/e2e-test-device/history", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["device"]["id"] == "e2e-test-device"

    def test_device_history_not_found(self):
        headers = get_dash_headers()
        resp = client.get("/api/dashboard/devices/nonexistent-device/history", headers=headers)
        assert resp.status_code == 404


# ─── Live Location ────────────────────────────────────────────────────────


class TestLiveLocation:
    def test_post_and_retrieve_location(self):
        device_id = "live-loc-dev"
        assert ensure_device(device_id)
        dev_headers = get_device_headers(device_id)

        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.1000,
                "lng": 8.7000,
                "accuracy_horizontal": 15.0,
                "speed": 1.0,
                "provider": "gps",
                "ping_sequence": 1,
            },
            headers=dev_headers,
        )
        assert resp.status_code == 200, f"Location post failed: {resp.json()}"

        dash_headers = get_dash_headers()
        resp = client.get(f"/api/dashboard/locations/{device_id}/live", headers=dash_headers)
        assert resp.status_code == 200
        assert resp.json()["location"] is not None


# ─── Theft Detection (single-ping, fresh device) ──────────────────────────


class TestTheftDetection:
    def device_id(self):
        return f"theft-{int(time.time() * 1000)}"

    def test_theft_triggers_on_fresh_device(self):
        """Fresh device (empty history) → false-positive check bypassed → stolen."""
        did = self.device_id()
        assert ensure_device(did)
        dev_headers = get_device_headers(did)

        # Score: sim(35) + airplane(15) + loc_disabled(20) + vehicle_speed(25) = 95
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": did,
                "lat": 9.25,
                "lng": 8.9,
                "accuracy_horizontal": 50.0,
                "speed": 45.0,
                "battery_percent": 60,
                "is_charging": False,
                "provider": "gps",
                "confidence_level": "MEDIUM",
                "is_location_enabled": False,
                "is_airplane_mode": True,
                "sim_changed": True,
                "ping_sequence": 1,
            },
            headers=dev_headers,
        )
        assert resp.status_code == 200, f"Theft ping failed: {resp.json()}"

        dash_headers = get_dash_headers()
        devices = client.get("/api/dashboard/devices", headers=dash_headers).json()["devices"]
        device = next(d for d in devices if d["id"] == did)
        assert device["is_stolen"], f"Device not stolen. Score: {device['sentinel_score']}"
        assert device["sentinel_score"] >= 80

    def test_evidence_case_created_on_theft(self):
        """Evidence case is created when theft is detected."""
        did = self.device_id()
        assert ensure_device(did)
        dev_headers = get_device_headers(did)

        resp = client.post(
            "/api/device/location",
            json={
                "device_id": did,
                "lat": 9.5,
                "lng": 8.5,
                "speed": 50.0,
                "sim_changed": True,
                "is_airplane_mode": True,
                "is_location_enabled": False,
                "ping_sequence": 1,
            },
            headers=dev_headers,
        )
        assert resp.status_code == 200, f"Theft ping failed: {resp.json()}"

        dash_headers = get_dash_headers()
        resp = client.get(f"/api/dashboard/evidence/{did}", headers=dash_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] is not None, f"No evidence case created: {data}"
        assert data["status"] in ("active", "generated")

    def test_normal_pings_no_theft(self):
        """Normal pings should not trigger theft."""
        did = self.device_id()
        assert ensure_device(did)
        dev_headers = get_device_headers(did)

        for seq in range(3):
            resp = client.post(
                "/api/device/location",
                json={
                    "device_id": did,
                    "lat": 9.082,
                    "lng": 8.6753,
                    "accuracy_horizontal": 8.0,
                    "speed": 0.5,
                    "battery_percent": 85,
                    "is_charging": False,
                    "provider": "gps",
                    "confidence_level": "HIGH",
                    "is_location_enabled": True,
                    "sim_changed": False,
                    "ping_sequence": seq + 1,
                },
                headers=dev_headers,
            )
            assert resp.status_code == 200

        dash_headers = get_dash_headers()
        devices = client.get("/api/dashboard/devices", headers=dash_headers).json()["devices"]
        device = next(d for d in devices if d["id"] == did)
        assert not device["is_stolen"]
        assert device["operating_mode"] == "normal"


# ─── Rate Limiting ────────────────────────────────────────────────────────


class TestRateLimiting:
    DEVICE_ID = "rate-limit-dev"

    def setup_method(self):
        assert ensure_device(self.DEVICE_ID)

    def test_rate_limit_exceeded(self):
        dev_headers = get_device_headers(self.DEVICE_ID)
        statuses = []
        for i in range(35):
            resp = client.post(
                "/api/device/location",
                json={
                    "device_id": self.DEVICE_ID,
                    "lat": 9.082,
                    "lng": 8.6753,
                    "accuracy_horizontal": 10.0,
                    "speed": 0.5,
                    "provider": "gps",
                    "ping_sequence": i + 1,
                },
                headers=dev_headers,
            )
            statuses.append(resp.status_code)

        rate_limited = [s for s in statuses if s == 429]
        assert len(rate_limited) > 0, f"No rate limiting: statuses={set(statuses)}"


# ─── Geofence ─────────────────────────────────────────────────────────────


class TestGeofenceBasic:
    DEVICE_ID = "geo-test-dev"

    def setup_method(self):
        assert ensure_device(self.DEVICE_ID)

    def test_create_and_delete_geofence(self):
        dash_headers = get_dash_headers()
        resp = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": self.DEVICE_ID,
                "name": "Test",
                "center_lat": 6.5,
                "center_lng": 3.4,
                "radius_meters": 500,
                "is_safe_zone": True,
            },
            headers=dash_headers,
        )
        assert resp.status_code == 200
        gf_id = resp.json()["geofence_id"]

        # List
        resp = client.get(f"/api/dashboard/geofences/{self.DEVICE_ID}", headers=dash_headers)
        assert resp.status_code == 200
        assert len(resp.json()["geofences"]) >= 1

        # Delete
        resp = client.delete(f"/api/dashboard/geofence/{gf_id}", headers=dash_headers)
        assert resp.status_code == 200
