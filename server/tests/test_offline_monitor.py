"""
Magneetar Offline Monitor Tests

Covers the offline-detection sweep added for production alerting:
- devices silent longer than the threshold are flagged (owned, non-stolen)
- already-alerted incidents are never re-alerted (dedup via the alerts table)
- stolen devices and unowned (orphan) devices are skipped
- a full sweep alerts exactly once per incident
"""

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient

# ── Test Environment Setup (mirrors test_multi_user.py) ─────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64  # fixed: cross-generation decryption (see conftest.py)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

# ROBUSTNESS NOTE — lazy resolution (see test_sim_change.py docstring):
# test_e2e / test_sim_change evict config/database/main/offline_monitor from
# sys.modules at IMPORT time and re-import them with THEIR env, so module-level
# bindings made before that eviction go stale (a dead database module pointing
# at this file's temp DB while app modules resolve the CURRENT module at call
# time). Every helper here therefore resolves modules lazily inside the
# function so writes and reads hit the SAME (current) database.


def _current_client():
    """TestClient bound to the CURRENT main.app (post-eviction module)."""
    import main  # noqa: F401

    return TestClient(main.app)


def _current_database():
    import database  # noqa: F401

    return database


def _current_api_key() -> str:
    import config  # noqa: F401

    return config.settings.API_KEY


def _find_offline_devices(*args, **kwargs):
    from offline_monitor import find_offline_devices as fn

    return fn(*args, **kwargs)


def _run_offline_sweep():
    from offline_monitor import run_offline_sweep as fn

    return fn()


# Each test owns a DISTINCT device id so no test depends on another's state
# (e.g. test 3 leaves an alert row that would change dedup for other tests).
DEVICE_STALE = "off-device-001"
DEVICE_RECENT = "off-device-002"
DEVICE_ALERTED = "off-device-003"
DEVICE_STOLEN = "off-device-004"
DEVICE_UNOWNED = "off-device-005"
DEVICE_SWEEP = "off-device-006"
DEVICE_SWEEP_REPORT = "off-device-007"


def api_key_headers() -> dict:
    return {"x-api-key": _current_api_key()}


def register_device(device_id: str) -> None:
    resp = _current_client().post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": device_id,
            "fingerprint": "fingerprint-0000",
            "model": "Offline Test Phone",
            "app_version": "1.0.0",
            "device_key": f"test-device-key-{device_id}",
        },
    )
    assert resp.status_code == 200, resp.text


def set_last_seen(device_id: str, hours_ago: int) -> None:
    """Force last_seen to a point `hours_ago` in the past (ISO-8601, like the
    live DB accumulates)."""
    with _current_database().get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET last_seen = datetime('now', ?) WHERE id=?",
            (f"-{hours_ago} hours", device_id),
        )
        conn.commit()


def link_owner(device_id: str, owner: str = "usr-offline-owner") -> None:
    with _current_database().get_db_context() as conn:
        conn.execute("UPDATE devices SET owner_id=? WHERE id=?", (owner, device_id))
        conn.commit()


def mark_stolen(device_id: str) -> None:
    with _current_database().get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET is_stolen=1, operating_mode='stolen' WHERE id=?",
            (device_id,),
        )
        conn.commit()


ALL_TEST_DEVICES = [
    DEVICE_STALE,
    DEVICE_RECENT,
    DEVICE_ALERTED,
    DEVICE_STOLEN,
    DEVICE_UNOWNED,
    DEVICE_SWEEP,
    DEVICE_SWEEP_REPORT,
]


def cleanup_test_devices() -> None:
    """Delete every test device (with cascade) so sweep tests only ever see the
    device they seeded — a sweep alerts ALL stale owned devices, not just one."""
    db = _current_database()
    from database import delete_device_cascade

    with db.get_db_context() as conn:
        for device_id in ALL_TEST_DEVICES:
            if conn.execute("SELECT 1 FROM devices WHERE id=?", (device_id,)).fetchone():
                delete_device_cascade(conn, device_id)
        conn.commit()


