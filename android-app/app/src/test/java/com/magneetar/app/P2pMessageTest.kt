package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the Layer-3 paired-P2P message codec (docs/offline-network-design.md
 * §4.3): AES-256-GCM encrypted JSON envelopes under the pair secret. A
 * drift here would let a tampered or foreign payload through the offline
 * channel.
 */
class P2pMessageTest {

    private fun secret(seed: Int): ByteArray {
        val s = ByteArray(32)
        for (i in s.indices) s[i] = (seed + i).toByte()
        return s
    }

    @Test
    fun `round-trips a CMD envelope`() {
        val enc = P2pMessage.Envelope(
            type = P2pMessage.TYPE_CMD,
            cmdId = 42,
            command = P2pMessage.CMD_SIREN,
            params = "3",
        )
        val ct = P2pMessage.encrypt(secret(1), enc)!!
        val dec = P2pMessage.decrypt(secret(1), ct)!!
        assertEquals(P2pMessage.TYPE_CMD, dec.type)
        assertEquals(42, dec.cmdId)
        assertEquals(P2pMessage.CMD_SIREN, dec.command)
        assertEquals("3", dec.params)
    }

    @Test
    fun `round-trips a LAST_KNOWN envelope`() {
        val enc = P2pMessage.Envelope(
            type = P2pMessage.TYPE_LAST_KNOWN,
            lat = 7.4936,
            lng = 4.5917,
            accuracy = 12.5,
            provider = "fused",
            timestamp = 1_700_000_000_000L,
        )
        val ct = P2pMessage.encrypt(secret(2), enc)!!
        val dec = P2pMessage.decrypt(secret(2), ct)!!
        assertEquals(P2pMessage.TYPE_LAST_KNOWN, dec.type)
        assertEquals(7.4936, dec.lat, 1e-9)
        assertEquals(4.5917, dec.lng, 1e-9)
        assertEquals(12.5, dec.accuracy, 1e-9)
        assertEquals("fused", dec.provider)
        assertEquals(1_700_000_000_000L, dec.timestamp)
    }

    @Test
    fun `round-trips a handshake AUTH envelope with nonce and mac`() {
        val enc = P2pMessage.Envelope(
            type = P2pMessage.TYPE_AUTH,
            nonce = "aabbccddeeff00112233445566778899",
            mac = "00112233445566778899aabbccddeeff",
        )
        val ct = P2pMessage.encrypt(secret(3), enc)!!
        val dec = P2pMessage.decrypt(secret(3), ct)!!
        assertEquals(P2pMessage.TYPE_AUTH, dec.type)
        assertEquals("aabbccddeeff00112233445566778899", dec.nonce)
        assertEquals("00112233445566778899aabbccddeeff", dec.mac)
    }

    @Test
    fun `wrong secret fails to decrypt`() {
        val ct = P2pMessage.encrypt(secret(1), P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = "mt-a"))!!
        assertNull(P2pMessage.decrypt(secret(2), ct))
    }

    @Test
    fun `a single flipped byte fails integrity`() {
        val ct = P2pMessage.encrypt(secret(1), P2pMessage.Envelope(type = P2pMessage.TYPE_CMD, cmdId = 7))!!
        val tampered = ct.copyOf()
        tampered[tampered.lastIndex] = (tampered.last().toInt() xor 0x01).toByte()
        assertNull(P2pMessage.decrypt(secret(1), tampered))
    }

    @Test
    fun `fresh nonce per encryption - same envelope encrypts differently`() {
        val env = P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = "mt-a")
        val c1 = P2pMessage.encrypt(secret(5), env)!!
        val c2 = P2pMessage.encrypt(secret(5), env)!!
        assertFalse(c1.contentEquals(c2))
    }

    @Test
    fun `wrong secret length fails closed`() {
        assertNull(P2pMessage.encrypt(ByteArray(8), P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO)))
        assertNull(P2pMessage.decrypt(ByteArray(8), ByteArray(20)))
        // truncated payload (nonce only) fails closed
        assertNull(P2pMessage.decrypt(secret(1), ByteArray(P2pMessage.NONCE_BYTES)))
    }

    @Test
    fun `sighting carrier round-trips the beacon envelope`() {
        val envelopeBytes = MeshBeacon.encode("a1b2c3d4e5f60718", hop = 1, originUnixSecs = 1_700_000_000L, relayed = true)!!
        val b64 = java.util.Base64.getEncoder().encodeToString(envelopeBytes)
        val enc = P2pMessage.Envelope(
            type = P2pMessage.TYPE_SIGHTING_CARRIER,
            beaconEnvelope = b64,
            lat = 6.5,
            lng = 3.4,
        )
        val ct = P2pMessage.encrypt(secret(6), enc)!!
        val dec = P2pMessage.decrypt(secret(6), ct)!!
        assertEquals(P2pMessage.TYPE_SIGHTING_CARRIER, dec.type)
        assertEquals(b64, dec.beaconEnvelope)
        assertEquals(6.5, dec.lat, 1e-9)

        // and the carried envelope decodes back to the same relay meta
        val meta = MeshBeacon.decode(java.util.Base64.getDecoder().decode(dec.beaconEnvelope))
        assertNotNull(meta)
        assertEquals("a1b2c3d4e5f60718", meta!!.token)
        assertEquals(1, meta.hop)
        assertTrue(meta.relayed)
    }

    @Test
    fun `malformed json fails closed`() {
        assertNull(P2pMessage.parseJsonObject("not json"))
        assertNull(P2pMessage.parseJsonObject("{"))
        assertNull(P2pMessage.parseJsonObject("{\"a\":}"))
        // nested object is rejected (flat codec only)
        assertNull(P2pMessage.parseJsonObject("{\"a\":{\"b\":1}}"))
        // valid flat object parses
        val m = P2pMessage.parseJsonObject("{\"type\":\"CMD\",\"cmdId\":5,\"lat\":1.5}")!!
        assertEquals("CMD", m["type"])
        assertEquals(5L, m["cmdId"])
        assertEquals(1.5, m["lat"])
    }

    @Test
    fun `json escaping survives the round trip`() {
        val tricky = "say \"hi\" \\ done\nnext"
        val enc = P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, nickname = tricky)
        val ct = P2pMessage.encrypt(secret(9), enc)!!
        val dec = P2pMessage.decrypt(secret(9), ct)!!
        assertEquals(tricky, dec.nickname)
    }

    @Test
    fun `unknown type still decrypts but envelope is parseable`() {
        // A future type must at least round-trip; the dispatcher decides.
        val enc = P2pMessage.Envelope(type = "FUTURE_TYPE", cmdId = 3)
        val ct = P2pMessage.encrypt(secret(4), enc)!!
        val dec = P2pMessage.decrypt(secret(4), ct)!!
        assertEquals("FUTURE_TYPE", dec.type)
        assertEquals(3, dec.cmdId)
        assertNotEquals("", dec.type)
    }
}
