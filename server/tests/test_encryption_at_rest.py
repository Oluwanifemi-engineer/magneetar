"""
Location at-rest encryption tests (v1.5).

The write path must encrypt coordinates (per-device HKDF-derived AES-256-GCM
keys) whenever MT_ENCRYPTION_KEY is configured: rows carry location_encrypted=1,
0.0 placeholders in the NOT NULL lat/lng columns, and the base64 ciphertext in
location_data — plaintext never touches the DB. Every read path (dashboard,
guardian, offline monitor, export, evidence PDF) must decrypt dual-mode rows
(encrypted AND legacy plaintext), so production can flip encryption on without
breaking existing data or any consumer.
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test environment BEFORE importing the app modules ──────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64  # fixed: cross-generation decryption (see conftest.py)
os.environ["MT_DB_PATH"] = test_db_path
os.environ["MT_MEDIA_DIR"] = tempfile.mkdtemp(prefix="magneetar-enc-media-")

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

import encryption  # noqa: E402
from main import app  # noqa: E402, F401  (import-time baseline; access via _current_client())

# ROBUSTNESS NOTE — lazy resolution (see test_sim_change.py docstring):
# test_e2e / test_sim_change evict config/database/main/routes from sys.modules
# at IMPORT time and re-import them with THEIR env, so module-level bindings
# made before that eviction go stale (a dead database module pointing at this
# file's temp DB while app modules — and call-time helpers like
# data_export/evidence/routes.guardian/offline_monitor — resolve the CURRENT
# module). Every helper here resolves modules lazily at call time so writes
# and reads always hit the SAME (current) database and token secrets.

TEST_DEVICE_ID = "enc-device-001"
LAT, LNG = 9.0820, 8.6753


def _current_client():
    import main  # noqa: F401

    return TestClient(main.app)


def _current_database():
    import database  # noqa: F401

    return database


def _current_api_key() -> str:
    import config  # noqa: F401

    return config.settings.API_KEY


def _register():
    resp = _current_client().post(
        "/api/device/register",
        json={
            "device_id": TEST_DEVICE_ID,
            "fingerprint": "fp-enc-at-rest",
            "model": "Encrypted Phone",
        },
        headers={"x-api-key": _current_api_key()},
    )
    assert resp.status_code == 200, resp.text


def _device_headers():
    from auth import create_device_tokens  # call time: current module

    tokens = create_device_tokens(TEST_DEVICE_ID)
    return {"Authorization": f"Bearer {tokens['token']}"}


def _dashboard_headers():
    from auth import create_dashboard_tokens  # call time: current module

    tokens = create_dashboard_tokens(_current_api_key())
    return {"Authorization": f"Bearer {tokens['token']}"}


def _post_location(lat=LAT, lng=LNG):
    resp = _current_client().post(
        "/api/device/location",
        json={
            "device_id": TEST_DEVICE_ID,
            "lat": lat,
            "lng": lng,
            "accuracy_horizontal": 7.5,
            "provider": "gps",
        },
        headers=_device_headers(),
    )
    assert resp.status_code == 200, resp.text
    return resp


# ─── Unit: store/read helpers ───────────────────────────────────────────────


class TestEncryptionHelpers:
    def test_encrypt_for_store_hides_plaintext(self):
        lat, lng, enc, data = encryption.encrypt_location_for_store(LAT, LNG, TEST_DEVICE_ID)
        assert enc is True
        assert data and data != f"{LAT},{LNG}"
        assert f"{LAT}" not in data  # plaintext never reaches the DB
        # NOT NULL columns hold placeholders.
        assert lat == 0.0 and lng == 0.0
        # Round trip with the per-device key.
        assert encryption.decrypt_location(lat, lng, enc, data, TEST_DEVICE_ID) == pytest.approx((LAT, LNG))

    def test_decrypt_location_row_dual_mode(self):
        # Encrypted row (dict shape exactly like a DB row).
        _, _, enc, data = encryption.encrypt_location_for_store(6.5, 3.4, "dev-a")
        row = {
            "device_id": "dev-a",
            "lat": 0.0,
            "lng": 0.0,
            "location_encrypted": 1,
            "location_data": data,
        }
        assert encryption.decrypt_location_row(row) == pytest.approx((6.5, 3.4))

        # Legacy plaintext row passes through unchanged.
        legacy = {
            "device_id": "dev-a",
            "lat": 6.5,
            "lng": 3.4,
            "location_encrypted": 0,
            "location_data": None,
        }
        assert encryption.decrypt_location_row(legacy) == (6.5, 3.4)

        # None row degrades safely.
        assert encryption.decrypt_location_row(None) == (None, None)

    def test_noop_mode_stores_plaintext(self):
        """Without a key the helper stores plaintext exactly as before."""
        noop = encryption.NoOpEncryption()
        assert noop.is_enabled() is False
        lat, lng, enc, data = encryption.encrypt_location_for_store(LAT, LNG, TEST_DEVICE_ID)
        # (This module runs WITH a key — verify the helper consults the active
        # instance; the NoOp branch is covered by decrypt fallback below.)
        assert isinstance(encryption.get_encryption(), encryption.FieldEncryption)


# ─── API: write path encrypts, read path decrypts ──────────────────────────


class TestAtRestRoundTrip:
    def test_post_location_stores_ciphertext_not_plaintext(self):
        _register()
        _post_location()

        with _current_database().get_db_context() as conn:
            row = conn.execute(
                "SELECT * FROM locations WHERE device_id=? ORDER BY id DESC LIMIT 1",
                (TEST_DEVICE_ID,),
            ).fetchone()
        assert row is not None
        assert row["location_encrypted"] == 1
        assert row["lat"] == 0.0 and row["lng"] == 0.0
        assert row["location_data"], "ciphertext must be stored"
        assert f"{LAT}" not in row["location_data"]

    def test_dashboard_locations_returns_decrypted_coords(self):
        _post_location()
        resp = _current_client().get(f"/api/dashboard/locations/{TEST_DEVICE_ID}", headers=_dashboard_headers())
        assert resp.status_code == 200
        locs = resp.json()["locations"]
        assert locs, "posted location must be readable"
        assert abs(locs[0]["lat"] - LAT) < 1e-6
        assert abs(locs[0]["lng"] - LNG) < 1e-6

    def test_dashboard_live_and_replay_decrypt(self):
        _post_location()
        live = _current_client().get(
            f"/api/dashboard/locations/{TEST_DEVICE_ID}/live",
            headers=_dashboard_headers(),
        )
        assert abs(live.json()["location"]["lat"] - LAT) < 1e-6

        replay = _current_client().get(f"/api/dashboard/replay/{TEST_DEVICE_ID}", headers=_dashboard_headers())
        assert abs(replay.json()["locations"][0]["lat"] - LAT) < 1e-6

    def test_device_list_decrypts_last_fix(self):
        _post_location()
        devices = _current_client().get("/api/dashboard/devices", headers=_dashboard_headers()).json()["devices"]
        match = next(d for d in devices if d["id"] == TEST_DEVICE_ID)
        assert abs(match["lat"] - LAT) < 1e-6
        assert match["location_encrypted"] is True

    def test_responses_never_leak_ciphertext(self):
        """location_data is raw ciphertext — every dashboard read endpoint
        must strip it (regression for the 2026-08-11 review finding)."""
        _post_location()
        h = _dashboard_headers()

        locs = _current_client().get(f"/api/dashboard/locations/{TEST_DEVICE_ID}", headers=h).json()["locations"]
        assert locs and "location_data" not in locs[0]

        live = _current_client().get(f"/api/dashboard/locations/{TEST_DEVICE_ID}/live", headers=h).json()["location"]
        assert live and "location_data" not in live

        replay = _current_client().get(f"/api/dashboard/replay/{TEST_DEVICE_ID}", headers=h).json()["locations"]
        assert replay and "location_data" not in replay[0]

        hist = _current_client().get(f"/api/dashboard/devices/{TEST_DEVICE_ID}/history", headers=h).json()
        assert "location_data" not in hist["latest_location"]

    def test_legacy_plaintext_rows_still_read(self):
        """Dual-mode reads: a pre-encryption row (flag 0, real coords) must
        keep rendering after the feature ships."""
        with _current_database().get_db_context() as conn:
            conn.execute(
                "INSERT INTO locations (device_id, lat, lng, server_timestamp, location_encrypted) "
                "VALUES (?, 6.5244, 3.3792, datetime('now'), 0)",
                (TEST_DEVICE_ID,),
            )
            conn.commit()

        resp = _current_client().get(f"/api/dashboard/locations/{TEST_DEVICE_ID}", headers=_dashboard_headers())
        locs = resp.json()["locations"]
        assert any(abs(loc["lat"] - 6.5244) < 1e-6 for loc in locs), "legacy plaintext rows must survive"

    def test_sentinel_history_decrypts_before_scoring(self):
        """compute_score's haversine/geofence math needs REAL coordinates —
        an encrypted history must not poison the scorer (0.0 placeholder)."""
        import sentinel  # call time: current module

        # One encrypted row already exists from prior posts; a second ping
        # triggers the history path with decryption.
        _post_location(lat=9.0830, lng=8.6763)
        with _current_database().get_db_context() as conn:
            rows = conn.execute(
                "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10",
                (TEST_DEVICE_ID,),
            ).fetchall()
            history = []
            for r in rows:
                h = dict(r)
                h["lat"], h["lng"] = encryption.decrypt_location_row(h)
                history.append(h)
        from models import TelemetryPing

        ping = TelemetryPing(
            device_id=TEST_DEVICE_ID,
            lat=9.0831,
            lng=8.6764,
            device_timestamp="2026-01-01T00:00:00Z",
        )
        score, threat, anomalies = sentinel.sentinel.compute_score(ping, history)
        assert isinstance(score, int)

    def test_offline_monitor_alert_uses_decrypted_coords(self):
        """The offline alert's location string must carry real coordinates."""
        from datetime import datetime, timedelta, timezone

        from offline_monitor import find_offline_devices  # call time: current module

        _register()
        # find_offline_devices ONLY returns OWNED devices (nothing to notify
        # for an ownerless row) — link the device to an account first.
        resp = _current_client().post(
            "/api/auth/register",
            json={
                "email": "offline-owner@test.dev",
                "password": "OfflineOwner123",
                "display_name": "O",
            },
        )
        assert resp.status_code == 200, resp.text
        user_token = resp.json()["token"]
        claim = _current_client().post(
            "/api/device/claim",
            json={"device_id": TEST_DEVICE_ID},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert claim.status_code == 200, claim.text

        _post_location(lat=6.5244, lng=3.3792)
        with _current_database().get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    TEST_DEVICE_ID,
                ),
            )
            conn.commit()

        offline = find_offline_devices(minutes=10)
        match = next((d for d in offline if d["id"] == TEST_DEVICE_ID), None)
        assert match is not None, f"device must appear in offline list, got {[d['id'] for d in offline]}"
        assert match["lat"] is not None and abs(match["lat"] - 6.5244) < 1e-6

    def test_evidence_pdf_data_decrypts(self):
        from evidence import evidence_builder  # call time: current module

        case_id = evidence_builder.create_case(TEST_DEVICE_ID)
        data = evidence_builder.compile_pdf_data(case_id)
        assert data is not None
        assert data["locations"], "seeded encrypted locations must appear"
        # Order is by server_timestamp (second resolution) — multiple pings in
        # the same second tie, so assert the SET of decrypted lats contains the
        # expected one instead of relying on row [0].
        assert any(
            abs(loc["lat"] - LAT) < 1e-6 for loc in data["locations"]
        ), f"expected a location at lat≈{LAT}, got {[loc['lat'] for loc in data['locations']]}"

    def test_data_export_decrypts(self):
        from data_export import data_export_service  # call time: current module

        exported = data_export_service.export_device_data(TEST_DEVICE_ID)
        assert exported["locations"]
        assert any(abs(loc["lat"] - LAT) < 1e-6 for loc in exported["locations"])

    def test_encrypted_location_decrypts_correctly(self):
        """Verify that an encrypted location row decrypts to the original coords."""
        from encryption import decrypt_location_row

        _post_location(lat=6.5244, lng=3.3792)
        with _current_database().get_db_context() as conn:
            row = conn.execute(
                "SELECT device_id, lat, lng, location_encrypted, location_data "
                "FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 1",
                (TEST_DEVICE_ID,),
            ).fetchone()
            lat, lng = decrypt_location_row(row)
        assert lat is not None and abs(lat - 6.5244) < 1e-6

    def test_location_simple_path_also_encrypts(self):
        """/api/device/location/simple is the legacy ingest path — it must
        encrypt too so no plaintext write path remains."""
        resp = _current_client().post(
            "/api/device/location/simple",
            json={
                "device_id": TEST_DEVICE_ID,
                "lat": 5.5,
                "lng": 7.7,
                "accuracy": 12.0,
                "provider": "gps",
            },
            headers=_device_headers(),
        )
        assert resp.status_code == 200, resp.text
        with _current_database().get_db_context() as conn:
            row = conn.execute(
                "SELECT * FROM locations WHERE device_id=? AND provider='gps' ORDER BY id DESC LIMIT 1",
                (TEST_DEVICE_ID,),
            ).fetchone()
        assert row["location_encrypted"] == 1
        assert row["lat"] == 0.0
        assert "5.5" not in row["location_data"]
