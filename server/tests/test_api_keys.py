"""
Magneetar Developer API Keys Tests (docs/developer-api.md)

Per-account, scoped, revocable keys for third-party integrations. These tests
lock in the full security contract:

- The key works on /api/v1/* data routes WITH its scopes, resolving to the
  owning account (all RBAC/share rules apply — a viewer-shared device stays
  read-only even through a devices:write key).
- The key is REJECTED everywhere else: /api/auth/*, /api/dashboard/*,
  /metrics, and the key-management endpoints themselves (a leaked key can
  never mint credentials or reach admin surface — the F-02 guarantee).
- Revoked / expired keys die instantly (401 on every request).
- The raw mtk_... value never appears in the DB or the audit log — only the
  12-char prefix and the SHA-256 hash.
- Create/revoke/rotate are step-up gated (account password, rate-limited):
  a stolen dashboard session alone cannot mint or destroy credentials.
- Operator/dashboard sessions cannot manage keys (user-account feature).
- Per-key rate limit (120 req/min) → 429.
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

os.environ["MT_API_KEY"] = "apikeys-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "apikeys-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

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


def key_headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device(device_id: str, user_token: str) -> dict:
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{device_id}",
            "model": "API Key Test Phone",
            "os_version": "Android 14",
            "app_version": "1.1.0",
            "device_key": f"devicekey-{device_id}",
        },
        headers={**api_key_headers(), "Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, f"register_device failed: {resp.text}"
    return resp.json()


def create_key(user: dict, name: str = "test key", scopes=None, expires_at=None, password=None, key_type=None) -> dict:
    """POST /api/account/api-keys (step-up gated)."""
    resp = client.post(
        "/api/account/api-keys",
        json={
            "name": name,
            "scopes": scopes if scopes is not None else ["devices:read"],
            "key_type": key_type if key_type is not None else "live",
            "expires_at": expires_at,
            "password": password if password is not None else TEST_USER_PASSWORD,
        },
        headers=user_headers(user["token"]),
    )
    return resp


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset the shared test DB between tests."""
    with database.get_db_context() as conn:
        for table in (
            "api_keys",
            "device_shares",
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
            "error_log",
            "rate_limits",
            "revoked_tokens",
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


# ─── Schema migration ────────────────────────────────────────────────────────


class TestSchemaMigration:
    def test_ensure_initialized_migrates_existing_db(self, monkeypatch):
        """An existing database (created before the api_keys table) must be
        migrated forward by ensure_initialized() on server startup — the
        device_shares no-op bug class."""
        fd, old_db_path = tempfile.mkstemp(suffix="-old.db")
        os.close(fd)

        conn = sqlite3.connect(old_db_path)
        conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        monkeypatch.setattr(database, "DB_PATH", old_db_path)
        assert database.ensure_initialized() is True

        conn = sqlite3.connect(old_db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()

        assert "api_keys" in tables
        os.remove(old_db_path)

    def test_ensure_initialized_adds_new_api_key_columns_to_existing_db(self, monkeypatch):
        """A DB that already has api_keys (v1.6 schema — no key_type /
        request_count) must still be migrated forward. The staleness check
        compares api_keys COLUMNS now; before that fix, an existing table
        made ensure_initialized take the no-op fast path and the guarded
        ALTERs never ran — this exact drift shipped to production on
        2026-08-14 (readonly keys 500'd on the live DB)."""
        fd, old_db_path = tempfile.mkstemp(suffix="-oldapi.db")
        os.close(fd)

        conn = sqlite3.connect(old_db_path)
        conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
        # The v1.6 api_keys schema — no key_type, no request_count.
        conn.execute(
            """CREATE TABLE api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                key_prefix TEXT NOT NULL UNIQUE,
                key_hash TEXT NOT NULL,
                scopes TEXT NOT NULL DEFAULT 'devices:read',
                created_at TEXT,
                last_used_at TEXT,
                expires_at TEXT,
                revoked_at TEXT
            )"""
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(database, "DB_PATH", old_db_path)
        assert database.ensure_initialized() is True

        conn = sqlite3.connect(old_db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(api_keys)")}
        conn.close()

        assert {"key_type", "request_count"}.issubset(cols)
        os.remove(old_db_path)


# ─── Key management ──────────────────────────────────────────────────────────


class TestKeyManagement:
    def test_create_returns_full_key_once_and_never_stores_it(self):
        user = register_user("create@example.com")
        resp = create_key(user, name="Reseller dash")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["key"].startswith("mtk_live_")
        assert len(body["key"]) == len("mtk_live_") + 32
        assert body["key_prefix"] == body["key"][:12]
        assert body["scopes"] == ["devices:read"]
        assert body["name"] == "Reseller dash"

        # The DB stores ONLY the prefix + SHA-256 hash — never the raw key.
        with database.get_db_context() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id=?", (body["id"],)).fetchone()
        assert row is not None
        assert row["key_prefix"] == body["key_prefix"]
        assert row["key_hash"] != body["key"]
        assert row["key_hash"] == __import__("hashlib").sha256(body["key"].encode()).hexdigest()
        assert body["key"] not in dict(row).values()

    def test_create_requires_stepup_password(self):
        user = register_user("stepup@example.com")
        # Wrong password → 401
        resp = create_key(user, password="WrongPass9")
        assert resp.status_code == 401
        # Missing password → 400 (model requires it)
        resp = client.post(
            "/api/account/api-keys",
            json={"name": "no password", "scopes": ["devices:read"]},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 422
        # No key was created
        with database.get_db_context() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM api_keys").fetchone()["c"]
        assert count == 0

    def test_create_validates_scopes(self):
        user = register_user("scopes@example.com")
        resp = create_key(user, scopes=["devices:read", "not_a_scope"])
        assert resp.status_code == 422
        resp = create_key(user, scopes=[])
        assert resp.status_code == 422

    def test_create_rejects_future_expiry_format(self):
        user = register_user("expiry@example.com")
        resp = create_key(user, expires_at="not-a-date")
        assert resp.status_code == 422

    def test_operator_session_cannot_manage_keys(self):
        """Dashboard/operator JWTs have no account — keys are a user feature."""
        login = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        assert login.status_code == 200
        admin_headers = user_headers(login.json()["token"])
        resp = client.post(
            "/api/account/api-keys",
            json={"name": "admin key", "scopes": ["devices:read"], "password": TEST_API_KEY},
            headers=admin_headers,
        )
        assert resp.status_code == 403

    def test_list_never_exposes_hash_or_full_key(self):
        user = register_user("list@example.com")
        created = create_key(user, name="Secret dash").json()
        # Use the key once so last_used_at is populated.
        client.get("/api/v1/devices", headers=key_headers(created["key"]))

        resp = client.get("/api/account/api-keys", headers=user_headers(user["token"]))
        assert resp.status_code == 200
        keys = resp.json()["api_keys"]
        assert len(keys) == 1
        listed = keys[0]
        assert listed["key_prefix"] == created["key_prefix"]
        assert "key_hash" not in listed
        assert created["key"] not in str(keys)
        assert listed["last_used_at"] is not None

    def test_revoke_kills_key_immediately(self):
        user = register_user("revoke@example.com")
        created = create_key(user).json()
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 200

        resp = client.request(
            "DELETE",
            f"/api/account/api-keys/{created['id']}",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200
        # Every subsequent request with the revoked key → 401.
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 401

    def test_revoke_requires_stepup_and_ownership(self):
        user = register_user("revoke2@example.com")
        other = register_user("revoke3@example.com")
        created = create_key(user).json()

        # Wrong password → 401
        resp = client.request(
            "DELETE",
            f"/api/account/api-keys/{created['id']}",
            json={"password": "WrongPass9"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 401
        # Another account cannot revoke it → 404 (no row for them)
        resp = client.request(
            "DELETE",
            f"/api/account/api-keys/{created['id']}",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(other["token"]),
        )
        assert resp.status_code == 404
        # Key still works (revoke failed both times).
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 200

    def test_rotate_revokes_old_and_mints_new(self):
        user = register_user("rotate@example.com")
        created = create_key(user, name="Leaky key", scopes=["alerts:read"]).json()

        resp = client.post(
            f"/api/account/api-keys/{created['id']}/rotate",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        rotated = resp.json()
        assert rotated["key"].startswith("mtk_live_")
        assert rotated["key"] != created["key"]
        assert rotated["name"] == "Leaky key"
        assert rotated["scopes"] == ["alerts:read"]

        # Old key dies instantly, new key works.
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 401
        assert client.get("/api/v1/alerts", headers=key_headers(rotated["key"])).status_code == 200

    def test_rotate_preserves_key_type(self):
        user = register_user("rotate-ro@example.com")
        created = create_key(user, name="Ro key", key_type="readonly").json()

        resp = client.post(
            f"/api/account/api-keys/{created['id']}/rotate",
            json={"password": TEST_USER_PASSWORD},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        rotated = resp.json()
        assert rotated["key_type"] == "readonly"
        assert rotated["key"].startswith("mtk_read_")


# ─── Readonly key type + usage metering ─────────────────────────────────────


class TestReadonlyKeysAndMetering:
    def _owner_with_device(self, email="ro-owner@example.com"):
        user = register_user(email)
        register_device("ro-owner-phone", user["token"])
        return user

    def test_readonly_key_has_mtk_read_prefix_and_type(self):
        user = register_user("ro-prefix@example.com")
        created = create_key(user, name="Read-only dash", key_type="readonly").json()
        assert created["key"].startswith("mtk_read_")
        assert len(created["key"]) == len("mtk_read_") + 32
        assert created["key_prefix"] == created["key"][:12]
        assert created["key_type"] == "readonly"
        # Stored as readonly too.
        with database.get_db_context() as conn:
            row = conn.execute("SELECT key_type FROM api_keys WHERE id=?", (created["id"],)).fetchone()
        assert row["key_type"] == "readonly"

    def test_readonly_key_cannot_be_created_with_write_scope(self):
        """Creation-time structural guarantee: a readonly key with
        devices:write is rejected with 422 — you cannot even mint it."""
        user = register_user("ro-write@example.com")
        resp = create_key(user, scopes=["devices:read", "devices:write"], key_type="readonly")
        assert resp.status_code == 422
        resp = create_key(user, scopes=["devices:write"], key_type="readonly")
        assert resp.status_code == 422

    def test_readonly_key_reads_but_cannot_command(self):
        """A readonly key works on the read surface but the devices:write
        gate returns 403 — wipe/lock are structurally impossible."""
        user = self._owner_with_device()
        created = create_key(user, scopes=["devices:read"], key_type="readonly").json()
        # Reads fine.
        resp = client.get("/api/v1/devices", headers=key_headers(created["key"]))
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 1
        # Write denied — the key has no devices:write scope at auth time.
        resp = client.post(
            "/api/v1/devices/ro-owner-phone/commands",
            json={"command": "lock"},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 403

    def test_readonly_enforced_at_auth_time_even_if_row_tampered(self):
        """Defense in depth: even if the stored scopes column is tampered to
        include devices:write, the auth path strips write scopes from any
        readonly key (stored key_type OR mtk_read_ prefix) before the route
        sees them — a leaked readonly key can never become a wipe/lock
        credential."""
        user = self._owner_with_device()
        created = create_key(user, scopes=["devices:read"], key_type="readonly").json()
        # Simulate a tampered row: write scope sneaked into the scopes column.
        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE api_keys SET scopes='devices:read,devices:write' WHERE id=?",
                (created["id"],),
            )
            conn.commit()
        resp = client.post(
            "/api/v1/devices/ro-owner-phone/commands",
            json={"command": "lock"},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 403

    def test_request_count_increments_and_is_listed(self):
        user = register_user("meter@example.com")
        created = create_key(user).json()
        # Fresh key: no usage yet.
        resp = client.get("/api/account/api-keys", headers=user_headers(user["token"]))
        assert resp.json()["api_keys"][0]["request_count"] == 0

        # Two key-authenticated requests (one that fails auth does NOT count
        # — metering happens after authentication).
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 200
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 200
        assert client.get("/api/v1/devices", headers=key_headers("mtk_live_bogus")).status_code == 401

        resp = client.get("/api/account/api-keys", headers=user_headers(user["token"]))
        listed = resp.json()["api_keys"][0]
        assert listed["request_count"] == 2
        assert listed["last_used_at"] is not None
        # DB agrees.
        with database.get_db_context() as conn:
            row = conn.execute("SELECT request_count FROM api_keys WHERE id=?", (created["id"],)).fetchone()
        assert row["request_count"] == 2


# ─── Data surface: scopes ────────────────────────────────────────────────────


class TestDataSurfaceScopes:
    def _owner_with_device(self, email="owner@example.com"):
        user = register_user(email)
        register_device("owner-phone", user["token"])
        return user

    def test_key_lists_owned_devices(self):
        user = self._owner_with_device()
        created = create_key(user).json()
        resp = client.get("/api/v1/devices", headers=key_headers(created["key"]))
        assert resp.status_code == 200, resp.text
        devices = resp.json()["devices"]
        assert len(devices) == 1
        assert devices[0]["id"] == "owner-phone"
        assert devices[0]["access_role"] == "owner"

    def test_locations_decrypted_for_owner(self):
        user = self._owner_with_device()
        created = create_key(user).json()
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES (?, ?, ?, datetime('now'))",
                ("owner-phone", 9.0820, 8.6753),
            )
            conn.commit()
        resp = client.get(
            "/api/v1/devices/owner-phone/locations",
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 200
        locs = resp.json()["locations"]
        assert len(locs) == 1
        assert locs[0]["lat"] == pytest.approx(9.0820)
        assert "location_data" not in locs[0]  # ciphertext never leaves

    def test_scope_gate_rejects_missing_scope(self):
        user = self._owner_with_device()
        # alerts:read key tries the devices endpoint → 403 (no devices:read).
        created = create_key(user, scopes=["alerts:read"]).json()
        resp = client.get("/api/v1/devices", headers=key_headers(created["key"]))
        assert resp.status_code == 403
        # ...but works on /api/v1/alerts.
        resp = client.get("/api/v1/alerts", headers=key_headers(created["key"]))
        assert resp.status_code == 200

    def test_alerts_scope_returns_account_alerts(self):
        user = self._owner_with_device()
        created = create_key(user, scopes=["alerts:read"]).json()
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO alerts (device_id, alert_type, channel, recipient, message, sent_at, delivered) "
                "VALUES (?, 'theft', 'push', 'owner@example.com', 'Device stolen', datetime('now'), 1)",
                ("owner-phone",),
            )
            conn.commit()
        resp = client.get("/api/v1/alerts", headers=key_headers(created["key"]))
        assert resp.status_code == 200
        alerts = resp.json()["alerts"]
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "theft"

    def test_media_owner_only(self):
        user = self._owner_with_device()
        created = create_key(user, scopes=["media:read"]).json()
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64) VALUES ('owner-phone', 'photo', '')",
            )
            conn.commit()
        resp = client.get("/api/v1/media/owner-phone", headers=key_headers(created["key"]))
        assert resp.status_code == 200
        assert len(resp.json()["media"]) == 1

    def test_command_with_write_scope_and_admin_role(self):
        user = self._owner_with_device()
        created = create_key(user, scopes=["devices:write"]).json()
        resp = client.post(
            "/api/v1/devices/owner-phone/commands",
            json={"command": "lock", "params": ""},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["command"] == "lock"

        with database.get_db_context() as conn:
            row = conn.execute("SELECT * FROM commands WHERE id=?", (resp.json()["command_id"],)).fetchone()
        assert row["command"] == "lock"
        assert row["status"] == "pending"
        assert row["delivery_channel"] == "poll"

    def test_command_wipe_rejected_for_keys(self):
        user = self._owner_with_device()
        created = create_key(user, scopes=["devices:write"]).json()
        resp = client.post(
            "/api/v1/devices/owner-phone/commands",
            json={"command": "wipe", "params": "CONFIRMED_WIPE"},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 400  # wipe needs dashboard step-up

    def test_command_unknown_command_422(self):
        user = self._owner_with_device()
        created = create_key(user, scopes=["devices:write"]).json()
        resp = client.post(
            "/api/v1/devices/owner-phone/commands",
            json={"command": "ghost_command"},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 422

    def test_device_only_share_stays_status_glance(self):
        owner = self._owner_with_device()
        viewer = register_user("viewer@example.com")
        # Grant a device_only share (privacy tier: no location).
        resp = client.post(
            "/api/dashboard/devices/owner-phone/shares",
            json={"email": "viewer@example.com", "role": "device_only"},
            headers=user_headers(owner["token"]),
        )
        assert resp.status_code == 200, resp.text

        created = create_key(viewer).json()
        resp = client.get("/api/v1/devices", headers=key_headers(created["key"]))
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert len(devices) == 1
        assert devices[0]["access_role"] == "device_only"
        assert devices[0]["lat"] is None and devices[0]["lng"] is None
        # Locations are off-limits entirely.
        resp = client.get("/api/v1/devices/owner-phone/locations", headers=key_headers(created["key"]))
        assert resp.status_code == 403

    def test_viewer_share_stays_read_only_through_write_key(self):
        """The RBAC intersection: even a devices:write key cannot command a
        device the account only views (spec §2/§4 — a viewer-shared device
        stays read-only for the key too)."""
        owner = self._owner_with_device()
        viewer = register_user("viewer2@example.com")
        resp = client.post(
            "/api/dashboard/devices/owner-phone/shares",
            json={"email": "viewer2@example.com", "role": "viewer"},
            headers=user_headers(owner["token"]),
        )
        assert resp.status_code == 200

        created = create_key(viewer, scopes=["devices:read", "devices:write"]).json()
        # Read works (viewer role ≥ viewer).
        resp = client.get("/api/v1/devices/owner-phone/locations", headers=key_headers(created["key"]))
        assert resp.status_code == 200
        # Write is denied (viewer < admin).
        resp = client.post(
            "/api/v1/devices/owner-phone/commands",
            json={"command": "lock"},
            headers=key_headers(created["key"]),
        )
        assert resp.status_code == 403


# ─── Rejection surface (F-02 family) ─────────────────────────────────────────


class TestRejectionSurface:
    def _key(self, scopes=None):
        user = register_user(f"reject-{secrets.token_hex(3)}@example.com")
        return create_key(user, scopes=scopes).json()["key"]

    def test_key_rejected_on_dashboard_routes(self):
        key = self._key()
        assert client.get("/api/dashboard/devices", headers=key_headers(key)).status_code == 401

    def test_key_rejected_on_auth_routes(self):
        key = self._key()
        assert client.get("/api/auth/me", headers=key_headers(key)).status_code == 401

    def test_key_rejected_on_metrics(self):
        key = self._key()
        assert client.get("/metrics", headers=key_headers(key)).status_code == 401

    def test_key_rejected_on_key_management(self):
        """A key can never mint or manage other keys (and cannot even list)."""
        key = self._key()
        resp = client.get("/api/account/api-keys", headers=key_headers(key))
        assert resp.status_code == 401

    def test_garbage_or_malformed_keys_rejected(self):
        assert client.get("/api/v1/devices", headers=key_headers("mtk_live_short")).status_code == 401
        assert client.get("/api/v1/devices", headers=key_headers("not-a-key")).status_code == 401
        assert client.get("/api/v1/devices", headers=key_headers("")).status_code == 401
        assert client.get("/api/v1/devices").status_code == 401

    def test_expired_key_rejected(self):
        user = register_user("expired@example.com")
        created = create_key(user).json()
        # Force the stored expiry into the past (the create model rejects past
        # timestamps, so this simulates time passing).
        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE api_keys SET expires_at=? WHERE id=?",
                ("2020-01-01T00:00:00+00:00", created["id"]),
            )
            conn.commit()
        assert client.get("/api/v1/devices", headers=key_headers(created["key"])).status_code == 401

    def test_raw_key_never_in_audit_log(self):
        user = register_user("leakcheck@example.com")
        created = create_key(user).json()
        # Use the key across several endpoints.
        client.get("/api/v1/devices", headers=key_headers(created["key"]))
        client.get("/api/v1/alerts", headers=key_headers(created["key"]))

        with database.get_db_context() as conn:
            audit_rows = conn.execute("SELECT * FROM audit_log").fetchall()
            error_rows = conn.execute("SELECT * FROM error_log").fetchall()
        blob = str([dict(r) for r in audit_rows]) + str([dict(r) for r in error_rows])
        assert created["key"] not in blob
        # The prefix is fine to log (it identifies the key without the secret).
        assert created["key_prefix"] in blob

    def test_rate_limit_429(self):
        user = register_user("ratelimit@example.com")
        created = create_key(user).json()
        headers = key_headers(created["key"])
        # The per-key bucket is 120 req/min. Fire 120 cheap data requests…
        for _ in range(120):
            resp = client.get("/api/v1/devices", headers=headers)
            assert resp.status_code == 200, resp.text
        # …and the 121st is throttled.
        resp = client.get("/api/v1/devices", headers=headers)
        assert resp.status_code == 429
