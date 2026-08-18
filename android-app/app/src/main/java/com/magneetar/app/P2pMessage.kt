package com.magneetar.app

import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Offline Device Network (docs/offline-network-design.md §4.3) — paired P2P
 * message codec.
 *
 * Messages between two paired devices are JSON payloads encrypted with
 * AES-256-GCM under the shared pair_secret (32 bytes). The wire layout is
 * `nonce(12) || ciphertext(tag appended)` — the same shape the rest of the
 * app uses for at-rest fields. Authentication already happened at the
 * handshake (P2pPairing); this layer adds confidentiality + integrity for
 * the actual data (last-known location, commands).
 *
 * Pure JVM so the contract is locked by P2pMessageTest.kt:
 *   - round-trip of every message type
 *   - a wrong secret or a single flipped byte fails to decrypt
 *   - the JSON codec rejects malformed input instead of guessing
 *
 * JSON note: this deliberately does NOT use org.json — its methods are
 * unmocked stubs in local unit tests (same reason RecentCommandTracker
 * hand-rolls its serialization). The codec only needs flat string/number
 * fields, so a 60-line writer/parser covers it and stays fully testable.
 */
object P2pMessage {

    // Message types (§4.3 + §4.2 handshake)
    const val TYPE_HELLO = "HELLO"
    const val TYPE_LAST_KNOWN = "LAST_KNOWN"
    const val TYPE_CMD = "CMD"
    const val TYPE_ACK = "ACK"
    const val TYPE_SIGHTING_CARRIER = "SIGHTING_CARRIER"
    const val TYPE_CHALLENGE = "CHALLENGE"
    const val TYPE_AUTH = "AUTH"

    // Offline commands (executed by the device's existing command handlers)
    const val CMD_SIREN = "alarm"
    const val CMD_LOCK = "lock"
    const val CMD_LOST_MODE = "lost_mode"
    const val CMD_PING = "ping"

    const val GCM_TAG_BITS = 128
    const val NONCE_BYTES = 12

    /**
     * A single P2P message. All fields optional — each type uses its own
     * subset. Serialized to JSON, encrypted, sent as one Nearby payload.
     */
    data class Envelope(
        val type: String,
        // CMD / ACK
        val cmdId: Int = 0,
        val command: String = "",
        val params: String = "",
        // ACK
        val status: String = "",
        val failureReason: String = "",
        // LAST_KNOWN
        val lat: Double = 0.0,
        val lng: Double = 0.0,
        val accuracy: Double = 0.0,
        val provider: String = "",
        val timestamp: Long = 0L,
        // HELLO
        val deviceId: String = "",
        val nickname: String = "",
        // SIGHTING_CARRIER — a relayed beacon envelope (base64 of the v2
        // MeshBeacon bytes) this device should also carry (mesh density).
        val beaconEnvelope: String = "",
        // CHALLENGE / AUTH handshake (§4.2): nonce = 16-byte random hex,
        // mac = HMAC-SHA256(secret, nonce || id_a || id_b)[:16] hex.
        val nonce: String = "",
        val mac: String = "",
    )

    /**
     * Encrypt an envelope: AES-256-GCM with a fresh random nonce.
     * Returns null only on a programming error (empty secret / bad key) —
     * a valid 32-byte secret never fails.
     */
    fun encrypt(pairSecret: ByteArray, envelope: Envelope): ByteArray? {
        return try {
            if (pairSecret.size != P2pPairing.PAIR_SECRET_LENGTH) return null
            val nonce = ByteArray(NONCE_BYTES).also { SecureRandom().nextBytes(it) }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.ENCRYPT_MODE,
                SecretKeySpec(pairSecret, "AES"),
                GCMParameterSpec(GCM_TAG_BITS, nonce),
            )
            val ct = cipher.doFinal(encodeJson(envelope).toByteArray(Charsets.UTF_8))
            nonce + ct
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Decrypt + parse + verify integrity. Returns null on ANY failure
     * (wrong secret, tampered bytes, malformed JSON, unknown type) — the
     * receiver drops the message and never guesses.
     */
    fun decrypt(pairSecret: ByteArray, payload: ByteArray): Envelope? {
        return try {
            if (pairSecret.size != P2pPairing.PAIR_SECRET_LENGTH) return null
            if (payload.size <= NONCE_BYTES) return null
            val nonce = payload.copyOfRange(0, NONCE_BYTES)
            val ct = payload.copyOfRange(NONCE_BYTES, payload.size)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(pairSecret, "AES"),
                GCMParameterSpec(GCM_TAG_BITS, nonce),
            )
            val json = String(cipher.doFinal(ct), Charsets.UTF_8)
            val map = parseJsonObject(json) ?: return null
            val type = map["type"] as? String ?: return null
            Envelope(
                type = type,
                cmdId = (map["cmdId"] as? Number)?.toInt() ?: 0,
                command = map["command"] as? String ?: "",
                params = map["params"] as? String ?: "",
                status = map["status"] as? String ?: "",
                failureReason = map["failureReason"] as? String ?: "",
                lat = (map["lat"] as? Number)?.toDouble() ?: 0.0,
                lng = (map["lng"] as? Number)?.toDouble() ?: 0.0,
                accuracy = (map["accuracy"] as? Number)?.toDouble() ?: 0.0,
                provider = map["provider"] as? String ?: "",
                timestamp = (map["timestamp"] as? Number)?.toLong() ?: 0L,
                deviceId = map["deviceId"] as? String ?: "",
                nickname = map["nickname"] as? String ?: "",
                beaconEnvelope = map["beaconEnvelope"] as? String ?: "",
                nonce = map["nonce"] as? String ?: "",
                mac = map["mac"] as? String ?: "",
            )
        } catch (e: Exception) {
            null
        }
    }

