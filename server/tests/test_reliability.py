"""
Magneetar Reliability Tests
Tests for: WebSocket connection limits, health endpoint DB check,
           AlertEngine retry/circuit breaker.
"""

import asyncio
import json
import os
import secrets
import socket
import tempfile
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uvicorn
import websockets

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "reliability-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "reliability-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

# Import modules with clean env
import config  # noqa: E402 (env set above)

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path
database.init_db(test_db_path)

from alerts import AlertEngine, normalize_phone_to_e164  # noqa: E402
from auth import create_token  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from websocket_manager import (  # noqa: E402
    MAX_DASHBOARD_CONNECTIONS,
    _safe_remove,
    active_dashboard_connections,
    can_accept_new_connection,
    prune_stale_connections,
)

client = TestClient(app)


async def _wait_until(predicate, timeout: float = 3.0) -> bool:
    """Poll a plain condition until it holds or the timeout elapses.

    WebSocket registration/eviction happens in the uvicorn thread, so the
    test must poll the shared module-level connection list rather than sleep.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def _assert_closed_with_code(url: str, code: int) -> None:
    """Assert that connecting to `url` is closed by the server with `code`.

    Assumes the endpoint accepts first and only closes afterward (e.g. 4001 on
    auth failure), so the client sees the close frame on recv(). If an endpoint
    ever rejected during the HTTP handshake instead, websockets.connect() would
    raise InvalidStatus (not ConnectionClosed) and this helper would surface it
    as a raw error rather than an assertion.
    """
    try:
        async with websockets.connect(url) as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
        raise AssertionError("connection should have been closed")
    except websockets.exceptions.ConnectionClosed as exc:
        assert getattr(exc.rcvd, "code", None) == code


@pytest.fixture
def live_ws_server():
    """Run the real FastAPI app under uvicorn in a background thread.

    Function-scoped (NOT module-scoped): the uvicorn lifespan starts a
    ~30s heartbeat task that iterates the shared active_dashboard_connections
    list. If it ran for the whole module, it could prune MagicMocks out from
    under the mock-based WS tests mid-assertion — a CI flakiness vector.
    Two quick server spins (~1-2s total) is a fair price for full isolation.

    Starlette's sync TestClient.websocket_connect() deadlocks against
    /ws/dashboard's persistent `while True: receive_text()` loop, so live
    endpoint coverage uses a real uvicorn server + the websockets client.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, args=([sock],), daemon=True)
    thread.start()

    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn failed to start for WebSocket integration test"

    yield f"ws://127.0.0.1:{port}/ws/dashboard"

    server.should_exit = True
    thread.join(timeout=5)


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
        for _i in range(MAX_DASHBOARD_CONNECTIONS):
            active_dashboard_connections.append(MagicMock())
        assert can_accept_new_connection() is False

    @pytest.mark.asyncio
    async def test_eviction_removes_oldest(self):
        """close_lowest_priority_connection() evicts the oldest connection."""
        from websocket_manager import close_lowest_priority_connection

        active_dashboard_connections.clear()
        mocks = []
        for _i in range(3):
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
        m.close.assert_awaited_once_with(code=1013, reason="Connection limit reached")

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
    @pytest.mark.asyncio
    async def test_server_rejects_at_capacity_via_websocket(self, live_ws_server):
        """Full WebSocket endpoint should evict oldest connection at capacity.

        Live integration test — real uvicorn server + websockets client.
        (TestClient.websocket_connect() blocks the event loop against the
        endpoint's persistent receive loop, so it can't test this path.)
        """
        import websocket_manager

        original_max = websocket_manager.MAX_DASHBOARD_CONNECTIONS
        websocket_manager.MAX_DASHBOARD_CONNECTIONS = 2

        ws2 = ws3 = None
        try:
            ws1 = await websockets.connect(live_ws_server)
            ws2 = await websockets.connect(live_ws_server)
            assert await _wait_until(lambda: len(active_dashboard_connections) == 2)

            ws3 = await websockets.connect(live_ws_server)

            # ws1 (oldest) must be evicted with close code 1013
            assert await _wait_until(lambda: len(active_dashboard_connections) == 2)
            try:
                await asyncio.wait_for(ws1.recv(), timeout=2.0)
                raise AssertionError("ws1 should have been evicted")
            except websockets.exceptions.ConnectionClosed as exc:
                assert getattr(exc.rcvd, "code", None) == 1013
        finally:
            for ws in (ws2, ws3):
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass
            websocket_manager.MAX_DASHBOARD_CONNECTIONS = original_max
            active_dashboard_connections.clear()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_accepts_valid_connection(self, live_ws_server):
        """A single WebSocket connection should be accepted, registered, and answer pings.

        Live integration test — real uvicorn server + websockets client.
        """
        active_dashboard_connections.clear()

        async with websockets.connect(live_ws_server) as ws:
            assert await _wait_until(lambda: len(active_dashboard_connections) == 1)
            await ws.send("ping")
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert pong["type"] == "pong"

        # Connection must be deregistered after the client disconnects
        assert await _wait_until(lambda: len(active_dashboard_connections) == 0)

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_accepts_valid_token(self, live_ws_server):
        """A connection with a valid dashboard/access token is accepted and registered."""
        token = create_token("dashboard:test", "dashboard")
        url = f"{live_ws_server}?token={token}"
        active_dashboard_connections.clear()

        async with websockets.connect(url) as ws:
            assert await _wait_until(lambda: len(active_dashboard_connections) == 1)
            await ws.send("ping")
            pong = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
            assert pong["type"] == "pong"

        assert await _wait_until(lambda: len(active_dashboard_connections) == 0)

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_invalid_token(self, live_ws_server):
        """A connection with a garbage token is rejected with close code 4001."""
        url = f"{live_ws_server}?token=not-a-real-token"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_wrong_token_type(self, live_ws_server):
        """A device-type token (not dashboard/access) is rejected with 4001."""
        token = create_token("device-123", "device")
        url = f"{live_ws_server}?token={token}"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_expired_token(self, live_ws_server):
        """An expired dashboard token is rejected with close code 4001."""
        from datetime import timedelta

        # exp in the past → decode_token raises ExpiredSignatureError → 4001
        token = create_token("dashboard:expired", "dashboard", timedelta(seconds=-60))
        url = f"{live_ws_server}?token={token}"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_revoked_token(self, live_ws_server):
        """A token whose jti is on the revocation list is rejected with 4001.

        Covers the end-to-end revocation path: DB row → decode_token's
        revocation check → generic handler → close 4001.
        """
        import jwt

        token = create_token("dashboard:revoked", "dashboard")
        jti = jwt.decode(token, config.settings.JWT_SECRET, algorithms=["HS256"])["jti"]
        with database.get_db_context() as conn:
            conn.execute("INSERT OR IGNORE INTO revoked_tokens (jti, reason) VALUES (?, ?)", (jti, "test"))
            conn.commit()

        url = f"{live_ws_server}?token={token}"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_tampered_signature(self, live_ws_server):
        """A valid token with a corrupted signature is rejected with 4001."""
        token = create_token("dashboard:tampered", "dashboard")
        # Flip one char in the signature segment (base64url chars only)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        assert tampered != token
        url = f"{live_ws_server}?token={tampered}"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_websocket_rejects_token_missing_type(self, live_ws_server):
        """A validly-signed JWT with no type claim is rejected with 4001.

        Covers payload.get("type") not in ("dashboard", "access") when the
        claim is absent entirely.
        """
        from datetime import datetime, timedelta, timezone

        import jwt

        now = datetime.now(timezone.utc)
        payload = {"sub": "dashboard:no-type", "iat": now, "exp": now + timedelta(hours=1)}
        token = jwt.encode(payload, config.settings.JWT_SECRET, algorithm="HS256")
        url = f"{live_ws_server}?token={token}"
        active_dashboard_connections.clear()

        await _assert_closed_with_code(url, 4001)
        assert len(active_dashboard_connections) == 0


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
        for _attempt in range(engine.MAX_CONSECUTIVE_FAILURES):
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
            patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry,
            patch("alerts.get_db_context") as mock_db,
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
                channels=["email", "sms"],
            )

            assert results.get("email") is True
            assert results.get("sms") is True
            assert mock_retry.await_count == 2

    @pytest.mark.asyncio
    async def test_send_all_with_push_tokens(self):
        """send_all should route push sends through _send_with_retry."""
        engine = AlertEngine()
        with (
            patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry,
            patch("alerts.get_db_context") as mock_db,
        ):
            # Per-device recipient lookup must return no row (None) so the
            # recipient resolution falls through to data/env instead of
            # treating the mock as a real device row.
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_db.return_value.__enter__.return_value = mock_conn
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
                channels=["push"],
            )

            assert results.get("push") is True
            mock_retry.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_all_handles_empty_tokens_gracefully(self):
        """send_all with push channel but no tokens should not crash."""
        engine = AlertEngine()
        with (
            patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)),
            patch("alerts.get_db_context") as mock_db,
        ):
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = None
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_db.return_value.__enter__.return_value = mock_conn
            results = await engine.send_all(
                device_id="no-token-device",
                alert_type="theft_detected",
                data={
                    "location": "0.0, 0.0",
                    "time": "2026-01-01T00:00:00",
                    "score": "0",
                },
                channels=["push"],
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


# ═══════════════════════════════════════════════════════════════════════════
# 4. AlertEngine — Channel Providers (Twilio SMS / WhatsApp)
# ═══════════════════════════════════════════════════════════════════════════


# Fixture restores config.settings after each test — it is a shared module-
# level singleton, so mutations MUST NOT leak into other tests.
@pytest.fixture(autouse=True)
def _restore_alert_settings():
    saved = {
        "TWILIO_SID": config.settings.TWILIO_SID,
        "TWILIO_AUTH_TOKEN": config.settings.TWILIO_AUTH_TOKEN,
        "TWILIO_SMS_FROM": config.settings.TWILIO_SMS_FROM,
        "TWILIO_WHATSAPP_FROM": config.settings.TWILIO_WHATSAPP_FROM,
        "TWILIO_WHATSAPP_TEMPLATE_SID": config.settings.TWILIO_WHATSAPP_TEMPLATE_SID,
        "TWILIO_WHATSAPP_TEMPLATE_VARIABLES": config.settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES,
        "TERMII_API_KEY": config.settings.TERMII_API_KEY,
    }
    yield
    for k, v in saved.items():
        setattr(config.settings, k, v)


class TestAlertEngineChannels:
    """SMS/WhatsApp channels must route to Twilio and use configurable From."""

    @pytest.mark.asyncio
    async def test_send_sms_prefers_twilio(self):
        """When Twilio SMS From is configured, send_sms uses Twilio."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "+15551234567"
        config.settings.TERMII_API_KEY = ""

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_sms("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is True
        call_kwargs = mock_client.return_value.__aenter__.return_value.post.call_args
        url = call_kwargs.args[0]
        data = call_kwargs.kwargs["data"]
        assert "api.twilio.com" in url
        assert data["To"] == "+15557654321"
        assert data["From"] == "+15551234567"
        assert "MAGNEETAR" in data["Body"]

    @pytest.mark.asyncio
    async def test_send_sms_falls_back_to_termii_when_twilio_unconfigured(self):
        """When Twilio SMS From is missing, send_sms falls back to Termii."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = ""  # not configured → fallback
        config.settings.TERMII_API_KEY = "termii-key-123"

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_sms("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is True
        url = mock_client.return_value.__aenter__.return_value.post.call_args.args[0]
        assert "api.termii.com" in url

    @pytest.mark.asyncio
    async def test_send_sms_returns_false_when_no_provider_configured(self):
        """No Twilio SMS From and no Termii key → returns False (no exception)."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = ""
        config.settings.TERMII_API_KEY = ""

        result = await engine.send_sms("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_sms_false_when_twilio_rejects_and_termii_unconfigured(self):
        """Twilio non-2xx AND no Termii key → send_sms returns False."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "+15551234567"
        config.settings.TERMII_API_KEY = ""

        twilio_fail = MagicMock()
        twilio_fail.status_code = 401
        twilio_fail.text = '{"code": 20003, "message": "Authentication Error"}'

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=twilio_fail)
            result = await engine.send_sms("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is False

    @pytest.mark.asyncio
    async def test_send_sms_falls_back_to_termii_when_twilio_rejects(self):
        """Twilio returns non-2xx (e.g. 401) → send_sms falls through to Termii."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "+15551234567"
        config.settings.TERMII_API_KEY = "termii-key-123"

        twilio_fail = MagicMock()
        twilio_fail.status_code = 401
        twilio_fail.text = '{"code": 20003, "message": "Authentication Error"}'
        termii_ok = MagicMock()
        termii_ok.status_code = 200

        # First call (Twilio) fails, second call (Termii) succeeds
        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_post = mock_client.return_value.__aenter__.return_value.post
            mock_post.side_effect = [twilio_fail, termii_ok]
            result = await engine.send_sms("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is True
        assert mock_post.await_count == 2
        urls = [call.args[0] for call in mock_post.call_args_list]
        assert "api.twilio.com" in urls[0]
        assert "api.termii.com" in urls[1]

    @pytest.mark.asyncio
    async def test_send_whatsapp_uses_configured_from(self):
        """WhatsApp uses the configurable TWILIO_WHATSAPP_FROM number."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_FROM = "whatsapp:+15559998888"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is True
        call_kwargs = mock_client.return_value.__aenter__.return_value.post.call_args
        data = call_kwargs.kwargs["data"]
        assert data["To"] == "whatsapp:+15557654321"
        assert data["From"] == "whatsapp:+15559998888"

    @pytest.mark.asyncio
    async def test_send_whatsapp_defaults_to_sandbox_number(self):
        """WhatsApp defaults to Twilio's shared sandbox number."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"  # default

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            await engine.send_whatsapp("+15557654321", "theft_detected", {"location": "0,0"})

        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        assert data["From"] == "whatsapp:+14155238886"

    @pytest.mark.asyncio
    async def test_send_whatsapp_returns_false_when_twilio_missing(self):
        """No Twilio creds → WhatsApp returns False without making a request."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = ""
        config.settings.TWILIO_AUTH_TOKEN = ""

        with patch("alerts.httpx.AsyncClient") as mock_client:
            result = await engine.send_whatsapp("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is False
        mock_client.return_value.__aenter__.return_value.post.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_whatsapp_rejects_template_required_error(self):
        """63010 (template required) → returns False and logs actionable warning."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"code": 63010, "message": "Template required"}'

        with (
            patch("alerts.httpx.AsyncClient") as mock_client,
            patch("alerts.logger") as mock_logger,
        ):
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp("+15557654321", "theft_detected", {"location": "0,0"})

        assert result is False
        # An actionable warning about the approved template must be logged
        warn_calls = " ".join(str(c.args) for c in mock_logger.warning.call_args_list)
        assert "63010" in warn_calls
        assert "template" in warn_calls.lower()

    @pytest.mark.asyncio
    async def test_send_whatsapp_uses_template_when_configured(self):
        """With a template SID set, send_whatsapp sends ContentSid+ContentVariables."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "HX" + "a" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES = {
            "1": "location",
            "2": "time",
            "3": "score",
        }

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp(
                "+2348081234567",
                "theft_detected",
                {"location": "9.08, 8.67", "time": "2026-01-01T00:00:00", "score": "85"},
            )

        assert result is True
        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        assert data["ContentSid"] == "HX" + "a" * 32
        assert "Body" not in data
        variables = json.loads(data["ContentVariables"])
        assert variables == {"1": "9.08, 8.67", "2": "2026-01-01T00:00:00", "3": "85"}

    @pytest.mark.asyncio
    async def test_send_whatsapp_template_uses_default_variables_mapping(self):
        """Unset template variables fall back to the default location/time/score map."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "HX" + "b" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES = {}  # unset → defaults

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            await engine.send_whatsapp(
                "+2348081234567",
                "theft_detected",
                {"location": "9.08, 8.67", "time": "2026-01-01T00:00:00", "score": "85"},
            )

        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        variables = json.loads(data["ContentVariables"])
        # Default map: 1→location, 2→time, 3→score
        assert variables["1"] == "9.08, 8.67"
        assert variables["2"] == "2026-01-01T00:00:00"
        assert variables["3"] == "85"

    @pytest.mark.asyncio
    async def test_send_whatsapp_template_missing_key_becomes_empty(self):
        """Missing data keys in template mode must not crash — empty string instead."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "HX" + "c" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES = {"1": "location", "2": "missing_key"}

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp(
                "+2348081234567",
                "theft_detected",
                {"location": "9.08, 8.67"},
            )

        assert result is True
        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        variables = json.loads(data["ContentVariables"])
        assert variables["1"] == "9.08, 8.67"
        assert variables["2"] == ""

    @pytest.mark.asyncio
    async def test_send_whatsapp_template_63018_detected(self):
        """63018 (template not found) must be detected and logged with guidance."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "HX" + "d" * 32

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"code": 63018, "message": "Template not found"}'

        with (
            patch("alerts.httpx.AsyncClient") as mock_client,
            patch("alerts.logger") as mock_logger,
        ):
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp(
                "+2348081234567",
                "theft_detected",
                {"location": "0,0"},
            )

        assert result is False
        warn_calls = " ".join(str(c.args) for c in mock_logger.warning.call_args_list)
        assert "63018" in warn_calls
        assert "TEMPLATE_SID" in warn_calls

    @pytest.mark.asyncio
    async def test_send_all_default_channels_include_whatsapp(self):
        """Default channel set must route whatsapp through _send_with_retry.

        Sets TWILIO_SID because send_all only fires the whatsapp branch when
        Twilio is configured (guard added to avoid needless retries for an
        unconfigured channel). The autouse _twilio_settings fixture restores
        the value afterward, so no leakage.
        """
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        with (
            patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry,
            patch("alerts.get_db_context") as mock_db,
        ):
            mock_db.return_value.__enter__.return_value = MagicMock()
            results = await engine.send_all(
                device_id="test-device",
                alert_type="theft_detected",
                data={
                    "phone": "+234800000000",
                    "location": "9.08, 8.67",
                    "time": "2026-01-01T00:00:00",
                    "score": "85",
                },
            )

            assert results.get("whatsapp") is True
            assert results.get("sms") is True
            assert "push" in results
            # whatsapp + sms + push each routed through the retry wrapper
            channels_called = {c.args[0] for c in mock_retry.call_args_list}
            assert "whatsapp" in channels_called
            assert "sms" in channels_called


# ═══════════════════════════════════════════════════════════════════════════
# 4b2. Per-Device Alert Recipients
# ═══════════════════════════════════════════════════════════════════════════


class TestPerDeviceRecipients:
    """send_all must resolve per-device recipients: data > device row > env."""

    def _insert_device(self, device_id: str, phone: str, email: str):
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO devices (id, alert_phone, alert_email) VALUES (?, ?, ?)",
                (device_id, phone, email),
            )
            conn.commit()

    @pytest.mark.asyncio
    async def test_send_all_uses_per_device_phone_from_db(self):
        """When data has no phone, send_all falls back to the device's alert_phone."""
        device_id = "pd-recipient-dev"
        self._insert_device(device_id, "+2348081234567", "dev@example.com")
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "+17432209510"

        with patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry:
            results = await engine.send_all(
                device_id=device_id,
                alert_type="theft_detected",
                data={"location": "9.08, 8.67", "time": "2026-01-01T00:00:00", "score": "85"},
            )

        # whatsapp must have been attempted with the per-device phone (E.164)
        wa_calls = [c for c in mock_retry.call_args_list if c.args[0] == "whatsapp"]
        assert wa_calls, "whatsapp channel should have been attempted"
        assert wa_calls[0].args[2] == "+2348081234567"
        # email must have been attempted with the per-device email
        email_calls = [c for c in mock_retry.call_args_list if c.args[0] == "email"]
        assert email_calls, "email channel should have been attempted"
        assert email_calls[0].args[2] == "dev@example.com"
        assert results.get("whatsapp") is True

    @pytest.mark.asyncio
    async def test_send_all_data_phone_overrides_device(self):
        """An explicit phone in the alert data must override the device setting."""
        device_id = "pd-override-dev"
        self._insert_device(device_id, "+2348081111111", "")
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32

        with patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry:
            await engine.send_all(
                device_id=device_id,
                alert_type="theft_detected",
                data={
                    "phone": "08089999999",  # local format — must normalize
                    "location": "0,0",
                    "time": "2026-01-01T00:00:00",
                    "score": "85",
                },
            )

        wa_calls = [c for c in mock_retry.call_args_list if c.args[0] == "whatsapp"]
        assert wa_calls, "whatsapp channel should have been attempted"
        # Data phone (normalized) wins over the device's +2348081111111
        assert wa_calls[0].args[2] == "+2348089999999"

    @pytest.mark.asyncio
    async def test_send_all_no_device_row_falls_back_to_env(self, monkeypatch):
        """Device without recipients + no data phone → global env is used."""
        # Create the device row (required by alerts FK) but leave its recipient
        # fields empty so the lookup falls through to the env fallback.
        with database.get_db_context() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO devices (id, alert_phone, alert_email) VALUES (?, '', '')",
                ("no-recipient-dev",),
            )
            conn.commit()

        monkeypatch.setenv("MT_ALERT_PHONE", "+2348123456789")
        monkeypatch.setenv("MT_ALERT_EMAIL", "")
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32

        with patch.object(engine, "_send_with_retry", new=AsyncMock(return_value=True)) as mock_retry:
            await engine.send_all(
                device_id="no-recipient-dev",
                alert_type="theft_detected",
                data={"location": "0,0", "time": "2026-01-01T00:00:00", "score": "85"},
            )

        wa_calls = [c for c in mock_retry.call_args_list if c.args[0] == "whatsapp"]
        assert wa_calls
        assert wa_calls[0].args[2] == "+2348123456789"


# ═══════════════════════════════════════════════════════════════════════════
# 4b. Phone Number Normalization (E.164)
# ═══════════════════════════════════════════════════════════════════════════


class TestPhoneNormalization:
    """Local phone numbers must be normalized to E.164 before hitting Twilio."""

    def test_nigerian_local_format_converts_to_e164(self):
        """0808... (11-digit local) → +234808... (E.164)."""
        assert normalize_phone_to_e164("08081234567") == "+2348081234567"

    def test_already_e164_unchanged(self):
        """Numbers already in E.164 are returned untouched."""
        assert normalize_phone_to_e164("+2348081234567") == "+2348081234567"
        assert normalize_phone_to_e164("+15557654321") == "+15557654321"

    def test_international_dialing_prefix_handled(self):
        """00-prefixed international dialing → E.164."""
        assert normalize_phone_to_e164("002348081234567") == "+2348081234567"

    def test_formatting_stripped(self):
        """Spaces, dashes, parens removed."""
        assert normalize_phone_to_e164("+1 (555) 123-4567") == "+15551234567"

    def test_empty_and_none_passthrough(self):
        """Empty input returned as-is (no crash)."""
        assert normalize_phone_to_e164("") == ""
        assert normalize_phone_to_e164(None) is None

    def test_short_nonlocal_number_unchanged(self):
        """Ambiguous short numbers are never guessed at."""
        assert normalize_phone_to_e164("1234") == "1234"

    def test_bare_digits_without_country_code_unchanged(self):
        """A bare number without '+' or leading 0 is ambiguous — pass through.
        E.g. a US number typed as 15557654321 must NOT become +2341555...
        (that would be a wrong-country mangling).
        """
        assert normalize_phone_to_e164("15557654321") == "15557654321"

    def test_country_code_without_plus_prefix_added(self):
        """Bare digits that already start with the country code get '+'."""
        assert normalize_phone_to_e164("2348081234567") == "+2348081234567"

    @pytest.mark.asyncio
    async def test_send_sms_normalizes_local_number(self):
        """send_sms must convert 0808... → +234808... before POSTing to Twilio."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "+17432209510"
        config.settings.TERMII_API_KEY = ""

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_sms("08081234567", "theft_detected", {"location": "0,0"})

        assert result is True
        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        assert data["To"] == "+2348081234567"

    @pytest.mark.asyncio
    async def test_send_whatsapp_normalizes_local_number(self):
        """send_whatsapp must normalize to E.164 before POSTing to Twilio."""
        engine = AlertEngine()
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.text = "sent"

        with patch("alerts.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            result = await engine.send_whatsapp("08081234567", "theft_detected", {"location": "0,0"})

        assert result is True
        data = mock_client.return_value.__aenter__.return_value.post.call_args.kwargs["data"]
        assert data["To"] == "whatsapp:+2348081234567"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Config — Optional Integration Validation (non-fatal)
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateOptional:
    """validate_optional() must warn (never raise) on bad optional config."""

    def test_empty_twilio_settings_produce_no_warnings(self):
        """Unset optional integrations must not warn."""
        config.settings.TWILIO_SID = ""
        config.settings.TWILIO_AUTH_TOKEN = ""
        config.settings.TWILIO_SMS_FROM = ""

        assert config.settings.validate_optional() == []

    def test_invalid_sid_prefix_warns(self):
        """A 'US' prefixed SID (the exact user mistake) must warn, not raise."""
        config.settings.TWILIO_SID = "US" + "x" * 32
        config.settings.TWILIO_AUTH_TOKEN = "y" * 32

        warnings = config.settings.validate_optional()
        assert any("MT_TWILIO_SID" in w and "AC" in w for w in warnings)

    def test_valid_ac_sid_produces_no_warning(self):
        """A correct 34-char AC-prefixed SID must not warn."""
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32

        warnings = config.settings.validate_optional()
        assert not any("MT_TWILIO_SID" in w for w in warnings)

    def test_invalid_auth_token_length_warns(self):
        """A non-32-char Auth Token must warn."""
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "short-token"

        warnings = config.settings.validate_optional()
        assert any("MT_TWILIO_AUTH_TOKEN" in w and "32" in w for w in warnings)

    def test_invalid_sms_from_format_warns(self):
        """A non-E.164 SMS From (no '+') must warn."""
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = "15551234567"

        warnings = config.settings.validate_optional()
        assert any("MT_TWILIO_SMS_FROM" in w for w in warnings)

    def test_twilio_configured_but_sms_from_missing_warns(self):
        """Twilio creds present but no SMS From → warn (SMS would silently no-op)."""
        config.settings.TWILIO_SID = "AC" + "1" * 32
        config.settings.TWILIO_AUTH_TOKEN = "2" * 32
        config.settings.TWILIO_SMS_FROM = ""

        warnings = config.settings.validate_optional()
        assert any("MT_TWILIO_SMS_FROM is empty" in w for w in warnings)

    def test_template_sid_wrong_prefix_warns(self):
        """A non-HX-prefixed Content template SID must warn."""
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "XX" + "x" * 32

        warnings = config.settings.validate_optional()
        assert any("MT_TWILIO_WHATSAPP_TEMPLATE_SID" in w and "HX" in w for w in warnings)

    def test_template_sid_valid_prefix_no_warning(self):
        """An HX-prefixed template SID must not warn."""
        config.settings.TWILIO_WHATSAPP_TEMPLATE_SID = "HX" + "1" * 32

        warnings = config.settings.validate_optional()
        assert not any("MT_TWILIO_WHATSAPP_TEMPLATE_SID" in w for w in warnings)

    def test_template_variables_invalid_json_warns(self, monkeypatch):
        """Invalid JSON in MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES must warn."""
        monkeypatch.setenv("MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES", "{not json}")
        # Force re-parse to exercise the env-based warning path
        config.settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES = {}

        warnings = config.settings.validate_optional()
        assert any("not valid JSON" in w for w in warnings)
