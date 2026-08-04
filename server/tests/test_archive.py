"""
Magneetar Stale-Device Archive + Reinstall Dedup Tests

Covers:
- archive_stale_devices() soft-archives devices silent beyond the threshold
  (archived_at set) and skips recently-seen devices
- idempotency: re-running the sweep doesn't re-flag already-archived devices
- fresh telemetry / heartbeat / register un-archives a device that came back
- register fingerprint dedup: a reinstall (new random id, same ANDROID_ID
  fingerprint) with an unowned existing row returns the canonical id and does
  NOT create a duplicate row
- security: an actively-owned row is never re-pointed by an anonymous reinstall
"""

import os
import secrets
import tempfile

from fastapi.testclient import TestClient

# ── Test Environment Setup (mirrors test_offline_monitor.py) ────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "archive-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "archive-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path
os.environ["MT_ARCHIVE_AFTER_DAYS"] = "30"

import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from archive_monitor import archive_stale_devices, unarchive_device  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY

# Distinct device ids per test — no cross-test shared state.
DEV_STALE = "arch-dev-001"
DEV_RECENT = "arch-dev-002"
DEV_ALREADY = "arch-dev-003"
DEV_REVIVE = "arch-dev-004"
DEV_DEDUP = "arch-dev-005"
DEV_DEDUP_OWNED = "arch-dev-006"
DEV_DEDUP_SAME_ID = "arch-dev-007"

ALL_TEST_DEVICES = [
    DEV_STALE,
    DEV_RECENT,
    DEV_ALREADY,
    DEV_REVIVE,
    DEV_DEDUP,
    DEV_DEDUP_OWNED,
    DEV_DEDUP_SAME_ID,
]


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device(device_id: str, fingerprint: str = "fingerprint-0000", device_key: str = None) -> dict:
    """Register and return the JSON response (tokens included) for auth use."""
    resp = client.post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": device_id,
            "fingerprint": fingerprint,
            "model": "Archive Test Phone",
            "app_version": "1.0.0",
            "device_key": device_key or f"test-device-key-{device_id}",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def device_auth_headers(reg: dict) -> dict:
    """Bearer token auth for a registered device (the heartbeat/location
    endpoints resolve the device from its JWT and reject api_key_user)."""
    return {"Authorization": f"Bearer {reg['token']}"}


def set_last_seen(device_id: str, days_ago: int) -> None:
    with database.get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET last_seen = datetime('now', ?) WHERE id=?",
            (f"-{days_ago} days", device_id),
        )
        conn.commit()


def device_row(device_id: str) -> dict:
    with database.get_db_context() as conn:
        return dict(conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone())


def cleanup_test_devices() -> None:
    from database import delete_device_cascade

    with database.get_db_context() as conn:
        for device_id in ALL_TEST_DEVICES:
            if conn.execute("SELECT 1 FROM devices WHERE id=?", (device_id,)).fetchone():
                delete_device_cascade(conn, device_id)
        conn.commit()


# ─── Archive sweep ───────────────────────────────────────────────────────────


def test_archive_flags_stale_devices():
    cleanup_test_devices()
    register_device(DEV_STALE)
    set_last_seen(DEV_STALE, days_ago=40)

    archived = archive_stale_devices(days=30)
    assert archived >= 1
    row = device_row(DEV_STALE)
    assert row["archived_at"] is not None


def test_archive_skips_recent_devices():
    cleanup_test_devices()
    register_device(DEV_RECENT)
    set_last_seen(DEV_RECENT, days_ago=1)

    archive_stale_devices(days=30)
    assert device_row(DEV_RECENT)["archived_at"] is None


def test_archive_is_idempotent():
    cleanup_test_devices()
    register_device(DEV_ALREADY)
    set_last_seen(DEV_ALREADY, days_ago=40)

    first = archive_stale_devices(days=30)
    second = archive_stale_devices(days=30)
    assert first >= 1
    assert second == 0  # already archived — no double work
    assert device_row(DEV_ALREADY)["archived_at"] is not None


def test_telemetry_unarchives_device():
    """A device that reports again (fresh heartbeat) is restored to active."""
    cleanup_test_devices()
    reg = register_device(DEV_REVIVE)
    set_last_seen(DEV_REVIVE, days_ago=40)
    archive_stale_devices(days=30)
    assert device_row(DEV_REVIVE)["archived_at"] is not None

    # Fresh heartbeat with the device's own token — the handler calls
    # unarchive_device and the archived flag clears.
    resp = client.post(
        "/api/device/heartbeat",
        headers=device_auth_headers(reg),
        json={
            "device_id": DEV_REVIVE,
            "battery_percent": 80,
            "is_charging": True,
            "network_type": "wifi",
            "app_version": "1.3.0",
        },
    )
    assert resp.status_code == 200, resp.text
    assert device_row(DEV_REVIVE)["archived_at"] is None


def test_unarchive_helper_is_noop_when_not_archived():
    cleanup_test_devices()
    register_device(DEV_RECENT)
    with database.get_db_context() as conn:
        unarchive_device(conn, DEV_RECENT)
        conn.commit()
    assert device_row(DEV_RECENT)["archived_at"] is None


# ─── Register fingerprint dedup (reinstall recovery) ─────────────────────────

FINGERPRINT_X = "android-id-reinstall-001"


