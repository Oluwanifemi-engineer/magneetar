"""
Network Failure Tests for Tier 1 Features
──────────────────────────────────────────
Tests that core features degrade gracefully when external services fail.

These tests are self-contained (no conftest fixture dependencies) and work
under full-suite collection.
"""

import secrets
from unittest.mock import patch

import config
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY


def _get_user_token():
    """Register a test user and return JWT token."""
    email = f"failtest-{secrets.token_hex(4)}@example.com"
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "SecurePass123!",
            "display_name": "Fail Test",
        },
    )
    if resp.status_code == 200:
        return resp.json()["token"]
    return None


def _register_and_claim():
    """Register a device, register a user, claim the device. Return (device_id, user_token)."""
    device_id = f"fail-dev-{secrets.token_hex(4)}"
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{secrets.token_hex(8)}",
            "model": "Test Phone",
        },
        headers={"x-api-key": TEST_API_KEY},
    )
    if resp.status_code != 200:
        return None, None

    user_token = _get_user_token()
    if not user_token:
        return device_id, None

    resp = client.post(
        "/api/device/claim",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    return device_id, user_token


# ── SMS webhook security ────────────────────────────────────────────────────


def test_sms_inbound_rejects_invalid_signature():
    """SMS inbound webhook should reject requests with invalid Twilio signature."""
    resp = client.post(
        "/api/sms/inbound",
        data={"From": "+2348012345678", "Body": "ACK 123 OK"},
        headers={"X-Twilio-Signature": "invalid_signature_12345"},
    )
    assert resp.status_code == 403


def test_sms_inbound_rejects_unconfigured():
    """SMS inbound should reject when Twilio auth token is not configured."""
    with patch.object(config.settings, "TWILIO_AUTH_TOKEN", ""):
        resp = client.post(
            "/api/sms/inbound",
            data={"From": "+2348012345678", "Body": "ACK 123 OK"},
            headers={"X-Twilio-Signature": "valid"},
        )
    assert resp.status_code == 403


# ── Config endpoint ─────────────────────────────────────────────────────────


def test_config_endpoint_works_without_device_key():
    """Config endpoint should return app version even without device key."""
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "app_version" in data
    assert "feature_flags" in data


# ── Command validation ──────────────────────────────────────────────────────


def test_command_to_nonexistent_device_returns_404():
    """Issuing a command to a nonexistent device should return 404."""
    user_token = _get_user_token()
    if not user_token:
        pytest.skip("Could not create user")

    resp = client.post(
        "/api/dashboard/command",
        json={
            "device_id": "nonexistent-device",
            "command": "lock",
            "params": "",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 404


def test_wipe_requires_confirmed_wipe_param():
    """Wipe command should require params='CONFIRMED_WIPE'."""
    device_id, user_token = _register_and_claim()
    if not user_token:
        pytest.skip("Could not set up device + user")

    resp = client.post(
        "/api/dashboard/command",
        json={
            "device_id": device_id,
            "command": "wipe",
            "params": "NOT_CONFIRMED",
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 400
    assert "CONFIRMED_WIPE" in resp.json()["detail"]


# ── FCM failure graceful degradation ────────────────────────────────────────


def test_command_queued_when_fcm_fails():
    """When FCM push fails, the command should still be queued via poll."""
    device_id, user_token = _register_and_claim()
    if not user_token:
        pytest.skip("Could not set up device + user")

    with patch("fcm_command.push_command_to_device", return_value=False):
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": device_id,
                "command": "lock",
                "params": "",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["command_id"] is not None
    assert data["fcm_pushed"] is False
    assert data["delivery"] == "poll"


# ── SMS failure fallback ────────────────────────────────────────────────────


def test_command_falls_back_to_poll_when_sms_fails():
    """When SMS send fails, the command should fall back to poll channel."""
    device_id, user_token = _register_and_claim()
    if not user_token:
        pytest.skip("Could not set up device + user")

    # Enable SMS commands for this device
    from database import get_db_context

    with get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET sms_phone='+2348012345678', "
            "sms_commands_enabled=1, last_seen='2020-01-01T00:00:00' "
            f"WHERE id='{device_id}'"
        )
        conn.commit()

    with patch("sms_relay.send_command_sms", return_value=False):
        resp = client.post(
            "/api/dashboard/command",
            json={
                "device_id": device_id,
                "command": "lock",
                "params": "",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sms_delivered"] is False
    assert data["delivery"] == "poll"
