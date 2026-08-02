"""
Magneetar Multi-User Tests
Tests for device→user linking (claim endpoint, register-with-user-token),
dashboard ownership scoping, and per-user device limits.
"""

import os
import secrets
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "multiuser-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "multiuser-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Override the settings module's DB_PATH
import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from auth import create_dashboard_tokens, create_device_tokens, decode_token, user_id_from_subject  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def user_id_of(token: str) -> str:
    """Extract the user id from a user token's subject (user:<id>)."""
    return user_id_from_subject(decode_token(token).get("sub", ""))

# Use the LIVE settings value, not the env var. config.settings is a shared
# singleton created by whichever test module imported config first — in a
# full-suite run that is test_api.py's key. Reading the env var here would
# send a mismatched x-api-key and 401 against the cached settings.
TEST_API_KEY = config.settings.API_KEY
TEST_USER_EMAIL = "owner@example.com"
TEST_USER_PASSWORD = "StrongPass1"


def register_user(email: str, password: str = TEST_USER_PASSWORD) -> dict:
    """Register a user and return their token pair."""
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Test User"},
    )
    assert resp.status_code == 200, f"register_user failed: {resp.text}"
    return resp.json()


def user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device(device_id: str, user_token: str = None) -> dict:
    """Register a device, optionally linking it to a user via bearer token."""
    headers = api_key_headers()
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{device_id}",
            "model": "Multi-User Test Device",
            "os_version": "Android 14",
            "app_version": "1.1.0",
            "device_key": f"devicekey-{device_id}",
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"register_device failed: {resp.text}"
    return resp.json()


