package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the Layer-2 relay outbox contract (docs/offline-network-design.md
 * §3.2): offline sightings queue + flush, re-advertise gating (hop/TTL/
 * cooldown), bounded storage. Pure JVM via an in-memory StringStore.
 */
class RelayOutboxTest {

    private var clock = 1_752_000_000_000L

    /** In-memory store + controllable clock. */
    private fun newOutbox(): Pair<RelayOutbox, StringBuilder> {
        val backing = StringBuilder()
        val store = object : StringStore {
            override fun read(): String = backing.toString()
            override fun write(s: String) {
                backing.setLength(0)
                backing.append(s)
            }
        }
        return RelayOutbox(store, { clock }) to backing
    }

    private fun token(n: Int): String = "a1b2c3d4e5f6%04x".format(n).take(16)

    @Test
    fun `queue then pendingFlush returns the offline sighting`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 2, originTs = 1_752_000_000L, lat = 9.08, lng = 8.67, relayed = true, needsFlush = true)
        val pending = box.pendingFlush()
        assertEquals(1, pending.size)
        assertEquals(token(1), pending[0].token)
        assertEquals(2, pending[0].hop)
        assertEquals(9.08, pending[0].lat, 1e-9)
        assertTrue(pending[0].relayed)
    }

    @Test
    fun `live posts never queue`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        assertTrue(box.pendingFlush().isEmpty())
        assertTrue(box.contains(token(1))) // bookkeeping stays for relay
    }

    @Test
    fun `markFlushed clears the pending flag but keeps relay bookkeeping`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 1, originTs = 1, lat = 9.0, lng = 8.0, relayed = true, needsFlush = true)
        box.markFlushed(token(1))
        assertTrue(box.pendingFlush().isEmpty())
        assertTrue(box.contains(token(1)))
    }

    @Test
    fun `same token upserts with the fresher hop`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 1, originTs = 1, lat = 9.0, lng = 8.0, relayed = true, needsFlush = true)
        box.queue(token(1), hop = 2, originTs = 2, lat = 9.1, lng = 8.1, relayed = true, needsFlush = false)
        val all = box.pendingFlush()
        assertEquals(1, all.size) // one entry per token
        assertEquals(2, all[0].hop)
        // needsFlush survives the upsert (a pending upload is never lost)
        assertTrue(all[0].needsFlush)
    }

    @Test
    fun `advertise candidates gate on hop max`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        box.queue(token(2), hop = 3, originTs = 1, lat = 9.0, lng = 8.0, relayed = true, needsFlush = false) // MAX_HOP
        box.queue(token(3), hop = 5, originTs = 1, lat = 9.0, lng = 8.0, relayed = true, needsFlush = false)
        val candidates = box.advertiseCandidates()
        assertEquals(listOf(token(1)), candidates.map { it.token })
    }

    @Test
    fun `advertise candidates gate on origin ttl`() {
        val (box, _) = newOutbox()
        val now = clock / 1000
        box.queue(token(1), hop = 0, originTs = now - 10, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        // Expired origin (over 24h old) — not a candidate
        box.queue(token(2), hop = 0, originTs = now - 100_000, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        // Unknown origin (direct beacon, no envelope) — treated as fresh
        box.queue(token(3), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        val candidates = box.advertiseCandidates().map { it.token }.toSet()
        assertTrue(candidates.contains(token(1)))
        assertFalse(candidates.contains(token(2)))
        assertTrue(candidates.contains(token(3)))
    }

    @Test
    fun `advertise candidates respect the re-advertise cooldown`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        assertTrue(box.advertiseCandidates().any { it.token == token(1) })

        box.markAdvertised(token(1))
        clock += 60_000L // 1 min later — inside the 15 min cooldown
        assertFalse(box.advertiseCandidates().any { it.token == token(1) })

        clock += 15 * 60_000L // past the cooldown
        assertTrue(box.advertiseCandidates().any { it.token == token(1) })
    }

    @Test
    fun `markAdvertised persists across store round-trips`() {
        val (box, backing) = newOutbox()
        box.queue(token(1), hop = 1, originTs = 0, lat = 9.0, lng = 8.0, relayed = true, needsFlush = true)
        box.markAdvertised(token(1))
        // A fresh outbox over the same store sees the same state (persistence)
        val reloaded = RelayOutbox(
            object : StringStore {
                override fun read(): String = backing.toString()
                override fun write(s: String) {}
            },
            { clock },
        )
        assertFalse(reloaded.advertiseCandidates().any { it.token == token(1) })
        assertTrue(reloaded.pendingFlush().any { it.token == token(1) })
    }

    @Test
    fun `store is bounded - oldest evicted beyond the cap`() {
        val (box, _) = newOutbox()
        for (i in 1..(RelayOutbox.MAX_ENTRIES + 50)) {
            clock += 60_000L
            box.queue(token(i), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = true)
        }
        val pending = box.pendingFlush()
        assertEquals(RelayOutbox.MAX_ENTRIES, pending.size)
        // The 50 oldest (lowest tokens) were evicted
        assertFalse(pending.any { it.token == token(1) })
        assertTrue(pending.any { it.token == token(RelayOutbox.MAX_ENTRIES + 50) })
    }

    @Test
    fun `stale entries age out after a week`() {
        val (box, _) = newOutbox()
        box.queue(token(1), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = true)
        clock += 8L * 24 * 60 * 60 * 1000 // 8 days
        box.queue(token(2), hop = 0, originTs = 0, lat = 9.0, lng = 8.0, relayed = false, needsFlush = false)
        val pending = box.pendingFlush()
        assertFalse(pending.any { it.token == token(1) }) // aged out
        assertTrue(box.contains(token(2)))
    }

    @Test
    fun `corrupt serialization degrades to empty`() {
        val store = object : StringStore {
            override fun read(): String = "garbage;;not|a|valid|entry;|1|2"
            override fun write(s: String) {}
        }
        val box = RelayOutbox(store, { clock })
        assertTrue(box.pendingFlush().isEmpty())
        assertTrue(box.advertiseCandidates().isEmpty())
    }
}
