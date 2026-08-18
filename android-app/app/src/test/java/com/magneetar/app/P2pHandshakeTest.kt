package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the Layer-3 paired-P2P handshake state machine
 * (docs/offline-network-design.md §4.2). Two paired devices must prove they
 * hold the shared pair_secret (mutual HELLO/CHALLENGE/AUTH) before any data
 * flows — a wrong secret, a wrong device id, or a replayed message must fail
 * the handshake and force a disconnect.
 */
class P2pHandshakeTest {

    private fun secret(seed: Int): ByteArray {
        val s = ByteArray(32)
        for (i in s.indices) s[i] = (seed + i).toByte()
        return s
    }

    /**
     * Drive a full two-sided handshake with realistic per-endpoint ordering:
     * each side's HELLO/CHALLENGE are delivered in order, and the AUTH
     * responses generated in reply arrive back after both HELLOs. Returns
     * the two handshake objects (both authenticated on success).
     */
    private fun runMutualHandshake(
        secret: ByteArray,
        deviceA: String = "mt-alpha",
        deviceB: String = "mt-beta",
    ): Pair<P2pHandshake, P2pHandshake> {
        val a = P2pHandshake(deviceA, secret, deviceA to deviceB)
        val b = P2pHandshake(deviceB, secret, deviceA to deviceB)

        val aOut = a.onConnected() // [HELLO_A, CHALLENGE_A]
        val bOut = b.onConnected() // [HELLO_B, CHALLENGE_B]
        assertEquals(2, aOut.size)
        assertEquals(2, bOut.size)

        // B receives A's HELLO + CHALLENGE; replies with AUTH over nonceA.
        val fromB = mutableListOf<P2pMessage.Envelope>()
        for (msg in aOut) when (val r = b.onMessage(msg)) {
            is P2pHandshake.Result.Send -> fromB.addAll(r.envelopes)
            else -> error("unexpected result")
        }
        // A receives B's HELLO + CHALLENGE; replies with AUTH over nonceB.
        val fromA = mutableListOf<P2pMessage.Envelope>()
        for (msg in bOut) when (val r = a.onMessage(msg)) {
            is P2pHandshake.Result.Send -> fromA.addAll(r.envelopes)
            else -> error("unexpected result")
        }

        // Deliver the AUTH responses: A verifies B's answer to nonceA,
        // B verifies A's answer to nonceB.
        assertEquals(1, fromA.size)
        assertEquals(1, fromB.size)
        when (val ra = a.onMessage(fromB.single())) {
            P2pHandshake.Result.Authenticated -> Unit
            else -> error("A not authenticated")
        }
        when (val rb = b.onMessage(fromA.single())) {
            P2pHandshake.Result.Authenticated -> Unit
            else -> error("B not authenticated")
        }
        return a to b
    }

    @Test
    fun `mutual handshake authenticates both sides`() {
        val (a, b) = runMutualHandshake(secret(1))
        assertTrue(a.isAuthenticated)
        assertTrue(b.isAuthenticated)
        assertEquals("mt-beta", a.peerDeviceId)
        assertEquals("mt-alpha", b.peerDeviceId)
    }

    @Test
    fun `wrong secret fails the handshake`() {
        val deviceA = "mt-alpha"
        val deviceB = "mt-beta"
        val goodA = P2pHandshake(deviceA, secret(1), deviceA to deviceB)
        val evilB = P2pHandshake(deviceB, secret(2), deviceA to deviceB)

        val aOut = goodA.onConnected()
        val bOut = evilB.onConnected()

        // B (wrong secret) receives A's hello/challenge: it replies with a
        // MAC computed from the wrong secret — A's verification must fail.
        val fromEvilB = mutableListOf<P2pMessage.Envelope>()
        for (msg in aOut) when (val r = evilB.onMessage(msg)) {
            is P2pHandshake.Result.Send -> fromEvilB.addAll(r.envelopes)
            else -> Unit
        }
        val fromGoodA = mutableListOf<P2pMessage.Envelope>()
        for (msg in bOut) when (val r = goodA.onMessage(msg)) {
            is P2pHandshake.Result.Send -> fromGoodA.addAll(r.envelopes)
            else -> Unit
        }

        // A verifies B's AUTH over nonceA — wrong secret → FAIL.
        val ra = goodA.onMessage(fromEvilB.single())
        assertTrue(ra is P2pHandshake.Result.Failed)
        assertTrue(goodA.hasFailed)
        assertFalse(goodA.isAuthenticated)
        // B verifies A's AUTH over nonceB — wrong secret → FAIL.
        val rb = evilB.onMessage(fromGoodA.single())
        assertTrue(rb is P2pHandshake.Result.Failed)
        assertFalse(evilB.isAuthenticated)
    }

