"""
Magneetar API Tests
Tests for all server endpoints.
"""

# Set test environment before importing anything
import os
import secrets
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Rate-limits are keyed per actor with a fixed window (step-up password
    verify 10/min, command issuance 20/min), and this file's tests — which
    share one dashboard actor and one DB — collectively consume far more than
    either budget across classes (destructive-action step-ups, the wipe
    gate, urgent-priority checks, and ack/redelivery flows). Clearing the
    buckets before each test keeps the suite deterministic without weakening
    enforcement: no test in THIS file asserts on rate limiting (that lives in
    test_media_delete.py / test_multi_user.py), so clearing here cannot mask
    a real regression. Same pattern as test_media_delete.py's table-clear
    fixture.

    NOTE: this deliberately uses the module-level `database` binding (the
    pre-eviction instance the app's routers imported at collection time), NOT
    `import database as _db` — under full-suite runs test_e2e evicts
    database/routes from sys.modules mid-collection, so a function-local
    import would resolve a fresh module whose DB_PATH points elsewhere and
    the clear would silently hit the wrong DB file."""
    with database.get_db_context() as conn:
        conn.execute("DELETE FROM rate_limits")
        conn.commit()
    yield


# Create a temporary database file for tests
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path
# Media files land in a temp dir (media_store.py resolves MT_MEDIA_DIR live
# from the environment at request time, so this works regardless of import
# order). Upload tests must never write into the repo tree.
test_media_dir = tempfile.mkdtemp(prefix="magneetar-test-media-")
os.environ["MT_MEDIA_DIR"] = test_media_dir

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

# Pre-eviction binding for the at-rest-encryption helper (same convention as
# evidence_builder above): test_e2e re-imports config with ITS OWN
# MT_ENCRYPTION_KEY, so encrypting with the live (post-eviction) module and
# decrypting through the app's (pre-eviction) module fails with
# "Location decrypt failed ... (MT_ENCRYPTION_KEY rotated?)". The CSV-export
# encrypted-row test must mint ciphertext with the SAME instance the app's
# read paths use.
from encryption import encrypt_location_for_store as _encrypt_location_for_store  # noqa: E402

# Bind evidence_builder at MODULE level (pre-eviction). test_e2e evicts
# evidence/database/routes from sys.modules mid-collection; a function-local
# `from evidence import evidence_builder` at test-run time would resolve the
# post-eviction module, which binds a different database module than the
# client's router — create_case then hits a different DB than the device
# registration wrote to (FK failures under full-suite runs). Binding here
# captures the same pre-eviction instance the app's dashboard router holds.
from evidence import evidence_builder  # noqa: E402

# Same pre-eviction binding for the APK ticket signer: test_e2e evicts
# config/main and re-imports them with a DIFFERENT MT_JWT_SECRET, so a
# function-local `from main import _sign_apk_ticket` (post-eviction) signs
# with e2e's key while the app's route still validates with the pre-eviction
# one — a genuinely signed URL would be rejected as forged. Binding here
# captures the same pre-eviction signer the app validates against.
from main import _sign_apk_ticket  # noqa: E402
from main import app  # noqa: E402

# Same pre-eviction binding for the devices router, so a monkeypatched
# broadcast_to_dashboards actually patches what the app's route calls (a
# function-local `import routes.devices` resolves the post-eviction module
# whose broadcast the app never invokes).
from routes import devices as devices_routes  # noqa: E402

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
        assert "server_time" in data
        # F-08: uptime is intentionally NOT public (it reveals deploy timing);
        # it stays available to operators via the admin-gated /api/metrics.
        assert "uptime" not in data

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

    def test_config_does_not_expose_sms_relay_number_anonymously(self):
        """F-08 family: the SMS relay number must NOT be disclosed to
        anonymous requests — an unauthenticated scraper of /api/config learns
        nothing about the Twilio relay. Only a registered device presenting
        its x-device-key sees the number (its sender allowlist needs it);
        everyone else gets an empty string and the app falls back to code-only
        SMS verification."""
        # Patch the MODULE-LEVEL `config` binding (imported at the top of this
        # file, pre-eviction) — a function-local re-import under full-suite
        # runs resolves the post-eviction config module whose settings object
        # the app's routes do NOT hold (same eviction pattern as database).
        saved = config.settings.TWILIO_SMS_FROM
        try:
            config.settings.TWILIO_SMS_FROM = "+15551234567"
            # 1) Anonymous request → relay number stays empty.
            assert client.get("/api/config").json()["sms_relay_number"] == ""

            # 2) Unknown/forged device key → still empty.
            resp = client.get("/api/config", headers={"x-device-key": "not-a-registered-device-key"})
            assert resp.status_code == 200
            assert resp.json()["sms_relay_number"] == ""

            # 3) A REGISTERED device's key → the number, mirrored exactly.
            device_id = f"cfg-dev-{secrets.token_hex(4)}"
            device_key = f"cfg-key-{secrets.token_hex(8)}"
            reg = client.post(
                "/api/device/register",
                json={"device_id": device_id, "fingerprint": f"fp-{device_id}", "device_key": device_key},
                headers=get_auth_headers(),
            )
            assert reg.status_code == 200, reg.text
            resp = client.get("/api/config", headers={"x-device-key": device_key})
            assert resp.status_code == 200
            assert resp.json()["sms_relay_number"] == "+15551234567"

            # 4) Unset relay → empty even for a registered device (the app
            #    then falls back to code-only verification).
            config.settings.TWILIO_SMS_FROM = ""
            resp = client.get("/api/config", headers={"x-device-key": device_key})
            assert resp.json()["sms_relay_number"] == ""
        finally:
            config.settings.TWILIO_SMS_FROM = saved


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

    def test_ws_broadcast_carries_fused_accuracy(self):
        """Regression (accuracy gap): the live WebSocket location broadcast
        used to omit accuracy_horizontal/provider/bearing/confidence, so the
        dashboard's real-time map + panel always rendered "±?m" even though
        the device reports its Kalman-fused accuracy on every ping. The
        broadcast payload must carry them so the live view shows the truth."""
        from unittest.mock import AsyncMock

        self._ensure_device()
        captured = {}
        # Keep the ORIGINAL reference to restore exactly what was bound before
        # (see the pre-eviction import note at the top of this file).
        original_broadcast = devices_routes.broadcast_to_dashboards

        async def fake_broadcast(message):
            captured.update(message)

        # Patch the module-level binding the app's route actually calls (see
        # the pre-eviction import note at the top of this file).
        devices_routes.broadcast_to_dashboards = AsyncMock(side_effect=fake_broadcast)
        try:
            resp = client.post(
                "/api/device/location",
                json={
                    "device_id": TEST_DEVICE_ID,
                    "lat": 9.0820,
                    "lng": 8.6753,
                    "accuracy_horizontal": 7.5,
                    "provider": "gps",
                    "bearing": 42.0,
                    "confidence_level": "HIGH",
                },
                headers=get_device_headers(),
            )
            assert resp.status_code == 200
        finally:
            # Restore so other tests keep broadcasting to real dashboards.
            devices_routes.broadcast_to_dashboards = original_broadcast

        assert captured, "broadcast must have fired"
        data = captured["data"]
        assert data["accuracy_horizontal"] == 7.5
        assert data["provider"] == "gps"
        assert data["bearing"] == 42.0
        assert data["confidence_level"] == "HIGH"


# ─── Simplified Location Reports ─────────────────────────────────────────────


class TestLocationReportSimple:
    """Regression (shipped once): /api/device/location/simple INSERTed into a
    non-existent `accuracy` column and 500'd on every call. It must persist a
    location and update last_seen."""

    def _ensure_device(self):
        headers = get_auth_headers()
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "fp-simple-loc",
                "model": "Simple Loc",
            },
            headers=headers,
        )

    def test_post_location_simple_persists(self):
        self._ensure_device()
        resp = client.post(
            "/api/device/location/simple",
            json={
                "device_id": TEST_DEVICE_ID,
                "lat": 9.0820,
                "lng": 8.6753,
                "accuracy": 12.0,
                "provider": "gps",
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ok"

        # The row must exist with the accuracy mapped to accuracy_horizontal
        with database.get_db_context() as conn:
            row = conn.execute(
                "SELECT * FROM locations WHERE device_id=? AND provider='gps' ORDER BY id DESC LIMIT 1",
                (TEST_DEVICE_ID,),
            ).fetchone()
        assert row is not None
        assert row["accuracy_horizontal"] == 12.0
        assert row["server_timestamp"] is not None

    def test_post_location_simple_device_mismatch_403(self):
        """The authenticated device_id must match the body's device_id — a
        device must not be able to write locations under another device's id."""
        self._ensure_device()
        resp = client.post(
            "/api/device/location/simple",
            json={
                "device_id": "some-other-device",
                "lat": 9.0,
                "lng": 8.6,
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 403


# ─── Evidence PDF Generation ────────────────────────────────────────────────


class TestEvidencePdf:
    """Regression (shipped once): the evidence PDF path SELECTed non-existent
    `accuracy`/`timestamp` columns from locations and 500'd. Generating a
    report must return a valid application/pdf even when the device has
    location history."""

    def _ensure_device_with_locations(self):
        headers = get_auth_headers()
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "fp-pdf-dev",
                "model": "PDF Test",
            },
            headers=headers,
        )
        # Seed a couple of location rows (the failing query only triggers
        # when the device has a location trail).
        dev_headers = get_device_headers()
        for lat in (9.08, 9.09):
            client.post(
                "/api/device/location",
                json={
                    "device_id": TEST_DEVICE_ID,
                    "lat": lat,
                    "lng": 8.67,
                    "accuracy": 10.0,
                },
                headers=dev_headers,
            )

    def test_generate_pdf_returns_pdf(self):
        self._ensure_device_with_locations()
        resp = client.post(
            f"/api/dashboard/evidence/{TEST_DEVICE_ID}/generate-pdf",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.content.startswith(b"%PDF")

    def test_compile_pdf_data_maps_real_columns(self):
        """compile_pdf_data must return location rows keyed by the names the
        PDF renderer reads (timestamp, lat, lng, speed, battery_percent)."""
        self._ensure_device_with_locations()

        case_id = evidence_builder.create_case(TEST_DEVICE_ID)
        data = evidence_builder.compile_pdf_data(case_id)
        assert data is not None
        assert data["locations"], "seeded locations must appear in PDF data"
        loc = data["locations"][0]
        assert "timestamp" in loc, "renderer needs a 'timestamp' key"
        assert "lat" in loc and "lng" in loc
        assert "battery_percent" in loc

    def test_compile_pdf_data_includes_command_timeline_and_alias(self):
        """The Recovery Dossier must include the owner's action record (remote
        commands issued + outcomes) and the device alias — a police officer
        wants to see "Mum's phone" and the lock/siren/wipe sequence, not just
        coordinates."""
        self._ensure_device_with_locations()
        # Alias the device so the dossier can show a friendly name.
        dash = get_dashboard_headers()
        resp = client.patch(
            f"/api/dashboard/devices/{TEST_DEVICE_ID}/alias",
            json={"alias": "Mum's phone"},
            headers=dash,
        )
        assert resp.status_code == 200, resp.text

        # Seed two commands with different statuses (alarm executed, wipe
        # pending) — the action record the dossier must carry. Wipe is a
        # destructive command, so it needs the step-up master API key.
        for cmd, params, password in (("alarm", "", None), ("wipe", "CONFIRMED_WIPE", TEST_API_KEY)):
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": TEST_DEVICE_ID, "command": cmd, "params": params, "password": password},
                headers=dash,
            )
            assert resp.status_code == 200, resp.text

        case_id = evidence_builder.create_case(TEST_DEVICE_ID)
        data = evidence_builder.compile_pdf_data(case_id)
        assert data is not None
        assert data["device"]["alias"] == "Mum's phone"
        cmds = data["commands"]
        assert len(cmds) >= 2
        kinds = {c["command"] for c in cmds}
        assert "alarm" in kinds and "wipe" in kinds
        wipe = next(c for c in cmds if c["command"] == "wipe")
        assert wipe["params"] == "CONFIRMED_WIPE"
        assert wipe["status"] in ("pending", "executed")
        assert "issued_at" in wipe, "command timeline needs issued_at for the PDF"


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

    def test_admin_command_for_missing_device_is_404_not_500(self):
        """Regression: the admin scope used to skip the device existence check
        in _assert_device_access, so a command for a nonexistent device raised
        an unhandled FOREIGN KEY IntegrityError (500). It must be a clean 404."""
        response = client.post(
            "/api/dashboard/command",
            json={"device_id": "no-such-device-xyz", "command": "ping"},
            headers=get_dashboard_headers(),
        )
        assert response.status_code == 404

    def test_admin_geofence_for_missing_device_is_404_not_500(self):
        """Same admin-existence regression for geofence creation."""
        response = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": "no-such-device-xyz",
                "name": "Ghost",
                "center_lat": 6.5,
                "center_lng": 3.3,
                "radius_meters": 100,
                "is_safe_zone": True,
            },
            headers=get_dashboard_headers(),
        )
        assert response.status_code == 404

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

    def test_reack_is_idempotent_and_never_redelivered(self):
        """Server half of the at-most-once contract (the Android half is
        RecentCommandTracker): when a device loses an ack and re-acks the same
        command on a later poll (the 'executes in loops' bug fix), the server
        must accept the duplicate ack (200, idempotent), keep the command in
        the executed state, and never re-deliver it — so a lost ack can never
        cause a second execution."""
        # Self-sufficient under -k filters: the commands FK requires the
        # device row, which other classes register only when they run.
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "fp-reack",
                "model": "ReAck",
            },
            headers=get_auth_headers(),
        )
        dash = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "ping"},
            headers=dash,
        )
        cmd_id = resp.json()["command_id"]

        # Pending + pollable before the ack.
        poll = client.get(f"/api/device/commands/{TEST_DEVICE_ID}", headers=get_device_headers()).json()
        assert any(c["id"] == cmd_id for c in poll["commands"])

        # First ack lands.
        first = client.post(
            f"/api/device/commands/{cmd_id}/ack",
            json={"status": "executed"},
            headers=get_device_headers(),
        )
        assert first.status_code == 200

        # The device lost the response and re-acks on the next poll — the
        # server must accept it as an idempotent no-op (this is exactly what
        # RecentCommandTracker.statusOf re-sends).
        second = client.post(
            f"/api/device/commands/{cmd_id}/ack",
            json={"status": "executed"},
            headers=get_device_headers(),
        )
        assert second.status_code == 200

        # Status stays executed, and the poll never delivers it again.
        with database.get_db_context() as conn:
            row = conn.execute("SELECT status FROM commands WHERE id=?", (cmd_id,)).fetchone()
        assert row["status"] == "executed"
        poll2 = client.get(f"/api/device/commands/{TEST_DEVICE_ID}", headers=get_device_headers()).json()
        assert all(c["id"] != cmd_id for c in poll2["commands"])

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

    def test_phantom_commands_are_not_valid(self):
        """Regression (dead API surface): the server used to accept commands
        the Android app could never execute (phantom_on/off, fake_shutdown,
        location_burst_stop, capture_photo_rear) — every one always acked
        'failed', so the dashboard could queue commands that could NEVER work.
        The valid set must match what TrackingService.handleCommand implements."""
        headers = get_dashboard_headers()
        for dead in (
            "phantom_on",
            "phantom_off",
            "fake_shutdown",
            "location_burst_stop",
            "capture_photo_rear",
        ):
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": TEST_DEVICE_ID, "command": dead},
                headers=headers,
            )
            assert resp.status_code == 422, f"{dead} must be rejected (got {resp.status_code})"

    def test_wipe_requires_password(self):
        """Wipe is a factory reset — the most destructive command. Like device
        deletion it must step-up re-authenticate; a stolen dashboard session
        alone must never be able to wipe a device."""
        headers = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "wipe",
                "params": "CONFIRMED_WIPE",
            },
            headers=headers,
        )
        assert resp.status_code == 400  # password required

    def test_wipe_wrong_password_rejected(self):
        headers = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "wipe",
                "params": "CONFIRMED_WIPE",
                "password": "not-the-master-key",
            },
            headers=headers,
        )
        assert resp.status_code == 401

    def test_wipe_with_master_api_key_succeeds(self):
        headers = get_dashboard_headers()
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": TEST_DEVICE_ID,
                "command": "wipe",
                "params": "CONFIRMED_WIPE",
                "password": TEST_API_KEY,
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

        # And the queued wipe carries priority 1 (executes before pings).
        with database.get_db_context() as conn:
            row = conn.execute("SELECT priority FROM commands WHERE id=?", (resp.json()["command_id"],)).fetchone()
        assert row["priority"] == 1

    def test_urgent_commands_priority_one(self):
        """wipe/lock/alarm/capture must jump the queue (device poll orders by
        priority ASC) so they execute before pings in a burst."""
        dash = get_dashboard_headers()
        for cmd_name in (
            "lock",
            "alarm",
            "capture_photo",
            "capture_audio",
            "capture_photo_front",
        ):
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": TEST_DEVICE_ID, "command": cmd_name},
                headers=dash,
            )
            assert resp.status_code == 200, resp.text
            with database.get_db_context() as conn:
                row = conn.execute(
                    "SELECT priority FROM commands WHERE id=?",
                    (resp.json()["command_id"],),
                ).fetchone()
            assert row["priority"] == 1, f"{cmd_name} should be priority 1, got {row['priority']}"

        # Non-urgent commands keep the default priority.
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": TEST_DEVICE_ID, "command": "ping"},
            headers=dash,
        )
        with database.get_db_context() as conn:
            row = conn.execute("SELECT priority FROM commands WHERE id=?", (resp.json()["command_id"],)).fetchone()
        assert row["priority"] == 5

    def test_sms_relay_routes_offline_command(self, monkeypatch):
        """When a device is offline and the owner enabled SMS commands with a
        phone number, issue_command must ALSO deliver the command over SMS
        (MAGNET wire format) and mark delivery_channel='sms' so the poll never
        double-delivers it."""

        device_id = "sms-relay-device"
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-relay",
                "model": "SMS Relay",
                "device_key": "sms-relay-key",
            },
            headers=get_auth_headers(),
        )
        # Enable the relay + set the phone number.
        resp = client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text

        # Backdate last_seen so the device looks offline.
        from datetime import datetime, timedelta, timezone

        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        import sms_relay

        sent = {}
        original = sms_relay.send_command_sms

        def fake_send(to, body):
            sent["to"] = to
            sent["body"] = body
            return True

        sms_relay.send_command_sms = fake_send
        try:
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "alarm"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["delivery"] == "sms"
        assert data["sms_delivered"] is True

        # The SMS body must carry the pairing code derived from the device key
        # (first 8 hex of SHA-256) + the command id + the command name.
        import hashlib

        code = hashlib.sha256(b"sms-relay-key").hexdigest()[:8]
        assert sent["to"] == "+2348012345678"
        assert sent["body"] == f"MAGNET {code} CMD {data['command_id']} alarm"

        # delivery_channel='sms' is persisted → the device poll excludes it.
        poll = client.get(f"/api/device/commands/{device_id}", headers=get_device_headers(device_id)).json()
        assert all(c["id"] != data["command_id"] for c in poll["commands"])

    def test_sms_relay_skipped_when_disabled_or_online(self, monkeypatch):
        """SMS routing only fires when the owner enabled it AND the device is
        offline — an online device (or one without the relay configured) uses
        the normal poll channel and costs nothing."""

        device_id = "sms-relay-online"
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-online",
                "model": "SMS",
            },
            headers=get_auth_headers(),
        )
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )

        import sms_relay

        sent = {}
        original = sms_relay.send_command_sms

        def fake_send(to, body):
            sent["to"] = to
            sent["body"] = body
            return True

        sms_relay.send_command_sms = fake_send
        try:
            # Device just registered → last_seen is now → ONLINE → no SMS.
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "ping"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.status_code == 200, resp.text
        assert resp.json()["delivery"] == "poll"
        assert not sent, "online device must use the poll channel, not SMS"

        # Disabled relay → never SMS, even offline.
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "", "sms_commands_enabled": False},
            headers=get_dashboard_headers(),
        )
        from datetime import datetime, timedelta, timezone

        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        sms_relay.send_command_sms = fake_send
        try:
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "ping"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.json()["delivery"] == "poll"
        assert not sent

    def test_sms_relay_send_failure_falls_back_to_poll(self, monkeypatch):
        """Regression (stranded-command bug): a failed SMS send used to leave
        the command stamped delivery_channel='sms', which excludes it from the
        device poll FOREVER — never executable, never retryable by the normal
        channel. It must fall back to the poll channel (with the poll expiry)
        so the command stays deliverable the moment the device returns, while
        sms_delivered=false tells the operator the SMS failed."""

        device_id = "sms-relay-fail"
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-fail",
                "model": "SMS",
                "device_key": "fail-key",
            },
            headers=get_auth_headers(),
        )
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        from datetime import datetime, timedelta, timezone

        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        import sms_relay

        original = sms_relay.send_command_sms
        sms_relay.send_command_sms = lambda to, body: False
        try:
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "alarm"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.status_code == 200, resp.text
        assert resp.json()["delivery"] == "poll", "failed SMS must fall back to poll"
        assert resp.json()["sms_delivered"] is False
        # The command row still exists (queued, not lost) AND is now poll-
        # deliverable with the poll (not 24h SMS) expiry.
        with database.get_db_context() as conn:
            row = conn.execute(
                "SELECT status, delivery_channel, expires_at FROM commands WHERE id=?",
                (resp.json()["command_id"],),
            ).fetchone()
        assert row["status"] == "pending"
        assert row["delivery_channel"] == "poll"

        # It is pollable — the device can now fetch it (not stranded).
        poll = client.get(f"/api/device/commands/{device_id}", headers=get_device_headers(device_id)).json()
        assert any(c["id"] == resp.json()["command_id"] for c in poll["commands"])

        # Alarm (sensitive) gets the 5-minute poll expiry, not 24h.
        import datetime as _dt

        row_expiry = row["expires_at"]
        age = _dt.datetime.now(_dt.timezone.utc) - _dt.datetime.fromisoformat(row_expiry)
        assert age < _dt.timedelta(minutes=10), "failed-SMS fallback must re-stamp poll expiry"

    def test_sms_relay_rate_limited_per_device(self, monkeypatch):
        """Each device may only relay 5 SMS commands per minute — the shared
        20/min dashboard-command budget is NOT enough to stop one user firing
        ~28k SMS/day at one number through the relay (cost/abuse vector)."""

        device_id = "sms-relay-ratelimit"
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-rl",
                "model": "SMS",
                "device_key": "rl-key",
            },
            headers=get_auth_headers(),
        )
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        from datetime import datetime, timedelta, timezone

        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        import sms_relay

        original = sms_relay.send_command_sms
        sms_relay.send_command_sms = lambda to, body: True
        try:
            for _ in range(5):
                resp = client.post(
                    "/api/dashboard/command",
                    json={"device_id": device_id, "command": "alarm"},
                    headers=get_dashboard_headers(),
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["delivery"] == "sms"

            # 6th SMS relay in the same minute → throttled.
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "alarm"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.status_code == 429
        assert "SMS" in resp.json()["detail"]

    def test_sms_relay_skipped_for_keyless_device(self, monkeypatch):
        """A device with NO device_key_hash can never verify the MAGNET
        pairing code on-device, so the relay must not route to it (the SMS
        would be ignored and the command stranded on the SMS channel)."""

        device_id = "sms-relay-keyless"
        # Register WITHOUT a device_key → device_key_hash stays NULL.
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-keyless",
                "model": "SMS",
            },
            headers=get_auth_headers(),
        )
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        from datetime import datetime, timedelta, timezone

        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        import sms_relay

        sent = {}
        original = sms_relay.send_command_sms

        def fake_send(to, body):
            sent["to"] = to
            return True

        sms_relay.send_command_sms = fake_send
        try:
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "alarm"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original

        assert resp.status_code == 200, resp.text
        assert resp.json()["delivery"] == "poll", "keyless device must use poll, not SMS"
        assert not sent, "no SMS may be sent to a keyless device"

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


