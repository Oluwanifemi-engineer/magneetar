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
        # user_auth/evidence_pdf/database_postgres/data_export also bind
        # config+settings (data_export does `from database import
        # get_db_context` at module level); leaving the stale copies in
        # sys.modules makes later test modules (test_multi_user,
        # test_reliability) mix config A tokens with config B decoding →
        # "Invalid token", write rate limits to the wrong DB, and — for
        # data_export — resolve get_db_context to a pre-eviction module whose
        # DB_PATH points at an earlier test file's temp DB, so account
        # deletion/export runs against the wrong database.
        or mod_name == "user_auth"
        or mod_name == "evidence_pdf"
        or mod_name == "database_postgres"
        or mod_name == "data_export"
        # archive_monitor/offline_monitor bind database at MODULE level; if
        # they were imported before this eviction (e.g. by test_archive,
        # which sorts earlier alphabetically), leaving the stale copies in
        # sys.modules makes their sweep read a dead database instance's path.
        or mod_name == "archive_monitor"
        or mod_name == "offline_monitor"
        # user_security/media_store (v1.4) are imported by main/user_auth and
        # also bind database+config at MODULE level. Without eviction they
        # keep pointing at a pre-eviction database module whose DB_PATH is an
        # earlier test file's temp DB — 2FA/reset writes land in the wrong
        # database and tests read them back from their own fresh one.
        or mod_name == "user_security"
        or mod_name == "media_store"
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


def count_locations(device_id, seq=None):
    """Count location rows for a device (optionally filtered by ping_sequence)."""
    import sqlite3

    conn = sqlite3.connect(settings.DB_PATH)
    if seq is None:
        cur = conn.execute("SELECT COUNT(*) FROM locations WHERE device_id=?", (device_id,))
    else:
        cur = conn.execute(
            "SELECT COUNT(*) FROM locations WHERE device_id=? AND ping_sequence=?",
            (device_id, seq),
        )
    n = cur.fetchone()[0]
    conn.close()
    return n


# ─── Device Management Endpoints ───────────────────────────────────────────


