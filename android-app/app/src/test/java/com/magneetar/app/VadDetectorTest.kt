package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.random.Random

/**
 * JVM tests for the adaptive noise-floor VAD (no Android classes — pure math).
 *
 * The VAD decides what the STEALTH watch persists: silence feeds the pre-roll
 * ring, speech opens a segment. Getting this wrong both ways is expensive:
 *  - false SPEECH on noise → megabytes of dead air uploaded hourly;
 *  - false SILENCE on real speech → the thief's first sentence is lost.
 */
class VadDetectorTest {

    private val sampleRate = 16_000
    private val blockSamples = 320  // 20 ms @ 16 kHz

    private fun silenceBlock(amplitude: Short = 40): ShortArray =
        ShortArray(blockSamples) { (Random.nextInt(-1, 2) * amplitude).toShort() }

    private fun speechBlock(amplitude: Short = 16000): ShortArray {
        // A loud conversational tone: RMS ≈ 16000/√2 ≈ 11.3k, comfortably above
        // the VAD's initial threshold (max(800*8, 1200) = 6400) and any floor
        // the quiet-ambient test leaves behind (a floor of 40 → 320).
        val out = ShortArray(blockSamples)
        for (i in out.indices) {
            val sample = kotlin.math.sin(i * 0.3) * amplitude
            out[i] = sample.toInt().toShort()
        }
        return out
    }

    @Test
    fun `steady silence never opens a segment`() {
        val vad = VadDetector(sampleRate)
        var speechEvents = 0
        repeat(500) {
            when (vad.classify(silenceBlock())) {
                VadDetector.SegmentEvent.SPEECH_START, VadDetector.SegmentEvent.SPEECH_CONTINUE -> speechEvents++
                else -> {}
            }
        }
        assertEquals(0, speechEvents)
    }

    @Test
    fun `sustained speech opens a segment and sustains it`() {
        val vad = VadDetector(sampleRate)
        val first = vad.classify(speechBlock())
        assertEquals(VadDetector.SegmentEvent.SPEECH_START, first)
        // 10 more speech blocks: all CONTINUE (hangover keeps it open).
        repeat(10) {
            assertEquals(VadDetector.SegmentEvent.SPEECH_CONTINUE, vad.classify(speechBlock()))
        }
        assertTrue("VAD must report speaking", vad.isSpeaking())
    }

    @Test
    fun `a single loud burst is discarded as too short`() {
        // One door-slam: SPEECH_START on the burst, but the following silence
        // runs past hangover with accumulated speech < minSpeechMs → SILENCE
        // (no SPEECH_END, segment never persisted).
        val vad = VadDetector(sampleRate, hangoverMs = 500, minSpeechMs = 200)
        assertEquals(VadDetector.SegmentEvent.SPEECH_START, vad.classify(speechBlock()))
        var sawEnd = false
        repeat(200) {  // 4 s of silence — hangover (500ms) + debounce exhausted
            val ev = vad.classify(silenceBlock())
            if (ev == VadDetector.SegmentEvent.SPEECH_END) sawEnd = true
        }
        assertEquals("a 20ms burst must not close a real segment", false, sawEnd)
        assertTrue("must be silent again", !vad.isSpeaking())
    }

    @Test
    fun `speech then silence closes the segment after hangover`() {
        val vad = VadDetector(sampleRate, hangoverMs = 500, minSpeechMs = 200)
        assertEquals(VadDetector.SegmentEvent.SPEECH_START, vad.classify(speechBlock()))
        repeat(25) { vad.classify(speechBlock()) }  // 500ms of speech
        var closed = false
        repeat(60) {  // 1.2s silence > 500ms hangover
            if (vad.classify(silenceBlock()) == VadDetector.SegmentEvent.SPEECH_END) closed = true
        }
        assertTrue("utterance must close with SPEECH_END after hangover", closed)
    }

    @Test
    fun `silence between words keeps the segment open (hangover)`() {
        val vad = VadDetector(sampleRate, hangoverMs = 500, minSpeechMs = 200)
        vad.classify(speechBlock())
        repeat(25) { vad.classify(speechBlock()) }
        // A 200ms pause (10 blocks) — inside the 500ms hangover.
        repeat(10) { vad.classify(silenceBlock()) }
        assertTrue("pause inside hangover must keep speaking=true", vad.isSpeaking())
        // Speech resumes — still CONTINUE, no new START.
        assertEquals(VadDetector.SegmentEvent.SPEECH_CONTINUE, vad.classify(speechBlock()))
    }
}
