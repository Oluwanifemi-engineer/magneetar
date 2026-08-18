package com.magneetar.app

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.util.UUID

/**
 * Offline Device Network (docs/offline-network-design.md), Layer 3 — paired
 * P2P pairing codec.
 *
 * Two of the OWNER's devices (same account) pair once over the internet
 * (one-time pair code, server-minted) and receive the same 32-byte
 * `pair_secret`. After that they can discover, authenticate and exchange
 * data FULLY OFFLINE:
 *
 *   1. Discovery: the Nearby/BLE service id is deterministic from the secret,
 *      so only paired devices derive the same UUID — non-paired phones do
 *      not even see each other's P2P traffic.
 *   2. Authentication: a 16-byte random challenge; the responder returns
 *      HMAC-SHA256(pair_secret, challenge || device_id_a || device_id_b)
 *      truncated to 16 bytes. Binding both device ids into the MAC prevents
 *      a chosen-prefix replay against another pair that shares... (it cannot:
 *      each pair has its own secret, and the id binding stops a MITM from
 *      splicing responses between two legitimate sessions).
 *   3. Payloads: AES-GCM with the pair secret (ciphertext layout is the
 *      caller's concern — this file locks discovery + authentication).
 *
 * Pure JVM (javax.crypto) so the contract is locked by P2pPairingTest.kt.
 */
object P2pPairing {

    /** Length of the pair secret the server mints (32 bytes). */
    const val PAIR_SECRET_LENGTH = 32

    /** Truncated HMAC length used in the offline handshake. */
    const val HANDSHAKE_MAC_LENGTH = 16

    private const val SERVICE_ID_PREFIX = "mg-p2p:"

    /**
     * Deterministic discovery service id for a pair. Derived from the secret
     * only — two devices holding the same pair_secret compute the same UUID;
     * everyone else derives garbage and never matches the scan filter.
     */
    fun serviceUuidFor(pairSecret: ByteArray): UUID {
        val digest = sha256(pairSecret)
        val hex = digest.toHex().take(16)
        return UUID.nameUUIDFromBytes((SERVICE_ID_PREFIX + hex).toByteArray())
    }

    /**
     * The offline handshake response: HMAC-SHA256(pair_secret,
     * challenge || device_id_a || device_id_b)[:16]. The caller decides
     * which device id is "a" and which is "b"; both sides must agree on the
     * ordering (e.g. lexicographic) or the handshake fails closed.
     */
    fun hmacResponse(pairSecret: ByteArray, challenge: ByteArray, deviceIdA: String, deviceIdB: String): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(pairSecret, "HmacSHA256"))
        mac.update(challenge)
        mac.update(deviceIdA.toByteArray(Charsets.UTF_8))
        mac.update(deviceIdB.toByteArray(Charsets.UTF_8))
        return mac.doFinal().copyOf(HANDSHAKE_MAC_LENGTH)
    }

    /**
     * Constant-time verification of a handshake response. Never throws;
     * a malformed response (wrong length, empty secret) simply fails.
     */
    fun verify(pairSecret: ByteArray, challenge: ByteArray, deviceIdA: String, deviceIdB: String, response: ByteArray): Boolean {
        if (pairSecret.size != PAIR_SECRET_LENGTH) return false
        if (challenge.isEmpty() || response.size != HANDSHAKE_MAC_LENGTH) return false
        val expected = hmacResponse(pairSecret, challenge, deviceIdA, deviceIdB)
        return MessageDigest.isEqual(expected, response)
    }

    private fun sha256(bytes: ByteArray): ByteArray =
        MessageDigest.getInstance("SHA-256").digest(bytes)

    private fun ByteArray.toHex(): String =
        joinToString("") { "%02x".format(it) }
}
