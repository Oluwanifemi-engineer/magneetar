package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Locks the Offline Command Relay SMS wire contract between the server
 * (sms_relay.py command_sms_body) and the Android app.
 *
 * The server builds:  "MAGNET <code> CMD <command_id> <command> [params]"
 * where <code> = first 8 hex chars of SHA-256(device_key) — the same value
 * PairingCode.of() derives locally. These vectors are hardcoded from the
 * server's own algorithm so a drift on either side fails here instead of
 * silently breaking offline commands in production.
 */
class SmsCommandTest {

    private val code = "1c50ff96" // PairingCode.of("devicekey-pair-ok-device")

    @Test
    fun `parses a simple command from the server format`() {
        val cmd = SmsCommand.parse("MAGNET 1c50ff96 CMD 42 alarm", code)
        assertNotNull(cmd)
        assertEquals(42, cmd!!.commandId)
        assertEquals("alarm", cmd.command)
        assertEquals("", cmd.params)
    }

    @Test
    fun `parses a command with params`() {
        val cmd = SmsCommand.parse("MAGNET 1c50ff96 CMD 43 wipe CONFIRMED_WIPE", code)
        assertNotNull(cmd)
        assertEquals(43, cmd!!.commandId)
        assertEquals("wipe", cmd.command)
        assertEquals("CONFIRMED_WIPE", cmd.params)
    }

    @Test
    fun `parses a command with multi-word params`() {
        val cmd = SmsCommand.parse("MAGNET 1c50ff96 CMD 44 display_message hello world", code)
        assertNotNull(cmd)
        assertEquals(44, cmd!!.commandId)
        assertEquals("display_message", cmd.command)
        assertEquals("hello world", cmd.params)
    }

    @Test
    fun `rejects a wrong pairing code`() {
        assertNull(SmsCommand.parse("MAGNET deadbeef CMD 42 alarm", code))
    }

    @Test
    fun `rejects a malformed body`() {
        assertNull(SmsCommand.parse("hello this is spam", code))
        assertNull(SmsCommand.parse("MAGNET", code))
        assertNull(SmsCommand.parse("MAGNET 1c50ff96 CMD", code))
        assertNull(SmsCommand.parse("MAGNET 1c50ff96 CMD notanumber alarm", code))
        assertNull(SmsCommand.parse(null, code))
        assertNull(SmsCommand.parse("", code))
        assertNull(SmsCommand.parse("MAGNET 1c50ff96 WRONG 42 alarm", code))
    }

    @Test
    fun `code comparison is case-insensitive like a hex digest`() {
        // The server sends lowercase hex; accept uppercase in case a carrier
        // mangles case — the security model is the code's entropy, not case.
        val cmd = SmsCommand.parse("MAGNET 1C50FF96 CMD 42 alarm", code)
        assertNotNull(cmd)
        assertEquals(42, cmd!!.commandId)
    }

    @Test
    fun `ignores surrounding whitespace and carrier concatenation`() {
        val cmd = SmsCommand.parse("  MAGNET 1c50ff96 CMD 42 alarm  ", code)
        assertNotNull(cmd)
        assertEquals("alarm", cmd!!.command)
    }

    // ── Sender allowlist (defense in depth) ────────────────────────────────

    @Test
    fun `allows the configured relay number`() {
        assertTrue(SmsCommand.isSenderAllowed("+15551234567", "+15551234567"))
    }

    @Test
    fun `allows the Termii alphanumeric sender`() {
        assertTrue(SmsCommand.isSenderAllowed("Magneetar", "+15551234567"))
    }

    @Test
    fun `rejects a foreign sender when a relay number is configured`() {
        // A leaked pairing code must NOT be replayable from a random number.
        assertFalse(SmsCommand.isSenderAllowed("+49999999999", "+15551234567"))
        assertFalse(SmsCommand.isSenderAllowed("ScammerCo", "+15551234567"))
    }

    @Test
    fun `degrades to code-only when no relay number is configured`() {
        // Server has no SMS sender (or app hasn't fetched config yet): the
        // pairing code remains the auth gate.
        assertTrue(SmsCommand.isSenderAllowed("+49999999999", ""))
        assertTrue(SmsCommand.isSenderAllowed("anything", null))
    }

    @Test
    fun `rejects an empty sender`() {
        assertFalse(SmsCommand.isSenderAllowed("", ""))
        assertFalse(SmsCommand.isSenderAllowed(null, "+15551234567"))
    }

    @Test
    fun `sender comparison ignores surrounding whitespace`() {
        assertTrue(SmsCommand.isSenderAllowed("  +15551234567 ", "+15551234567"))
    }
}
