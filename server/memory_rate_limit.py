"""
Magneetar In-Memory Rate Limiter (telemetry hot path)

The DB-backed limiter (database.check_rate_limit) writes a rate_limits row +
commit on EVERY call — on the telemetry hot path (location pings, heartbeats,
media uploads, command polls) that alone is ~2/3 of the DB writes per event
and the measured bottleneck for fleet ingest (~1,900 pings/sec).

This module replaces the DB limiter for DEVICE TELEMETRY ONLY:
  * location (30/min), heartbeat (10/min), media (10/min), command poll (30/min)
  * identical per-minute semantics, so anti-flood guardrails don't weaken

Multi-worker note: each uvicorn worker keeps its OWN instance, so with N
workers a device could in theory reach N x the per-minute limit before being
blocked. These are anti-flood guardrails rather than hard quotas — the slight
per-worker looseness is the deliberate trade for removing DB writes from the
hot path. Everything security-sensitive (login, claim, step-up, 2FA, command
issuance, SMS) stays on the DB limiter.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Deque

_lock = threading.Lock()
# key -> deque of event timestamps (oldest first), bounded to the window
_windows: dict[str, Deque[float]] = defaultdict(deque)

_MAX_KEYS = 50_000  # beyond this, idle keys are swept


def check_memory_rate_limit(key: str, max_requests: int, window_seconds: int = 60) -> bool:
    """True when the caller may proceed (within limit); records the attempt.

    Sliding window: allows up to `max_requests` events in the rolling
    `window_seconds`. Prunes expired timestamps from the front of the deque
    (amortized O(1) per call).
    """
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _windows[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        # Opportunistic memory guard: when the table grows large, drop keys
        # whose newest event has fully aged out of the window.
        if len(_windows) > _MAX_KEYS:
            sweep_locked(now=now)
        return True


def sweep(now: float | None = None) -> int:
    """Drop idle keys (all events older than the 60s window). Safe to call
    from a background task (main.py's periodic cleanup). Returns keys removed."""
    with _lock:
        return sweep_locked(now=now)


def sweep_locked(now: float | None = None) -> int:
    cutoff = (now if now is not None else time.monotonic()) - 60
    stale = [k for k, b in _windows.items() if not b or b[-1] < cutoff]
    for k in stale:
        del _windows[k]
    return len(stale)