class TestMediaStorageRefactor:
    """v1.4 media refactor E2E: bytes land on DISK (file_path/file_size), the
    SQLite row stays lean (data_b64 empty for new rows), read-back serves the
    exact bytes, and oversized / mismatched payloads are rejected with the
    right status codes (413/415)."""

    def _ensure_device(self):
        headers = get_auth_headers()
        client.post(
            "/api/device/register",
            json={
                "device_id": TEST_DEVICE_ID,
                "fingerprint": "fp-media-refactor",
                "model": "Media Refactor",
            },
            headers=headers,
        )

    def test_upload_persists_to_disk_not_sqlite(self):
        import base64

        self._ensure_device()
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
        resp = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "photo",
                "data_b64": base64.b64encode(png).decode(),
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 200, resp.text
        media_id = resp.json()["media_id"]

        with database.get_db_context() as conn:
            row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        assert row["file_path"], "new media rows must carry a file_path"
        assert row["file_size"] == len(png)
        assert row["data_b64"] == "", "new rows must NOT duplicate bytes into SQLite"

        # The file exists on disk with the exact bytes.
        import os as _os

        full = _os.path.join(_os.environ["MT_MEDIA_DIR"], row["file_path"])
        assert _os.path.isfile(full)
        with open(full, "rb") as f:
            assert f.read() == png

    def test_media_file_read_back_returns_exact_bytes(self):
        import base64

        self._ensure_device()
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 300
        media_id = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "photo",
                "data_b64": base64.b64encode(png).decode(),
            },
            headers=get_device_headers(),
        ).json()["media_id"]

        fetched = client.get(f"/api/dashboard/media/file/{media_id}", headers=get_dashboard_headers())
        assert fetched.status_code == 200
        assert fetched.json()["data_b64"] == base64.b64encode(png).decode()
        assert fetched.json()["sha256_hash"] is not None

    def test_legacy_base64_row_still_reads_back(self):
        """Pre-refactor rows (data_b64 populated, file_path NULL) must keep
        working through the same endpoint — no data loss on upgrade."""
        import base64

        self._ensure_device()
        legacy_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64, timestamp) VALUES (?, 'photo', ?, datetime('now'))",
                (TEST_DEVICE_ID, base64.b64encode(legacy_png).decode()),
            )
            conn.commit()
            media_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        fetched = client.get(f"/api/dashboard/media/file/{media_id}", headers=get_dashboard_headers())
        assert fetched.status_code == 200
        assert fetched.json()["data_b64"] == base64.b64encode(legacy_png).decode()

    def test_oversized_upload_rejected_413(self):
        import base64

        self._ensure_device()
        huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * (15 * 1024 * 1024)  # > 15MB photo cap
        resp = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "photo",
                "data_b64": base64.b64encode(huge).decode(),
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 413, resp.text

    def test_wrong_magic_rejected_415(self):
        import base64

        self._ensure_device()
        resp = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "photo",
                "data_b64": base64.b64encode(b"nope not an image").decode(),
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 415, resp.text

    def test_audio_upload_magic_validated(self):
        import base64

        self._ensure_device()
        mp3 = b"ID3\x04\x00\x00\x00" + b"\x00" * 100
        resp = client.post(
            "/api/device/media",
            json={
                "device_id": TEST_DEVICE_ID,
                "type": "audio",
                "data_b64": base64.b64encode(mp3).decode(),
            },
            headers=get_device_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["media_id"] > 0


class TestUnownedDeviceCap:
    """F-07: the master API key ships inside every APK (public), so anyone
    can register devices. The unowned-device cap bounds that storage-pollution
    surface — account-linked devices are bounded by the per-user limit instead."""

    def test_cap_blocks_unowned_flood(self):
        # Module-level `database` binding (pre-eviction instance the app's
        # routers use — a function-local import resolves the post-eviction
        # module whose DB_PATH points at another file's DB under full-suite
        # runs, and the cap count would read the wrong table).
        with database.get_db_context() as conn:
            unowned = conn.execute("SELECT COUNT(*) FROM devices WHERE owner_id IS NULL").fetchone()[0]
        saved = config.settings.MAX_UNOWNED_DEVICES
        config.settings.MAX_UNOWNED_DEVICES = unowned + 2
        try:
            for i in range(2):
                resp = client.post(
                    "/api/device/register",
                    json={
                        "device_id": f"unowned-cap-{i}",
                        "fingerprint": f"fp-unowned-{i}",
                    },
                    headers=get_auth_headers(),
                )
                assert resp.status_code == 200, resp.text
            # One over the cap → 403, and NO row created.
            resp = client.post(
                "/api/device/register",
                json={
                    "device_id": "unowned-cap-overflow",
                    "fingerprint": "fp-unowned-overflow",
                },
                headers=get_auth_headers(),
            )
            assert resp.status_code == 403
            with database.get_db_context() as conn:
                assert conn.execute("SELECT 1 FROM devices WHERE id='unowned-cap-overflow'").fetchone() is None
        finally:
            config.settings.MAX_UNOWNED_DEVICES = saved

    def test_account_linked_registration_ignores_cap(self):
        """A device registered WITH a user token is bounded by the per-user
        limit, not the unowned cap — even when the cap is tiny."""
        # Register an account + device token (registration links ownership).
        email = "cap-owner@test.dev"
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": "CapOwner123", "display_name": "Cap"},
        )
        assert reg.status_code == 200
        user_token = reg.json()["token"]

        saved = config.settings.MAX_UNOWNED_DEVICES
        config.settings.MAX_UNOWNED_DEVICES = 0  # nothing unowned allowed
        try:
            resp = client.post(
                "/api/device/register",
                json={"device_id": "cap-owned-device", "fingerprint": "fp-cap-owned"},
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "x-api-key": TEST_API_KEY,
                },
            )
        finally:
            config.settings.MAX_UNOWNED_DEVICES = saved
        assert resp.status_code == 200, resp.text


