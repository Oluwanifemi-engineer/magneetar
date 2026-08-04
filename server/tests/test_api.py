"""
Magneetar API Tests
Tests for all server endpoints.
"""

# Set test environment before importing anything
import os
import secrets
import tempfile

from fastapi.testclient import TestClient

# Create a temporary database file for tests
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Override the settings module's DB_PATH
import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

# Import database module and set DB_PATH
import database  # noqa: E402

database.DB_PATH = test_db_path

# Initialize database
from database import init_db  # noqa: E402

init_db(test_db_path)

from auth import create_dashboard_tokens, create_device_tokens  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

# Test fixtures
TEST_API_KEY = os.environ["MT_API_KEY"]
TEST_DEVICE_ID = "test-device-001"


def get_auth_headers(api_key: str = None) -> dict:
    """Get headers with API key."""
    return {"x-api-key": api_key or TEST_API_KEY}


def get_device_headers(device_id: str = None) -> dict:
    """Get headers with device JWT token."""
    tokens = create_device_tokens(device_id or TEST_DEVICE_ID)
    return {"Authorization": f"Bearer {tokens['token']}"}


def get_dashboard_headers() -> dict:
    """Get headers with dashboard JWT token."""
    tokens = create_dashboard_tokens(TEST_API_KEY)
    return {"Authorization": f"Bearer {tokens['token']}"}


# ─── Health & Config ────────────────────────────────────────────────────────


