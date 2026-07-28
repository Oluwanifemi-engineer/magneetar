"""
Magneetar Auth Tests
Tests for JWT authentication and authorization.
"""
import pytest
import os
import secrets
import time

# Set test environment
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = ":memory:"

from auth import (
    create_token, decode_token, create_device_tokens,
    create_dashboard_tokens, refresh_access_token
)


class TestTokenGeneration:
    def test_create_access_token(self):
        token = create_token("test-subject", "access")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_device_token(self):
        token = create_token("device-123", "device")
        payload = decode_token(token)
        assert payload["sub"] == "device-123"
        assert payload["type"] == "device"

    def test_create_dashboard_token(self):
        token = create_token("dashboard:user", "dashboard")
        payload = decode_token(token)
        assert payload["sub"] == "dashboard:user"
        assert payload["type"] == "dashboard"

    def test_token_has_expiry(self):
        token = create_token("test", "access")
        payload = decode_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_token_has_unique_id(self):
        token1 = create_token("test", "access")
        token2 = create_token("test", "access")
        payload1 = decode_token(token1)
        payload2 = decode_token(token2)
        assert payload1["jti"] != payload2["jti"]


class TestTokenValidation:
    def test_valid_token_decodes(self):
        token = create_token("valid-subject", "access")
        payload = decode_token(token)
        assert payload["sub"] == "valid-subject"

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            decode_token("invalid.token.here")

    def test_tampered_token_raises(self):
        token = create_token("test", "access")
        # Tamper with token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(Exception):
            decode_token(tampered)


class TestDeviceTokens:
    def test_create_device_tokens_pair(self):
        tokens = create_device_tokens("device-abc")
        assert "token" in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"
        assert tokens["expires_in"] == 86400

    def test_device_token_contains_device_id(self):
        tokens = create_device_tokens("device-xyz")
        payload = decode_token(tokens["token"])
        assert payload["sub"] == "device-xyz"


class TestDashboardTokens:
    def test_create_dashboard_tokens_pair(self):
        tokens = create_dashboard_tokens("my-api-key")
        assert "token" in tokens
        assert "refresh_token" in tokens

    def test_dashboard_token_type(self):
        tokens = create_dashboard_tokens("api-key")
        payload = decode_token(tokens["token"])
        assert payload["type"] == "dashboard"


class TestTokenRefresh:
    def test_refresh_returns_new_tokens(self):
        original = create_device_tokens("device-refresh")
        new_tokens = refresh_access_token(original["refresh_token"])

        assert new_tokens["token"] != original["token"]
        assert new_tokens["refresh_token"] != original["refresh_token"]

    def test_refresh_preserves_subject(self):
        original = create_device_tokens("device-refresh-2")
        new_tokens = refresh_access_token(original["refresh_token"])

        old_payload = decode_token(original["token"])
        new_payload = decode_token(new_tokens["token"])

        assert old_payload["sub"] == new_payload["sub"]

    def test_refresh_token_rejects_access_token(self):
        tokens = create_device_tokens("device-bad")
        # Try to use access token as refresh
        with pytest.raises(Exception):
            refresh_access_token(tokens["token"])
