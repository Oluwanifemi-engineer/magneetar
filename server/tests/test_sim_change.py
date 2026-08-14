"""
Magneetar SIM-Change Detection Tests

The Android app detects a SIM swap permission-free (ACTION_SIM_STATE_CHANGED +
TelephonyManager.getSimOperator()/getSimOperatorName() — no READ_PHONE_STATE,
so it works identically on the Play and sideload flavors) and reports it
exactly once on the telemetry or heartbeat path. The server must:

  1. fire the always-deliver `sim_changed` alert IMMEDIATELY — not only when
     the theft score accumulates to the confirmation threshold (sim_changed
     alone scores 35/80, so without the direct alert an owner would never be
     told about a SIM swap);
  2. dedupe repeated/queued replays so one incident = one alert;
  3. keep scoring the signal through Sentinel (existing behavior);
  4. not alert on normal pings (sim_changed=false).

ROBUSTNESS NOTE — lazy imports: several test files (test_e2e and this one)
set env vars + evict config/database/main from sys.modules at IMPORT time.
Module-level bindings made before a later file's eviction go stale (a dead
database module instance), and the alert engine's `_log_alert` deliberately
does `from database import get_db_context` AT CALL TIME so it follows the
CURRENT module. Every helper here therefore resolves app/auth/database
lazily inside the function — the exact convention documented in
server/alerts.py / test_e2e.py — so this suite passes regardless of whether
it is collected before or after test_e2e in the same pytest process.
"""

import os
import secrets
import sys
import tempfile

# Set test environment BEFORE any imports
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "sim-test-key-" + "z" * 32
os.environ["MT_JWT_SECRET"] = "sim-test-jwt-" + "y" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Clear cached modules so they re-import with new env vars (same list as
# test_e2e.py — anything binding config/database at module level).
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

# Imported ONLY to establish the isolation baseline (init the temp DB). All
# per-test access goes through the lazy helpers below.
import database  # noqa: E402  (env set above)

database.init_db(test_db_path)


# ─── Lazy helpers (see module docstring — robust to test_e2e eviction) ───────


def _current_api_key() -> str:
    """The API key the CURRENT config was built with.

    Reading os.environ at call time is NOT safe: some test files (e.g.
    test_sentinel.py) overwrite env vars at import WITHOUT evicting modules,
    so the live env can diverge from the key baked into the imported app's
    config. Resolving the current config module keeps register/validate
    consistent regardless of collection order.
    """
    import config  # noqa: F401

    return config.settings.API_KEY


def _client():
    """A TestClient bound to the CURRENT main app (re-import resolves the
    post-eviction module, keeping registrations + alert logging in one DB)."""
    import main  # noqa: F401
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def get_device_headers(device_id: str):
    import auth  # noqa: F401

    tokens = auth.create_device_tokens(device_id)
    return {"Authorization": f"Bearer {tokens['token']}"}


def ensure_device(device_id: str) -> bool:
    resp = _client().post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": "sim-fingerprint",
            "model": "SIM Test",
            "os_version": "Android 14",
            "app_version": "1.4.1",
        },
        headers={"x-api-key": _current_api_key()},
    )
    return resp.status_code == 200


def count_alerts(device_id: str, alert_type: str = "sim_changed") -> int:
    """Incident count = rows for one canonical channel.

    alert_engine.send_all logs one row PER channel (email/sms/whatsapp/push),
    so a single incident produces 4 rows. Counting one canonical channel
    (sms — always in the default channel set in tests) counts INCIDENTS,
    which is what the dedup guarantees: one incident = one row here.
    """
    from database import get_db_context  # lazy: follows the current module

    with get_db_context() as conn:
        return conn.execute(
            "SELECT COUNT(*) AS cnt FROM alerts " "WHERE device_id=? AND alert_type=? AND channel='sms'",
            (device_id, alert_type),
        ).fetchone()["cnt"]


