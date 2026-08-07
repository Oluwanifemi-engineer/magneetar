"""
Magneetar Write Queue — batched SQLite commits for the telemetry hot path.

Why this exists (measured, not assumed): with per-request commits every
location ping serializes on SQLite's single-writer lock — a 4-worker server
saturated at ~370 req/s with p50 latency of 3s because every request WAITED
up to busy_timeout for the write lock, regardless of how many workers
handled reads. Deferring the hot-path writes to ONE dedicated writer
connection per worker and committing every MT_WRITE_BATCH_MS collapses
many commits into one, taking the write lock out of the request path
entirely (requests become read-only WAL readers).

Trade-off: on crash/kill, up to one flush window (~250ms) of telemetry is
lost — acceptable for high-frequency location pings (the device re-reports
constantly; a tracking UI cares about the last fix, not every intermediate
one). Sentinel scoring uses the ping's own payload plus the previous
~10-row history; a ≤250ms lag in that history is immaterial.

Opt-in: MT_WRITE_BATCH_MS=0 (default) keeps the original synchronous
per-request commit path byte-for-byte, so this module changes nothing
unless explicitly enabled.
"""

import asyncio
import logging
import os
import sqlite3
from typing import Callable, List, Optional

logger = logging.getLogger("magneetar")


def _batch_ms() -> int:
    """Read MT_WRITE_BATCH_MS live (not at import) so tests can toggle it."""
    try:
        return max(0, int(os.environ.get("MT_WRITE_BATCH_MS", "0") or "0"))
    except ValueError:
        return 0


def write_queue_enabled() -> bool:
    """True when batched commits are configured for this process."""
    return _batch_ms() > 0


class SQLiteWriteQueue:
    """Collects write callables and commits them in one transaction per window.

    One instance per uvicorn worker (each worker is its own process, so a
    module-level singleton is correct). The writer connection is used ONLY
    from the writer task, so no cross-thread sqlite access occurs; callables
    enqueued by request handlers are plain Python objects (functools.partial)
    carrying their own parameter values.
    """

    def __init__(self, db_path: str, flush_ms: int):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._flush_seconds = flush_ms / 1000.0
        self._queue: "asyncio.Queue[Callable[[sqlite3.Connection], None]]" = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Spawn the flush loop on the current event loop."""
        self._task = asyncio.create_task(self._run(), name="sqlite-write-queue")
        logger.info("SQLite write queue started (flush window %.0f ms)", self._flush_seconds * 1000)

    async def stop(self) -> None:
        """Cancel the loop, best-effort flush anything left, close the connection."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        leftover: List[Callable] = []
        while True:
            try:
                leftover.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if leftover:
            try:
                self._flush(leftover)
            except Exception as e:  # pragma: no cover - shutdown path
                logger.error(f"write-queue final flush failed: {e}")
        self._conn.close()

    def enqueue(self, fn: Callable[[sqlite3.Connection], None]) -> None:
        """Schedule a write for the next flush window."""
        self._queue.put_nowait(fn)

    async def _run(self) -> None:
        """Collect for one flush window, then commit the whole batch."""
        while True:
            try:
                first = await self._queue.get()
            except asyncio.CancelledError:
                raise
            batch: List[Callable] = [first]
            # Accumulation window starts at the FIRST item so a quiet channel
            # flushes promptly instead of holding the first write indefinitely.
            await asyncio.sleep(self._flush_seconds)
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            try:
                self._flush(batch)
            except Exception as e:  # pragma: no cover - DB fault path
                # Telemetry is non-critical: log and drop the batch rather than
                # letting one bad write poison the whole queue.
                logger.error(f"write-queue flush failed ({len(batch)} ops dropped): {e}")

    def _flush(self, batch: List[Callable]) -> None:
        with self._conn:  # one transaction for the whole batch
            for fn in batch:
                fn(self._conn)


# ── Module-level singleton (per worker process) ─────────────────────────────
_writer: Optional[SQLiteWriteQueue] = None


async def start_write_queue(db_path: str) -> None:
    """Create and start the per-worker writer (no-op unless enabled)."""
    global _writer
    if _writer is None and write_queue_enabled():
        _writer = SQLiteWriteQueue(db_path, _batch_ms())
    if _writer is not None:
        await _writer.start()


async def stop_write_queue() -> None:
    """Flush and close the per-worker writer (no-op if never started)."""
    global _writer
    if _writer is not None:
        await _writer.stop()
        _writer = None


def enqueue_write(fn: Callable[[sqlite3.Connection], None]) -> bool:
    """Queue a write for the batched path.

    Returns True when queued; False when the queue is disabled or not yet
    started, so callers can fall back to the synchronous path instead of
    silently dropping a write.
    """
    if _writer is None:
        return False
    _writer.enqueue(fn)
    return True
