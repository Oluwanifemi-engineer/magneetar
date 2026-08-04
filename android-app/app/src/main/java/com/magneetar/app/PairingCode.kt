package com.magneetar.app

/**
 * Pure, unit-testable pairing-code computation for the "Link a device" flow.
 *
 * The pairing code is the first 8 hex chars of SHA-256(device_key) — the
 * server stores the full hash and compares the same 8-char prefix
 * (routes/dashboard.py, claim-by-pairing endpoint). Deriving it from the
 * device key (not the device id) means an onlooker who learns the device id
 * still cannot claim the phone.
 *
 * This file is deliberately free of Android types so the server contract is
 * locked in on the plain JVM (see PairingCodeTest.kt) — if the algorithm on
 * either side drifts, the test fails instead of the pairing silently breaking
 * in production.
 */
object PairingCode {

    /**
     * Lowercase-hex SHA-256 of the raw device key, first 8 characters.
     * Matches the server exactly: `hashlib.sha256(key.encode()).hexdigest()[:8]`.
     * Returns "" on any failure (never throws — pairing is a UX nicety).
     */
    fun of(deviceKey: String): String = try {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
            .digest(deviceKey.toByteArray(Charsets.UTF_8))
        digest.joinToString("") { "%02x".format(it) }.take(8)
    } catch (e: Exception) {
        ""
    }
}