def insert_offline_alert(device_id: str) -> None:
    """Simulate an offline alert already sent for this incident."""
    with _current_database().get_db_context() as conn:
        conn.execute(
            "INSERT INTO alerts (device_id, alert_type, channel, recipient, message, delivered) "
            "VALUES (?, 'device_offline', 'sms', '+2348000000000', 'already alerted', 0)",
            (device_id,),
        )
        conn.commit()


def test_find_offline_devices_returns_stale_owned_devices():
    register_device(DEVICE_STALE)
    link_owner(DEVICE_STALE)
    set_last_seen(DEVICE_STALE, hours_ago=2)

    found = _find_offline_devices(minutes=30)
    ids = [d["id"] for d in found]
    assert DEVICE_STALE in ids
    row = next(d for d in found if d["id"] == DEVICE_STALE)
    assert row["last_seen"] is not None


def test_find_offline_devices_skips_recent_devices():
    register_device(DEVICE_RECENT)
    link_owner(DEVICE_RECENT)
    set_last_seen(DEVICE_RECENT, hours_ago=0)  # just now

    found = _find_offline_devices(minutes=30)
    assert all(d["id"] != DEVICE_RECENT for d in found)


def test_find_offline_devices_skips_already_alerted():
    register_device(DEVICE_ALERTED)
    link_owner(DEVICE_ALERTED)
    set_last_seen(DEVICE_ALERTED, hours_ago=2)
    insert_offline_alert(DEVICE_ALERTED)  # alert sent AFTER last_seen

    found = _find_offline_devices(minutes=30)
    assert all(d["id"] != DEVICE_ALERTED for d in found)


def test_find_offline_devices_skips_stolen_and_unowned():
    register_device(DEVICE_STOLEN)
    link_owner(DEVICE_STOLEN)
    mark_stolen(DEVICE_STOLEN)
    set_last_seen(DEVICE_STOLEN, hours_ago=2)

    register_device(DEVICE_UNOWNED)  # no owner_id
    set_last_seen(DEVICE_UNOWNED, hours_ago=2)

    found = _find_offline_devices(minutes=30)
    ids = [d["id"] for d in found]
    assert DEVICE_STOLEN not in ids
    assert DEVICE_UNOWNED not in ids


def test_offline_sweep_alerts_once_per_incident():
    cleanup_test_devices()
    register_device(DEVICE_SWEEP)
    link_owner(DEVICE_SWEEP)
    set_last_seen(DEVICE_SWEEP, hours_ago=2)

    # First sweep alerts the device (one incident → one alert)
    first = asyncio.run(_run_offline_sweep())
    assert first == 1

    with _current_database().get_db_context() as conn:
        alerts = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE device_id=? AND alert_type='device_offline'",
            (DEVICE_SWEEP,),
        ).fetchone()[0]
    assert alerts >= 1

    # Second sweep: deduped — no re-alert while the device stays offline
    second = asyncio.run(_run_offline_sweep())
    assert second == 0


def test_offline_report_clears_incident_for_future_alerts():
    """A device that reports again (heartbeat/location) advances last_seen past
    the old alert, ending the incident. It is no longer flagged as offline.
    (A later offline spell — not reachable in-test without time travel — would
    then alert again, because the dedup rule only blocks alerts that are NEWER
    than last_seen.)"""
    cleanup_test_devices()
    register_device(DEVICE_SWEEP_REPORT)
    link_owner(DEVICE_SWEEP_REPORT)
    set_last_seen(DEVICE_SWEEP_REPORT, hours_ago=2)
    assert asyncio.run(_run_offline_sweep()) == 1

    # Device reports: last_seen advances past the alert's sent_at → not offline
    with _current_database().get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET last_seen = datetime('now', '+1 minute') WHERE id=?",
            (DEVICE_SWEEP_REPORT,),
        )
        conn.commit()
    assert asyncio.run(_run_offline_sweep()) == 0

    # The dedup guard no longer matches: the alert is now OLDER than last_seen
    with _current_database().get_db_context() as conn:
        row = conn.execute(
            "SELECT 1 FROM alerts a JOIN devices d ON d.id = a.device_id "
            "WHERE a.device_id=? AND a.alert_type='device_offline' "
            "AND datetime(a.sent_at) > datetime(d.last_seen)",
            (DEVICE_SWEEP_REPORT,),
        ).fetchone()
    assert row is None
