"""
Magneetar Per-Device Alert Settings Tests

Covers the per-device alert preferences wired in this release:
- PATCH /api/dashboard/devices/{id}/alert-settings accepts and validates
  channels, enabled types, and quiet hours (and returns them)
- send_all honors per-device channels (restricts which channels fire)
- send_all honors enabled_types (disabled types are suppressed) — except
  emergency types (theft, SIM change, factory reset) which ALWAYS deliver
- send_all honors quiet hours (non-emergency suppressed inside the window)
- defaults are restored when the device row has no preferences (None = all)
"""

import asyncio
import json
import os
import secrets
import tempfile

from fastapi.testclient import TestClient

# ── Test Environment Setup (mirrors test_offline_monitor.py) ────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

# NOTE: this file sorts BEFORE test_api.py / test_auth.py alphabetically, so it
# binds the shared config singleton first. Use the SAME MT_API_KEY / MT_JWT_SECRET
# values those modules use — a different key here would 401 every pre-e2e test
# that authenticates against config.settings.API_KEY. The DB path is still
# overridden per-module below.
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

import main  # noqa: E402
from alerts import ALWAYS_DELIVER_TYPES, AlertEngine  # noqa: E402
from auth import create_dashboard_tokens  # noqa: E402

client = TestClient(main.app)

TEST_API_KEY = config.settings.API_KEY
DEVICE_ID = "alerts-device-001"

ADMIN_HEADERS = {"x-api-key": TEST_API_KEY}


def _admin_token() -> str:
    """Mint an admin dashboard token (admin sees all devices)."""
    return create_dashboard_tokens(TEST_API_KEY)["token"]


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {_admin_token()}"}


def register_device() -> None:
    """Register the device via the API (used by the endpoint tests)."""
    resp = client.post(
        "/api/device/register",
        headers=ADMIN_HEADERS,
        json={
            "device_id": DEVICE_ID,
            "fingerprint": "fingerprint-alert-0001",
            "model": "Alert Settings Phone",
            "app_version": "1.1.0",
            "device_key": "alert-settings-device-key",
        },
    )
    assert resp.status_code == 200, resp.text


def seed_device_row() -> None:
    """Insert the device row DIRECTLY into the CURRENT database module's DB.

    send_all resolves `from database import get_db_context` at call time, so it
    reads/writes whichever `database` module is live in sys.modules. test_e2e
    evicts the server modules at collection, so by the time these tests RUN the
    live `database` module may be a DIFFERENT instance than the one the app's
    TestClient binds to — an app-based register_device() would seed the wrong
    DB and the alert INSERT would fail its foreign key. Writing the row through
    the same module send_all uses keeps the send_all tests consistent in any
    collection order (isolation or full suite).
    """
    import database as db_module

    with db_module.get_db_context() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO devices
               (id, device_fingerprint, model, app_version, registered, last_seen)
               VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (DEVICE_ID, "fingerprint-alert-0001", "Alert Settings Phone", "1.1.0"),
        )
        conn.commit()


def get_device_prefs() -> dict:
    """Read the devices-row prefs via the dashboard device list."""
    resp = client.get("/api/dashboard/devices", headers=_auth_headers())
    assert resp.status_code == 200, resp.text
    device = next(d for d in resp.json()["devices"] if d["id"] == DEVICE_ID)
    return device


def patch_prefs(body: dict) -> dict:
    resp = client.patch(f"/api/dashboard/devices/{DEVICE_ID}/alert-settings", headers=_auth_headers(), json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def set_prefs_row(
    channels: str | None = None,
    enabled_types: str | None = None,
    quiet_start: int | None = None,
    quiet_end: int | None = None,
) -> None:
    """Write prefs directly to the devices row (bypasses endpoint for send_all tests).

    Imports database fresh (codebase convention): test_e2e evicts the module
    from sys.modules mid-suite, so a module-level binding would write to a
    different DB than the running app.
    """
    import database as db_module

    with db_module.get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET alert_channels=?, enabled_types=?, quiet_hours_start=?, quiet_hours_end=? WHERE id=?",
            (channels, enabled_types, quiet_start, quiet_end, DEVICE_ID),
        )
        conn.commit()


# ─── Endpoint: validation & persistence ──────────────────────────────────────


