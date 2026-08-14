package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Locks the security-critical piece of the in-app self-updater: the download
 * is only ever installed after its size AND SHA-256 match the digest the
 * server reports for the exact bytes it serves. Any drift (truncation,
 * tampering, a stale file) must fail closed.
 */
class AppUpdaterTest {

    private fun tempFile(content: String): File {
        val f = File.createTempFile("magneetar-updater-test", ".bin")
        f.deleteOnExit()
        f.writeText(content)
        return f
    }

    @Test
    fun `sha256 matches the standard vector`() {
        // SHA-256("hello") — well-known digest.
        val f = tempFile("hello")
        assertEquals(
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            AppUpdater.sha256(f)
        )
    }

    @Test
    fun `verify accepts exact size and hash`() {
        val f = tempFile("magneetar-apk-bytes")
        val digest = AppUpdater.sha256(f)
        assertTrue(AppUpdater.verify(f, digest, f.length()))
    }

    @Test
    fun `verify rejects when the hash differs`() {
        val f = tempFile("magneetar-apk-bytes")
        val wrong = "0".repeat(64)
        assertFalse(AppUpdater.verify(f, wrong, f.length()))
    }

    @Test
    fun `verify rejects when the size differs`() {
        val f = tempFile("magneetar-apk-bytes")
        assertFalse(AppUpdater.verify(f, AppUpdater.sha256(f), f.length() + 1))
    }

    @Test
    fun `verify rejects an empty expected hash`() {
        val f = tempFile("anything")
        assertFalse(AppUpdater.verify(f, "", f.length()))
    }

    @Test
    fun `verify is case-insensitive on the digest`() {
        val f = tempFile("case-insensitive")
        val upper = AppUpdater.sha256(f).uppercase()
        assertTrue(AppUpdater.verify(f, upper, f.length()))
    }

    @Test
    fun `verify rejects a truncated file even when size check is skipped`() {
        // expectedSizeBytes <= 0 skips the size gate; the hash must still fail.
        val f = tempFile("full-content-of-the-apk")
        val original = AppUpdater.sha256(f)
        f.writeText("short")
        assertFalse(AppUpdater.verify(f, original, -1L))
    }
}
