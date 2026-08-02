"""
Magneetar Heartbeat / Theft-Activation Regression Tests

Covers two production bugs found live (device "online" but dashboard frozen
at a stale "last seen"):

1. post_heartbeat called sentinel.auto_activate_theft_mode() BEFORE committing
   the request's own writes. auto_activate_theft_mode opens its own sqlite
   connection, whose write blocked on the outer connection's uncommitted
   transaction -> "database is locked" after busy_timeout -> 500 -> the
   heartbeat's last_seen update was rolled back, freezing the dashboard's
   "last seen" timestamp.

2. auto_activate_theft_mode accepted ANY score even though its docstring
   promises "score >= threshold", so a bare heartbeat with
   device_admin_active=False could flip a device to stolen at score 40 —
   far below the 80-point THEFT_SCORE_THRESHOLD.
"""

import os
import secrets
import tempfile

from fastapi.testclient import TestClient

# ── Test Environment Setup (mirrors test_multi_user.py) ─────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "heartbeat-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "heartbeat-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from main import app  # noqa: E402
from sentinel import sentinel  # noqa: E402

client = TestClient(app)

# Use the LIVE settings value (shared singleton across the suite) rather than
# the env var — same pitfall test_multi_user.py documents.
TEST_API_KEY = config.settings.API_KEY
TEST_DEVICE_ID = "hb-device-001"


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device() -> dict:
    """Register the test device and return its token pair."""
    resp = client.post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": TEST_DEVICE_ID,
            "fingerprint": "fingerprint-0000",
            "model": "Test Phone",
            "os_version": "Android 14",
            "app_version": "1.0.0",
            "device_key": "test-device-key-heartbeat",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def device_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_device_row() -> dict:
    with database.get_db_context() as conn:
        return dict(conn.execute("SELECT * FROM devices WHERE id=?", (TEST_DEVICE_ID,)).fetchone())


def test_heartbeat_admin_inactive_does_not_activate_theft_and_updates_last_seen():
    """Regression #1+#2: a heartbeat with device_admin_active=False must return
    200, advance last_seen, and NOT flip the device to stolen (score 40 is
    below the 80 threshold)."""
    token = register_device()["token"]

    resp = client.post(
        "/api/device/heartbeat",
        headers=device_headers(token),
        json={
            "device_id": TEST_DEVICE_ID,
            "battery_percent": 88,
            "is_charging": False,
            "network_type": "wifi",
            "device_admin_active": False,
            "app_version": "1.0.0",
        },
    )
    # 200 (not 500 — the old code deadlocked on its nested write)
    assert resp.status_code == 200, resp.text

    row = get_device_row()
    assert row["operating_mode"] == "normal"
    assert row["is_stolen"] == 0
    # last_seen would be rolled back (None here) if the handler had 500'd
    assert row["last_seen"] is not None
    # The admin-disabled signal is still surfaced via an elevated score
    assert row["sentinel_score"] >= 40

    # No evidence case or capture commands — activation must not have happened
    with database.get_db_context() as conn:
        cases = conn.execute("SELECT COUNT(*) FROM evidence_cases WHERE device_id=?", (TEST_DEVICE_ID,)).fetchone()[0]
        cmds = conn.execute("SELECT COUNT(*) FROM commands WHERE device_id=?", (TEST_DEVICE_ID,)).fetchone()[0]
    assert cases == 0
    assert cmds == 0


def test_heartbeat_returns_200_when_admin_active():
    """Sanity: the normal heartbeat path still works and keeps last_seen fresh."""
    token = register_device()["token"]

    resp = client.post(
        "/api/device/heartbeat",
        headers=device_headers(token),
        json={
            "device_id": TEST_DEVICE_ID,
            "battery_percent": 90,
            "is_charging": True,
            "device_admin_active": True,
            "app_version": "1.0.0",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["operating_mode"] == "normal"


def test_auto_activate_theft_mode_requires_threshold_score():
    """Regression #2: sub-threshold scores are no-ops; threshold scores activate."""
    register_device()

    # Score 40 (what the heartbeat path used to pass) must NOT activate
    sentinel.auto_activate_theft_mode(TEST_DEVICE_ID, 40)
    row = get_device_row()
    assert row["operating_mode"] == "normal"
    assert row["is_stolen"] == 0

    # At the real threshold, activation happens: stolen mode + evidence + commands
    sentinel.auto_activate_theft_mode(TEST_DEVICE_ID, config.settings.THEFT_SCORE_THRESHOLD)
    row = get_device_row()
    assert row["operating_mode"] == "stolen"
    assert row["is_stolen"] == 1

    with database.get_db_context() as conn:
        cases = conn.execute("SELECT COUNT(*) FROM evidence_cases WHERE device_id=?", (TEST_DEVICE_ID,)).fetchone()[0]
        cmds = conn.execute(
            "SELECT COUNT(*) FROM commands WHERE device_id=? AND status='pending'", (TEST_DEVICE_ID,)
        ).fetchone()[0]
    assert cases == 1
    assert cmds >= 3