class TestHealthEndpoint:
    def test_health_returns_online(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert "version" in data
        assert "uptime" in data
        assert "server_time" in data

    def test_health_no_auth_required(self):
        response = client.get("/health")
        assert response.status_code == 200


class TestConfigEndpoint:
    def test_config_returns_features(self):
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "app_version" in data
        assert "features_enabled" in data
        assert "sentinel" in data["features_enabled"]

    def test_config_version_matches_health(self):
        """Regression (F-08): /api/config used to hardcode app_version=1.2.0
        while /health reported 1.3.0 — the stale value silently killed the
        Android 'update available' nudge for 1.2.0 users. Both must now read
        the VERSION file (single source of truth)."""
        from main import APP_VERSION

        config = client.get("/api/config").json()
        health = client.get("/health").json()
        assert config["app_version"] == health["version"] == APP_VERSION


# ─── Device Registration ─────────────────────────────────────────────────────


class TestDeviceRegistration:
    def test_register_new_device(self):
        headers = get_auth_headers()
        response = client.post(
            "/api/device/register",
            json={
                "device_id": "new-test-device",
                "fingerprint": "test-fingerprint-123",
                "model": "Test Phone",
                "os_version": "Android 14",
                "app_version": "1.0.0",
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_existing_device_updates(self):
        headers = get_auth_headers()
        # Register once
        client.post(
            "/api/device/register",
            json={
                "device_id": "existing-device",
                "fingerprint": "fp123456789",
                "model": "Old Model",
            },
            headers=headers,
        )

        # Register again with updated info
        response = client.post(
            "/api/device/register",
            json={
                "device_id": "existing-device",
                "fingerprint": "fp987654321",
                "model": "New Model",
            },
            headers=headers,
        )
        assert response.status_code == 200

    def test_register_requires_api_key(self):
        response = client.post(
            "/api/device/register",
            json={
                "device_id": "no-auth-device",
                "fingerprint": "fingerprint123",
            },
        )
        assert response.status_code == 422 or response.status_code == 401

    def test_register_rejects_malformed_device_id(self):
        """Defense-in-depth: SQL-injection / whitespace / control-char device
        IDs must be rejected at registration (the Android app generates
        'mt-<8 hex>' and the simulator uses simple alphanumerics — neither
        ever needs exotic characters)."""
        headers = get_auth_headers()
        bad_ids = [
            "x' OR '1'='1",  # SQL injection
            "device with spaces",  # whitespace
            "dev;rm -rf /",  # shell metacharacters
            "a",  # too short (< 3)
            "x" * 80,  # too long (> 64)
            "\n<script>alert(1)</script>",  # log/HTML injection
        ]
        for bad in bad_ids:
            resp = client.post(
                "/api/device/register",
                json={"device_id": bad, "fingerprint": "fp-malformed", "model": "X"},
                headers=headers,
            )
            assert resp.status_code == 422, f"device_id {bad!r} → {resp.status_code} (expected 422)"

        # Legit formats still register fine (mt- prefix + simple names).
        # fingerprint must be >= 8 chars per the model — use a long one so
        # the 422s above are attributable to the device_id, not the fingerprint.
        # Note: the Pydantic model itself rejects dots, so "good" uses the
        # alphanumeric/hyphen/underscore charset the model AND the app allow.
        for good in ("mt-a1b2c3d4", "test-device-001", "device_with_underscores-1"):
            resp = client.post(
                "/api/device/register",
                json={"device_id": good, "fingerprint": "fp-good-123456", "model": "X"},
                headers=headers,
            )
            assert resp.status_code == 200, f"device_id {good!r} → {resp.status_code}"


# ─── Location Reports ────────────────────────────────────────────────────────


class TestLocationReport:
    def _ensure_device(self):
        """Create test device if it doesn't exist."""
        headers = get_auth_headers()
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "test-fp-003",
                "model": "Test Model",
            },
            headers=headers,
        )

    def test_post_location_valid(self):
        self._ensure_device()
        headers = get_device_headers()
        response = client.post(
            "/api/device/location",
            json={
                "device_id": TEST_DEVICE_ID,
                "lat": 9.0820,
                "lng": 8.6753,
                "accuracy": 10.0,
                "provider": "gps",
                "battery_percent": 85,
                "speed": 0.5,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_post_location_invalid_coords(self):
        headers = get_device_headers()
        response = client.post(
            "/api/device/location",
            json={
                "device_id": TEST_DEVICE_ID,
                "lat": 100.0,  # Invalid - out of range
                "lng": 8.6753,
            },
            headers=headers,
        )
        assert response.status_code == 422  # Validation error

    def test_post_location_requires_auth(self):
        response = client.post(
            "/api/device/location",
            json={
                "device_id": TEST_DEVICE_ID,
                "lat": 9.0820,
                "lng": 8.6753,
            },
        )
        assert response.status_code == 403 or response.status_code == 401


# ─── Commands ────────────────────────────────────────────────────────────────


class TestCommands:
    def test_issue_command(self):
        headers = get_dashboard_headers()
        response = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "ping",
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "command_id" in data

    def test_get_device_commands(self):
        # Issue a command first
        headers = get_dashboard_headers()
        client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "ping",
            },
            headers=headers,
        )

        # Get commands as device
        device_headers = get_device_headers()
        response = client.get(f"/api/device/commands/{TEST_DEVICE_ID}", headers=device_headers)
        assert response.status_code == 200
        data = response.json()
        assert "commands" in data

    def test_ack_command(self):
        # Issue command
        dash_headers = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "ping",
            },
            headers=dash_headers,
        )
        command_id = resp.json()["command_id"]

        # Ack as device
        device_headers = get_device_headers()
        response = client.post(
            f"/api/device/commands/{command_id}/ack",
            json={"status": "executed"},
            headers=device_headers,
        )
        assert response.status_code == 200

    def test_invalid_command_rejected(self):
        headers = get_dashboard_headers()
        response = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "invalid_command",
            },
            headers=headers,
        )
        assert response.status_code == 422  # Validation error

    def test_stale_pending_command_auto_expires(self):
        """A pending command past its expiry must show EXPIRED in history and
        must never be delivered by the device poll (regression: the ISO-8601
        'T+offset' expires_at format compared lexicographically against SQLite's
        space-separated datetime('now') always looked 'in the future', so stale
        commands were delivered and stayed PENDING forever)."""
        from datetime import datetime, timedelta, timezone

        dash = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "ping"},
            headers=dash,
        )
        cmd_id = resp.json()["command_id"]

        # Backdate expires_at beyond the expiry window, ISO format (exactly as
        # the server writes it).
        expired = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        with database.get_db_context() as conn:
            conn.execute("UPDATE commands SET expires_at=? WHERE id=?", (expired, cmd_id))
            conn.commit()

        # Dashboard history marks it EXPIRED
        history = client.get(f"/api/dashboard/commands/{TEST_DEVICE_ID}", headers=dash).json()
        row = next(c for c in history["commands"] if c["id"] == cmd_id)
        assert row["status"] == "expired"

        # Device poll no longer delivers it
        poll = client.get(f"/api/device/commands/{TEST_DEVICE_ID}", headers=get_device_headers()).json()
        assert all(c["id"] != cmd_id for c in poll["commands"])

    def test_pending_command_within_window_stays_pending(self):
        """A freshly issued command is still pending and pollable."""
        dash = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "ping"},
            headers=dash,
        )
        cmd_id = resp.json()["command_id"]
        history = client.get(f"/api/dashboard/commands/{TEST_DEVICE_ID}", headers=dash).json()
        row = next(c for c in history["commands"] if c["id"] == cmd_id)
        assert row["status"] == "pending"