class TestDeviceManagement:
    def setup_method(self):
        assert ensure_device()

    def test_update_device_alias(self):
        headers = get_dash_headers()
        resp = client.patch(
            "/api/dashboard/devices/e2e-test-device/alias",
            json={"alias": "My Phone"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["alias"] == "My Phone"

    def test_update_device_alias_empty_rejected(self):
        headers = get_dash_headers()
        resp = client.patch(
            "/api/dashboard/devices/e2e-test-device/alias",
            json={"alias": ""},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_mark_device_recovered(self):
        with db_module.get_db_context() as db:
            db.execute(
                "UPDATE devices SET is_stolen=1, operating_mode='stolen' WHERE id=?",
                ("e2e-test-device",),
            )
            db.commit()

        headers = get_dash_headers()
        resp = client.post("/api/dashboard/devices/e2e-test-device/recover", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        with db_module.get_db_context() as db:
            device = db.execute(
                "SELECT is_stolen, operating_mode FROM devices WHERE id=?",
                ("e2e-test-device",),
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

    def test_duplicate_ping_not_double_inserted(self):
        """At-most-once: re-POSTing the SAME ping (device + seq + device
        timestamp) must NOT insert a second row — OkHttp retryOnConnectionFailure
        re-sends identical bodies when a connection dies after the server
        processed the request (seen live: every ping inserted twice during a
        captive-portal reconnect). The device row's last_seen still refreshes."""
        device_id = "dup-ping-dev"
        assert ensure_device(device_id)
        dev_headers = get_device_headers(device_id)
        payload = {
            "device_id": device_id,
            "lat": 9.1000,
            "lng": 8.7000,
            "accuracy_horizontal": 15.0,
            "provider": "gps",
            "ping_sequence": 42,
            "device_timestamp": "2026-08-15T12:10:35.075Z",
        }

        for _ in range(2):
            resp = client.post("/api/device/location", json=payload, headers=dev_headers)
            assert resp.status_code == 200

        count = count_locations(device_id, seq=42)
        assert count == 1, f"Duplicate ping inserted {count} times — expected 1"

    def test_offline_queue_duplicate_not_double_inserted(self):
        """Same at-most-once guard on the batched offline-queue path."""
        device_id = "dup-queue-dev"
        assert ensure_device(device_id)
        dev_headers = get_device_headers(device_id)
        ping = {
            "device_id": device_id,
            "lat": 9.1000,
            "lng": 8.7000,
            "accuracy_horizontal": 15.0,
            "provider": "gps",
            "ping_sequence": 7,
            "device_timestamp": "2026-08-15T11:56:35.075Z",
        }

        for _ in range(2):
            resp = client.post(
                "/api/device/offline-queue",
                json={"pings": [ping]},
                headers=dev_headers,
            )
            assert resp.status_code == 200

        assert count_locations(device_id, seq=7) == 1


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


class TestGeofenceExitFlow:
    """End-to-end: the v1.5 persisted last_inside state makes a safe-zone EXIT
    fire BOTH the geofence_exit alert (real alert engine, real DB) and the
    per-zone auto-action command queue — exactly once."""

    DEVICE_ID = "geo-exit-dev"
    CENTER = (6.5244, 3.3792)
    OUTSIDE = (9.0579, 7.4951)  # ~600 km away — far beyond any test radius

    def setup_method(self):
        assert ensure_device(self.DEVICE_ID)
        self._seed_current_db_device()

    def _seed_current_db_device(self):
        """Seed the device row into the CURRENT database module's DB.

        send_all resolves `from database import get_db_context` at call time,
        so its alert-row INSERT (FK -> devices.id) lands in whichever database
        module is live in sys.modules — in the full suite that can be a
        DIFFERENT instance than the one the app's TestClient binds to (the
        documented test_e2e eviction hazard). Without this seed the INSERT
        fails its foreign key and the alert row never appears. Mirrors
        test_alert_settings.seed_device_row.
        """
        import database as db_module

        with db_module.get_db_context() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO devices "
                "(id, device_fingerprint, model, app_version, registered, last_seen) "
                "VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                (self.DEVICE_ID, "fingerprint-geo-exit", "Geo Exit Phone", "1.5.0"),
            )
            conn.commit()

    def _post_location(self, lat, lng):
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": self.DEVICE_ID,
                "lat": lat,
                "lng": lng,
                "accuracy_horizontal": 7.5,
                "provider": "gps",
            },
            headers=get_device_headers(self.DEVICE_ID),
        )
        assert resp.status_code == 200, resp.text

    def _alert_count(self, device_id: str) -> int:
        # send_all writes alert rows via the CURRENT module (documented
        # full-suite eviction hazard — see test_api.TestGeofenceAutoActions
        # _alerts helper), so query the call-time binding, not the module-
        # level db_module captured at import.
        import database as _current_db

        with _current_db.get_db_context() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM alerts WHERE device_id=? AND alert_type='geofence_exit'",
                (device_id,),
            ).fetchone()
        return row["n"]

    def test_exit_queues_capture_auto_action_and_alerts(self):
        dash = get_dash_headers()
        resp = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": self.DEVICE_ID,
                "name": "Home",
                "center_lat": self.CENTER[0],
                "center_lng": self.CENTER[1],
                "radius_meters": 500,
                "is_safe_zone": True,
                "auto_action": "capture",
            },
            headers=dash,
        )
        assert resp.status_code == 200

        # Entry first, then exit.
        self._post_location(*self.CENTER)
        self._post_location(*self.OUTSIDE)

        # Transition state persisted: the device is now OUTSIDE the zone.
        zones = client.get(f"/api/dashboard/geofences/{self.DEVICE_ID}", headers=dash).json()["geofences"]
        assert zones, "geofence must exist"
        assert zones[0]["last_inside"] == 0, zones[0]

        # The capture auto-action queued front-photo + audio evidence commands.
        cmds = client.get(f"/api/dashboard/commands/{self.DEVICE_ID}", headers=dash).json()["commands"]
        pending = [c["command"] for c in cmds if c["status"] == "pending"]
        assert "capture_photo_front" in pending, pending
        assert "capture_audio" in pending, pending

        # The geofence_exit alert was written through the real alert engine.
        assert self._alert_count(self.DEVICE_ID) >= 1

    def test_restricted_zone_exit_stays_silent(self):
        # v1.5 semantics: exits from RESTRICTED zones don't alert, and with no
        # auto_action nothing is queued.
        dash = get_dash_headers()
        before = self._alert_count(self.DEVICE_ID)

        resp = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": self.DEVICE_ID,
                "name": "Restricted",
                "center_lat": 6.1,
                "center_lng": 3.1,
                "radius_meters": 300,
                "is_safe_zone": False,
            },
            headers=dash,
        )
        assert resp.status_code == 200

        self._post_location(6.1, 3.1)
        self._post_location(8.0, 6.0)

        assert self._alert_count(self.DEVICE_ID) == before, "restricted exit must not alert"