class TestEvidenceRetentionPurge:
    """v1.4: the retention purge must NOT delete evidence belonging to an
    ACTIVE evidence case — a forensic case must never lose its photos/audio
    while open. Closed-case and orphaned media age out normally."""

    def test_active_case_media_survives_purge(self):
        client.post(
            "/api/device/register",
            json={"device_id": "purge-device", "fingerprint": "fp-purge", "model": "P"},
            headers=get_auth_headers(),
        )
        with database.get_db_context() as conn:
            case_id = evidence_builder.create_case("purge-device")
            # Media rows with a very old timestamp: one tied to an ACTIVE
            # case, one with NO case, one tied to a CLOSED case.
            closed_id = evidence_builder.create_case("purge-device")
            conn.execute("UPDATE evidence_cases SET status='closed' WHERE id=?", (closed_id,))
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64, timestamp, evidence_case_id) "
                "VALUES ('purge-device', 'photo', 'AAAA', '2020-01-01 00:00:00', ?)",
                (case_id,),
            )
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64, timestamp) "
                "VALUES ('purge-device', 'photo', 'BBBB', '2020-01-01 00:00:00')",
            )
            conn.execute(
                "INSERT INTO media (device_id, type, data_b64, timestamp, evidence_case_id) "
                "VALUES ('purge-device', 'photo', 'CCCC', '2020-01-01 00:00:00', ?)",
                (closed_id,),
            )
            conn.commit()

        # Module-level `database` binding for the same eviction reason as the
        # cap test: purge must run against the SAME DB the rows above were
        # inserted into.
        result = database.purge_old_data(0)  # 0-day retention: everything old is stale

        with database.get_db_context() as conn:
            remaining = [
                r["data_b64"]
                for r in conn.execute("SELECT data_b64 FROM media WHERE device_id='purge-device'").fetchall()
            ]
        # Only the active-case photo survives (other test rows may have been
        # purged too — assert on OUR rows, not an exact global count).
        assert remaining == ["AAAA"], f"expected only active-case media, got {remaining}"
        assert result["media_purged"] >= 2


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
            # download is redirected (the gating itself), never served bytes.
            assert client.get("/apk/download").status_code == 302
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

    def test_updater_pulls_are_marked_in_the_access_log(self, caplog):
        """The in-app self-updater tags its own checksum/ticket/download
        calls with X-Magneetar-Client: app-updater, so a device that
        self-updated is distinguishable from a web download in the logs
        (the G1 signal that the updater actually ran)."""
        import logging

        with caplog.at_level(logging.INFO, logger="magneetar"):
            client.get("/apk/checksum", headers={"X-Magneetar-Client": "app-updater"})
            client.get("/apk/checksum")

        access = [r for r in caplog.records if r.getMessage() == "access"]
        marked = [r for r in access if getattr(r, "extra_data", {}).get("client") == "app-updater"]
        plain = [r for r in access if "client" not in getattr(r, "extra_data", {})]
        assert len(marked) == 1, "updater call must be marked"
        assert len(plain) == 1, "plain call must stay unmarked"

    def test_download_requires_valid_ticket(self):
        """F-05 gating: /apk/download without a valid signed ticket never
        serves bytes. The three failure modes are distinguished by intent:
        - bare link (no sig) → 302 self-heal to the download page (human error)
        - PRESENT but forged/tampered sig → 403 (attack probe / corrupted link;
          masking it with a redirect would hide the tampering)
        - genuine signature whose window lapsed → 302 self-heal (stale link)
        """
        import time

        download_page = config.settings.DASHBOARD_URL.rstrip("/") + "/download"

        def assert_redirects(resp):
            assert resp.status_code == 302, f"expected 302 redirect, got {resp.status_code}"
            assert resp.headers.get("location", "") == download_page, resp.headers.get("location")

        # follow_redirects=False — the test app has no /download route, and the
        # point is to assert the redirect itself, not its target page.
        assert_redirects(client.get("/apk/download", follow_redirects=False))

        # A PRESENT but forged signature must be rejected with a clean 403 —
        # never a redirect (which would mask tampering) and never bytes.
        forged = client.get("/apk/download?expires=9999999999&sig=deadbeef", follow_redirects=False)
        assert forged.status_code == 403, f"expected 403 for forged sig, got {forged.status_code}"

        # A genuinely signed URL is redirected once its window has lapsed.
        past = int(time.time()) - 3600
        assert_redirects(
            client.get(
                f"/apk/download?expires={past}&sig={_sign_apk_ticket(past)}",
                follow_redirects=False,
            )
        )

    def test_valid_ticket_still_downloads(self):
        """A freshly minted ticket must still serve the APK bytes (the 302
        only applies to INVALID tickets — valid ones bypass the redirect)."""
        url = self._mint_ticket()
        if url is None:
            return  # no APK staged in this test environment
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/vnd.android.package-archive"
        assert resp.content[:2] == b"PK"  # zip magic — an APK, not a redirect/JSON

    def test_checksum_stable_across_requests(self):
        """Repeated calls return a stable checksum (cache-consistent), and both
        endpoints agree nothing is downloadable when no APK is staged."""
        first = client.get("/apk/checksum")
        if first.status_code == 404:
            # Ticketless download is redirected (302) to the download page;
            # no ticket can be minted without an APK.
            assert client.get("/apk/download", follow_redirects=False).status_code == 302
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

    # ─── Source tarball (per-release open source — repo is private) ────────────

    def test_source_tarball_served_publicly_with_checksum(self):
        """/apk/source + /apk/source/checksum must serve the release source
        tarball WITHOUT a ticket — it is deliberately public (it replaces the
        open repo). The checksum must match the served bytes exactly.
        """
        import hashlib

        checksum_resp = client.get("/apk/source/checksum")
        if checksum_resp.status_code == 404:
            # No tarball staged in this test environment: the download must
            # 404 too (never serve an unrelated file).
            assert client.get("/apk/source").status_code == 404
            return

        data = checksum_resp.json()
        assert len(data["sha256"]) == 64
        int(data["sha256"], 16)  # valid lowercase hex
        assert data["size_bytes"] > 0
        assert data["filename"].endswith("-source.tar.gz")

        dl = client.get("/apk/source")  # no ticket required
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/gzip"
        assert hashlib.sha256(dl.content).hexdigest() == data["sha256"]
        assert len(dl.content) == data["size_bytes"]

    def test_source_checksum_stable_across_requests(self):
        """Repeated source-checksum calls return the same digest (same cache
        path as the APK checksum)."""
        first = client.get("/apk/source/checksum")
        if first.status_code == 404:
            return
        second = client.get("/apk/source/checksum")
        assert second.status_code == 200
        assert first.json()["sha256"] == second.json()["sha256"]


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