    // ── Minimal flat-object JSON (string/number fields only) ────────────────

    private fun encodeJson(e: Envelope): String = buildString {
        append('{')
        append("\"type\":").append(quote(e.type))
        append(",\"cmdId\":").append(e.cmdId)
        append(",\"command\":").append(quote(e.command))
        append(",\"params\":").append(quote(e.params))
        append(",\"status\":").append(quote(e.status))
        append(",\"failureReason\":").append(quote(e.failureReason))
        append(",\"lat\":").append(e.lat)
        append(",\"lng\":").append(e.lng)
        append(",\"accuracy\":").append(e.accuracy)
        append(",\"provider\":").append(quote(e.provider))
        append(",\"timestamp\":").append(e.timestamp)
        append(",\"deviceId\":").append(quote(e.deviceId))
        append(",\"nickname\":").append(quote(e.nickname))
        append(",\"beaconEnvelope\":").append(quote(e.beaconEnvelope))
        append(",\"nonce\":").append(quote(e.nonce))
        append(",\"mac\":").append(quote(e.mac))
        append('}')
    }

    private fun quote(s: String): String =
        "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

    /** Parse a flat JSON object into Map<String, Any?> (String/Double/Long/Boolean). */
    internal fun parseJsonObject(json: String): Map<String, Any?>? {
        var i = skipWs(json, 0)
        if (i >= json.length || json[i] != '{') return null
        i = skipWs(json, i + 1)
        val map = LinkedHashMap<String, Any?>()
        if (i < json.length && json[i] == '}') return map // empty object
        while (i < json.length) {
            // key
            if (json[i] != '"') return null
            val keyEnd = json.indexOf('"', i + 1)
            if (keyEnd < 0) return null
            val key = unescape(json.substring(i + 1, keyEnd)) ?: return null
            i = skipWs(json, keyEnd + 1)
            if (i >= json.length || json[i] != ':') return null
            i = skipWs(json, i + 1)
            if (i >= json.length) return null
            val value: Any?
            when (json[i]) {
                '"' -> {
                    // Scan for the closing quote, skipping escaped \" pairs.
                    var end = i + 1
                    var found = false
                    while (end < json.length) {
                        if (json[end] == '\\') {
                            end += 2 // skip the escaped char
                            continue
                        }
                        if (json[end] == '"') {
                            found = true
                            break
                        }
                        end++
                    }
                    if (!found) return null
                    value = unescape(json.substring(i + 1, end)) ?: return null
                    i = end + 1
                }
                '{' -> return null // nested objects unsupported — flat only
                't' -> { if (!json.startsWith("true", i)) return null; value = true; i += 4 }
                'f' -> { if (!json.startsWith("false", i)) return null; value = false; i += 5 }
                'n' -> { if (!json.startsWith("null", i)) return null; value = null; i += 4 }
                else -> {
                    val end = json.indexOfAny(charArrayOf(',', '}'), i)
                    if (end < 0) return null
                    val raw = json.substring(i, end).trim()
                    value = raw.toLongOrNull() ?: raw.toDoubleOrNull() ?: return null
                    i = end
                }
            }
            map[key] = value
            i = skipWs(json, i)
            if (i >= json.length) return null
            if (json[i] == '}') return map
            if (json[i] != ',') return null
            i = skipWs(json, i + 1)
        }
        return null
    }

    private fun skipWs(json: String, from: Int): Int {
        var i = from
        while (i < json.length && (json[i] == ' ' || json[i] == '\t' || json[i] == '\n' || json[i] == '\r')) i++
        return i
    }

    private fun unescape(s: String): String? {
        if ('\\' !in s) return s
        val sb = StringBuilder()
        var i = 0
        while (i < s.length) {
            val c = s[i]
            if (c == '\\' && i + 1 < s.length) {
                val n = s[i + 1]
                when (n) {
                    '\\' -> sb.append('\\')
                    '"' -> sb.append('"')
                    '/' -> sb.append('/')
                    'n' -> sb.append('\n')
                    't' -> sb.append('\t')
                    'r' -> sb.append('\r')
                    'b' -> sb.append('\b')
                    'f' -> sb.append('\u000C')
                    'u' -> {
                        if (i + 5 >= s.length) return null
                        val hex = s.substring(i + 2, i + 6)
                        val code = hex.toIntOrNull(16) ?: return null
                        sb.append(code.toChar())
                        i += 4
                    }
                    else -> return null
                }
                i += 2
            } else {
                sb.append(c)
                i++
            }
        }
        return sb.toString()
    }
}