# ─── Media ───────────────────────────────────────────────────────────────────


class TestMedia:
    def _ensure_device(self):
        """Create test device if it doesn't exist."""
        headers = get_auth_headers()
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "test-fp-002",
                "model": "Test Model",
            },
            headers=headers,
        )

    def test_upload_media(self):
        import base64

        self._ensure_device()
        # Create a small test image (1x1 pixel PNG)
        test_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        data_b64 = base64.b64encode(test_data).decode()

        headers = get_device_headers()
        response = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "photo",
                "data_b64": data_b64,
                "lat": 9.0820,
                "lng": 8.6753,
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "media_id" in data

    def test_get_media_list(self):
        headers = get_dashboard_headers()
        response = client.get(f"/api/dashboard/media/{TEST_DEVICE_ID}", headers=headers)
        assert response.status_code == 200
        assert "media" in response.json()


# ─── Authentication ──────────────────────────────────────────────────────────


class TestAuthentication:
    def test_dashboard_login_valid(self):
        response = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "refresh_token" in data

    def test_dashboard_login_invalid_key(self):
        response = client.post("/api/auth/login", json={"api_key": "invalid-key"})
        assert response.status_code == 401

    def test_token_refresh(self):
        # Login first
        login_resp = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        refresh_token = login_resp.json()["refresh_token"]

        # Refresh
        response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert "token" in response.json()


# ─── Security Hardening (F-02: no x-api-key admin backdoor) ──────────────────