def get_dashboard_devices(auth: dict) -> list:
    resp = client.get("/api/dashboard/devices", headers=auth)
    assert resp.status_code == 200, f"list devices failed: {resp.text}"
    return resp.json()["devices"]


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset the shared test DB between tests.

    These tests reuse fixed emails/device ids across many tests, and the DB
    file persists for the whole module run, so re-registering the same email
    would 409 without a reset. Registration is also capped at 3 per IP per 10
    minutes, so rate_limits must be cleared too. Child tables are wiped first
    to satisfy FK constraints.
    """
    with database.get_db_context() as conn:
        # Child tables first (satisfy FK constraints): the Guardian Network
        # tables reference devices, so wipe them before devices/users.
        for table in (
            "locations",
            "media",
            "commands",
            "evidence_cases",
            "alerts",
            "heartbeats",
            "geofences",
            "fcm_tokens",
            "recovery_sightings",
            "recovery_requests",
            "guardian_profiles",
            "devices",
            "users",
            "audit_log",
            "rate_limits",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()

    # Clear in-memory WebSocket owner caches too — register/claim call
    # update_device_owner(), so stale mappings accumulate across tests.
    import websocket_manager

    websocket_manager._device_owners.clear()
    websocket_manager._connection_owners.clear()
    yield


def teardown_module(module):
    """Clean up test database after all tests."""
    try:
        os.remove(test_db_path)
    except OSError:
        pass


# ─── Registration-time linking ───────────────────────────────────────────────


class TestRegisterLinksOwner:
    def test_register_with_user_token_sets_owner(self):
        user = register_user("link-owner@example.com")
        data = register_device("link-owner-device", user_token=user["token"])
        assert data["owner_id"] is not None

        devices = get_dashboard_devices(user_headers(user["token"]))
        assert any(d["id"] == "link-owner-device" for d in devices)

    def test_register_without_user_token_no_owner(self):
        data = register_device("no-owner-device")
        assert data["owner_id"] is None


# ─── Claim endpoint ──────────────────────────────────────────────────────────


class TestClaimDevice:
    def test_claim_by_device_id(self):
        user = register_user("claim-id@example.com")
        register_device("claim-id-device")  # registered without user token

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "claim-id-device"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["owner_id"] is not None

    def test_claim_by_device_key(self):
        user = register_user("claim-key@example.com")
        register_device("claim-key-device")

        resp = client.post(
            "/api/device/claim",
            json={},
            headers={
                **user_headers(user["token"]),
                "x-device-key": "devicekey-claim-key-device",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["device_id"] == "claim-key-device"

    def test_claim_requires_user_auth(self):
        resp = client.post("/api/device/claim", json={"device_id": "any-device"}, headers=api_key_headers())
        assert resp.status_code == 401

    def test_claim_unknown_device_404(self):
        user = register_user("claim-404@example.com")
        resp = client.post(
            "/api/device/claim",
            json={"device_id": "never-existed"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 404

    def test_claim_device_owned_by_other_user_403(self):
        owner = register_user("claim-owner-a@example.com")
        intruder = register_user("claim-owner-b@example.com")
        register_device("claim-owner-device")

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "claim-owner-device"},
            headers=user_headers(owner["token"]),
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "claim-owner-device"},
            headers=user_headers(intruder["token"]),
        )
        assert resp.status_code == 403


# ─── Orphaned (ghost) ownership recovery ───────────────────────────────────
# A device whose owner account was permanently deleted (e.g. wiped by a DB
# restore, or the account-deletion flow) must remain claimable — the 403 guard
# only applies when the existing owner is a REAL account. This is what lets a
# user sign up fresh and re-link their phone after data loss.


class TestGhostOwnerRecovery:
    def _orphan_device(self, device_id: str, ghost_owner: str = "usr-deleted-ghost"):
        """Register a device then point its owner_id at a non-existent user."""
        register_device(device_id)
        with database.get_db_context() as conn:
            conn.execute("UPDATE devices SET owner_id=? WHERE id=?", (ghost_owner, device_id))
            conn.commit()

    def test_claim_device_with_ghost_owner_succeeds(self):
        user = register_user("ghost-claim@example.com")
        self._orphan_device("ghost-claim-device")

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "ghost-claim-device"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["owner_id"] == user_id_of(user["token"])

        # Now owned by the real user → shows on their dashboard.
        devices = get_dashboard_devices(user_headers(user["token"]))
        assert any(d["id"] == "ghost-claim-device" for d in devices)

    def test_claim_ghost_device_by_key_succeeds(self):
        user = register_user("ghost-key@example.com")
        self._orphan_device("ghost-key-device")

        resp = client.post(
            "/api/device/claim",
            json={},
            headers={
                **user_headers(user["token"]),
                "x-device-key": "devicekey-ghost-key-device",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["device_id"] == "ghost-key-device"

    def test_register_with_stale_deleted_user_token_not_relinked(self):
        """A stale token for a DELETED account must not create a ghost link."""
        user = register_user("ghost-stale@example.com")
        stale_token = user["token"]
        deleted_user_id = user_id_of(stale_token)
        # Permanently delete the account (cascades devices away).
        resp = client.delete("/api/auth/user/account", headers=user_headers(stale_token))
        assert resp.status_code == 200

        headers = {**api_key_headers(), "Authorization": f"Bearer {stale_token}"}
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": "ghost-stale-device",
                "fingerprint": "fp-ghost-stale",
                "model": "Test",
                "os_version": "Android 14",
                "app_version": "1.1.0",
            },
            headers=headers,
        )
        # Token still signs (JWTs outlive the account row), but the device must
        # NOT be linked to the deleted user id.
        assert resp.status_code == 200, resp.text
        assert resp.json()["owner_id"] is None
        assert resp.json()["owner_id"] != deleted_user_id

    def test_register_with_new_user_token_relinks_ghost_device(self):
        """Signing up fresh then re-registering takes over the ghost-owned device."""
        self._orphan_device("ghost-relink-device")
        new_user = register_user("ghost-new@example.com")

        data = register_device("ghost-relink-device", user_token=new_user["token"])
        assert data["owner_id"] == user_id_of(new_user["token"])

        devices = get_dashboard_devices(user_headers(new_user["token"]))
        assert any(d["id"] == "ghost-relink-device" for d in devices)

    def test_real_owner_claim_still_403(self):
        """The guard still blocks claiming a device owned by a LIVE account."""
        owner = register_user("ghost-real-owner@example.com")
        intruder = register_user("ghost-real-intruder@example.com")
        register_device("ghost-real-device", user_token=owner["token"])

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "ghost-real-device"},
            headers=user_headers(intruder["token"]),
        )
        assert resp.status_code == 403

    def test_claim_with_stale_deleted_token_401(self):
        """A stale token from a deleted account cannot claim devices."""
        user = register_user("ghost-claim-stale@example.com")
        stale_token = user["token"]
        register_device("ghost-claim-stale-device")
        # Delete the account; the JWT stays valid but the user row is gone.
        resp = client.delete("/api/auth/user/account", headers=user_headers(stale_token))
        assert resp.status_code == 200

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "ghost-claim-stale-device"},
            headers=user_headers(stale_token),
        )
        assert resp.status_code == 401
        assert "no longer exists" in resp.json()["detail"].lower()

        # The device stays claimable by a REAL user.
        real = register_user("ghost-claim-real@example.com")
        resp = client.post(
            "/api/device/claim",
            json={"device_id": "ghost-claim-stale-device"},
            headers=user_headers(real["token"]),
        )
        assert resp.status_code == 200, resp.text


# ─── Dashboard ownership scoping ─────────────────────────────────────────────


class TestDashboardScoping:
    def _setup(self):
        """Register two users, each with one device, plus an unowned device."""
        user_a = register_user("scope-a@example.com")
        user_b = register_user("scope-b@example.com")
        register_device("scope-device-a", user_token=user_a["token"])
        register_device("scope-device-b", user_token=user_b["token"])
        register_device("scope-device-unowned")
        return user_a, user_b

    def test_user_sees_only_own_devices(self):
        user_a, _user_b = self._setup()
        devices = get_dashboard_devices(user_headers(user_a["token"]))
        ids = {d["id"] for d in devices}
        assert "scope-device-a" in ids
        assert "scope-device-b" not in ids
        assert "scope-device-unowned" not in ids

    def test_admin_sees_all_devices(self):
        self._setup()
        tokens = create_dashboard_tokens(TEST_API_KEY)
        devices = get_dashboard_devices({"Authorization": f"Bearer {tokens['token']}"})
        ids = {d["id"] for d in devices}
        assert {"scope-device-a", "scope-device-b", "scope-device-unowned"} <= ids

    def test_non_owner_denied_location_history(self):
        user_a, user_b = self._setup()
        # user_b cannot read user_a's location history
        resp = client.get("/api/dashboard/locations/scope-device-a", headers=user_headers(user_b["token"]))
        assert resp.status_code == 403

    def test_owner_allowed_location_history(self):
        user_a, _user_b = self._setup()
        resp = client.get("/api/dashboard/locations/scope-device-a", headers=user_headers(user_a["token"]))
        assert resp.status_code == 200

    def test_non_owner_denied_command_issue(self):
        user_a, user_b = self._setup()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": "scope-device-a", "command": "ping"},
            headers=user_headers(user_b["token"]),
        )
        assert resp.status_code == 403

    def test_owner_allowed_command_issue(self):
        user_a, _user_b = self._setup()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": "scope-device-a", "command": "ping"},
            headers=user_headers(user_a["token"]),
        )
        assert resp.status_code == 200

    def test_non_owner_denied_media(self):
        user_a, user_b = self._setup()
        resp = client.get("/api/dashboard/media/scope-device-a", headers=user_headers(user_b["token"]))
        assert resp.status_code == 403

    def test_non_owner_denied_alerts(self):
        user_a, user_b = self._setup()
        resp = client.get("/api/dashboard/alerts/scope-device-a", headers=user_headers(user_b["token"]))
        assert resp.status_code == 403

    def test_non_owner_denied_geofence_list(self):
        user_a, user_b = self._setup()
        resp = client.get("/api/dashboard/geofences/scope-device-a", headers=user_headers(user_b["token"]))
        assert resp.status_code == 403

    def test_non_owner_denied_evidence(self):
        user_a, user_b = self._setup()
        resp = client.get("/api/dashboard/evidence/scope-device-a", headers=user_headers(user_b["token"]))
        assert resp.status_code == 403

    def test_non_owner_denied_alias_update(self):
        user_a, user_b = self._setup()
        resp = client.patch(
            "/api/dashboard/devices/scope-device-a/alias",
            json={"alias": "hacked"},
            headers=user_headers(user_b["token"]),
        )
        assert resp.status_code == 403

    def test_non_owner_denied_recover(self):
        user_a, user_b = self._setup()
        resp = client.post(
            "/api/dashboard/devices/scope-device-a/recover",
            headers=user_headers(user_b["token"]),
        )
        assert resp.status_code == 403


# ─── Per-user device limit ───────────────────────────────────────────────────


class TestDeviceLimit:
    def test_register_rejected_when_at_limit(self, monkeypatch):
        """Registering a NEW device with a user token enforces the limit too."""
        monkeypatch.setattr(config.settings, "MAX_DEVICES_PER_USER", 1)
        user = register_user("limit-reg@example.com")
        register_device("limit-reg-device-1", user_token=user["token"])

        # Second NEW device with the same user token → 403
        headers = {**api_key_headers(), "Authorization": f"Bearer {user['token']}"}
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": "limit-reg-device-2",
                "fingerprint": "fp-limit-reg-device-2",
                "model": "Test",
                "os_version": "Android 14",
                "app_version": "1.1.0",
            },
            headers=headers,
        )
        assert resp.status_code == 403
        assert "limit" in resp.json()["detail"].lower()

    def test_register_same_device_at_limit_still_ok(self, monkeypatch):
        """Re-registering an already-owned device at the limit is allowed."""
        monkeypatch.setattr(config.settings, "MAX_DEVICES_PER_USER", 1)
        user = register_user("limit-same@example.com")
        register_device("limit-same-device", user_token=user["token"])

        headers = {**api_key_headers(), "Authorization": f"Bearer {user['token']}"}
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": "limit-same-device",
                "fingerprint": "fp-limit-same-device",
                "model": "Test",
                "os_version": "Android 14",
                "app_version": "1.1.0",
            },
            headers=headers,
        )
        assert resp.status_code == 200

    def test_claim_rejected_when_at_limit(self, monkeypatch):
        monkeypatch.setattr(config.settings, "MAX_DEVICES_PER_USER", 1)
        user = register_user("limit@example.com")
        register_device("limit-device-1", user_token=user["token"])
        register_device("limit-device-2")  # unlinked

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "limit-device-2"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 403
        assert "limit" in resp.json()["detail"].lower()

    def test_claim_allowed_under_limit(self, monkeypatch):
        monkeypatch.setattr(config.settings, "MAX_DEVICES_PER_USER", 5)
        user = register_user("limit-ok@example.com")
        register_device("limit-ok-device-1", user_token=user["token"])
        register_device("limit-ok-device-2")

        resp = client.post(
            "/api/device/claim",
            json={"device_id": "limit-ok-device-2"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200


# ─── Permanent deletion (privacy policy promise) ─────────────────────────────


class TestPermanentDeletion:
    def _seed_device_data(self, device_id: str):
        """Insert child rows so cascade deletion is exercised, not just the row."""
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES (?, ?, ?, datetime('now'))",
                (device_id, 9.0820, 8.6753),
            )
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64, timestamp) VALUES (?, 'photo', 'AAAA', datetime('now'))",
                (device_id,),
            )
            conn.execute(
                "INSERT INTO commands (device_id, command, params, status) VALUES (?, 'lock', '', 'pending')",
                (device_id,),
            )
            conn.execute(
                "INSERT INTO evidence_cases (id, device_id, theft_time, status) VALUES (?, ?, datetime('now'), 'active')",
                (f"case-{device_id}", device_id),
            )
            conn.execute(
                "INSERT INTO alerts (device_id, alert_type, channel, message) VALUES (?, 'theft_detected', 'sms', 'x')",
                (device_id,),
            )
            conn.execute(
                "INSERT INTO heartbeats (device_id, battery_percent) VALUES (?, 80)",
                (device_id,),
            )
            conn.execute(
                "INSERT INTO geofences (device_id, name, center_lat, center_lng, radius_meters) "
                "VALUES (?, 'home', 9.0, 8.6, 500)",
                (device_id,),
            )
            conn.execute(
                "INSERT INTO fcm_tokens (device_id, fcm_token) VALUES (?, 'tok-' || ?)",
                (device_id, device_id),
            )
            conn.execute(
                "INSERT INTO recovery_requests (id, device_id, owner_id, status) VALUES (?, ?, 'usr-owner', 'active')",
                (f"rec-{device_id}", device_id),
            )
            conn.execute(
                "INSERT INTO recovery_sightings (request_id, guardian_id, guardian_handle, lat, lng) "
                "VALUES (?, 'usr-guardian', 'Eagle', 9.1, 8.7)",
                (f"rec-{device_id}",),
            )
            conn.commit()

    def _count_related(self, device_id: str) -> int:
        """Count rows referencing the device across all child tables."""
        with database.get_db_context() as conn:
            total = 0
            for table in (
                "locations", "media", "commands", "evidence_cases", "alerts",
                "heartbeats", "geofences", "fcm_tokens", "recovery_requests",
            ):
                total += conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE device_id=?", (device_id,)
                ).fetchone()[0]
            total += conn.execute(
                "SELECT COUNT(*) FROM recovery_sightings WHERE request_id IN "
                "(SELECT id FROM recovery_requests WHERE device_id=?)",
                (device_id,),
            ).fetchone()[0]
            return total

    def test_delete_device_permanent_cascade(self):
        user = register_user("del-dev@example.com")
        register_device("del-device", user_token=user["token"])
        self._seed_device_data("del-device")
        assert self._count_related("del-device") > 0

        resp = client.delete("/api/dashboard/devices/del-device", headers=user_headers(user["token"]))
        assert resp.status_code == 200, resp.text
        assert "permanently deleted" in resp.json()["message"]

        # Device row is gone AND all child rows are gone.
        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM devices WHERE id='del-device'").fetchone()[0] == 0
        assert self._count_related("del-device") == 0

    def test_delete_device_other_user_403(self):
        owner = register_user("del-owner@example.com")
        intruder = register_user("del-intruder@example.com")
        register_device("del-guarded", user_token=owner["token"])

        resp = client.delete("/api/dashboard/devices/del-guarded", headers=user_headers(intruder["token"]))
        assert resp.status_code == 403

        # Device still exists.
        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM devices WHERE id='del-guarded'").fetchone()[0] == 1

    def test_delete_device_requires_auth(self):
        # No auth at all → 401 (an API key alone is accepted as admin auth, so
        # the key path is tested separately in the admin test below).
        resp = client.delete("/api/dashboard/devices/whatever")
        assert resp.status_code == 401

    def test_admin_can_delete_any_device(self):
        owner = register_user("del-admin-owner@example.com")
        register_device("del-admin-device", user_token=owner["token"])

        tokens = create_dashboard_tokens(TEST_API_KEY)
        resp = client.delete(
            "/api/dashboard/devices/del-admin-device",
            headers={"Authorization": f"Bearer {tokens['token']}"},
        )
        assert resp.status_code == 200, resp.text

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM devices WHERE id='del-admin-device'").fetchone()[0] == 0

    def test_delete_unknown_device_404(self):
        user = register_user("del-404@example.com")
        resp = client.delete("/api/dashboard/devices/never-existed", headers=user_headers(user["token"]))
        assert resp.status_code == 404

    def test_delete_user_account_removes_everything(self):
        user = register_user("del-acc@example.com")
        register_device("del-acc-device", user_token=user["token"])
        self._seed_device_data("del-acc-device")

        resp = client.delete("/api/auth/user/account", headers=user_headers(user["token"]))
        assert resp.status_code == 200, resp.text
        assert resp.json()["devices_removed"] == 1

        with database.get_db_context() as conn:
            assert conn.execute("SELECT COUNT(*) FROM users WHERE email='del-acc@example.com'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM devices WHERE id='del-acc-device'").fetchone()[0] == 0
        assert self._count_related("del-acc-device") == 0

    def test_delete_user_account_rejects_api_key(self):
        resp = client.delete("/api/auth/user/account", headers=api_key_headers())
        assert resp.status_code == 401
