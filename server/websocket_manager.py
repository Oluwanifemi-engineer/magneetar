"""
Magneetar WebSocket Manager
Shared state for WebSocket connections and broadcasting to dashboards.
Extracted from main.py to avoid circular imports between main.py and route modules.
"""

import asyncio
import logging
import time

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────
MAX_DASHBOARD_CONNECTIONS: int = 100
"""Hard limit to prevent resource exhaustion from rogue or excessive connections."""

HEARTBEAT_INTERVAL: int = 30
"""Seconds between heartbeat pings to connected dashboards."""

STALE_TIMEOUT: float = 90.0
"""If a dashboard hasn't responded to a heartbeat ping within this many seconds,
it is considered stale and pruned. Set to 3x HEARTBEAT_INTERVAL by default."""


# ── Active Connections ───────────────────────────────────────────────────
active_dashboard_connections: list[WebSocket] = []
"""Live dashboard WebSocket connections. Guarded by MAX_DASHBOARD_CONNECTIONS."""

# Track last time each connection sent a pong response (for stale detection)
_last_pong_times: dict[int, float] = {}
"""Maps id(ws) -> timestamp of last received pong from that client.
Initialized to the connection time when the client first connects."""


def add_connection(ws: WebSocket):
    """Register a new WebSocket connection and initialize its pong tracking."""
    active_dashboard_connections.append(ws)
    _last_pong_times[id(ws)] = time.time()


async def broadcast_to_dashboards(message: dict):
    """Send message to all connected dashboard clients.

    Iterates over a snapshot to avoid races with concurrent heartbeat pruning.
    Dead connections are silently pruned after the broadcast.
    """
    dead: list[WebSocket] = []
    for ws in list(active_dashboard_connections):  # snapshot to avoid race with prune
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _safe_remove(ws, reason="broadcast_failure")


def remove_websocket(ws: WebSocket):
    """Remove a WebSocket from active connections (safe to call from anywhere)."""
    _safe_remove(ws, reason="explicit_removal")


def record_pong(ws: WebSocket):
    """Record a pong response from a dashboard client."""
    _last_pong_times[id(ws)] = time.time()


def _safe_remove(ws: WebSocket, reason: str = "unknown"):
    """Safely remove a WebSocket and log the reason."""
    if ws in active_dashboard_connections:
        active_dashboard_connections.remove(ws)
        _last_pong_times.pop(id(ws), None)
        logger.info(
            "WebSocket removed",
            extra={
                "extra_data": {
                    "reason": reason,
                    "remaining": len(active_dashboard_connections),
                    "max": MAX_DASHBOARD_CONNECTIONS,
                }
            },
        )


def can_accept_new_connection() -> bool:
    """Check if the connection limit allows a new WebSocket."""
    return len(active_dashboard_connections) < MAX_DASHBOARD_CONNECTIONS


async def close_lowest_priority_connection():
    """If at capacity, forcibly close the oldest connection to make room.

    This is a last resort — callers should check can_accept_new_connection() first.
    """
    if active_dashboard_connections:
        oldest = active_dashboard_connections[0]
        try:
            await oldest.close(code=1013, reason="Connection limit reached")
        except Exception:
            pass
        _safe_remove(oldest, reason="evicted_connection_limit")


async def prune_stale_connections():
    """Periodic task: close connections that have gone silent.

    Two-layer detection:
    1. Send a JSON ping — if send_json() throws, the socket is dead, remove immediately.
    2. Check last_pong timestamp — if a client hasn't responded within STALE_TIMEOUT
       seconds, close it as unresponsive (application-level heartbeat miss).
    """
    now = time.time()
    dead_send: list[WebSocket] = []
    dead_pong: list[WebSocket] = []

    for ws in list(active_dashboard_connections):  # snapshot
        try:
            await ws.send_json({"type": "ping"})
            # Check pong freshness
            last_pong = _last_pong_times.get(id(ws), 0.0)
            if last_pong > 0 and now - last_pong > STALE_TIMEOUT:
                dead_pong.append(ws)
        except Exception:
            dead_send.append(ws)

    for ws in dead_send:
        _safe_remove(ws, reason="prune_stale_dead_socket")
    for ws in dead_pong:
        _safe_remove(ws, reason="prune_stale_no_pong")

    total = len(dead_send) + len(dead_pong)
    if total:
        logger.warning(
            "Pruned stale WebSocket connections",
            extra={
                "extra_data": {
                    "dead_socket": len(dead_send),
                    "no_pong": len(dead_pong),
                    "remaining": len(active_dashboard_connections),
                }
            },
        )


async def start_connection_heartbeat(interval: int = None):
    """Background asyncio task: periodically prune stale connections.

    Args:
        interval: Seconds between heartbeat checks (default HEARTBEAT_INTERVAL = 30).
    """
    if interval is None:
        interval = HEARTBEAT_INTERVAL
    while True:
        await asyncio.sleep(interval)
        await prune_stale_connections()
