"""
Magneetar Reliability Tests
Tests for: WebSocket connection limits, health endpoint DB check,
           AlertEngine retry/circuit breaker.
"""
import pytest
import json
import os
import sys
import secrets
import tempfile
import time
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db')
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "reliability-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "reliability-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Import modules with clean env
import config
config.settings.DB_PATH = test_db_path

import database
database.DB_PATH = test_db_path
database.init_db(test_db_path)

from fastapi.testclient import TestClient
from main import app
from websocket_manager import (
    active_dashboard_connections,
    MAX_DASHBOARD_CONNECTIONS,
    can_accept_new_connection,
    _safe_remove,
    prune_stale_connections,
)
from alerts import AlertEngine, alert_engine

client = TestClient(app)


# ── Cleanup ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def cleanup_ws_connections():
    """Ensure WebSocket connections are cleared after every test.
    Using autouse fixture instead of teardown_module to guarantee
    cleanup even if a test hangs or fails."""
    yield
    active_dashboard_connections.clear()


def teardown_module(module):
    """Clean up test database after all tests."""
    try:
        os.remove(test_db_path)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 1. Health Endpoint — Database Connectivity Check
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthEndpointReliability:
    """Health endpoint must report database connectivity accurately."""

    def test_health_returns_db_status(self):
        """Health response should include a 'database' field indicating connectivity."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "online"
        assert data["database"] is True
        assert "version" in data
        assert "uptime" in data
        assert "server_time" in data

    def test_health_after_db_file_removed(self, monkeypatch):
        """Simulate DB becoming inaccessible — health should report degraded."""
        monkeypatch.setattr(database, "DB_PATH", "/nonexistent/magneetar.db")

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] is False

    def test_health_requires_no_auth(self):
        """Health must be publicly accessible with no authentication."""
        response = client.get("/health")
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 2. WebSocket Connection Limits
# ═══════════════════════════════════════════════════════════════════════════

class TestWebSocketConnectionLimits:
    """WebSocket connections must be bounded and stale connections pruned."""

    def teardown_method(self):
        """Clean up connections after each test."""
        active_dashboard_connections.clear()

    @pytest.mark.asyncio
    async def test_can_accept_with_room(self):
        """can_accept_new_connection() returns True when under the limit."""
        active_dashboard_connections.clear()
        assert can_accept_new_connection() is True

    @pytest.mark.asyncio
    async def test_cannot_accept_at_capacity(self):
        """can_accept_new_connection() returns False when at the limit."""
        active_dashboard_connections.clear()
        # Fill to capacity
        for i in range(MAX_DASHBOARD_CONNECTIONS):
            active_dashboard_connections.append(MagicMock())
        assert can_accept_new_connection() is False

    @pytest.mark.asyncio
    async def test_eviction_removes_oldest(self):
        """close_lowest_priority_connection() evicts the oldest connection."""
        from websocket_manager import close_lowest_priority_connection

        active_dashboard_connections.clear()
        mocks = []
        for i in range(3):
            m = MagicMock()
            m.close = AsyncMock()
            active_dashboard_connections.append(m)
            mocks.append(m)

        oldest = mocks[0]
        await close_lowest_priority_connection()

        assert oldest not in active_dashboard_connections
        oldest.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_eviction_fires_close_with_1013(self):
        """Evicted connections receive a 1013 close code."""
        from websocket_manager import close_lowest_priority_connection

        active_dashboard_connections.clear()
        m = MagicMock()
        m.close = AsyncMock()
        active_dashboard_connections.append(m)

        await close_lowest_priority_connection()
        m.close.assert_awaited_once_with(
            code=1013, reason="Connection limit reached"
        )

    @pytest.mark.asyncio
    async def test_stale_connection_removed_on_prune(self):
        """prune_stale_connections() removes connections that fail to send."""
        active_dashboard_connections.clear()

        good = MagicMock()
        good.send_json = AsyncMock()  # succeeds

        bad = MagicMock()
        bad.send_json = AsyncMock(side_effect=Exception("connection dead"))  # fails

        active_dashboard_connections.append(good)
        active_dashboard_connections.append(bad)

        await prune_stale_connections()

        assert good in active_dashboard_connections
        assert bad not in active_dashboard_connections
        assert len(active_dashboard_connections) == 1

    @pytest.mark.asyncio
    async def test_safe_remove_logs_reason(self):
        """_safe_remove() should remove the WebSocket and log the reason."""
        active_dashboard_connections.clear()
        m = MagicMock()
        active_dashboard_connections.append(m)

        _safe_remove(m, reason="test_removal")
        assert m not in active_dashboard_connections

    @pytest.mark.slow
    def test_server_rejects_at_capacity_via_websocket(self):
        """Full WebSocket endpoint should evict oldest connection.
        NOTE: Skipped in CI (via -k "not slow") because TestClient
        .websocket_connect() blocks the event loop. The mock-based
        tests above cover the same logic. Run directly with:
            pytest -k "slow"
        """
        active_dashboard_connections.clear()

        import websocket_manager
        original_max = websocket_manager.MAX_DASHBOARD_CONNECTIONS
        websocket_manager.MAX_DASHBOARD_CONNECTIONS = 2

        try:
            with client.websocket_connect("/ws/dashboard") as ws1:
                data1 = ws1.receive_json()
                assert data1 is not None

                with client.websocket_connect("/ws/dashboard") as ws2:
                    data2 = ws2.receive_json()
                    assert data2 is not None

                    with client.websocket_connect("/ws/dashboard") as ws3:
                        data3 = ws3.receive_json()
                        assert data3 is not None

            assert len(active_dashboard_connections) <= 2
        finally:
            websocket_manager.MAX_DASHBOARD_CONNECTIONS = original_max
            active_dashboard_connections.clear()

    @pytest.mark.slow
    def test_websocket_accepts_valid_connection(self):
        """A single WebSocket connection should be accepted and registered.
        NOTE: Skipped in CI (via -k "not slow") because TestClient
        .websocket_connect() blocks the event loop. The mock-based
        tests above cover the same logic. Run directly with:
            pytest -k "slow"
        """
        active_dashboard_connections.clear()

        with client.websocket_connect("/ws/dashboard") as ws:
            assert ws is not None
            assert len(active_dashboard_connections) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. AlertEngine — Retry & Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════

class TestAlertEngineRetry:
    """AlertEngine must retry failed sends and track consecutive failures."""

    @pytest.mark.asyncio
    async def test_send_with_retry_succeeds_first_attempt(self):
        """Happy path: single attempt succeeds, no retry needed."""
        engine = AlertEngine()
        send_fn = AsyncMock(return_value=True)

        result = await engine._send_with_retry("email", send_fn, "to@example.com", "theft_detected", {})

        assert result is True
        send_fn.assert_awaited_once()
        assert engine._channel_failures.get("email") == 0

    @pytest.mark.asyncio
    async def test_send_with_retry_retries_on_failure(self):
        """First attempt fails, retry succeeds."""
        engine = AlertEngine()
        send_fn = AsyncMock(side_effect=[False, True])

        result = await engine._send_with_retry("email", send_fn, "to@example.com", "theft_detected", {})

        assert result is True
        assert send_fn.await_count == 2

    @pytest.mark.asyncio
    async def test_send_with_retry_retries_on_exception(self):
        """First attempt raises, retry succeeds."""
        engine = AlertEngine()
        send_fn = AsyncMock(side_effect=[ConnectionError("network down"), True])

        result = await engine._send_with_retry("email", send_fn, "to@example.com", "theft_detected", {})

        assert result is True
        assert send_fn.await_count == 2

    @pytest.mark.asyncio
    async def test_channel_disabled_after_5_failures(self):
        """After MAX_CONSECUTIVE_FAILURES, channel is skipped."""
        engine = AlertEngine()
        send_fn = AsyncMock(return_value=False)

        # 5 consecutive failures
        for attempt in range(engine.MAX_CONSECUTIVE_FAILURES):
            result = await engine._send_with_retry("test_ch", send_fn)
            assert result is False

        assert engine._should_skip_channel("test_ch") is True

    @pytest.mark.asyncio
    async def test_skipped_channel_returns_false_immediately(self):
        """Skipped channel should return False without calling send_fn.
        The circuit breaker must be open (disabled_at set) for the skip to trigger.
        """
        engine = AlertEngine()
        send_fn = AsyncMock(return_value=True)

        # Disable channel — set both counter AND disabled_at timestamp
        engine._channel_failures["skip_ch"] = engine.MAX_CONSECUTIVE_FAILURES
        engine._channel_disabled_at["skip_ch"] = time.time()

        result = await engine._send_with_retry("skip_ch", send_fn)

        assert result is False
        send_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_channel_recovered_after_success(self):
        """A single success should reset the failure count to 0."""
        engine = AlertEngine()
        send_fn = AsyncMock(return_value=False)

        # 3 failures
        for _ in range(3):
            await engine._send_with_retry("recover_ch", send_fn)

        assert engine._channel_failures["recover_ch"] == 3

        # Now succeed
        send_fn.return_value = True
        result = await engine._send_with_retry("recover_ch", send_fn)

        assert result is True
        assert engine._channel_failures["recover_ch"] == 0

    @pytest.mark.asyncio
    async def test_different_channels_independent(self):
        """Failure in one channel should not affect another."""
        engine = AlertEngine()
        fail_fn = AsyncMock(return_value=False)
        success_fn = AsyncMock(return_value=True)

        # Fail email 3 times
        for _ in range(3):
            await engine._send_with_retry("email", fail_fn)

        # SMS should still succeed
        result = await engine._send_with_retry("sms", success_fn)
        assert result is True

        assert engine._channel_failures.get("email") == 3
        assert engine._channel_failures.get("sms") == 0

    @pytest.mark.asyncio
    async def test_send_all_with_retry(self):
        """send_all should route through _send_with_retry and record results."""
        engine = AlertEngine()
        with (
            patch.object(engine, '_send_with_retry', new=AsyncMock(return_value=True)) as mock_retry,
            patch('alerts.get_db_context') as mock_db,
        ):
            mock_db.return_value.__enter__.return_value = MagicMock()
            results = await engine.send_all(
                device_id="test-device",
                alert_type="theft_detected",
                data={
                    "email": "test@example.com",
                    "phone": "+234800000000",
                    "location": "9.0820, 8.6753",
                    "time": "2026-01-01T00:00:00",
                    "score": "85",
                },
                channels=["email", "sms"]
            )

            assert results.get("email") is True
            assert results.get("sms") is True
            assert mock_retry.await_count == 2

    @pytest.mark.asyncio
    async def test_send_all_with_push_tokens(self):
        """send_all should route push sends through _send_with_retry."""
        engine = AlertEngine()
        with (
            patch.object(engine, '_send_with_retry', new=AsyncMock(return_value=True)) as mock_retry,
            patch('alerts.get_db_context') as mock_db,
        ):
            mock_db.return_value.__enter__.return_value = MagicMock()
            results = await engine.send_all(
                device_id="test-device",
                alert_type="theft_detected",
                data={
                    "email": "test@example.com",
                    "push_token": "fcm-token-123",
                    "location": "9.0820, 8.6753",
                    "time": "2026-01-01T00:00:00",
                    "score": "85",
                },
                channels=["push"]
            )

            assert results.get("push") is True
            mock_retry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_all_handles_empty_tokens_gracefully(self):
        """send_all with push channel but no tokens should not crash."""
        engine = AlertEngine()
        with (
            patch.object(engine, '_send_with_retry', new=AsyncMock(return_value=True)),
            patch('alerts.get_db_context') as mock_db,
        ):
            mock_db.return_value.__enter__.return_value = MagicMock()
            results = await engine.send_all(
                device_id="no-token-device",
                alert_type="theft_detected",
                data={
                    "location": "0.0, 0.0",
                    "time": "2026-01-01T00:00:00",
                    "score": "0",
                },
                channels=["push"]
            )
            # push without tokens = no calls to retry, success=False
            assert "push" in results

    @pytest.mark.asyncio
    async def test_circuit_breaker_independent_instances(self):
        """Two AlertEngine instances should have independent circuit breaker state."""
        engine1 = AlertEngine()
        engine2 = AlertEngine()
        fail_fn = AsyncMock(return_value=False)

        # Only engine1 fails
        for _ in range(3):
            await engine1._send_with_retry("sms", fail_fn)

        assert engine1._should_skip_channel("sms") is False  # 3 < 5
        assert engine2._should_skip_channel("sms") is False  # fresh instance

    @pytest.mark.asyncio
    async def test_channel_failures_capped_at_max(self):
        """Failure count should not exceed MAX_CONSECUTIVE_FAILURES."""
        engine = AlertEngine()
        send_fn = AsyncMock(return_value=False)

        # Fail 10 times — count should plateau at MAX_CONSECUTIVE_FAILURES after the 5th
        for _ in range(10):
            await engine._send_with_retry("cap_ch", send_fn)

        assert engine._channel_failures["cap_ch"] == engine.MAX_CONSECUTIVE_FAILURES
