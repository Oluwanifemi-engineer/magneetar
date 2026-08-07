"""Tests for the batched SQLite write queue (write_queue.py).

The queue is opt-in (MT_WRITE_BATCH_MS>0) and defaults to OFF, so the rest of
the suite exercises the original synchronous path untouched. These tests
drive the writer directly against a temp DB.
"""

import asyncio
import sqlite3

from write_queue import SQLiteWriteQueue, enqueue_write, write_queue_enabled


def _make_db(tmp_path) -> str:
    path = str(tmp_path / "wq.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    conn.close()
    return path


def _rows(path: str):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT v FROM t ORDER BY id").fetchall()
    finally:
        conn.close()


def test_batched_writes_land_in_one_flush(tmp_path):
    """Multiple enqueues inside one window commit together (all rows appear)."""
    path = _make_db(tmp_path)

    async def main():
        q = SQLiteWriteQueue(path, flush_ms=100)
        await q.start()
        for i in range(5):
            q.enqueue(lambda c, i=i: c.execute("INSERT INTO t (v) VALUES (?)", (f"v{i}",)))
        await asyncio.sleep(0.4)  # well past the flush window
        await q.stop()

    asyncio.run(main())
    assert [r[0] for r in _rows(path)] == ["v0", "v1", "v2", "v3", "v4"]


def test_batches_accumulate_across_windows(tmp_path):
    """Writes arriving in separate windows all persist (no drops)."""
    path = _make_db(tmp_path)

    async def main():
        q = SQLiteWriteQueue(path, flush_ms=100)
        await q.start()
        q.enqueue(lambda c: c.execute("INSERT INTO t (v) VALUES ('first')"))
        await asyncio.sleep(0.25)  # first window flushed
        q.enqueue(lambda c: c.execute("INSERT INTO t (v) VALUES ('second')"))
        await asyncio.sleep(0.25)  # second window flushed
        await q.stop()

    asyncio.run(main())
    assert [r[0] for r in _rows(path)] == ["first", "second"]


def test_writer_transaction_atomicity(tmp_path):
    """A failing write rolls back the whole batch (nothing half-applied)."""
    path = _make_db(tmp_path)

    async def main():
        q = SQLiteWriteQueue(path, flush_ms=100)
        await q.start()
        q.enqueue(lambda c: c.execute("INSERT INTO t (v) VALUES ('good')"))
        q.enqueue(lambda c: c.execute("INSERT INTO no_such_table (v) VALUES (?)", ("bad",)))
        await asyncio.sleep(0.4)
        await q.stop()

    asyncio.run(main())
    # The good row must NOT survive the failed batch (single transaction).
    assert _rows(path) == []


def test_enabled_flag_reads_env(monkeypatch):
    monkeypatch.delenv("MT_WRITE_BATCH_MS", raising=False)
    assert write_queue_enabled() is False
    monkeypatch.setenv("MT_WRITE_BATCH_MS", "250")
    assert write_queue_enabled() is True
    monkeypatch.setenv("MT_WRITE_BATCH_MS", "0")
    assert write_queue_enabled() is False


def test_enqueue_write_noop_when_disabled(tmp_path):
    """enqueue_write with no active writer reports False (caller falls back)."""
    assert enqueue_write(lambda c: None) is False
