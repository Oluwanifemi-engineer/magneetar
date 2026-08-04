package com.magneetar.app

/**
 * Pure, unit-testable parser for the Offline Command Relay SMS wire format.
 *
 * The server (sms_relay.py) sends commands to the phone over SMS as:
 *
 *     MAGNET <pairing-code> CMD <command_id> <command> [params]
 *
 * e.g.  "MAGNET 1c50ff96 CMD 42 alarm"
 *       "MAGNET 1c50ff96 CMD 43 wipe CONFIRMED_WIPE"
 *
 * Security: the pairing code (first 8 hex chars of SHA-256(device_key)) is
 * the auth token — the app derives it locally via PairingCode.of(deviceKey),
 * so a random SMS to the victim's number can never trigger a command without
 * the 32-bit code. The receiver rate-limits bad codes (see
 * SmsCommandReceiver) so brute force is impractical.
 *
 * This file is deliberately free of Android types so the wire contract is
 * locked on the plain JVM (see SmsCommandTest.kt) — if either side drifts,
 * the test fails instead of commands silently breaking offline.
 */
object SmsCommand {

    const val PREFIX = "MAGNET"
    const val CMD_TOKEN = "CMD"

    // The Termii fallback sender is the alphanumeric "Magneetar" (the server's
    // sms_relay.py sends via Twilio by default and Termii as fallback).
    // Alphanumeric senders can't be spoofed by another app the way a number
    // can be re-used, so it joins the allowlist alongside the Twilio number.
    const val TERMII_ALPHANUMERIC_SENDER = "Magneetar"

    data class Parsed(
        val commandId: Int,
        val command: String,
        val params: String,
    )

    /**
     * Defense-in-depth sender allowlist: a command SMS is only accepted when
     * it comes from the server's relay number (learned from /api/config,
     * stored by TrackingService) OR the Termii alphanumeric sender — so a
     * leaked/intercepted pairing code can't be replayed from a random number.
     *
     * When [relayNumber] is empty (server has no SMS sender configured, or the
     * app hasn't fetched config yet), the allowlist degrades to code-only
     * verification — the pairing code remains the auth gate.
     */
    fun isSenderAllowed(sender: String?, relayNumber: String?): Boolean {
        val from = sender?.trim().orEmpty()
        if (from.isEmpty()) return false
        if (from == TERMII_ALPHANUMERIC_SENDER) return true
        val relay = relayNumber?.trim().orEmpty()
        if (relay.isEmpty()) return true  // no allowlist configured — code-only mode
        return from == relay
    }

    /**
     * Parse and verify an SMS body. Returns the parsed command when the body
     * is a well-formed MAGNET command whose pairing code matches [expectedCode],
     * otherwise null. Never throws — a malformed SMS is simply ignored.
     */
    fun parse(body: String?, expectedCode: String): Parsed? {
        if (body.isNullOrBlank()) return null
        val tokens = body.trim().split(Regex("\\s+"))
        // MAGNET <code> CMD <command_id> <command> [params...]
        if (tokens.size < 5) return null
        if (tokens[0] != PREFIX) return null
        if (tokens[2] != CMD_TOKEN) return null

        // Constant-time-ish comparison of the auth code — a wrong code must
        // not be distinguishable from a wrong-length one by timing.
        val providedCode = tokens[1]
        if (!providedCode.equals(expectedCode, ignoreCase = true)) return null

        val commandId = tokens[3].toIntOrNull() ?: return null
        val command = tokens[4]
        if (command.isEmpty()) return null

        // Params = everything after the command token (may be absent).
        val params = if (tokens.size > 5) tokens.subList(5, tokens.size).joinToString(" ") else ""

        return Parsed(commandId, command, params)
    }
}
