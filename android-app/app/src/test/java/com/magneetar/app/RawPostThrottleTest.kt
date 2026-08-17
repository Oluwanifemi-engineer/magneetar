package com.magneetar.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * G1-16 regression tests for the raw-path post throttle.
 *
 * The raw GPS listener (added in the fused branch) can deliver ~1 fix/s
 * during a lock, and the raw network listener fires on cell/WiFi change —
 * without a shared throttle the two would post far faster than the server's
 * 30/min location rate limit and 429 the stream (observed live during the
 * Ile-Ife incident: a fused drop + redundant raw fixes double-posted).
 *
 * The throttle caps raw-path uploads at 1 per RAW_POST_MIN_INTERVAL_NS (5s →
 * max 12/min, comfortably under 30/min) while the Kalman filter still
 * ingests every fix.
 */
class RawPostThrottleTest {

    private val minIntervalNs = 5L * 1_000_000_000L // 5s, mirror of the constant

    @Test
    fun `post is due when the interval has fully elapsed`() {
        assertTrue(rawPostDue(lastPostNs = 0L, nowNs = minIntervalNs, minIntervalNs = minIntervalNs))
    }

    @Test
    fun `post is due when way over the interval`() {
        assertTrue(
            rawPostDue(
                lastPostNs = 1_000L,
                nowNs = 1_000L + 10 * minIntervalNs,
                minIntervalNs = minIntervalNs,
            )
        )
    }

    @Test
    fun `post is NOT due before the interval elapses`() {
        assertFalse(rawPostDue(lastPostNs = 0L, nowNs = minIntervalNs - 1L, minIntervalNs = minIntervalNs))
        assertFalse(rawPostDue(lastPostNs = 100L, nowNs = 100L + minIntervalNs / 2, minIntervalNs = minIntervalNs))
    }

    @Test
    fun `burst of raw fixes at one per second is throttled to one per interval`() {
        // Simulate a raw GPS lock delivering 1 fix/s for 30s.
        var lastPostNs = 0L
        var posts = 0
        var nowNs = 0L
        while (nowNs < 30L * 1_000_000_000L) {
            nowNs += 1L * 1_000_000_000L
            if (rawPostDue(lastPostNs, nowNs, minIntervalNs)) {
                posts++
                lastPostNs = nowNs
            }
        }
        // 30s of 1/s fixes → at most 1 post per 5s → ≤6 posts, never 30.
        assertTrue("expected ≤6 posts, got $posts", posts <= 6)
    }

    @Test
    fun `steady cadence stays under the server rate limit`() {
        // Worst case: fixes arrive every 5s (interval boundary) for an hour.
        var lastPostNs = 0L
        var posts = 0
        var nowNs = 0L
        while (nowNs < 60L * 60L * 1_000_000_000L) {
            nowNs += minIntervalNs
            if (rawPostDue(lastPostNs, nowNs, minIntervalNs)) {
                posts++
                lastPostNs = nowNs
            }
        }
        // 12 posts/min = 720/hour — exactly the designed budget (30/min limit).
        assertTrue("expected 720 posts/hour, got $posts", posts == 720)
    }
}
