package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Regression tests for the Armed Watch honesty contract (Android 14/15).
 *
 * On stock Android 14+ a camera|microphone foreground service cannot be
 * STARTED from the background, so a remote capture command only works while
 * the armed service is alive. When it isn't, the app must surface 'failed'
 * (via the re-arm prompt path) — never a phantom 'executed' that leaves the
 * dashboard claiming evidence that doesn't exist.
 *
 * These tests run on the plain JVM (no Robolectric): CaptureRouting is pure
 * Kotlin, and the MediaCaptureService action strings are const vals inlined
 * at compile time, so no Android classes are loaded.
 */
class CaptureRoutingTest {

    @Test
    fun `unarmed capture commands route to the re-arm prompt`() {
        // The core honesty contract: EVERY capture command on an unarmed
        // device must take the PROMPT_REARM path (re-arm notification +
        // 'failed' ack), for photo, front-camera, AND audio alike.
        for (command in listOf("capture_photo", "capture_photo_front", "capture_audio")) {
            assertEquals(
                "unarmed + $command must route to PROMPT_REARM",
                CapturePath.PROMPT_REARM,
                CaptureRouting.route(armed = false, command = command),
            )
        }
    }

    @Test
    fun `unarmed unknown command also routes to the re-arm prompt`() {
        assertEquals(CapturePath.PROMPT_REARM, CaptureRouting.route(armed = false, command = "ping"))
        assertEquals(CapturePath.PROMPT_REARM, CaptureRouting.route(armed = false, command = "bogus"))
    }

    @Test
    fun `armed capture commands route to the armed service`() {
        assertEquals(CapturePath.RUN_ARMED_CAPTURE, CaptureRouting.route(armed = true, command = "capture_photo"))
        assertEquals(
            CapturePath.RUN_ARMED_CAPTURE,
            CaptureRouting.route(armed = true, command = "capture_photo_front"),
        )
        assertEquals(CapturePath.RUN_ARMED_CAPTURE, CaptureRouting.route(armed = true, command = "capture_audio"))
    }

    @Test
    fun `armed service action matches the command`() {
        assertEquals(MediaCaptureService.ACTION_CAPTURE_PHOTO, CaptureRouting.actionFor("capture_photo"))
        assertEquals(MediaCaptureService.ACTION_CAPTURE_PHOTO_FRONT, CaptureRouting.actionFor("capture_photo_front"))
        assertEquals(MediaCaptureService.ACTION_CAPTURE_AUDIO, CaptureRouting.actionFor("capture_audio"))
        assertNull(CaptureRouting.actionFor("ping"))
        assertNull(CaptureRouting.actionFor(""))
    }

    @Test
    fun `unknown command while armed is refused honestly`() {
        // Defensive: an unknown command must never run — it acks failed.
        assertEquals(CapturePath.REFUSE_UNKNOWN, CaptureRouting.route(armed = true, command = "not_a_command"))
    }
}
