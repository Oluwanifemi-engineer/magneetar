"""
Magneetar Leader Lock — single-worker execution for background tasks

With uvicorn --workers > 1, every background loop started from the lifespan
runs in EVERY worker. That is safe for idempotent DB sweeps but NOT for
tasks with real side effects (offline alerting → SMS/WhatsApp/email/push):
all worker loops are phase-aligned (they tick every N seconds from process
start), so the moment a device crosses the offline threshold EVERY worker's
sweep finds it before any of them has written the dedup alert row — the
owner would receive N duplicate alerts for one incident.

This module provides a Redis SETNX leader lock:

  won, token = await acquire_task_lock("offline_monitor", ttl=120)
  if not won:
      continue            # another worker is the leader this cycle
  try:
      await run_sweep()
  finally:
      await release_task_lock("offline_monitor", token)

- Exactly one worker wins per TTL window (SET NX EX).
- release is token-safe: it only deletes the key while it still holds THIS
  acquisition, so a slow leader can never clobber a successor's lock.
- Without MT_REDIS_URL (single-worker / degraded mode) every caller wins,
  preserving the original always-run behavior.
- On a Redis hiccup the lock degrades to "granted" — running a task twice
  is better than never running it (alerts are deduped again on the next
  sweep once the row exists).
"""

import logging
import os
import secrets

logger = logging.getLogger(__name__)

_redis_client = None
_redis_attempted = False


async def _get_redis():
    """Lazy shared redis client; None when Redis is not configured/unreachable.

    Env is read at CALL time (not import time) to match websocket_manager's
    pattern — env may not be set when the module is first imported (tests,
    config loaders)."""
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
    except Exception:
        return None


async def acquire_task_lock(name: str, ttl: int = 600) -> tuple[bool, str]:
    """Try to become the leader for `name` for up to `ttl` seconds.

    Returns (won, token) — `won` is True when THIS worker should run the
    task; `token` must be passed back to release_task_lock so the release
    can never delete a newer holder's lock.
    """
    r = await _get_redis()
    if r is None:
        return True, ""  # no Redis → single-worker/local mode: everyone runs
    token = secrets.token_hex(8)
    try:
        ok = await r.set(f"magneetar:tasklock:{name}", token, nx=True, ex=ttl)
        return bool(ok), token
    except Exception:
        logger.warning(f"Leader lock '{name}' degraded: Redis unavailable — task may run in multiple workers")
        return True, token  # Redis hiccup → run anyway (see module docstring)


_UNLOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


async def release_task_lock(name: str, token: str) -> None:
    """Release the lock only if this worker still holds it (token match).

    Uses an atomic compare-and-delete Lua script (NOT get-then-delete, which
    has a TOCTOU, and NOT GETDEL, which deletes unconditionally): if our lock
    expired and a successor re-acquired it, this release leaves the
    successor's lock untouched — otherwise a slow leader finishing late
    would clobber the new leader and two workers would run the task.
    """
    if not token:
        return
    r = await _get_redis()
    if r is None:
        return
    try:
        key = f"magneetar:tasklock:{name}"
        await r.eval(_UNLOCK_SCRIPT, 1, key, token)
    except Exception:
        pass  # expiry will clean it up; never raise from a release