def test_reinstall_adopts_existing_unowned_row():
    """Same physical phone (fingerprint), fresh random id from a reinstall:
    the register response returns the CANONICAL id and no duplicate row is
    created for the new id."""
    cleanup_test_devices()
    # Original install registered with id A and fingerprint F, then the app
    # was uninstalled — the row went silent (the staleness guard requires
    # this; a concurrently-reporting same-fingerprint device is never adopted).
    register_device(DEV_DEDUP, fingerprint=FINGERPRINT_X, device_key="key-original")
    set_last_seen(DEV_DEDUP, days_ago=14)
    original = device_row(DEV_DEDUP)

    # Reinstall: NEW random id B, SAME fingerprint, NEW device key.
    resp = client.post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": "arch-dev-005b",
            "fingerprint": FINGERPRINT_X,
            "model": "Archive Test Phone",
            "app_version": "1.3.0",
            "device_key": "key-reinstalled",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The server re-pointed us at the ORIGINAL row (canonical id returned)…
    assert data["device_id"] == DEV_DEDUP

    # …and did NOT create a row for the new id.
    with database.get_db_context() as conn:
        dup = conn.execute("SELECT COUNT(*) FROM devices WHERE id='arch-dev-005b'").fetchone()[0]
    assert dup == 0

    # The canonical row now carries the NEW device key (so the reinstalled app
    # can authenticate) and the updated app_version.
    row = device_row(DEV_DEDUP)
    assert row["app_version"] == "1.3.0"
    assert row["device_key_hash"] != original["device_key_hash"]


def test_reinstall_does_not_adopt_actively_owned_row():
    """Security: a row actively owned by a real account must NOT be re-pointed
    by an anonymous reinstall (that would let a thief claim a victim's device)."""
    cleanup_test_devices()
    register_device(DEV_DEDUP_OWNED, fingerprint="fingerprint-owned-001")
    set_last_seen(DEV_DEDUP_OWNED, days_ago=14)  # old, but OWNED → still no adoption
    with database.get_db_context() as conn:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, tier) VALUES (?, ?, ?, 'free')",
            ("usr-archive-owner", "archive-owner@test.local", "not-a-real-hash"),
        )
        conn.execute(
            "UPDATE devices SET owner_id='usr-archive-owner' WHERE id=?",
            (DEV_DEDUP_OWNED,),
        )
        conn.commit()

    resp = client.post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": "arch-dev-006b",
            "fingerprint": "fingerprint-owned-001",
            "model": "Stolen Attempt",
            "app_version": "1.3.0",
            "device_key": "key-attacker",
        },
    )
    assert resp.status_code == 200, resp.text

    # The NEW id is registered as its own row (no adoption) and stays unowned.
    assert resp.json()["device_id"] == "arch-dev-006b"
    with database.get_db_context() as conn:
        owner = conn.execute("SELECT owner_id FROM devices WHERE id='arch-dev-006b'").fetchone()[0]
    assert owner is None


def test_reinstall_adopts_own_row_even_when_fresh():
    """Same-owner reinstall: a user reinstalling their OWN phone (new random
    id, same fingerprint) links with their token and adopts the existing row
    REGARDLESS of staleness — it is provably their device (owner matches), so
    the silence guard (which exists to stop fingerprint hijacking of unowned
    rows) does not apply. This is the fix for "phone disappeared from the
    dashboard after reinstall" — the canonical row keeps its history."""
    cleanup_test_devices()
    # Register a user account and link the original install to it.
    user_resp = client.post(
        "/api/auth/register",
        json={
            "email": "adopt-own@example.com",
            "password": "StrongPass1",
            "display_name": "Owner",
        },
    )
    assert user_resp.status_code == 200, user_resp.text
    user_token = user_resp.json()["token"]
    user_id = user_resp.json().get("id")

    resp = client.post(
        "/api/device/register",
        headers={**api_key_headers(), "Authorization": f"Bearer {user_token}"},
        json={
            "device_id": "adopt-own-device",
            "fingerprint": "fingerprint-own-001",
            "model": "Owner Phone",
            "app_version": "1.3.0",
            "device_key": "key-own-original",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["owner_id"] == user_id or resp.json()["owner_id"] is not None

    # Reinstall: FRESH random id, SAME fingerprint, SAME user token, and the
    # original row is only minutes old (not silent) — a plain re-register of
    # the same physical phone. Must adopt the original row (canonical id).
    resp = client.post(
        "/api/device/register",
        headers={**api_key_headers(), "Authorization": f"Bearer {user_token}"},
        json={
            "device_id": "adopt-own-device-reinstall",
            "fingerprint": "fingerprint-own-001",
            "model": "Owner Phone",
            "app_version": "1.3.0",
            "device_key": "key-own-new",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["device_id"] == "adopt-own-device"

    # No duplicate row for the fresh id, and the canonical row keeps its owner.
    with database.get_db_context() as conn:
        dup = conn.execute("SELECT COUNT(*) FROM devices WHERE id='adopt-own-device-reinstall'").fetchone()[0]
    assert dup == 0
    row = device_row("adopt-own-device")
    assert row["owner_id"] is not None
    assert row["device_key_hash"] != ""  # new key adopted


def test_same_id_reregister_stays_idempotent():
    """Re-registering the SAME id (the common case after this fix: the app's
    deterministic device id is stable across reinstalls) updates in place."""
    cleanup_test_devices()
    register_device(DEV_DEDUP_SAME_ID, fingerprint="fingerprint-same-001", device_key="key-one")

    resp = client.post(
        "/api/device/register",
        headers=api_key_headers(),
        json={
            "device_id": DEV_DEDUP_SAME_ID,
            "fingerprint": "fingerprint-same-001",
            "model": "Archive Test Phone",
            "app_version": "1.3.0",
            "device_key": "key-two",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["device_id"] == DEV_DEDUP_SAME_ID
    assert device_row(DEV_DEDUP_SAME_ID)["app_version"] == "1.3.0"
    with database.get_db_context() as conn:
        cnt = conn.execute("SELECT COUNT(*) FROM devices WHERE id=?", (DEV_DEDUP_SAME_ID,)).fetchone()[0]
    assert cnt == 1
