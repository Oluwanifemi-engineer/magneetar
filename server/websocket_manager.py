"""
Magneetar WebSocket Manager
Shared state for WebSocket connections and broadcasting to dashboards.
Extracted from main.py to avoid circular imports between main.py and route modules.
"""

import asyncio
import logging
import time
from typing import Optional

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

# Per-connection scope. NEVER None for a live connection: None means the
# connection was not authenticated, and unauthenticated connections must not
# receive any device data (see _connection_can_receive).
#   ADMIN_OWNER  -> dashboard/operator token: sees all devices
#   str user id  -> user token: sees only devices linked to that account
_connection_owners: dict[int, Optional[str]] = {}

# Explicit sentinel for authenticated admin connections. The old design used
# None as "admin", which made UNauthenticated connections admin too — a live
# location feed for every device, no token required (F-01).
ADMIN_OWNER = "__magneetar_admin__"

# device_id -> owner_id cache, kept in sync by routes on register/claim.
_device_owners: dict[str, str] = {}


def add_connection(ws: WebSocket, owner: Optional[str] = None):
    """Register a new WebSocket connection and initialize its pong tracking.

    Args:
        owner: ADMIN_OWNER for an authenticated dashboard/operator token
            (sees all devices), or a user id (sees only devices linked to
            that account). Callers MUST pass a resolved owner — passing None
            here registers an anonymous connection that can never receive
            device broadcasts.
    """
    active_dashboard_connections.append(ws)
    _connection_owners[id(ws)] = owner
    _last_pong_times[id(ws)] = time.time()


def update_device_owner(device_id: str, owner_id: Optional[str]):
    """Keep the in-memory device→owner cache in sync after register/claim."""
    if owner_id:
        _device_owners[device_id] = owner_id
    else:
        _device_owners.pop(device_id, None)


def _message_device_id(message: dict) -> Optional[str]:
    """Extract the device_id from a broadcast message, if present."""
    if not isinstance(message, dict):
        return None
    data = message.get("data")
    if isinstance(data, dict) and data.get("device_id"):
        return data["device_id"]
    return message.get("device_id")


def _connection_can_receive(ws: WebSocket, message: dict) -> bool:
    """Scoped delivery: authenticated admins get everything, users only get
    their own devices, and UNauthenticated connections get nothing.

    Global messages without a device_id (ping, shutdown) reach every
    authenticated connection. Security: an owner of None (never registered
    with a valid token) is denied — it must never default to admin.
    """
    owner = _connection_owners.get(id(ws))
    if owner is None:
        return False  # unauthenticated — never receive device data
    if owner == ADMIN_OWNER:
        return True  # authenticated admin sees all devices
    device_id = _message_device_id(message)
    if device_id is None:
        return True  # global broadcast
    return _device_owners.get(device_id) == owner


async def broadcast_to_dashboards(message: dict):
    """Send message to all matching dashboard clients (ownership-scoped).

    Iterates over a snapshot to avoid races with concurrent heartbeat pruning.
    Dead connections are silently pruned after the broadcast.
    """
    dead: list[WebSocket] = []
    for ws in list(active_dashboard_connections):  # snapshot to avoid race with prune
        if not _connection_can_receive(ws, message):
            continue
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
        _connection_owners.pop(id(ws), None)
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