def post_location(device_id: str, *, sim_changed: bool, seq: int = 1) -> None:
    resp = _client().post(
        "/api/device/location",
        json={
            "device_id": device_id,
            "lat": 6.5244,
            "lng": 3.3792,
            "accuracy_horizontal": 12.0,
            "speed": 1.0,
            "provider": "gps",
            "confidence_level": "HIGH",
            "is_location_enabled": True,
            "is_airplane_mode": False,
            "sim_changed": sim_changed,
            "ping_sequence": seq,
        },
        headers=get_device_headers(device_id),
    )
    assert resp.status_code == 200, f"Location post failed: {resp.text}"


# ─── Location path ──────────────────────────────────────────────────────────


class TestSimChangeLocationAlert:
    def test_sim_changed_fires_alert_immediately(self):
        """A SIM swap alerts the owner even though the score (35) is far below
        the theft-confirmation threshold (80)."""
        did = "sim-loc-alert"
        assert ensure_device(did)

        post_location(did, sim_changed=True)

        assert count_alerts(did) == 1, "sim_changed alert must fire on the flag"

    def test_sim_changed_dedupes_replays(self):
        """Queued/offline replays of the same incident must not re-alert."""
        did = "sim-loc-dedup"
        assert ensure_device(did)

        post_location(did, sim_changed=True, seq=1)
        post_location(did, sim_changed=True, seq=2)  # replayed ping
        post_location(did, sim_changed=True, seq=3)

        assert count_alerts(did) == 1, "one incident = one alert"

    def test_normal_pings_never_alert(self):
        did = "sim-loc-normal"
        assert ensure_device(did)

        for seq in range(3):
            post_location(did, sim_changed=False, seq=seq + 1)

        assert count_alerts(did) == 0

    def test_sentinel_still_scores_sim_change(self):
        """The signal keeps feeding Sentinel scoring on top of the direct alert."""
        did = "sim-loc-score"
        assert ensure_device(did)

        post_location(did, sim_changed=True)
        from database import get_db_context  # lazy: follows the current module

        with get_db_context() as conn:
            score = conn.execute(
                "SELECT sentinel_score FROM locations " "WHERE device_id=? ORDER BY id DESC LIMIT 1",
                (did,),
            ).fetchone()["sentinel_score"]
        assert score >= 35, f"sim_changed must score >=35, got {score}"


# ─── Heartbeat path ─────────────────────────────────────────────────────────


class TestSimChangeHeartbeatAlert:
    def test_sim_changed_on_heartbeat_alerts(self):
        """Belt-and-braces: a device whose location stream is quiet still
        reports the change on its 60s heartbeat."""
        did = "sim-hb-alert"
        assert ensure_device(did)

        resp = _client().post(
            "/api/device/heartbeat",
            json={
                "device_id": did,
                "battery_percent": 80,
                "is_charging": False,
                "network_type": "wifi",
                "device_admin_active": True,
                "sim_changed": True,
            },
            headers=get_device_headers(did),
        )
        assert resp.status_code == 200, f"Heartbeat failed: {resp.text}"

        assert count_alerts(did) == 1

    def test_heartbeat_dedupes_with_location_alert(self):
        """Location and heartbeat both flag the change → still exactly one alert."""
        did = "sim-hb-dedup"
        assert ensure_device(did)

        post_location(did, sim_changed=True)
        _client().post(
            "/api/device/heartbeat",
            json={"device_id": did, "sim_changed": True},
            headers=get_device_headers(did),
        )

        assert count_alerts(did) == 1

    def test_location_dedupes_with_heartbeat_alert(self):
        """Symmetric order: heartbeat fires first, a later location replay
        must not re-alert."""
        did = "sim-loc-after-hb"
        assert ensure_device(did)

        resp = _client().post(
            "/api/device/heartbeat",
            json={"device_id": did, "sim_changed": True},
            headers=get_device_headers(did),
        )
        assert resp.status_code == 200
        post_location(did, sim_changed=True, seq=1)

        assert count_alerts(did) == 1
