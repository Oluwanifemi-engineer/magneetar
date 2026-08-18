package com.magneetar.app

import java.security.SecureRandom

/**
 * Offline Device Network (docs/offline-network-design.md §4.2) — the mutual
 * HMAC handshake as a pure-JVM state machine.
 *
 * Two paired devices that just connected (Nearby / BLE) must prove to each
 * other that they hold the shared 32-byte pair_secret BEFORE any data flows:
 *
 *   1. Both sides send HELLO{device_id} + CHALLENGE{nonce} on connect.
 *   2. On CHALLENGE: reply AUTH{nonce, mac} where
 *        mac = HMAC-SHA256(secret, nonce || idA || idB)[:16]
 *      with the two device ids in lexicographic order — both sides agree on
 *      the ordering, and binding both ids into the MAC stops a chosen-prefix
 *      relay against another pair.
 *   3. On AUTH: verify the MAC against the nonce WE sent. Match →
 *      AUTHENTICATED; mismatch → FAIL (caller disconnects).
 *
 * Cross-check: a HELLO from a device id that is not part of this pairing
 * fails immediately (the connection was made under a service id derived from
 * a different secret — reject rather than handshake).
 *
 * Extracted from P2pOfflineService so the protocol is locked by
 * P2pHandshakeTest.kt on the plain JVM (same philosophy as P2pPairing /
 * MeshBeacon) — a drift here would let the wrong phone authenticate offline.
 */
class P2pHandshake(
    private val ownDeviceId: String,
    /** The pair secret for THIS pairing (32 bytes). */
    private val secret: ByteArray,
    /** The two device ids bound by the pairing (any order accepted). */
    private val pairedDeviceIds: Pair<String, String>,
) {

    enum class State { AWAITING_HELLO, HANDSHAKING, AUTHENTICATED, FAILED }

    var state: State = State.AWAITING_HELLO
        private set

    var peerDeviceId: String = ""
        private set

    private var sentNonceHex: String? = null

    /** The (a, b) id ordering both sides agree on — lexicographic. */
    private val orderedIds: Pair<String, String>
        get() {
            val myId = ownDeviceId
            val peerId = peerDeviceId
            return if (myId <= peerId) myId to peerId else peerId to myId
        }

    val isAuthenticated: Boolean get() = state == State.AUTHENTICATED
    val hasFailed: Boolean get() = state == State.FAILED

    /**
     * Called when the transport connects: returns the messages to send first
     * (HELLO + CHALLENGE). Safe to call once per connection.
     */
    fun onConnected(): List<P2pMessage.Envelope> {
        if (state == State.AWAITING_HELLO) state = State.HANDSHAKING
        val nonce = randomNonceHex()
        sentNonceHex = nonce
        return listOf(
            P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = ownDeviceId),
            P2pMessage.Envelope(type = P2pMessage.TYPE_CHALLENGE, nonce = nonce),
        )
    }

    /** Outcome of feeding an inbound message into the handshake. */
    sealed class Result {
        /** Send these messages back to the peer (may be empty). */
        data class Send(val envelopes: List<P2pMessage.Envelope>) : Result()

        /** Handshake completed successfully — data may now flow. */
        data object Authenticated : Result()

        /** Handshake failed — the caller MUST disconnect. */
        data object Failed : Result()

        /** Not a handshake message (HELLO/CHALLENGE/AUTH) — ignore. */
        data object Ignore : Result()
    }

    /**
     * Feed one inbound message. Never throws; a malformed or unexpected
     * message fails the handshake (fail-closed).
     */
    fun onMessage(msg: P2pMessage.Envelope): Result {
        if (state == State.FAILED) return Result.Failed
        return when (msg.type) {
            P2pMessage.TYPE_HELLO -> onHello(msg.deviceId)
            P2pMessage.TYPE_CHALLENGE -> onChallenge(msg.nonce)
            P2pMessage.TYPE_AUTH -> onAuth(msg.nonce, msg.mac)
            else -> Result.Ignore
        }
    }

    private fun onHello(peerId: String): Result {
        // The peer must be the OTHER half of this pairing.
        val (a, b) = pairedDeviceIds
        val valid = peerId == a || peerId == b
        if (!valid || peerId == ownDeviceId) {
            state = State.FAILED
            return Result.Failed
        }
        peerDeviceId = peerId
        return Result.Send(emptyList())
    }

    private fun onChallenge(nonceHex: String): Result {
        if (peerDeviceId.isEmpty()) {
            // A challenge before HELLO — the peer never identified. Fail.
            state = State.FAILED
            return Result.Failed
        }
        val nonceBytes = nonceHex.hexToBytes()
        if (nonceBytes.size != 16) {
            state = State.FAILED
            return Result.Failed
        }
        val (idA, idB) = orderedIds
        val mac = P2pPairing.hmacResponse(secret, nonceBytes, idA, idB)
        return Result.Send(
            listOf(
                P2pMessage.Envelope(
                    type = P2pMessage.TYPE_AUTH,
                    nonce = nonceHex,
                    mac = mac.toHex(),
                )
            )
        )
    }

    private fun onAuth(nonceHex: String, macHex: String): Result {
        val expected = sentNonceHex ?: run {
            state = State.FAILED
            return Result.Failed
        }
        if (peerDeviceId.isEmpty() || nonceHex != expected) {
            state = State.FAILED
            return Result.Failed
        }
        val (idA, idB) = orderedIds
        val ok = P2pPairing.verify(secret, expected.hexToBytes(), idA, idB, macHex.hexToBytes())
        return if (ok) {
            state = State.AUTHENTICATED
            Result.Authenticated
        } else {
            state = State.FAILED
            Result.Failed
        }
    }

    private fun randomNonceHex(): String {
        val bytes = ByteArray(16).also { SecureRandom().nextBytes(it) }
        return bytes.toHex()
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun String.hexToBytes(): ByteArray {
        if (length % 2 != 0) return ByteArray(0)
        return ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}
