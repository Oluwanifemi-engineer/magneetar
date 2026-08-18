package com.magneetar.app

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.UUID

/**
 * Locks the Layer-3 paired-P2P contract (docs/offline-network-design.md §4):
 * deterministic discovery service id + HMAC-SHA256 challenge/response
 * handshake. A drift here would let the wrong phone authenticate offline.
 */
class P2pPairingTest {

    private fun secret(seed: Int): ByteArray {
        val s = ByteArray(32)
        for (i in s.indices) s[i] = (seed + i).toByte()
        return s
    }

    @Test
    fun `service id is deterministic for the same secret`() {
        val a = P2pPairing.serviceUuidFor(secret(1))
        val b = P2pPairing.serviceUuidFor(secret(1))
        assertEquals(a, b)
        assertTrue(a is UUID)
    }

    @Test
    fun `service id differs across pairs`() {
        assertNotEquals(
            P2pPairing.serviceUuidFor(secret(1)),
            P2pPairing.serviceUuidFor(secret(2)),
        )
    }

    @Test
    fun `valid handshake verifies with agreed id ordering`() {
        val challenge = ByteArray(16) { it.toByte() }
        val response = P2pPairing.hmacResponse(secret(7), challenge, "device-a", "device-b")
        assertTrue(
            P2pPairing.verify(secret(7), challenge, "device-a", "device-b", response)
        )
    }

    @Test
    fun `wrong secret fails the handshake`() {
        val challenge = ByteArray(16) { it.toByte() }
        val response = P2pPairing.hmacResponse(secret(7), challenge, "device-a", "device-b")
        assertFalse(
            P2pPairing.verify(secret(8), challenge, "device-a", "device-b", response)
        )
    }

    @Test
    fun `wrong device id binding fails the handshake`() {
        val challenge = ByteArray(16) { it.toByte() }
        val response = P2pPairing.hmacResponse(secret(7), challenge, "device-a", "device-b")
        // Swapped id order / different ids must not verify
        assertFalse(
            P2pPairing.verify(secret(7), challenge, "device-b", "device-a", response)
        )
        assertFalse(
            P2pPairing.verify(secret(7), challenge, "device-a", "device-c", response)
        )
    }

    @Test
    fun `response is truncated to the fixed length`() {
        val challenge = ByteArray(16) { it.toByte() }
        val response = P2pPairing.hmacResponse(secret(7), challenge, "a", "b")
        assertEquals(P2pPairing.HANDSHAKE_MAC_LENGTH, response.size)
    }

    @Test
    fun `different challenge yields a different response`() {
        val c1 = ByteArray(16) { 1 }
        val c2 = ByteArray(16) { 2 }
        val r1 = P2pPairing.hmacResponse(secret(7), c1, "a", "b")
        val r2 = P2pPairing.hmacResponse(secret(7), c2, "a", "b")
        assertFalse(r1.contentEquals(r2))
        assertArrayEquals(r1, P2pPairing.hmacResponse(secret(7), c1, "a", "b"))
    }

    @Test
    fun `malformed inputs fail closed`() {
        val challenge = ByteArray(16) { 1 }
        val good = P2pPairing.hmacResponse(secret(7), challenge, "a", "b")
        // Wrong secret length is rejected outright
        assertFalse(P2pPairing.verify(ByteArray(8), challenge, "a", "b", good))
        // Wrong response length
        assertFalse(P2pPairing.verify(secret(7), challenge, "a", "b", ByteArray(8)))
        // Empty challenge
        assertFalse(P2pPairing.verify(secret(7), ByteArray(0), "a", "b", good))
    }
}