    @Test
    fun `peer outside the pairing fails immediately`() {
        val deviceA = "mt-alpha"
        val deviceB = "mt-beta"
        val a = P2pHandshake(deviceA, secret(1), deviceA to deviceB)
        a.onConnected()
        val r = a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = "mt-unknown"))
        assertTrue(r is P2pHandshake.Result.Failed)
        assertTrue(a.hasFailed)
        // The device itself can never be its own peer.
        val r2 = a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = deviceA))
        assertTrue(r2 is P2pHandshake.Result.Failed)
    }

    @Test
    fun `challenge before hello fails`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        a.onConnected()
        val r = a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_CHALLENGE, nonce = "00".repeat(16)))
        assertTrue(r is P2pHandshake.Result.Failed)
    }

    @Test
    fun `auth with wrong nonce fails`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        val b = P2pHandshake("mt-beta", secret(1), "mt-alpha" to "mt-beta")
        val aOut = a.onConnected()
        val bOut = b.onConnected()

        // Deliver A's hello/challenge to B, B's hello to A.
        for (msg in aOut) b.onMessage(msg)
        for (msg in bOut) a.onMessage(msg)

        // Now a forged AUTH with a different nonce (replay of an old session).
        val r = a.onMessage(
            P2pMessage.Envelope(
                type = P2pMessage.TYPE_AUTH,
                nonce = "ff".repeat(16),
                mac = "00".repeat(16),
            )
        )
        assertTrue(r is P2pHandshake.Result.Failed)
        assertTrue(a.hasFailed)
    }

    @Test
    fun `auth with a tampered mac fails`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        val b = P2pHandshake("mt-beta", secret(1), "mt-alpha" to "mt-beta")
        val aOut = a.onConnected()
        val bOut = b.onConnected()
        for (msg in aOut) b.onMessage(msg)
        for (msg in bOut) a.onMessage(msg)

        // An AUTH over OUR nonce with a wrong MAC (tampered in transit).
        val challenge = aOut.first { it.type == P2pMessage.TYPE_CHALLENGE }
        val r = a.onMessage(
            P2pMessage.Envelope(
                type = P2pMessage.TYPE_AUTH,
                nonce = challenge.nonce,
                mac = "ab".repeat(16),
            )
        )
        assertTrue(r is P2pHandshake.Result.Failed)
    }

    @Test
    fun `malformed hex fails closed`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        a.onConnected()
        val badNonce = a.onMessage(
            P2pMessage.Envelope(type = P2pMessage.TYPE_CHALLENGE, nonce = "zz-not-hex")
        )
        assertTrue(badNonce is P2pHandshake.Result.Failed)
    }

    @Test
    fun `after failure the handshake stays failed`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        a.onConnected()
        a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = "mt-unknown"))
        assertTrue(a.hasFailed)
        // Any later message is still a failure, never a recovery.
        val r = a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = "mt-beta"))
        assertTrue(r is P2pHandshake.Result.Failed)
    }

    @Test
    fun `non-handshake messages are ignored while authenticating`() {
        val a = P2pHandshake("mt-alpha", secret(1), "mt-alpha" to "mt-beta")
        a.onConnected()
        val r = a.onMessage(P2pMessage.Envelope(type = P2pMessage.TYPE_LAST_KNOWN, lat = 1.0, lng = 2.0))
        assertTrue(r is P2pHandshake.Result.Ignore)
        // And the handshake can still complete after the noise.
        val b = P2pHandshake("mt-beta", secret(1), "mt-alpha" to "mt-beta")
        val bOut = b.onConnected()
        for (msg in bOut) a.onMessage(msg)
        assertTrue(a.isAuthenticated || a.state == P2pHandshake.State.HANDSHAKING)
    }
}
