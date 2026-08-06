"""
Magneetar WebSocket Manager
Shared state for WebSocket connections and broadcasting to dashboards.
Extracted from main.py to avoid circular imports between main.py and route modules.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────
# Per-process cap on live dashboard connections. Configurable via
# MT_MAX_WS_CONNECTIONS so a multi-worker deployment can size it per worker
# (compose sets 250; 4 workers => up to ~1,000 live dashboards total).
MAX_DASHBOARD_CONNECTIONS: int = int(os.environ.get("MT_MAX_WS_CONNECTIONS", "100"))
"""Hard limit to prevent resource exhaustion from rogue or excessive connections."""

HEARTBEAT_INTERVAL: int = 30
"""Seconds between heartbeat pings to connected dashboards."""

STALE_TIMEOUT: float = 90.0
"""If a dashboard hasn't responded to a heartbeat ping within this many seconds,
it is considered stale and pruned. Set to 3x HEARTBEAT_INTERVAL by default."""

# ── Multi-worker broadcast (Redis pub/sub) ───────────────────────────────
# With --workers > 1 each worker holds its OWN in-memory connection registry,
# so a broadcast from the worker that handled a request would never reach
# dashboards connected to another worker. Messages are therefore published to
# a shared Redis channel and every worker's subscriber (redis_broadcast_listener)
# delivers them to its local connections — exactly-once per connection.
# Without MT_REDIS_URL, broadcast_to_dashboards falls back to direct local
# delivery (single-worker / degraded mode), preserving the original behavior.
REDIS_CHANNEL: str = "magneetar:ws"
_redis_client = None
_redis_attempted = False


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


def _schedule_owner_change_publish(device_id: str, owner_id: Optional[str]):
    """Fire-and-forget: tell every worker's listener to update ITS local
    device→owner cache. With --workers > 1 only the worker handling a
    register/claim updates its own cache; without this cross-worker
    invalidation the other workers would scope broadcasts to the OLD owner
    forever (their DB fallback only fires on cache MISS)."""
    r = _get_redis()
    if r is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no event loop (e.g. tests) — nothing to schedule on

    async def _publish():
        try:
            await r.publish(
                REDIS_CHANNEL,
                json.dumps(
                    {"type": "device_owner_changed", "device_id": device_id, "owner_id": owner_id},
                    default=str,
                ),
            )
        except Exception:
            pass  # cross-worker sync is best-effort; 3s polling masks misses

    loop.create_task(_publish())


def update_device_owner(device_id: str, owner_id: Optional[str]):
    """Keep the in-memory device→owner cache in sync after register/claim.

    Updates THIS worker's cache and publishes a cross-worker invalidation so
    every worker's listener refreshes its own copy (multi-worker correct)."""
    if owner_id:
        _device_owners[device_id] = owner_id
    else:
        _device_owners.pop(device_id, None)
    _schedule_owner_change_publish(device_id, owner_id)


def _message_device_id(message: dict) -> Optional[str]:
    """Extract the device_id from a broadcast message, if present."""
    if not isinstance(message, dict):
        return None
    data = message.get("data")
    if isinstance(data, dict) and data.get("device_id"):
        return data["device_id"]
    return message.get("device_id")


_UNSET = object()  # sentinel: distinguishes "no scope attached" from "unowned" (None)


def _get_redis():
    """Lazy redis client. Returns None when MT_REDIS_URL is unset or
    unreachable (single-worker / degraded mode -> local delivery only)."""
    global _redis_client, _redis_attempted
    if _redis_attempted:
        return _redis_client
    _redis_attempted = True
    url = os.environ.get("MT_REDIS_URL", "")
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return _redis_client
    except Exception as e:  # pragma: no cover - env-dependent
        logger.warning(f"Redis client init failed — falling back to local broadcast: {e}")
        return None


