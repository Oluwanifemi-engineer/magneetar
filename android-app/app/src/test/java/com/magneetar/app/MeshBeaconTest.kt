package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the Layer-2 relay-envelope wire contract (docs/offline-network-design.md
 * §3.1). Any drift in the byte layout silently breaks the mesh — these tests
 * are the tripwire, mirroring SosBeaconTest's role for the v1 UUID.
 */
class MeshBeaconTest {

    private val token = "a1b2c3d4e5f60718" // 16 lowercase hex chars

    @Test
    fun `round-trip preserves token hop origin and relayed flag`() {
        val origin = 1_752_000_000L
        val payload = MeshBeacon.encode(token, hop = 2, originUnixSecs = origin, relayed = true)!!
        val meta = MeshBeacon.decode(payload)!!
        assertEquals(token, meta.token)
        assertEquals(2, meta.hop)
        assertEquals(origin, meta.originUnixSecs)
        assertTrue(meta.relayed)
    }

    @Test
    fun `origin advertisement has relayed flag clear`() {
        val payload = MeshBeacon.encode(token, hop = 0, originUnixSecs = 1_752_000_000L, relayed = false)!!
        val meta = MeshBeacon.decode(payload)!!
        assertFalse(meta.relayed)
        assertEquals(0, meta.hop)
    }

    @Test
    fun `envelope has the fixed 19-byte layout`() {
        val payload = MeshBeacon.encode(token, hop = 1, originUnixSecs = 1_752_000_000L, relayed = false)!!
        assertEquals(MeshBeacon.ENVELOPE_LENGTH, payload.size)
        // Magic + version prefix
        assertEquals(0x4D.toByte(), payload[0])
        assertEquals(0x47.toByte(), payload[1])
        assertEquals(MeshBeacon.VERSION, payload[2])
        // Reserved tail stays zero
        assertEquals(0.toByte(), payload[17])
        assertEquals(0.toByte(), payload[18])
    }

    @Test
    fun `rejects foreign payloads and malformed tokens`() {
        // Not Magneetar magic
        val foreign = ByteArray(MeshBeacon.ENVELOPE_LENGTH) { 0x11 }
        assertNull(MeshBeacon.decode(foreign))
        // Wrong version byte
        val wrongVersion = MeshBeacon.encode(token, hop = 0, originUnixSecs = 1L, relayed = false)!!
        wrongVersion[2] = 0x01 // v1 UUID version, not the v2 envelope
        assertNull(MeshBeacon.decode(wrongVersion))
        // Malformed token (non-hex chars)
        assertNull(MeshBeacon.encode("zz1b2c3d4e5f60718", hop = 0, originUnixSecs = 1L, relayed = false))
        assertNull(MeshBeacon.encode("a1b2", hop = 0, originUnixSecs = 1L, relayed = false))
        // Too-short payload
        assertNull(MeshBeacon.decode(ByteArray(5)))
    }

    @Test
    fun `token packing round-trips the full 16-hex alphabet`() {
        val allHex = "0123456789abcdef"
        val payload = MeshBeacon.encode(allHex, hop = 0, originUnixSecs = 1L, relayed = false)!!
        assertEquals(allHex, MeshBeacon.decode(payload)!!.token)
    }

    @Test
    fun `hop gating stops relays at the max`() {
        assertTrue(MeshBeacon.canRelay(0))
        assertTrue(MeshBeacon.canRelay(2))
        assertFalse(MeshBeacon.canRelay(3)) // MAX_HOP reached
        assertFalse(MeshBeacon.canRelay(9))
        assertFalse(MeshBeacon.canRelay(-1))
    }

    @Test
    fun `ttl expiry drops stale beacons`() {
        val now = 1_752_000_000L
        assertFalse(MeshBeacon.isExpired(now - 100, now))          // fresh
        assertFalse(MeshBeacon.isExpired(now - 23 * 3600, now))    // just under 24h
        assertTrue(MeshBeacon.isExpired(now - 25 * 3600, now))     // over 24h
        assertTrue(MeshBeacon.isExpired(now - 100_000_000L, now))  // ancient
    }

    @Test
    fun `decode is lenient to trailing extension bytes`() {
        val base = MeshBeacon.encode(token, hop = 1, originUnixSecs = 1_752_000_000L, relayed = true)!!
        val extended = base + byteArrayOf(0x42, 0x43) // future extension
        val meta = MeshBeacon.decode(extended)!!
        assertEquals(token, meta.token)
        assertEquals(1, meta.hop)
        assertTrue(meta.relayed)
    }
}