def test_alert_settings_endpoint_stores_and_returns_prefs():
    register_device()
    result = patch_prefs(
        {
            "alert_phone": "+2348000000000",
            "alert_email": "owner@example.com",
            "alert_channels": ["whatsapp", "sms"],
            "enabled_types": ["theft_detected", "sim_changed", "device_offline"],
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
        }
    )
    assert result["alert_channels"] == ["whatsapp", "sms"]
    assert result["enabled_types"] == ["theft_detected", "sim_changed", "device_offline"]
    assert result["quiet_hours_start"] == 22
    assert result["quiet_hours_end"] == 7

    # The device list exposes the same values back to the dashboard
    prefs = get_device_prefs()
    assert prefs["alert_phone"] == "+2348000000000"
    assert prefs["alert_email"] == "owner@example.com"
    assert prefs["alert_channels"] == ["whatsapp", "sms"]
    assert prefs["enabled_types"] == ["theft_detected", "sim_changed", "device_offline"]
    assert prefs["quiet_hours_start"] == 22
    assert prefs["quiet_hours_end"] == 7


def test_alert_settings_endpoint_rejects_invalid_channels():
    register_device()
    resp = client.patch(
        f"/api/dashboard/devices/{DEVICE_ID}/alert-settings",
        headers=_auth_headers(),
        json={"alert_channels": ["carrier_pigeon"]},
    )
    assert resp.status_code == 400
    assert "Invalid channels" in resp.json()["detail"]


def test_alert_settings_endpoint_rejects_non_list_channels():
    register_device()
    resp = client.patch(
        f"/api/dashboard/devices/{DEVICE_ID}/alert-settings",
        headers=_auth_headers(),
        json={"alert_channels": "sms"},
    )
    assert resp.status_code == 400
    assert "must be a list" in resp.json()["detail"]


def test_alert_settings_rejects_bool_quiet_hour():
    """JSON true is an int subclass in Python — must NOT pass hour validation."""
    register_device()
    resp = client.patch(
        f"/api/dashboard/devices/{DEVICE_ID}/alert-settings",
        headers=_auth_headers(),
        json={"quiet_hours_start": True},
    )
    assert resp.status_code == 400
    assert "quiet_hours_start" in resp.json()["detail"]


def test_alert_settings_partial_quiet_hours_normalize_to_off():
    """A one-sided window is meaningless — both sides must clear to "off"."""
    register_device()
    result = patch_prefs({"quiet_hours_start": 22})
    assert result["quiet_hours_start"] is None
    assert result["quiet_hours_end"] is None


def test_alert_settings_endpoint_rejects_invalid_types_and_hours():
    register_device()
    resp = client.patch(
        f"/api/dashboard/devices/{DEVICE_ID}/alert-settings",
        headers=_auth_headers(),
        json={"enabled_types": ["theft_detected", "not_a_real_type"]},
    )
    assert resp.status_code == 400
    assert "Invalid alert types" in resp.json()["detail"]

    resp = client.patch(
        f"/api/dashboard/devices/{DEVICE_ID}/alert-settings",
        headers=_auth_headers(),
        json={"quiet_hours_start": 25},
    )
    assert resp.status_code == 400
    assert "quiet_hours_start" in resp.json()["detail"]


def test_alert_settings_clearing_restores_defaults():
    register_device()
    patch_prefs(
        {
            "alert_channels": ["sms"],
            "enabled_types": ["device_offline"],
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
        }
    )
    patch_prefs({"alert_channels": [], "enabled_types": [], "quiet_hours_start": None, "quiet_hours_end": None})
    prefs = get_device_prefs()
    assert prefs["alert_channels"] is None
    assert prefs["enabled_types"] is None
    assert prefs["quiet_hours_start"] is None
    assert prefs["quiet_hours_end"] is None


# ─── send_all: per-device gating ─────────────────────────────────────────────


def test_send_all_respects_per_device_channels():
    seed_device_row()
    set_prefs_row(channels=json.dumps(["sms"]))

    engine = AlertEngine()
    with unittest_patch_retry(engine, channels_attempted=[]) as attempted:
        asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "battery_low",
                {"battery": "10", "location": "0,0", "time": "now"},
            )
        )
    assert attempted == ["sms"], f"Only the configured channel should fire, got {attempted}"


def test_send_all_suppresses_disabled_non_emergency_type():
    seed_device_row()
    set_prefs_row(enabled_types=json.dumps(["theft_detected", "sim_changed", "device_offline"]))

    engine = AlertEngine()
    with unittest_patch_retry(engine, channels_attempted=[]) as attempted:
        results = asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "battery_low",  # NOT in enabled_types
                {"battery": "10", "location": "0,0", "time": "now"},
            )
        )
    assert attempted == [], "Disabled type must not fire any channel"
    assert all(v is False for v in results.values())