class TestNoApiKeyBackdoor:
    """The master API key ships inside every APK, so it must NEVER grant
    dashboard access. Regression for F-02: an x-api-key header (or a token
    with an api_key_user subject) must be rejected on user/dashboard routes.
    """

    def test_x_api_key_header_rejected_on_dashboard_routes(self):
        """x-api-key alone must not authenticate dashboard routes."""
        response = client.get("/api/dashboard/devices", headers={"x-api-key": TEST_API_KEY})
        assert response.status_code == 401

    def test_x_api_key_header_rejected_on_me(self):
        """x-api-key alone must not authenticate user routes (/api/auth/me)."""
        response = client.get("/api/auth/me", headers={"x-api-key": TEST_API_KEY})
        assert response.status_code == 401

    def test_dashboard_jwt_from_login_is_admin(self):
        """The legitimate path — exchange the key for a dashboard JWT at the
        rate-limited login endpoint, then use Bearer."""
        login = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        assert login.status_code == 200
        token = login.json()["token"]

        response = client.get("/api/dashboard/devices", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_me_resolves_dashboard_subject_as_admin(self):
        """A dashboard JWT (subject 'dashboard:<hash>') maps to the admin
        profile so the operator dashboard's plan card keeps working."""
        login = client.post("/api/auth/login", json={"api_key": TEST_API_KEY})
        token = login.json()["token"]

        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["tier"] == "admin"


# ─── Security Hardening (F-06: FCM must not create devices) ─────────────────


class TestFcmNoDeviceCreation:
    """Regression for F-06: /api/device/fcm-token used to INSERT a placeholder
    device row for any arbitrary device_id (fingerprint='fcm_*'), so anyone
    could pollute the devices table. It must now reject unknown devices.
    """

    def test_fcm_token_unknown_device_rejected(self):
        """An unregistered device_id gets 401 and NO device row is created."""
        before = client.get("/api/dashboard/stats", headers=get_dashboard_headers()).json()["total_devices"]

        resp = client.post(
            "/api/device/fcm-token",
            json={
                "fcm_token": "fcm-pollution-token",
                "device_id": "never-registered-dev",
            },
            headers={"x-api-key": TEST_API_KEY},
        )
        assert resp.status_code == 401

        with database.get_db_context() as conn:
            assert conn.execute("SELECT 1 FROM devices WHERE id='never-registered-dev'").fetchone() is None
        after = client.get("/api/dashboard/stats", headers=get_dashboard_headers()).json()["total_devices"]
        assert after == before

    def test_fcm_token_shared_key_cannot_hijack_existing_device(self):
        """The public shared API key (api_key_user, no principal) must NOT be
        able to attach a push token to an EXISTING device — that would let an
        attacker with the embedded APK key receive a victim's theft alerts.
        Regression for the push-hijack variant of F-06.
        """
        victim = "fcm-victim-device"
        reg = client.post(
            "/api/device/register",
            json={
                "device_id": victim,
                "fingerprint": "fp-fcm-victim",
                "model": "FCM Victim",
                "device_key": "fcm-victim-key",
            },
            headers={"x-api-key": TEST_API_KEY},
        )
        assert reg.status_code == 200

        # Attacker tries to register THEIR token under the victim's device_id
        # using only the shared key — must be rejected even though the device
        # exists (existence is not ownership).
        resp = client.post(
            "/api/device/fcm-token",
            json={"fcm_token": "attacker-fcm-token", "device_id": victim},
            headers={"x-api-key": TEST_API_KEY},
        )
        assert resp.status_code == 401

        with database.get_db_context() as conn:
            hijack = conn.execute(
                "SELECT 1 FROM fcm_tokens WHERE device_id=? AND fcm_token=?",
                (victim, "attacker-fcm-token"),
            ).fetchone()
        assert hijack is None

    def test_fcm_token_registered_device_ok(self):
        """A real registered device can register FCM.

        Auth uses the device JWT from the register response (the production
        flow) rather than x-device-key: get_current_device_or_key resolves
        x-device-key via a function-local DB lookup, and under full-suite
        collection every test file rebinds the shared database.DB_PATH module
        global, so that lookup can read a different temp DB than the one the
        register wrote to (pre-existing suite isolation quirk). The JWT path
        performs no DB lookup, so the request lands in the same app-bound DB
        the register used.
        """
        device_id = "fcm-ok-device"
        reg = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-fcm-ok",
                "model": "FCM Test",
                "device_key": "fcm-ok-device-key",
            },
            headers={"x-api-key": TEST_API_KEY},
        )
        assert reg.status_code == 200
        token = reg.json()["token"]

        resp = client.post(
            "/api/device/fcm-token",
            json={"fcm_token": "fcm-ok-token", "device_id": device_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["device_id"] == device_id


# ─── Dashboard Endpoints ─────────────────────────────────────────────────────


class TestDashboard:
    def test_list_devices(self):
        headers = get_dashboard_headers()
        response = client.get("/api/dashboard/devices", headers=headers)
        assert response.status_code == 200
        assert "devices" in response.json()

    def test_get_stats(self):
        headers = get_dashboard_headers()
        response = client.get("/api/dashboard/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_devices" in data
        assert "active_devices" in data

    def test_stats_reflect_registered_devices(self):
        """Regression: stats must read the same SQLite data plane as every other
        endpoint. The old PostgreSQL branch returned 0/0/0 because the Docker
        Postgres sits empty while the live DB is SQLite."""
        client.post(
            "/api/device/register",
            json={
                "device_id": "stats-device-1",
                "fingerprint": "fp-stats-1",
                "model": "Stats Phone",
            },
            headers=get_auth_headers(),
        )
        data = client.get("/api/dashboard/stats", headers=get_dashboard_headers()).json()
        assert data["total_devices"] >= 1

    def test_stats_active_devices_respect_last_seen(self):
        """An offline device (last_seen > 5 min) must NOT count as active.
        Regression for the ISO-vs-SQLite timestamp comparison ('T' > ' ')."""
        from datetime import datetime, timedelta, timezone

        client.post(
            "/api/device/register",
            json={
                "device_id": "stats-device-2",
                "fingerprint": "fp-stats-2",
                "model": "Stats Phone",
            },
            headers=get_auth_headers(),
        )
        # Backdate last_seen to 15h ago, in the exact ISO format the server writes.
        stale = (datetime.now(timezone.utc) - timedelta(hours=15)).isoformat()
        with database.get_db_context() as conn:
            conn.execute("UPDATE devices SET last_seen=? WHERE id=?", (stale, "stats-device-2"))
            conn.commit()

        data = client.get("/api/dashboard/stats", headers=get_dashboard_headers()).json()
        # Cross-check against the ground truth directly in the DB.
        with database.get_db_context() as conn:
            recent = conn.execute(
                "SELECT COUNT(*) FROM devices WHERE datetime(last_seen) > datetime('now', '-5 minutes')"
            ).fetchone()[0]
        assert data["active_devices"] == recent


# ─── APK Download & Checksum ───────────────────────────────────────────────


class TestApkChecksum:
    def _mint_ticket(self):
        """Mint a signed download URL via /apk/ticket, or None if no APK staged."""
        resp = client.get("/apk/ticket")
        if resp.status_code == 404:
            return None
        assert resp.status_code == 200, f"ticket mint failed: {resp.text}"
        return resp.json()["url"]

    def test_checksum_pairs_with_served_bytes(self):
        """Whatever APK /apk/download serves, /apk/checksum must describe its
        exact sha256 + size — the pairing sideloaders rely on. Endpoint-driven
        so it holds whether or not an APK is staged."""
        import hashlib

        checksum_resp = client.get("/apk/checksum")
        if checksum_resp.status_code == 404:
            # No APK staged: no ticket is mintable, and an anonymous (ticketless)
            # download is rejected 403 (the gating itself), never served.
            assert client.get("/apk/download").status_code == 403
            assert self._mint_ticket() is None
            return

        data = checksum_resp.json()
        assert len(data["sha256"]) == 64
        int(data["sha256"], 16)  # valid lowercase hex
        assert data["size_bytes"] > 0
        assert isinstance(data["version"], str) and data["version"]

        url = self._mint_ticket()
        assert url, "ticket must be mintable when an APK is staged"
        dl = client.get(url)
        assert dl.status_code == 200
        assert hashlib.sha256(dl.content).hexdigest() == data["sha256"]
        assert len(dl.content) == data["size_bytes"]

    def test_download_requires_valid_ticket(self):
        """F-05 gating: /apk/download without a valid signed ticket is 403,
        including forged/expired signatures."""
        import time

        assert client.get("/apk/download").status_code == 403
        assert client.get("/apk/download?expires=9999999999&sig=deadbeef").status_code == 403

        # A genuinely signed URL is rejected once its window has lapsed.
        from main import _sign_apk_ticket

        past = int(time.time()) - 3600
        assert client.get(f"/apk/download?expires={past}&sig={_sign_apk_ticket(past)}").status_code == 403

    def test_checksum_stable_across_requests(self):
        """Repeated calls return a stable checksum (cache-consistent), and both
        endpoints agree nothing is downloadable when no APK is staged."""
        first = client.get("/apk/checksum")
        if first.status_code == 404:
            assert client.get("/apk/download").status_code == 403
            assert client.get("/apk/ticket").status_code == 404
            return
        second = client.get("/apk/checksum")
        assert second.status_code == 200
        assert first.json()["sha256"] == second.json()["sha256"]

    def test_checksum_cache_invalidates_on_file_change(self):
        """The checksum cache is keyed on (mtime, size): a replaced file with
        the same size but a newer mtime must produce a fresh digest."""
        import main

        fd, path = tempfile.mkstemp(suffix=".apk")
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(b"first-bytes")  # 11 bytes
            first, size = main._get_apk_checksum(path)
            assert size == 11
            assert main._get_apk_checksum(path)[0] == first  # cached

            with open(path, "wb") as f:
                f.write(b"other-bytes")  # still 11 bytes, different content
            future = os.path.getmtime(path) + 5
            os.utime(path, (future, future))
            assert main._get_apk_checksum(path)[0] != first
        finally:
            # Don't leave the temp path in the module-level cache.
            main._apk_checksum_cache.pop(path, None)
            if os.path.exists(path):
                os.remove(path)


# ─── Security: device deletion requires step-up password ────────────────────


class TestDeviceDeleteStepUp:
    """Deleting a device is destructive + privacy-sensitive: a stolen dashboard
    session alone must not destroy a device's history. The DELETE endpoint
    re-authenticates with the master API key (admin mode) or the account
    password (user mode) — same contract as media deletion.
    """

    def _register(self, device_id: str):
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-del-stepup",
                "model": "StepUp Test",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200

    def _exists(self, device_id: str) -> bool:
        with database.get_db_context() as conn:
            return conn.execute("SELECT 1 FROM devices WHERE id=?", (device_id,)).fetchone() is not None

    def test_delete_requires_password(self):
        device_id = "stepup-device-nopw"
        self._register(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/devices/{device_id}",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400  # password required
        assert self._exists(device_id), "device must survive a passwordless delete attempt"

    def test_delete_wrong_password_rejected(self):
        device_id = "stepup-device-wrong"
        self._register(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/devices/{device_id}",
            json={"password": "not-the-master-key"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 401
        assert self._exists(device_id), "device must survive a wrong-password delete attempt"

    def test_delete_with_master_api_key_succeeds(self):
        device_id = "stepup-device-ok"
        self._register(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/devices/{device_id}",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        assert not self._exists(device_id), "device must be gone after a verified delete"

    def test_delete_unknown_device_404(self):
        resp = client.request(
            "DELETE",
            "/api/dashboard/devices/never-registered-dev",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 404


class TestCommandDeleteStepUp:
    """Command history is an audit trail (wipe/lock/alarm) — deleting it must
    re-authenticate with a step-up password, exactly like media/device
    deletion. Pending commands are never erased by the 'clear finished' path.
    """

    def _register(self, device_id: str) -> str:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-cmd-stepup",
                "model": "Cmd Test",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200
        return resp.json()["token"]

    def _issue(self, device_id: str, command: str = "ping") -> int:
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": device_id, "command": command},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        return resp.json()["command_id"]

    def _count(self, device_id: str, status: str = None) -> int:
        with database.get_db_context() as conn:
            if status:
                return conn.execute(
                    "SELECT COUNT(*) FROM commands WHERE device_id=? AND status=?",
                    (device_id, status),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM commands WHERE device_id=?", (device_id,)).fetchone()[0]

    def _mark(self, command_id: int, status: str):
        with database.get_db_context() as conn:
            conn.execute("UPDATE commands SET status=? WHERE id=?", (status, command_id))
            conn.commit()

    def test_delete_single_requires_password(self):
        device_id = "cmd-del-nopw"
        self._register(device_id)
        cmd_id = self._issue(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/{cmd_id}",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400  # password required
        assert self._count(device_id) == 1, "command must survive a passwordless delete"

    def test_delete_single_wrong_password_rejected(self):
        device_id = "cmd-del-wrong"
        self._register(device_id)
        cmd_id = self._issue(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/{cmd_id}",
            json={"password": "wrong"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 401
        assert self._count(device_id) == 1

    def test_delete_single_succeeds(self):
        device_id = "cmd-del-ok"
        self._register(device_id)
        cmd_id = self._issue(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/{cmd_id}",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        assert self._count(device_id) == 0

    def test_clear_finished_keeps_pending(self):
        device_id = "cmd-clear-finished"
        self._register(device_id)
        done = self._issue(device_id)  # ping
        self._mark(done, "executed")
        self._issue(device_id)  # stays pending

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/device/{device_id}?only_finished=true",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1
        assert self._count(device_id, "pending") == 1, "pending command must survive"
        assert self._count(device_id) == 1

    def test_clear_all_includes_pending(self):
        device_id = "cmd-clear-all"
        self._register(device_id)
        self._issue(device_id)
        self._issue(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/device/{device_id}?only_finished=false",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        assert self._count(device_id) == 0

    def test_clear_finished_requires_password(self):
        device_id = "cmd-clear-nopw"
        self._register(device_id)
        self._issue(device_id)

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/device/{device_id}",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400
        assert self._count(device_id) == 1

    def test_clear_finished_wrong_password_rejected(self):
        device_id = "cmd-clear-wrong"
        self._register(device_id)
        done = self._issue(device_id)
        self._mark(done, "executed")

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/device/{device_id}",
            json={"password": "not-the-master-key"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 401
        assert self._count(device_id) == 1, "wrong password must preserve history"

    def test_delete_unknown_command_404(self):
        resp = client.request(
            "DELETE",
            "/api/dashboard/commands/99999999",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 404

    def test_cross_tenant_delete_forbidden(self):
        # A second user must NOT be able to delete another account's commands.
        device_id = "cmd-del-other"
        self._register(device_id)
        cmd_id = self._issue(device_id)

        # Local user registration (test_api.py has no shared helper; the
        # dashboard view for a user is scoped to their OWN devices, so a
        # different account hitting this command id must 403 at ownership).
        other = client.post(
            "/api/auth/register",
            json={
                "email": "cmd-other-owner@example.com",
                "password": "Test-Pass-12345",
            },
        )
        assert other.status_code == 200
        other_token = other.json()["token"]

        resp = client.request(
            "DELETE",
            f"/api/dashboard/commands/{cmd_id}",
            json={"password": "Test-Pass-12345"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp.status_code == 403


# ─── Geofences ───────────────────────────────────────────────────────────────


class TestGeofences:
    def test_create_geofence(self):
        headers = get_dashboard_headers()
        response = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": TEST_DEVICE_ID,
                "name": "Home",
                "center_lat": 9.0820,
                "center_lng": 8.6753,
                "radius_meters": 100,
                "is_safe_zone": True,
            },
            headers=headers,
        )
        assert response.status_code == 200
        assert "geofence_id" in response.json()

    def test_list_geofences(self):
        headers = get_dashboard_headers()
        response = client.get(f"/api/dashboard/geofences/{TEST_DEVICE_ID}", headers=headers)
        assert response.status_code == 200
        assert "geofences" in response.json()


# ─── Schema migrations on existing databases ────────────────────────────────


class TestSchemaMigration:
    def test_init_db_migrates_existing_database(self):
        """Regression: init_db must apply column migrations to a DB created
        before the columns existed. The old ensure_initialized short-circuit
        skipped init_db entirely when every TABLE was present, so migrations
        never landed on production databases — new features then 500'd with
        'no such column' (capture_armed, alert_channels, quiet_hours_*).
        """
        import sqlite3
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            # Old schema: devices table WITHOUT the newer columns
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY, alias TEXT, owner_id TEXT, last_seen TIMESTAMP)")
            conn.commit()
            conn.close()

            init_db(path)

            conn = sqlite3.connect(path)
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(devices)")}
            finally:
                conn.close()
            for expected in (
                "device_key_hash",
                "alert_channels",
                "quiet_hours_start",
                "capture_armed",
            ):
                assert expected in cols, f"migration did not add column: {expected}"
        finally:
            if os.path.exists(path):
                os.remove(path)


# ─── Armed Watch state (capture_armed plumbing) ─────────────────────────────


class TestCaptureArmedState:
    """The Armed Watch "product truth": the dashboard must show whether a
    device's camera|mic capture service is armed, because remote capture is
    only possible while it is (Android 14+ can't background-start one).
    """

    def _register_device(self, device_id: str) -> str:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-armed-123",
                "model": "Armed Test",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200
        return resp.json()["token"]

    def _device_row(self, device_id: str) -> dict:
        devices = client.get("/api/dashboard/devices", headers=get_dashboard_headers()).json()["devices"]
        return next(d for d in devices if d["id"] == device_id)

    def test_capture_armed_roundtrip_via_telemetry(self):
        device_id = "armed-device-telemetry"
        token = self._register_device(device_id)
        auth = {"Authorization": f"Bearer {token}"}

        # Device reports armed=True on a location ping
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.08,
                "lng": 8.67,
                "capture_armed": True,
            },
            headers=auth,
        )
        assert resp.status_code == 200
        assert self._device_row(device_id)["capture_armed"] is True

        # Owner disarms — the dashboard must flip to False
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.08,
                "lng": 8.67,
                "capture_armed": False,
            },
            headers=auth,
        )
        assert resp.status_code == 200
        assert self._device_row(device_id)["capture_armed"] is False

    def test_capture_armed_roundtrip_via_heartbeat(self):
        """Idle devices only send heartbeats — the armed state must also flow
        through /api/device/heartbeat so it never goes stale."""
        device_id = "armed-device-heartbeat"
        token = self._register_device(device_id)

        resp = client.post(
            "/api/device/heartbeat",
            json={"device_id": device_id, "battery_percent": 50, "capture_armed": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert self._device_row(device_id)["capture_armed"] is True

    def test_capture_armed_unknown_until_reported(self):
        """A device that never reports capture_armed stays null ("Unknown" in
        the UI) — the dashboard must not fabricate a state."""
        device_id = "armed-device-silent"
        self._register_device(device_id)
        assert self._device_row(device_id)["capture_armed"] is None

    def test_old_app_build_does_not_wipe_armed_state(self):
        """A telemetry ping WITHOUT the capture_armed field (old APK) must not
        reset a previously reported armed state to null — COALESCE keeps it."""
        device_id = "armed-device-legacy"
        token = self._register_device(device_id)
        auth = {"Authorization": f"Bearer {token}"}

        client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.08,
                "lng": 8.67,
                "capture_armed": True,
            },
            headers=auth,
        )
        # Old build: no capture_armed key at all
        resp = client.post(
            "/api/device/location",
            json={"device_id": device_id, "lat": 9.09, "lng": 8.68},
            headers=auth,
        )
        assert resp.status_code == 200
        assert self._device_row(device_id)["capture_armed"] is True


class TestCaptureCommandHonestAck:
    """Regression for the Armed Watch honesty contract: a capture command on
    an unarmed device must end as 'failed' — never a phantom 'executed'. The
    app acks failed + posts the re-arm prompt; the server must persist it.
    """

    def _ensure_device(self):
        """Create the shared test device if it doesn't exist, so these tests
        pass in isolation (the file's other classes also register it, but a
        -k filtered run may skip them)."""
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "fp-honest-ack",
                "model": "Honest Ack",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200

    def test_capture_command_failed_ack_visible_in_history(self):
        self._ensure_device()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "capture_photo"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        cmd_id = resp.json()["command_id"]

        # The device (unarmed) acks 'failed' honestly
        resp = client.post(
            f"/api/device/commands/{cmd_id}/ack",
            json={"status": "failed"},
            headers=get_device_headers(),
        )
        assert resp.status_code == 200

        history = client.get(f"/api/dashboard/commands/{TEST_DEVICE_ID}", headers=get_dashboard_headers()).json()
        row = next(c for c in history["commands"] if c["id"] == cmd_id)
        assert row["status"] == "failed"

    def test_failed_ack_command_not_redelivered(self):
        """An acked command (failed or executed) must never be re-delivered by
        the device poll — otherwise a failed capture would retry forever."""
        self._ensure_device()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "capture_audio"},
            headers=get_dashboard_headers(),
        )
        cmd_id = resp.json()["command_id"]

        client.post(
            f"/api/device/commands/{cmd_id}/ack",
            json={"status": "failed"},
            headers=get_device_headers(),
        )

        poll = client.get(f"/api/device/commands/{TEST_DEVICE_ID}", headers=get_device_headers()).json()
        assert all(c["id"] != cmd_id for c in poll["commands"])
