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
            f"/api/device/commands/{command_id}/ack", json={"status": "executed"}, headers=device_headers
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
            json={"device_id": "stats-device-1", "fingerprint": "fp-stats-1", "model": "Stats Phone"},
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
            json={"device_id": "stats-device-2", "fingerprint": "fp-stats-2", "model": "Stats Phone"},
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