class TestDeleteArchivedDevices:
    """Bulk purge of stale (archived) devices — password-gated like
    single-device deletion, scoped to the caller's own archived devices.
    (The module-level _clear_rate_buckets fixture keeps the step-up verify
    and command-issuance rate limits from compounding across tests in this
    file.)
    """

    def _register_archived(self, device_id: str):
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-arch-{device_id}",
                "model": "Archived Test",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200
        # Soft-archive it the same way archive_monitor does.
        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET archived_at=datetime('now') WHERE id=?",
                (device_id,),
            )
            conn.commit()

    def _exists(self, device_id: str) -> bool:
        with database.get_db_context() as conn:
            return conn.execute("SELECT 1 FROM devices WHERE id=?", (device_id,)).fetchone() is not None

    def test_bulk_delete_requires_password(self):
        device_id = "arch-bulk-nopw"
        self._register_archived(device_id)
        resp = client.request("DELETE", "/api/dashboard/devices/archived", headers=get_dashboard_headers())
        assert resp.status_code == 400
        assert self._exists(device_id), "device must survive a passwordless bulk delete"

    def test_bulk_delete_wrong_password_rejected(self):
        device_id = "arch-bulk-wrong"
        self._register_archived(device_id)
        resp = client.request(
            "DELETE",
            "/api/dashboard/devices/archived",
            json={"password": "nope"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 401
        assert self._exists(device_id)

    def test_bulk_delete_removes_all_archived(self):
        ids = [f"arch-bulk-{i}" for i in range(3)]
        for did in ids:
            self._register_archived(did)
        # A NON-archived device must survive the purge.
        alive = "arch-bulk-alive"
        resp = client.post(
            "/api/device/register",
            json={"device_id": alive, "fingerprint": "fp-arch-alive", "model": "Alive"},
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200

        resp = client.request(
            "DELETE",
            "/api/dashboard/devices/archived",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        # NOTE: the DB may already hold archived devices left by earlier tests
        # in this class (each test archives its own row and the class shares
        # one DB), so assert our three are all gone + at least those 3 deleted
        # rather than an exact global count.
        assert data["count"] >= 3
        assert set(ids).issubset(set(data["deleted"]))
        for did in ids:
            assert not self._exists(did), "archived device must be gone"
        assert self._exists(alive), "active device must survive the purge"

    def test_bulk_delete_cascade_removes_locations(self):
        """Cascade must wipe the archived device's history, not just the row."""
        device_id = "arch-bulk-cascade"
        self._register_archived(device_id)
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES (?,?,?,datetime('now'))",
                (device_id, 9.0, 8.6),
            )
            conn.commit()

        client.request(
            "DELETE",
            "/api/dashboard/devices/archived",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        with database.get_db_context() as conn:
            locs = conn.execute("SELECT COUNT(*) FROM locations WHERE device_id=?", (device_id,)).fetchone()[0]
        assert locs == 0

    def test_bulk_delete_static_path_not_captured_as_device_id(self):
        """The /archived static route must win over /{device_id} (FastAPI
        matches in registration order) — otherwise this 404s as an unknown
        device instead of bulk-deleting."""
        self._register_archived("arch-route-order")
        resp = client.request(
            "DELETE",
            "/api/dashboard/devices/archived",
            json={"password": TEST_API_KEY},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text


class TestSmsInboundWebhook:
    """The SMS reply return channel: the phone best-effort SMS-replies
    'MT-ACK #<id> <status>' to the relay number; Twilio forwards it here.
    Signature-verified (only genuine Twilio traffic may drive acks) and
    sender-matched to the device's sms_phone (a stranger can never ack
    another device's commands)."""

    def _sign(self, url: str, form: dict, auth_token: str) -> str:
        """Compute the Twilio X-Twilio-Signature for a webhook request (the
        exact algorithm the endpoint verifies): base64(HMAC-SHA1(auth_token,
        url + urlencoded_sorted_params))."""
        import base64
        import hashlib
        import hmac as _hmac
        import urllib.parse

        sorted_params = urllib.parse.urlencode(sorted(form.items()))
        digest = _hmac.new(auth_token.encode(), f"{url}{sorted_params}".encode(), hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _issue_sms_command(self, device_id: str, device_key: str) -> int:
        """Register a device (offline + SMS-enabled) and issue a command over
        the relay; returns the command id."""
        from datetime import datetime, timedelta, timezone

        import sms_relay

        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-sms-in-{device_id}",
                "model": "SMS",
                "device_key": device_key,
            },
            headers=get_auth_headers(),
        )
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        with database.get_db_context() as conn:
            conn.execute(
                "UPDATE devices SET last_seen=? WHERE id=?",
                (
                    (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                    device_id,
                ),
            )
            conn.commit()

        original = sms_relay.send_command_sms
        sms_relay.send_command_sms = lambda to, body: True
        try:
            resp = client.post(
                "/api/dashboard/command",
                json={"device_id": device_id, "command": "alarm"},
                headers=get_dashboard_headers(),
            )
        finally:
            sms_relay.send_command_sms = original
        assert resp.json()["delivery"] == "sms"
        return resp.json()["command_id"]

    def test_webhook_rejects_missing_signature(self):
        resp = client.post(
            "/api/sms/inbound",
            data={"From": "+2348012345678", "Body": "MT-ACK #1 executed"},
        )
        assert resp.status_code == 403

    def test_webhook_rejects_bad_signature(self):
        """A genuine signature mismatch must 403 (not the 'not configured'
        branch) — pin a token so the HMAC check actually runs."""
        saved_token = config.settings.TWILIO_AUTH_TOKEN
        config.settings.TWILIO_AUTH_TOKEN = "D" * 32
        try:
            resp = client.post(
                "/api/sms/inbound",
                data={"From": "+2348012345678", "Body": "MT-ACK #1 executed"},
                headers={"X-Twilio-Signature": "forged-signature"},
            )
        finally:
            config.settings.TWILIO_AUTH_TOKEN = saved_token
        assert resp.status_code == 403

    def test_webhook_acks_command_from_owner_number(self, monkeypatch):
        """A signature-valid MT-ACK from the device's own sms_phone marks the
        command executed server-side — the instant return channel."""
        # Patch the MODULE-LEVEL `config` binding (see test_config_exposes...
        # for the eviction rationale) — the routes hold the pre-eviction
        # settings object, so a function-local re-import would patch the wrong
        # one and the webhook would see an unset/foreign token.
        saved_token = config.settings.TWILIO_AUTH_TOKEN
        config.settings.TWILIO_AUTH_TOKEN = "A" * 32
        try:
            device_id = "sms-in-ok"
            cmd_id = self._issue_sms_command(device_id, "in-ok-key")

            url = "http://testserver/api/sms/inbound"
            form = {"From": "+2348012345678", "Body": f"MT-ACK #{cmd_id} executed"}
            sig = self._sign(url, form, "A" * 32)
            resp = client.post(
                "/api/sms/inbound",
                data=form,
                headers={"X-Twilio-Signature": sig},
            )
        finally:
            config.settings.TWILIO_AUTH_TOKEN = saved_token

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "acknowledged"
        with database.get_db_context() as conn:
            row = conn.execute("SELECT status FROM commands WHERE id=?", (cmd_id,)).fetchone()
        assert row["status"] == "executed"

    def test_webhook_rejects_ack_from_foreign_number(self):
        """The From number must match the device's sms_phone — a different
        number must never ack (or forge) this device's commands."""
        saved_token = config.settings.TWILIO_AUTH_TOKEN
        config.settings.TWILIO_AUTH_TOKEN = "B" * 32
        try:
            device_id = "sms-in-foreign"
            cmd_id = self._issue_sms_command(device_id, "in-foreign-key")

            url = "http://testserver/api/sms/inbound"
            form = {
                "From": "+15551234567",
                "Body": f"MT-ACK #{cmd_id} executed",
            }  # NOT the owner's number
            sig = self._sign(url, form, "B" * 32)
            resp = client.post(
                "/api/sms/inbound",
                data=form,
                headers={"X-Twilio-Signature": sig},
            )
        finally:
            config.settings.TWILIO_AUTH_TOKEN = saved_token

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "sender_mismatch"
        with database.get_db_context() as conn:
            row = conn.execute("SELECT status FROM commands WHERE id=?", (cmd_id,)).fetchone()
        assert row["status"] == "pending", "foreign sender must not change the command"

    def test_webhook_ignores_non_ack_sms(self):
        saved_token = config.settings.TWILIO_AUTH_TOKEN
        config.settings.TWILIO_AUTH_TOKEN = "C" * 32
        try:
            url = "http://testserver/api/sms/inbound"
            form = {"From": "+2348012345678", "Body": "hello from a friend"}
            sig = self._sign(url, form, "C" * 32)
            resp = client.post(
                "/api/sms/inbound",
                data=form,
                headers={"X-Twilio-Signature": sig},
            )
        finally:
            config.settings.TWILIO_AUTH_TOKEN = saved_token

        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_parse_ack_sms(self):
        """The wire format is case-insensitive on status and rejects garbage."""
        from sms_relay import parse_ack_sms

        assert parse_ack_sms("MT-ACK #42 executed") == (42, "executed")
        assert parse_ack_sms("MT-ACK #7 failed") == (7, "failed")
        assert parse_ack_sms("mt-ack #9 FAILED") == (9, "failed")
        assert parse_ack_sms("MT-ACK #42") is None  # missing status
        assert parse_ack_sms("MT-ACK x42 executed") is None  # non-numeric id
        assert parse_ack_sms("") is None
        assert parse_ack_sms("hello world") is None


class TestSmsSettingsEndpoint:
    """Offline Command Relay configuration — E.164 validation, ownership
    scoping, and the enable-requires-number contract."""

    def _register(self, device_id: str):
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-sms-set-{device_id}",
                "model": "SMS Settings",
            },
            headers=get_auth_headers(),
        )

    def test_set_sms_phone_and_enable(self):
        self._register("sms-set-ok")
        resp = client.patch(
            "/api/dashboard/devices/sms-set-ok/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["sms_phone"] == "+2348012345678"
        assert resp.json()["sms_commands_enabled"] is True

        # Persisted and surfaced in the device list.
        devices = client.get("/api/dashboard/devices", headers=get_dashboard_headers()).json()["devices"]
        row = next(d for d in devices if d["id"] == "sms-set-ok")
        assert row["sms_phone"] == "+2348012345678"
        assert row["sms_commands_enabled"] is True

    def test_requires_e164_phone(self):
        self._register("sms-set-bad")
        resp = client.patch(
            "/api/dashboard/devices/sms-set-bad/sms-settings",
            json={"sms_phone": "08012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400

    def test_enable_requires_number(self):
        self._register("sms-set-nonum")
        resp = client.patch(
            "/api/dashboard/devices/sms-set-nonum/sms-settings",
            json={"sms_phone": "", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400

    def test_unknown_device_404(self):
        resp = client.patch(
            "/api/dashboard/devices/never-sms/sms-settings",
            json={"sms_phone": "+2348012345678", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 404

    def test_registration_prefills_sms_phone_from_sim_phone(self):
        """The app reports its SIM number best-effort; the server prefills
        sms_phone ONLY when it is still NULL (never overwrites an
        owner-confirmed number)."""
        device_id = "sms-set-prefill"
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-prefill",
                "model": "Prefill",
                "sim_phone": "+2348099999999",
            },
            headers=get_auth_headers(),
        )
        devices = client.get("/api/dashboard/devices", headers=get_dashboard_headers()).json()["devices"]
        row = next(d for d in devices if d["id"] == device_id)
        assert row["sms_phone"] == "+2348099999999"

        # Owner sets a different number; a re-register with the same sim_phone
        # must NOT overwrite it.
        client.patch(
            f"/api/dashboard/devices/{device_id}/sms-settings",
            json={"sms_phone": "+2348077777777", "sms_commands_enabled": True},
            headers=get_dashboard_headers(),
        )
        client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": "fp-sms-prefill",
                "model": "Prefill",
                "sim_phone": "+2348099999999",
            },
            headers=get_auth_headers(),
        )
        devices = client.get("/api/dashboard/devices", headers=get_dashboard_headers()).json()["devices"]
        row = next(d for d in devices if d["id"] == device_id)
        assert row["sms_phone"] == "+2348077777777"


class TestCellLocate:
    """Cell-tower fingerprint resolution — cache-first, provider-pluggable,
    graceful degradation when no provider is configured."""

    def test_unconfigured_provider_degrades_gracefully(self):
        config.settings.CELL_LOOKUP_API_KEY = ""
        resp = client.post(
            "/api/dashboard/cell-locate",
            json={"cell_tower_ids": ["lte:621:20:30544:123456"]},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["resolved"] is False
        assert data["reason"] == "no_provider_configured"

    def test_cache_hit_returns_stored_fix(self):
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cell_location_cache "
                "(fingerprint, lat, lng, accuracy_meters, provider) VALUES (?, ?, ?, ?, ?)",
                ("lte:621:20:30544:123456", 6.5244, 3.3792, 120.0, "test"),
            )
            conn.commit()
        resp = client.post(
            "/api/dashboard/cell-locate",
            json={"cell_tower_ids": ["lte:621:20:30544:123456"]},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved"] is True
        assert data["cached"] is True
        assert abs(data["lat"] - 6.5244) < 1e-6
        assert abs(data["lng"] - 3.3792) < 1e-6

    def test_provider_resolution_roundtrip(self, monkeypatch):
        """With a provider configured, a resolve stores the fix in the cache
        so a second call is a cache hit."""

        config.settings.CELL_LOOKUP_API_KEY = "test-token"
        calls = []

        import httpx as _httpx

        def fake_client(*args, **kwargs):
            class FakeResp:
                def json(self):
                    return {
                        "status": "ok",
                        "lat": 9.0765,
                        "lon": 7.3986,
                        "accuracy": 95,
                    }

            class FakeCtx:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def post(self, url, json=None):
                    calls.append(url)
                    return FakeResp()

            return FakeCtx()

        monkeypatch.setattr(_httpx, "Client", fake_client)
        try:
            resp = client.post(
                "/api/dashboard/cell-locate",
                json={"cell_tower_ids": ["lte:621:20:30544:987654"]},
                headers=get_dashboard_headers(),
            )
        finally:
            config.settings.CELL_LOOKUP_API_KEY = ""

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["resolved"] is True
        assert data["cached"] is False
        assert abs(data["lat"] - 9.0765) < 1e-6
        assert calls, "provider must have been called"

        # Second call is now a cache hit (no provider call).
        resp2 = client.post(
            "/api/dashboard/cell-locate",
            json={"cell_tower_ids": ["lte:621:20:30544:987654"]},
            headers=get_dashboard_headers(),
        )
        assert resp2.json()["cached"] is True
        assert len(calls) == 1

    def test_invalid_input_rejected(self):
        resp = client.post("/api/dashboard/cell-locate", json={}, headers=get_dashboard_headers())
        assert resp.status_code == 400
        resp = client.post(
            "/api/dashboard/cell-locate",
            json={"cell_tower_ids": ["not-a-tower-id"]},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 400


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


# ─── Geofence auto-actions (v1.5 — COMPETITOR_AUDIT P0 gap-closer #1) ───────


class TestGeofenceAutoActions:
    """Owner-set per-zone reactions on an EXIT transition: 'capture' queues
    front-photo + audio evidence commands, 'siren' queues the alarm. The
    exit alert fires for SAFE-ZONE exits (the template says 'safe zone'; the
    old condition was inverted, so exits never alerted and auto-actions had
    no trigger — see the v1.5 fix notes in routes/devices.py)."""

    CENTER = (9.0820, 8.6753)
    OUTSIDE = (9.2000, 8.8000)

    def _register(self, device_id: str) -> str:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-geoact-{device_id}",
                "model": "Geofence Action",
                "device_key": f"key-{device_id}",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def _create_fence(
        self,
        device_id: str,
        auto_action: str = None,
        is_safe_zone: bool = True,
        name: str = "Home",
    ) -> int:
        body = {
            "device_id": device_id,
            "name": name,
            "center_lat": self.CENTER[0],
            "center_lng": self.CENTER[1],
            "radius_meters": 100,
            "is_safe_zone": is_safe_zone,
        }
        if auto_action is not None:
            body["auto_action"] = auto_action
        resp = client.post("/api/dashboard/geofence", json=body, headers=get_dashboard_headers())
        assert resp.status_code == 200, resp.text
        return resp.json()["geofence_id"]

    def _post_location(self, device_id: str, token: str, lat: float, lng: float):
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": lat,
                "lng": lng,
                "accuracy_horizontal": 7.5,
                "provider": "gps",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        return resp

    def _pending(self, device_id: str, command: str = None) -> list:
        # Commands are written by the app's routers, which hold PRE-eviction
        # module references — the module-level `database` binding matches.
        with database.get_db_context() as conn:
            if command:
                rows = conn.execute(
                    "SELECT command, priority FROM commands WHERE device_id=? AND command=? AND status='pending'",
                    (device_id, command),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT command, priority FROM commands WHERE device_id=? AND status='pending'",
                    (device_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def _seed_current_db_device(self, device_id: str) -> None:
        """alert_engine.send_all resolves `from database import get_db_context`
        at CALL time, so under full-suite runs it reads/writes the CURRENT
        (post-eviction) database module. Seed the device row there too, or the
        prefs lookup misses and the alert row's FK fails silently (same
        convention as test_alert_settings.py's seed_device_row)."""
        import database as _current_db

        with _current_db.get_db_context() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO devices (id, model, alert_phone, alert_email) "
                "VALUES (?, 'Geofence Action', '+2348000000000', 'geofence-test@example.com')",
                (device_id,),
            )
            conn.commit()

    def _alerts(self, device_id: str, alert_type: str = "geofence_exit") -> list:
        # send_all writes alert rows via the CURRENT module (see above).
        import database as _current_db

        with _current_db.get_db_context() as conn:
            rows = conn.execute(
                "SELECT alert_type, delivered FROM alerts WHERE device_id=? AND alert_type=?",
                (device_id, alert_type),
            ).fetchall()
        return [dict(r) for r in rows]

    def test_capture_auto_action_queues_evidence_commands_on_exit(self):
        device_id = "geo-act-capture"
        token = self._register(device_id)
        self._seed_current_db_device(device_id)
        self._create_fence(device_id, auto_action="capture")

        # Enter the safe zone (first observation → entered, state persisted)
        self._post_location(device_id, token, *self.CENTER)
        assert self._pending(device_id) == [], "entry must not queue anything"

        # Exit the safe zone → alert + capture_photo_front + capture_audio
        self._post_location(device_id, token, *self.OUTSIDE)
        pending = self._pending(device_id)
        commands = {p["command"] for p in pending}
        assert {"capture_photo_front", "capture_audio"} <= commands
        assert all(p["priority"] == 1 for p in pending), "auto-actions must jump the queue"
        # send_all logs one row per configured channel (email/whatsapp/sms/push)
        # — one incident = len(channels) rows, all undelivered (no creds here).
        alert_rows = self._alerts(device_id)
        assert len(alert_rows) >= 1 and all(a["alert_type"] == "geofence_exit" for a in alert_rows)

        # Still outside, pinging again → no duplicate commands, no repeat alert
        self._post_location(device_id, token, *self.OUTSIDE)
        assert len(self._pending(device_id)) == 2, "exit transition must fire exactly once"
        assert len(self._alerts(device_id)) == len(alert_rows), "second ping must not re-alert"

    def test_siren_auto_action_queues_alarm_on_exit(self):
        device_id = "geo-act-siren"
        token = self._register(device_id)
        self._create_fence(device_id, auto_action="siren")

        self._post_location(device_id, token, *self.CENTER)
        self._post_location(device_id, token, *self.OUTSIDE)

        pending = self._pending(device_id, command="alarm")
        assert len(pending) == 1 and pending[0]["priority"] == 1

    def test_alert_only_fence_fires_alert_without_commands(self):
        device_id = "geo-act-alert"
        token = self._register(device_id)
        self._seed_current_db_device(device_id)
        self._create_fence(device_id, auto_action=None)

        self._post_location(device_id, token, *self.CENTER)
        self._post_location(device_id, token, *self.OUTSIDE)

        assert self._pending(device_id) == []
        assert len(self._alerts(device_id)) >= 1

    def test_non_safe_zone_exit_does_not_alert_but_acts(self):
        # v1.5 semantic fix: the geofence_exit alert fires for SAFE-ZONE exits
        # ("your device left home"); restricted-zone exits stay silent. The
        # owner-set auto_action still fires — the policy is per-zone, not
        # per-classification.
        device_id = "geo-act-restricted"
        token = self._register(device_id)
        self._seed_current_db_device(device_id)
        self._create_fence(device_id, auto_action="capture", is_safe_zone=False, name="Restricted")

        self._post_location(device_id, token, *self.CENTER)
        self._post_location(device_id, token, *self.OUTSIDE)

        # Seeded into the current DB, so [] genuinely means no alert fired.
        assert self._alerts(device_id) == []
        commands = {p["command"] for p in self._pending(device_id)}
        assert {"capture_photo_front", "capture_audio"} <= commands

    def test_invalid_auto_action_rejected(self):
        resp = client.post(
            "/api/dashboard/geofence",
            json={
                "device_id": TEST_DEVICE_ID,
                "name": "Bad",
                "center_lat": 6.5,
                "center_lng": 3.3,
                "radius_meters": 100,
                "auto_action": "nuke",
            },
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 422


# ─── Location history CSV export (v1.5 — Prey-parity) ───────────────────────


class TestLocationCsvExport:
    def _register(self, device_id: str) -> str:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-csv-{device_id}",
                "model": "CSV Phone",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def _post_location(self, device_id: str, token: str, lat: float, lng: float, battery: int = 88):
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": lat,
                "lng": lng,
                "accuracy_horizontal": 7.5,
                "provider": "gps",
                "speed": 1.2,
                "battery_percent": battery,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

    def test_export_returns_rows_oldest_first(self):
        device_id = "csv-device-001"
        token = self._register(device_id)
        self._post_location(device_id, token, 6.5244, 3.3792)
        self._post_location(device_id, token, 6.5245, 3.3793, battery=80)

        resp = client.get(
            f"/api/dashboard/locations/{device_id}/export/csv",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers.get("content-disposition", "")

        text = resp.text
        # UTF-8 BOM so Excel decodes correctly (rides on the header row)
        lines = text.splitlines()
        assert lines[0].startswith("\ufeff")
        assert lines[0].lstrip("\ufeff") == (
            "server_timestamp,device_timestamp,lat,lng,accuracy_m,altitude_m,"
            "speed_ms,bearing_deg,provider,battery_percent,threat_level,sentinel_score,was_queued"
        )
        assert len(lines) == 3  # header + 2 pings
        # Oldest first + real coordinates survive (not the 0.0 placeholders)
        assert lines[1].split(",")[2] == "6.5244"
        assert lines[2].split(",")[2] == "6.5245"
        assert lines[2].split(",")[9] == "80"

    def test_export_encrypted_rows_decrypted(self):
        """With at-rest encryption configured, the exported lat/lng must be the
        real coordinates, never the 0.0 ciphertext placeholders."""
        device_id = "csv-device-enc"
        self._register(device_id)
        # Module-level (pre-eviction) binding — see the note above the import.
        lat, lng, enc, data = _encrypt_location_for_store(6.5244, 3.3792, device_id)
        assert enc is True
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT INTO locations (device_id, lat, lng, accuracy_horizontal, provider, "
                "device_timestamp, server_timestamp, location_encrypted, location_data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    device_id,
                    lat,
                    lng,
                    5.0,
                    "gps",
                    "2026-08-01T10:00:00+00:00",
                    "2026-08-01T10:00:00+00:00",
                    data,
                ),
            )
            conn.commit()

        resp = client.get(
            f"/api/dashboard/locations/{device_id}/export/csv",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        lines = resp.text.splitlines()
        assert len(lines) == 2
        row_lat = float(lines[1].split(",")[2])
        row_lng = float(lines[1].split(",")[3])
        assert abs(row_lat - 6.5244) < 1e-6
        assert abs(row_lng - 3.3792) < 1e-6

    def test_export_missing_device_is_404(self):
        resp = client.get(
            "/api/dashboard/locations/ghost-csv-device/export/csv",
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 404

    def test_export_requires_dashboard_auth(self):
        resp = client.get(f"/api/dashboard/locations/{TEST_DEVICE_ID}/export/csv")
        assert resp.status_code == 401


# ─── Lost Mode command (v1.5 — COMPETITOR_AUDIT P0 gap-closer #2) ───────────


class TestLostModeCommand:
    def _register(self, device_id: str) -> None:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-lostmode-{device_id}",
                "model": "Lost Mode Phone",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200, resp.text

    def test_lost_mode_accepted_and_prioritized(self):
        device_id = "lostmode-device-001"
        self._register(device_id)
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": device_id,
                "command": "lost_mode",
                "params": "This phone is lost — call +2348012345678",
            },
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text
        command_id = resp.json()["command_id"]

        with database.get_db_context() as conn:
            row = conn.execute(
                "SELECT command, params, priority, status, delivery_channel FROM commands WHERE id=?",
                (command_id,),
            ).fetchone()
        assert row["command"] == "lost_mode"
        assert row["params"] == "This phone is lost — call +2348012345678"
        assert row["priority"] == 1, "lost mode must jump the command queue"
        assert row["status"] == "pending"

    def test_lost_mode_is_not_stepup_gated(self):
        # Lost mode locks the screen to a recovery message — reversible on the
        # device, so unlike wipe it must NOT require the step-up password.
        device_id = "lostmode-device-002"
        self._register(device_id)
        resp = client.post(
            "/api/dashboard/command",
            json={"device_id": device_id, "command": "lost_mode"},
            headers=get_dashboard_headers(),
        )
        assert resp.status_code == 200, resp.text


# ─── Schema migrations on existing databases ────────────────────────────────


class TestSchemaMigration:
    def test_ensure_initialized_migrates_commands_failure_reason(self, monkeypatch):
        """Regression (shipped once in production): the live DB's commands
        table was missing failure_reason while the running ack route already
        wrote it — every device ack 500'd with 'no such column'. The old
        ensure_initialized short-circuit only validated DEVICES columns, so
        it returned 'current' and never ran the commands ALTER migration.
        It must now detect a stale commands table too."""
        import sqlite3
        import tempfile

        fd, path = tempfile.mkstemp(suffix="-commands-stale.db")
        os.close(fd)
        try:
            # A complete schema WITHOUT the failure_reason column (exactly
            # what production looked like before the migration landed).
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT,
                    display_name TEXT, tier TEXT DEFAULT 'free', is_active BOOLEAN DEFAULT TRUE,
                    email_verified BOOLEAN DEFAULT FALSE, created_at TIMESTAMP, last_login TIMESTAMP);
                CREATE TABLE devices (id TEXT PRIMARY KEY, alias TEXT, owner_id TEXT,
                    device_fingerprint TEXT, platform TEXT DEFAULT 'android', app_version TEXT,
                    os_version TEXT, model TEXT, imei_hash TEXT, sim_serial_hash TEXT,
                    device_key_hash TEXT, last_seen TIMESTAMP, registered TIMESTAMP,
                    is_stolen BOOLEAN DEFAULT FALSE, theft_confirmed_at TIMESTAMP,
                    operating_mode TEXT DEFAULT 'normal', sentinel_score INTEGER DEFAULT 0,
                    capture_armed BOOLEAN, alert_phone TEXT, alert_email TEXT,
                    alert_channels TEXT, enabled_types TEXT, quiet_hours_start INTEGER,
                    quiet_hours_end INTEGER, archived_at TIMESTAMP);
                CREATE TABLE commands (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL, command TEXT NOT NULL, params TEXT,
                    status TEXT DEFAULT 'pending', priority INTEGER DEFAULT 5,
                    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP, expires_at TIMESTAMP);
                """
            )
            conn.commit()
            conn.close()

            monkeypatch.setattr(database, "DB_PATH", path)
            assert database.ensure_initialized() is True, "stale commands table must trigger migration"

            conn = sqlite3.connect(path)
            try:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(commands)")}
            finally:
                conn.close()
            assert "failure_reason" in cols, "migration must add failure_reason to commands"

            # And the second call is a no-op: the DB is now current.
            assert database.ensure_initialized() is False
        finally:
            if os.path.exists(path):
                os.remove(path)

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


# ─── Failed-Unlock "Theftie" Auto-Capture (COMPETITOR_AUDIT P1 #4) ──────────


class TestFailedUnlockTheftie:
    """Repeated failed unlock attempts ("theftie") must trigger the same
    automatic evidence capture machinery as a geofence exit: when the device
    reports a failed_unlock_count >= the threshold, the server queues
    capture_photo_front + capture_audio (priority 1, deduped against
    already-pending identical commands) and fires an always-deliver
    failed_unlock_attempts alert (10-minute dedup). Below the threshold — or
    with the field absent (old app builds) — nothing is queued."""

    def _register(self, device_id: str) -> str:
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-theftie-{device_id}",
                "model": "Theftie",
                "device_key": f"key-{device_id}",
            },
            headers=get_auth_headers(),
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["token"]

    def _seed_current_db_device(self, device_id: str) -> None:
        """alert_engine.send_all resolves `from database import get_db_context`
        at CALL time, so under full-suite runs it reads/writes the CURRENT
        (post-eviction) database module. Seed the device row there too, or the
        alert row's FK fails silently (same convention as test_alert_settings.py
        and TestGeofenceAutoActions)."""
        import database as _current_db

        with _current_db.get_db_context() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO devices (id, model, alert_phone, alert_email) "
                "VALUES (?, 'Theftie', '+2348000000000', 'theftie-test@example.com')",
                (device_id,),
            )
            conn.commit()

    def _post_location(self, device_id: str, token: str, failed_unlock_count: int) -> None:
        resp = client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.0820,
                "lng": 8.6753,
                "accuracy_horizontal": 7.5,
                "provider": "gps",
                "failed_unlock_count": failed_unlock_count,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

    def _pending(self, device_id: str) -> list:
        with database.get_db_context() as conn:
            rows = conn.execute(
                "SELECT command, priority FROM commands WHERE device_id=? AND status='pending'",
                (device_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _alerts(self, device_id: str) -> list:
        import database as _current_db

        with _current_db.get_db_context() as conn:
            rows = conn.execute(
                "SELECT alert_type, delivered FROM alerts WHERE device_id=? AND alert_type='failed_unlock_attempts'",
                (device_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def test_threshold_crossed_queues_capture_and_alerts(self):
        device_id = "theftie-capture"
        token = self._register(device_id)
        self._seed_current_db_device(device_id)

        # One ping above the threshold → evidence pair queued + alert fired.
        self._post_location(device_id, token, config.settings.FAILED_UNLOCK_THRESHOLD)

        pending = self._pending(device_id)
        commands = {p["command"] for p in pending}
        assert {"capture_photo_front", "capture_audio"} <= commands
        assert all(p["priority"] == 1 for p in pending), "theftie capture must jump the queue"

        alert_rows = self._alerts(device_id)
        assert len(alert_rows) >= 1, "failed_unlock_attempts alert must fire"
        assert all(a["alert_type"] == "failed_unlock_attempts" for a in alert_rows)

        # Still locked, pinging again → no duplicate commands, no repeat alert.
        self._post_location(device_id, token, config.settings.FAILED_UNLOCK_THRESHOLD + 2)
        assert len(self._pending(device_id)) == 2, "theftie reaction must fire exactly once per incident"
        assert len(self._alerts(device_id)) == len(alert_rows), "second ping must not re-alert"

    def test_below_threshold_queues_nothing(self):
        device_id = "theftie-quiet"
        token = self._register(device_id)
        self._seed_current_db_device(device_id)

        self._post_location(device_id, token, config.settings.FAILED_UNLOCK_THRESHOLD - 1)
        assert self._pending(device_id) == [], "below threshold must not queue anything"
        assert self._alerts(device_id) == [], "below threshold must not alert"

    def test_field_absent_queues_nothing(self):
        """Old app builds that never report failed_unlock_count must be inert
        (None is treated as 'not reported', not as a failure count)."""
        device_id = "theftie-legacy"
        resp = client.post(
            "/api/device/register",
            json={"device_id": device_id, "fingerprint": f"fp-theftie-legacy-{device_id}"},
            headers=get_auth_headers(),
        )
        token = resp.json()["token"]
        self._seed_current_db_device(device_id)

        client.post(
            "/api/device/location",
            json={
                "device_id": device_id,
                "lat": 9.0820,
                "lng": 8.6753,
                "accuracy_horizontal": 7.5,
                "provider": "gps",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert self._pending(device_id) == []
        assert self._alerts(device_id) == []

    def test_heartbeat_threshold_also_queues_capture(self):
        """The 60s heartbeat must react too — a device with its location
        stream quiet (permission revoked) still reports the locked screen."""
        device_id = "theftie-heartbeat"
        resp = client.post(
            "/api/device/register",
            json={"device_id": device_id, "fingerprint": f"fp-theftie-hb-{device_id}"},
            headers=get_auth_headers(),
        )
        token = resp.json()["token"]
        self._seed_current_db_device(device_id)

        resp = client.post(
            "/api/device/heartbeat",
            json={
                "device_id": device_id,
                "failed_unlock_count": config.settings.FAILED_UNLOCK_THRESHOLD,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        pending = self._pending(device_id)
        commands = {p["command"] for p in pending}
        assert {"capture_photo_front", "capture_audio"} <= commands
        assert len(self._alerts(device_id)) >= 1, "heartbeat must fire the theftie alert too"