def test_send_all_emergency_type_always_delivers_even_if_disabled():
    seed_device_row()
    # Emergency type NOT listed, quiet hours in effect — must still deliver.
    set_prefs_row(enabled_types=json.dumps(["sim_changed"]), quiet_start=22, quiet_end=7)

    engine = AlertEngine()
    with unittest_patch_retry(engine, channels_attempted=[]) as attempted:
        asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "theft_detected",
                {"location": "0,0", "time": "now", "score": "95"},
            )
        )
    assert "theft_detected" in ALWAYS_DELIVER_TYPES
    assert len(attempted) > 0, "Emergency alerts must bypass enabled-types AND quiet-hours gates"


def test_send_all_suppresses_non_emergency_during_quiet_hours():
    seed_device_row()
    set_prefs_row(quiet_start=22, quiet_end=7)

    # Import FRESH inside the test (codebase convention): test_e2e evicts the
    # alerts module from sys.modules during collection, so a module-level
    # AlertEngine + patch("alerts.datetime") would target different instances.
    from alerts import AlertEngine as FreshEngine

    engine = FreshEngine()
    # Force "now" into the quiet window (23:00) regardless of wall clock.
    with unittest_patch_retry(engine, channels_attempted=[]) as attempted, patch_quiet_hour(engine, 23):
        results = asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "device_offline",
                {"location": "0,0", "time": "now"},
            )
        )
    assert attempted == [], "Non-emergency alert inside quiet hours must be suppressed"
    assert all(v is False for v in results.values())


def test_send_all_suppresses_within_non_wrapping_quiet_window():
    """Quiet hours 01:00-06:00 (start < end): hour 03 is inside, hour 08 is not."""
    seed_device_row()
    set_prefs_row(quiet_start=1, quiet_end=6)

    from alerts import AlertEngine as FreshEngine

    engine = FreshEngine()
    with unittest_patch_retry(engine, channels_attempted=[]) as attempted, patch_quiet_hour(engine, 3):
        results = asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "device_offline",
                {"location": "0,0", "time": "now"},
            )
        )
    assert attempted == [], "Hour 03 inside 01:00-06:00 must be suppressed"
    assert all(v is False for v in results.values())

    with unittest_patch_retry(engine, channels_attempted=[]) as attempted, patch_quiet_hour(engine, 8):
        results = asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "device_offline",
                {"location": "0,0", "time": "now"},
            )
        )
    assert attempted, "Hour 08 outside the quiet window must deliver"


def test_send_all_suppressed_alerts_still_write_dedup_row():
    """Suppressed alerts must persist a delivered=0 row so the offline monitor's
    alerts-table dedup records the incident (no per-sweep re-alert spam)."""
    seed_device_row()
    set_prefs_row(enabled_types=json.dumps(["theft_detected", "sim_changed"]))

    import database as db_module

    engine = AlertEngine()
    with unittest_patch_retry(engine, channels_attempted=[]):
        asyncio.run(
            engine.send_all(
                DEVICE_ID,
                "device_offline",  # disabled per-device
                {"location": "0,0", "time": "now"},
            )
        )

    with db_module.get_db_context() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM alerts WHERE device_id=? AND alert_type=? AND delivered=0",
            (DEVICE_ID, "device_offline"),
        ).fetchone()
    assert row["cnt"] > 0, "Suppressed alerts must leave a delivered=0 dedup row"


# ─── Test helpers (no pytest-asyncio dependency) ─────────────────────────────


def unittest_patch_retry(engine: AlertEngine, channels_attempted: list):
    """Swap _send_with_retry for a recorder so no real channel fires.

    The context manager yields `channels_attempted` (channels in the order
    they were attempted) — NOT the mock, which would shadow the list.
    """
    from unittest.mock import AsyncMock, patch

    async def fake_send(channel: str, send_fn, *args, **kwargs) -> bool:
        channels_attempted.append(channel)
        return True

    class _RecorderPatch:
        def __init__(self):
            self._patcher = patch.object(engine, "_send_with_retry", new=AsyncMock(side_effect=fake_send))

        def __enter__(self):
            self._patcher.__enter__()
            return channels_attempted

        def __exit__(self, exc_type, exc, tb):
            self._patcher.__exit__(exc_type, exc, tb)

    return _RecorderPatch()


def patch_quiet_hour(engine: AlertEngine, hour: int):
    """Force datetime.now().hour to `hour` inside the quiet-hours check."""
    from unittest.mock import patch

    class _FakeDateTime:
        @classmethod
        def now(cls):
            class _Inner:
                pass

            _Inner.hour = hour
            return _Inner()

    return patch("alerts.datetime", _FakeDateTime)
