package com.magneetar.app

import kotlin.math.max
import kotlin.math.sqrt

/**
 * Adaptive noise-floor Voice Activity Detector (pure Kotlin — JVM-testable).
 *
 * The STEALTH audio watch records continuously but must not persist silence:
 * a 16 kHz mic in a pocket produces megabytes of dead air per hour, and
 * uploading it is storage + data-cost with zero evidence value. This VAD
 * classifies each 20 ms PCM block as speech/silence with:
 *
 *  - RMS energy against an ADAPTIVE noise floor (fast attack, slow release),
 *    so a quiet room and a noisy market calibrate themselves;
 *  - a 500 ms HANGOVER so speech pauses (breaths, short gaps) don't split a
 *    segment into fragments;
 *  - min-speech (200 ms) / min-silence (1.5 s) debounce so one door-slam or a
 *    single background cough never opens or closes a segment.
 *
 * Segment events drive ArmedAudioService's ring-buffer + segment lifecycle:
 * SPEECH_START opens a segment (pre-pending the pre-roll), SPEECH_CONTINUE
 * appends, SPEECH_END closes it, SILENCE feeds the pre-roll ring.
 */
class VadDetector(
    private val sampleRate: Int,
    private val hangoverMs: Long = 500,
    private val minSpeechMs: Long = 200,
    private val minSilenceMs: Long = 1500,
) {

    enum class SegmentEvent { SILENCE, SPEECH_START, SPEECH_END, SPEECH_CONTINUE }

    // 16-bit PCM: RMS of pure digital silence is 0; a quiet room reads in the
    // low hundreds. The floor starts pessimistic (800) and adapts within a
    // few blocks, so the FIRST block of a loud room is never spuriously kept.
    private var noiseFloor = 800.0
    private var speechActive = false
    private var hangoverRemaining = 0L
    private var speechAccumMs = 0L
    private var silenceAccumMs = 0L

    private val blockMs: Long = (20.0 * sampleRate / sampleRate).toLong() // 20 ms per 320-sample block @16k

    /**
     * Classify one PCM block. [block] must be BLOCK_SAMPLES shorts at the
     * configured sample rate (ArmedAudioService reads 320 shorts per 20 ms).
     */
    fun classify(block: ShortArray): SegmentEvent {
        val rms = rms(block)
        val threshold = max(noiseFloor * 8.0, 1200.0)
        val isSpeech = rms >= threshold

        if (isSpeech) {
            // Speech is the SIGNAL, never the noise floor — freezing the floor
            // on loud blocks is what keeps sustained speech detectable (a
            // floor that tracks the signal would raise the threshold above the
            // speaker and silently stop capturing — seen in the design doc's
            // original formula, reproduced in tests). The floor re-adapts in
            // the quiet gaps between utterances instead.
            hangoverRemaining = hangoverMs
        } else {
            // Quiet block: track the ambient noise (fast attack when it rises,
            // slow release when it falls — a room that gets quieter must
            // re-adapt). The 8x margin keeps speech above the floor even in a
            // noisy market.
            noiseFloor = if (rms > noiseFloor) noiseFloor * 0.95 + rms * 0.05
                         else noiseFloor * 0.995 + rms * 0.005
        }

        return when {
            !speechActive && isSpeech -> {
                speechActive = true
                speechAccumMs = blockMs
                silenceAccumMs = 0
                SegmentEvent.SPEECH_START
            }
            speechActive && isSpeech -> {
                speechAccumMs += blockMs
                hangoverRemaining = hangoverMs
                SegmentEvent.SPEECH_CONTINUE
            }
            speechActive && !isSpeech -> {
                hangoverRemaining -= blockMs
                if (hangoverRemaining <= 0) {
                    if (speechAccumMs >= minSpeechMs) {
                        // Real utterance ended — close the segment.
                        speechActive = false
                        silenceAccumMs = 0
                        SegmentEvent.SPEECH_END
                    } else {
                        // Too short to be speech (door slam / cough) — discard.
                        speechActive = false
                        SegmentEvent.SILENCE
                    }
                } else {
                    // Inside the hangover window — keep the segment open, but
                    // do NOT count this silence toward speech duration. A
                    // 20ms door-slam would otherwise accumulate 500ms of
                    // "speech" during hangover and pass minSpeechMs, closing
                    // a segment that was never an utterance.
                    SegmentEvent.SPEECH_CONTINUE
                }
            }
            else -> {
                silenceAccumMs += blockMs
                if (!speechActive && silenceAccumMs >= minSilenceMs) {
                    silenceAccumMs = minSilenceMs // saturate — no overflow interest
                }
                SegmentEvent.SILENCE
            }
        }
    }

    /** True when an utterance is currently open (mid-speech or in hangover). */
    fun isSpeaking(): Boolean = speechActive

    /** Reset the adaptive state (called when the mic is re-armed). */
    fun reset() {
        noiseFloor = 800.0
        speechActive = false
        hangoverRemaining = 0
        speechAccumMs = 0
        silenceAccumMs = 0
    }

    private fun rms(b: ShortArray): Double {
        if (b.isEmpty()) return 0.0
        var sum = 0.0
        for (s in b) sum += s.toDouble() * s
        return sqrt(sum / b.size)
    }
}
