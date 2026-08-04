package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Locks the at-most-once contract that breaks the "executes in loops" bug:
 * a command recorded within the retention window is never handed back for
 * re-execution, and re-acking refreshes the window instead of expiring it.
 */
class RecentCommandTrackerTest {

    private class MemoryStore(var json: String = "{}") : StringStore {
        override fun read(): String = json
        override fun write(json: String) { this.json = json }
    }

    private var now = 1_000_000L

    private fun tracker(store: MemoryStore = MemoryStore()) =
        RecentCommandTracker(store, nowMs = { now })

    @Test
    fun `statusOf is null for an unknown command`() {
        assertNull(tracker().statusOf(42))
    }

    @Test
    fun `statusOf returns the recorded status within the retention window`() {
        val t = tracker()
        t.remember(42, "executed")
        assertEquals("executed", t.statusOf(42))
    }

    @Test
    fun `statusOf is null after the retention window expires`() {
        val t = tracker()
        t.remember(42, "executed")
        now += RecentCommandTracker.DEFAULT_RETENTION_MS + 1
        assertNull(t.statusOf(42))
    }

    @Test
    fun `re-remembering refreshes the window`() {
        val t = tracker()
        t.remember(42, "executed")
        now += RecentCommandTracker.DEFAULT_RETENTION_MS - 1_000
        // A re-acked command is re-remembered with the same status — this is
        // what keeps it inside the window while it is still pending server-side.
        t.remember(42, "executed")
        now += 2_000
        assertEquals("executed", t.statusOf(42))
    }

    @Test
    fun `latest status wins on re-remember`() {
        val t = tracker()
        t.remember(42, "executed")
        t.remember(42, "failed")
        assertEquals("failed", t.statusOf(42))
    }

    @Test
    fun `corrupt store degrades to empty instead of crashing`() {
        val t = tracker(MemoryStore("{not json"))
        assertNull(t.statusOf(42))
        // And it can still record afterwards.
        t.remember(42, "failed")
        assertEquals("failed", t.statusOf(42))
    }

    @Test
    fun `distinct commands are tracked independently`() {
        val t = tracker()
        t.remember(1, "executed")
        t.remember(2, "failed")
        assertEquals("executed", t.statusOf(1))
        assertEquals("failed", t.statusOf(2))
        assertNull(t.statusOf(3))
    }

    @Test
    fun `old entries are pruned on write`() {
        val store = MemoryStore()
        val t = tracker(store)
        t.remember(1, "executed")
        // Advance well past 2x retention and record a new command — the old
        // entry must be pruned so the persisted map stays bounded.
        now += RecentCommandTracker.DEFAULT_RETENTION_MS * 2 + 5_000
        t.remember(2, "executed")
        assertNull(t.statusOf(1))
        assertEquals("executed", t.statusOf(2))
    }
}
