package com.magneetar.app

/**
 * Pure, unit-testable decision logic for remote capture commands.
 *
 * Android 14+ refuses to START a camera|microphone foreground service from
 * the background, so capture only ever runs through the ALREADY-armed
 * MediaCaptureService. When it isn't armed, the only honest options are a
 * tap-to-re-arm notification and a 'failed' ack — the dashboard shows the
 * truth instead of a phantom 'executed'.
 *
 * This file is deliberately free of Android types so the honesty contract is
 * unit-testable on the JVM (see CaptureRoutingTest.kt). The action strings
 * are const vals of MediaCaptureService, inlined at compile time — no Android
 * classes are loaded when this module runs under plain JUnit.
 */
enum class CapturePath {
    /** Capture service not armed — post the re-arm notification + ack 'failed'. */
    PROMPT_REARM,

    /** Armed and the command maps to a real capture action — run it there. */
    RUN_ARMED_CAPTURE,

    /**
     * The armed AUDIO WATCH is holding the mic — escalate it to EVIDENCE
     * mode instead of running a 30s clip in MediaCaptureService. Only one
     * mic user may exist (two concurrent AudioRecords would fight); the
     * watch already listens continuously, so the command becomes an
     * EVIDENCE escalation on the already-running service.
     */
    RUN_AUDIO_WATCH,

    /** Armed but the command is unknown — ack 'failed', never run anything. */
    REFUSE_UNKNOWN,
}

object CaptureRouting {

    /** Map a capture command name to the armed service action; null when unknown. */
    fun actionFor(command: String): String? = when (command) {
        "capture_photo" -> MediaCaptureService.ACTION_CAPTURE_PHOTO
        "capture_photo_front" -> MediaCaptureService.ACTION_CAPTURE_PHOTO_FRONT
        "capture_audio" -> MediaCaptureService.ACTION_CAPTURE_AUDIO
        else -> null
    }

    /**
     * How a capture command must be handled (MediaCaptureService-only view):
     * - Not armed → PROMPT_REARM (the FGS cannot be background-started on
     *   Android 14+, so capture is honestly unavailable).
     * - Armed with a known command → RUN_ARMED_CAPTURE.
     * - Armed with an unknown command → REFUSE_UNKNOWN (defensive — the
     *   server validates commands, so this should never happen).
     */
    fun route(armed: Boolean, command: String): CapturePath = when {
        !armed -> CapturePath.PROMPT_REARM
        actionFor(command) == null -> CapturePath.REFUSE_UNKNOWN
        else -> CapturePath.RUN_ARMED_CAPTURE
    }

    /**
     * Full capture routing including the armed audio watch (mic exclusivity).
     *
     * [watchArmed] — ArmedAudioService is running and holding the mic.
     * [mediaArmed] — MediaCaptureService (camera|mic FGS) is armed.
     *
     * `capture_audio` prefers the audio watch when it is armed (it already
     * holds the mic; escalating to EVIDENCE is the only mic-safe capture).
     * Everything else keeps the MediaCaptureService path.
     */
    fun routeFull(watchArmed: Boolean, mediaArmed: Boolean, command: String): CapturePath = when {
        command == "capture_audio" && watchArmed -> CapturePath.RUN_AUDIO_WATCH
        command == "capture_audio" && mediaArmed -> CapturePath.RUN_ARMED_CAPTURE
        command == "capture_audio" -> CapturePath.PROMPT_REARM
        !mediaArmed -> CapturePath.PROMPT_REARM
        actionFor(command) == null -> CapturePath.REFUSE_UNKNOWN
        else -> CapturePath.RUN_ARMED_CAPTURE
    }
}