def _resolve_scope_owner(message: dict):
    """Attach the recipient owner scope to a broadcast message so ANY worker's
    subscriber can filter its local connections without a shared in-memory
    cache. Prefers the local device->owner cache; falls back to the DB on a
    miss (register/claim may have run on another worker)."""
    if message.get("_scope_resolved"):
        return
    message["_scope_resolved"] = True
    device_id = _message_device_id(message)
    if device_id is None:
        return
    owner = _device_owners.get(device_id)
    if owner is None:
        try:
            from database import get_db_context

            with get_db_context() as conn:
                row = conn.execute("SELECT owner_id FROM devices WHERE id=?", (device_id,)).fetchone()
                if row is not None:
                    owner = row["owner_id"]
                    _device_owners[device_id] = owner  # seed local cache
        except Exception:
            owner = None
    message["_scope_owner"] = owner


def _connection_can_receive(ws: WebSocket, message: dict) -> bool:
    """Scoped delivery: authenticated admins get everything, users only get
    their own devices, and UNauthenticated connections get nothing.

    When a broadcast carries a resolved scope (_scope_owner, attached by
    _resolve_scope_owner at publish time) it is the single source of truth —
    this is what makes cross-worker filtering correct. Global messages
    without a device_id (ping, shutdown) reach every authenticated
    connection. Security: an owner of None (never registered with a valid
    token) is denied — it must never default to admin.
    """
    owner = _connection_owners.get(id(ws))
    if owner is None:
        return False  # unauthenticated — never receive device data
    if owner == ADMIN_OWNER:
        return True  # authenticated admin sees all devices
    scope_owner = message.get("_scope_owner", _UNSET)
    if scope_owner is not _UNSET:
        return scope_owner == owner
    device_id = _message_device_id(message)
    if device_id is None:
        return True  # global broadcast
    return _device_owners.get(device_id) == owner


async def _deliver_locally(message: dict):
    """Send a message to this process's matching dashboard clients
    (ownership-scoped). Iterates over a snapshot to avoid races with
    concurrent heartbeat pruning; dead connections are silently pruned."""
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


async def broadcast_to_dashboards(message: dict):
    """Fan a message out to all matching dashboard connections.

    With Redis configured (multi-worker), publish to the shared channel and
    let every worker's subscriber deliver it locally — one delivery per
    connection, exactly. Without Redis (single worker / degraded), deliver
    locally in-process. A Redis hiccup falls back to local delivery so
    dashboards never go dark (they also poll every 3s as a safety net).
    """
    _resolve_scope_owner(message)
    r = _get_redis()
    if r is not None:
        try:
            # publish returns the number of subscribers that received the
            # message. 0 = no worker's listener is subscribed yet (startup
            # window / all listeners down) — fall back to local delivery so
            # THIS worker's dashboards still see the update.
            n = await r.publish(REDIS_CHANNEL, json.dumps(message, default=str))
            if n > 0:
                return
        except Exception:
            pass  # Redis hiccup — deliver locally
    await _deliver_locally(message)


async def redis_broadcast_listener():
    """Per-worker background task: forward shared-channel messages to this
    worker's local WebSocket connections. Self-heals on disconnects; exits
    silently when Redis is not configured (single-worker mode)."""
    r = _get_redis()
    if r is None:
        return
    while True:
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    data = json.loads(msg.get("data") or "{}")
                except (ValueError, TypeError):
                    continue
                if not isinstance(data, dict):
                    continue
                # Cross-worker owner-cache invalidation (see
                # update_device_owner) — refresh this worker's cache, never
                # broadcast it as a dashboard event.
                if data.get("type") == "device_owner_changed":
                    did = data.get("device_id")
                    oid = data.get("owner_id")
                    if oid:
                        _device_owners[did] = oid
                    else:
                        _device_owners.pop(did, None)
                    continue
                await _deliver_locally(data)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - reconnection path
            logger.warning(f"Redis listener disconnected — reconnecting: {e}")
            await asyncio.sleep(2)


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
