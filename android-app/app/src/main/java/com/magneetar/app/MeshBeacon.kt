package com.magneetar.app

/**
 * Offline Device Network (docs/offline-network-design.md), Layer 2 — the
 * relay-mesh manufacturer-data envelope.
 *
 * The v1 SOS beacon (SosBeacon.kt) stays byte-identical so Phase-1 scanners
 * keep working. Relay metadata rides in the MANUFACTURER DATA field of the
 * same advertisement (Android 8+/BLE 5.0 extended advertising; also fits
 * legacy 31-byte packets — the 16-byte service UUID leaves room):
 *
 *   [ 0x4D 0x47 ] [ 0x02 ] [ 8 raw token bytes ] [ hop:1 ] [ origin_ts:4 BE ] [ flags:1 ] [ reserved:2 ]
 *        magic      version              token                    hop     unix seconds          bit0: relayed
 *
 * - hop        — how many guardian relays this beacon has passed through.
 *                MAX_HOP = 3; a beacon at hop >= MAX_HOP is never re-advertised.
 * - origin_ts  — when the LOST DEVICE started advertising (unix seconds).
 *                Relays drop beacons older than RELAY_TTL_S (24h).
 * - flags bit0 — relayed: set by a guardian re-advertising; the lost device's
 *                own advertisement has it clear, so a scanner can tell origin
 *                from relay and weight trust accordingly.
 *
 * Deliberately free of Android types so the wire contract is locked on the
 * plain JVM (MeshBeaconTest.kt) — same tripwire philosophy as SosBeacon.kt.
 * Drift on either side silently breaks the mesh; the test catches it.
 */
object MeshBeacon {

    /** Maximum relay hops — beyond this a beacon is never re-advertised. */
    const val MAX_HOP = 3

    /** Beacons older than this (seconds) are dropped by relays. */
    const val RELAY_TTL_S = 24 * 60 * 60L

    /** Wire version for the relay envelope. */
    const val VERSION: Byte = 0x02

    /** flags bit 0 — set when a guardian re-advertises a beacon. */
    const val FLAG_RELAYED = 0x01

    private val MAGIC = byteArrayOf(0x4D, 0x47)

    /** Fixed envelope length (payload only, excludes the manufacturer header). */
    const val ENVELOPE_LENGTH = 19

    /** Decoded relay metadata for one advertisement. */
    data class RelayMeta(
        val token: String,
        val hop: Int,
        val originUnixSecs: Long,
        val relayed: Boolean,
    )

    /** True while [hop] may still be relayed onward. */
    fun canRelay(hop: Int): Boolean = hop in 0 until MAX_HOP

    /** True when a beacon whose origin is [originUnixSecs] is too old to relay. */
    fun isExpired(originUnixSecs: Long, nowUnixSecs: Long): Boolean =
        nowUnixSecs - originUnixSecs > RELAY_TTL_S

    /**
     * Encode the relay envelope, or null when the token is malformed or hop
     * is out of range (never throws). [relayed] sets flags bit 0.
     */
    fun encode(token: String, hop: Int, originUnixSecs: Long, relayed: Boolean): ByteArray? {
        if (!SosBeacon.isValidToken(token)) return null
        if (hop < 0 || hop > 0xFF) return null
        val out = ByteArray(ENVELOPE_LENGTH)
        MAGIC.copyInto(out, 0)
        out[2] = VERSION
        // Pack the 16 hex chars into 8 raw bytes (two chars per byte).
        for (i in 0 until 8) {
            val hi = hexNibble(token[i * 2])
            val lo = hexNibble(token[i * 2 + 1])
            out[3 + i] = ((hi shl 4) or lo).toByte()
        }
        out[11] = hop.toByte()
        writeInt32Be(out, 12, originUnixSecs)
        out[16] = if (relayed) FLAG_RELAYED.toByte() else 0
        // out[17..18] reserved — stay zero.
        return out
    }

    /**
     * Decode a relay envelope from an advertisement's manufacturer payload,
     * or null when it is not a v2 Magneetar relay envelope (magic/version
     * mismatch, malformed token). Lenient on trailing bytes so a future
     * version extension cannot break old scanners.
     */
    fun decode(payload: ByteArray): RelayMeta? {
        if (payload.size < ENVELOPE_LENGTH) return null
        if (payload[0] != MAGIC[0] || payload[1] != MAGIC[1]) return null
        if (payload[2] != VERSION) return null
        val sb = StringBuilder(16)
        for (i in 0 until 8) {
            val b = payload[3 + i].toInt() and 0xFF
            sb.append("0123456789abcdef"[b shr 4])
            sb.append("0123456789abcdef"[b and 0x0F])
        }
        val token = sb.toString()
        if (!SosBeacon.isValidToken(token)) return null
        val hop = payload[11].toInt() and 0xFF
        val origin = readInt32Be(payload, 12)
        val relayed = (payload[16].toInt() and FLAG_RELAYED) != 0
        return RelayMeta(token, hop, origin, relayed)
    }

    private fun hexNibble(c: Char): Int = when (c) {
        in '0'..'9' -> c - '0'
        in 'a'..'f' -> c - 'a' + 10
        in 'A'..'F' -> c - 'A' + 10
        else -> 0
    }

    private fun writeInt32Be(out: ByteArray, offset: Int, value: Long) {
        out[offset] = ((value ushr 24) and 0xFF).toByte()
        out[offset + 1] = ((value ushr 16) and 0xFF).toByte()
        out[offset + 2] = ((value ushr 8) and 0xFF).toByte()
        out[offset + 3] = (value and 0xFF).toByte()
    }

    private fun readInt32Be(payload: ByteArray, offset: Int): Long {
        return ((payload[offset].toLong() and 0xFF) shl 24) or
            ((payload[offset + 1].toLong() and 0xFF) shl 16) or
            ((payload[offset + 2].toLong() and 0xFF) shl 8) or
            (payload[offset + 3].toLong() and 0xFF)
    }
}
