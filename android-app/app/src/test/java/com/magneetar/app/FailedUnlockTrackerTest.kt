package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * Locks the failed-unlock ("theftie") counting contract that the server's
 * automatic evidence capture reacts to (COMPETITOR_AUDIT P1 #4):
 *
 *   - a screen-on behind the keyguard that ends without a successful unlock
 *     counts as exactly one failed attempt,
 *   - a screen-on with the keyguard already dismissed (device unlocked)
 *     never counts,
 *   - a successful unlock (USER_PRESENT) resets the counter to zero,
 *   - an authoritative DPC count overwrites the heuristic,
 *   - the persisted state survives a tracker rebuild (service restart).
 */
class FailedUnlockTrackerTest {

    private class MemoryStore(var raw: String = "") : StringStore {
        override fun read(): String = raw
        override fun write(json: String) { raw = json }
    }

    private fun tracker(store: MemoryStore = MemoryStore()) =
        FailedUnlockTracker(store)

    @Test
    fun `fresh tracker starts at zero`() {
        assertEquals(0, tracker().count())
    }

    @Test
    fun `screen on locked then off counts one failed attempt`() {
        val t = tracker()
        t.onScreenOn(locked = true)
        assertEquals("no failure until the screen goes off", 0, t.count())
        t.onScreenOff()
        assertEquals(1, t.count())
    }

    @Test
    fun `screen on with keyguard dismissed never counts`() {
        val t = tracker()
        t.onScreenOn(locked = false)
        t.onScreenOff()
        assertEquals("an unlocked screen session is not a failure", 0, t.count())
    }

    @Test
    fun `repeated locked sessions accumulate`() {
        val t = tracker()
        repeat(3) {
            t.onScreenOn(locked = true)
            t.onScreenOff()
        }
        assertEquals(3, t.count())
    }

    @Test
    fun `screen off without a locked session does not count`() {
        val t = tracker()
        t.onScreenOff()
        assertEquals(0, t.count())
    }

    @Test
    fun `user present resets the counter and closes the session`() {
        val t = tracker()
        t.onScreenOn(locked = true)
        t.onScreenOff()
        t.onScreenOn(locked = true)
        assertEquals(1, t.count())
        t.onUserPresent()
        assertEquals(0, t.count())
        // The open session is gone too — a later screen-off must not count.
        t.onScreenOff()
        assertEquals(0, t.count())
    }

    @Test
    fun `authoritative dpc count overwrites the heuristic`() {
        val t = tracker()
        t.onScreenOn(locked = true)
        t.onScreenOff()
        assertEquals(1, t.count())
        t.record(4)
        assertEquals(4, t.count())
    }

    @Test
    fun `dpc zero after a successful unlock clears an open session`() {
        val t = tracker()
        t.onScreenOn(locked = true)
        t.record(0)
        t.onScreenOff()
        assertEquals("a stale open session must not count after the OS confirmed an unlock", 0, t.count())
    }

    @Test
    fun `null dpc count leaves the heuristic untouched`() {
        val t = tracker()
        t.onScreenOn(locked = true)
        t.onScreenOff()
        t.record(null)
        assertEquals(1, t.count())
    }

    @Test
    fun `state survives a tracker rebuild`() {
        val store = MemoryStore()
        tracker(store).apply {
            onScreenOn(locked = true)
            onScreenOff()
            onScreenOn(locked = true)
            onScreenOff()
        }
        assertEquals(2, tracker(store).count())
    }

    @Test
    fun `open session survives a rebuild so screen off counts it`() {
        // G1-8 regression: production builds a FRESH tracker per event
        // (FailedUnlockMonitor.tracker() on every broadcast), so an open
        // session that was only held in memory would be gone by the time the
        // SCREEN_OFF arrives — the failed attempt never counted. The session
        // flag must persist with the count.
        val store = MemoryStore()
        tracker(store).onScreenOn(locked = true)   // instance A opens the session
        tracker(store).onScreenOff()               // instance B must still see it
        assertEquals(1, tracker(store).count())
    }

    @Test
    fun `user present persists the reset`() {
        val store = MemoryStore()
        tracker(store).apply {
            onScreenOn(locked = true)
            onScreenOff()
            onUserPresent()
        }
        assertEquals(0, tracker(store).count())
        assertFalse("persisted blob must record the reset", store.raw.startsWith("1"))
    }
}
