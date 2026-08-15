package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.hypot

/**
 * JVM tests for the location fusion Kalman filter.
 *
 * The filter is pure Kotlin (no Android types) specifically so the math can
 * be locked down here without Robolectric: convergence, outlier rejection,
 * stationary lock, and accuracy-weighted fusion are the four contracts that
 * matter for a tracker that must show a STABLE position, not a jittery one.
 */
class LocationFilterTest {

    private fun fix(
        lat: Double,
        lng: Double,
        acc: Float = 5f,
        ts: Long = 0L,
        provider: String = "gps",
    ) = LocationFilter.Fix(lat, lng, acc, ts, provider)

    /** ~111.32 km per degree of latitude — the meters/deg used by the filter. */
    private fun mPerDeg() = 111_320.0

    @Test
    fun `first fix initializes the filter at that position`() {
        val f = LocationFilter()
        val e = f.update(fix(6.5, 3.4, 5f, 1000L))!!
        assertEquals(6.5, e.lat, 1e-9)
        assertEquals(3.4, e.lng, 1e-9)
        assertFalse(e.outlier)
        // Initial accuracy comes from the reported 5m.
        assertTrue(e.accuracyMeters <= 6.0)
    }

    @Test
    fun `straight-line track converges without bias`() {
        val f = LocationFilter()
        val startLat = 6.5
        val startLng = 3.4
        f.update(fix(startLat, startLng, 5f, 0L))

        // Simulate walking ~50m north over 10 seconds at 1Hz (5 m/s — brisk
        // jog), with small GPS noise on top.
        val mPerDeg = mPerDeg()
        val noise = 5.0 / mPerDeg
        var lat = startLat
        val stepMeters = 5.0 // 5 m per 1 Hz step = 50 m total over 10 s
        val expectedDelta = stepMeters / mPerDeg
        var ts = 0L
        var last: LocationFilter.Estimate? = null
        for (i in 1..10) {
            ts += 1000L
            lat = startLat + expectedDelta * i + ((i % 3) * 0.2 - 0.2) * noise * 2
            last = f.update(fix(lat, startLng, 5f, ts))
        }
        val estimate = last ?: error("filter never produced an estimate")
        val travelled = (estimate.lat - startLat) * mPerDeg
        // Filtered displacement should be within ~15m of the true 50m.
        assertTrue(
            "expected ~50m travelled, got ${travelled}m",
            kotlin.math.abs(travelled - 50.0) < 15.0,
        )
        assertFalse(estimate.stationary)
    }

    @Test
    fun `slow walker keeps full speed and position`() {
        val f = LocationFilter()
        val startLat = 6.5
        val mPerDeg = mPerDeg()
        f.update(fix(startLat, 3.4, 5f, 0L))

        // 1.5 m/s pedestrian for 20s — the anti-drift lock must NOT bleed
        // this velocity (direction never reverses), or the position would lag.
        var ts = 0L
        var last: LocationFilter.Estimate? = null
        for (i in 1..20) {
            ts += 1000L
            last = f.update(fix(startLat + (1.5 / mPerDeg) * i, 3.4, 5f, ts))
        }
        val estimate = last ?: error("filter never produced an estimate")
        val travelled = (estimate.lat - startLat) * mPerDeg
        assertTrue(
            "slow walker must track the full 30m, got ${travelled}m",
            kotlin.math.abs(travelled - 30.0) < 6.0,
        )
        assertTrue("slow walker speed should stay ~1.5 m/s, got ${estimate.speedMps}",
            estimate.speedMps > 1.0)
    }

    @Test
    fun `stationary device locks position despite GPS jitter`() {
        val f = LocationFilter()
        val lat = 6.5
        val lng = 3.4
        f.update(fix(lat, lng, 4f, 0L))

        // 20 jittered fixes (±8m) around the same spot, 1Hz.
        val mPerDeg = mPerDeg()
        var ts = 0L
        var last: LocationFilter.Estimate? = null
        for (i in 1..20) {
            ts += 1000L
            val jitterDeg = 8.0 / mPerDeg * (if (i % 2 == 0) 1 else -1)
            last = f.update(fix(lat + jitterDeg, lng, 4f, ts))
        }
        val estimate = last ?: error("filter never produced an estimate")
        val drift = hypot((estimate.lat - lat) * mPerDeg, (estimate.lng - lng) * mPerDeg)
        assertTrue("drift should be well under jitter, got ${drift}m", drift < 6.0)
        // The stationary lock should have kicked in.
        assertTrue(estimate.stationary || estimate.speedMps < 0.5)
    }

    @Test
    fun `impossible teleport is rejected as outlier`() {
        val f = LocationFilter()
        f.update(fix(6.5, 3.4, 5f, 0L))
        // A 500m jump in 3 seconds = ~167 m/s: physically impossible for a phone.
        val mPerDeg = mPerDeg()
        val e = f.update(fix(6.5 + 500.0 / mPerDeg, 3.4, 5f, 3000L))!!
        assertTrue("500m/3s jump must be gated as an outlier", e.outlier)
    }

    @Test
    fun `network fix with huge accuracy barely moves the estimate`() {
        val f = LocationFilter()
        f.update(fix(6.5, 3.4, 5f, 0L))
        val mPerDeg = mPerDeg()

        // A network fix with 300m accuracy, 200m off: R is huge so the gain
        // should be tiny — the filtered position must NOT chase it.
        val e = f.update(fix(6.5 + 200.0 / mPerDeg, 3.4, 300f, 2000L))!!
        val moved = hypot((e.lat - 6.5) * mPerDeg, (e.lng - 3.4) * mPerDeg)
        assertTrue("200m network fix with 300m accuracy should be heavily damped, moved ${moved}m", moved < 40.0)
    }

    @Test
    fun `good gps fix after network is trusted more`() {
        val f = LocationFilter()
        f.update(fix(6.5, 3.4, 300f, 0L)) // poor first fix
        val mPerDeg = mPerDeg()
        // A precise GPS fix 10m away should pull the estimate most of the way.
        val e = f.update(fix(6.5 + 10.0 / mPerDeg, 3.4, 3f, 1000L))!!
        val moved = hypot((e.lat - 6.5) * mPerDeg, (e.lng - 3.4) * mPerDeg)
        assertTrue("precise fix should move estimate towards it, moved ${moved}m", moved > 4.0)
    }

    @Test
    fun `reset clears all state`() {
        val f = LocationFilter()
        assertNull(f.lastEstimate())
        f.update(fix(6.5, 3.4, 5f, 0L))
        assertTrue(f.isInitialized)
        assertTrue(f.lastEstimate() != null)
        f.reset()
        assertFalse(f.isInitialized)
        assertNull(f.lastEstimate())
    }

    @Test
    fun `nan fix is rejected and cannot poison the state`() {
        val f = LocationFilter()
        val e1 = f.update(fix(6.5, 3.4, 5f, 0L))!!
        // A NaN fix: both outlier gates are false for NaN, so only the
        // explicit finiteness guard can stop it. It must coast, not corrupt.
        val e2 = f.update(fix(Double.NaN, 3.4, 5f, 1000L))!!
        assertTrue("NaN fix must be flagged", e2.outlier)
        assertTrue("estimate lat must stay finite", e2.lat.isFinite())
        // And the filter must recover cleanly on the next good fix.
        val e3 = f.update(fix(6.5 + 10.0 / mPerDeg(), 3.4, 5f, 2000L))!!
        assertTrue(e3.lat.isFinite() && e3.lng.isFinite())
        val moved = hypot((e3.lat - e1.lat) * mPerDeg(), (e3.lng - e1.lng) * mPerDeg())
        assertTrue("filter must still track after a NaN fix, moved ${moved}m", moved > 1.0)
    }

    @Test
    fun `rejected fixes while GPS is lost never blow up the reported accuracy`() {
        // G1 field finding (2026-08-15, live): parked+locked phone lost GPS;
        // only far-away cell fixes arrived, each gated as an outlier. The old
        // coast path never advanced lastTs, so dt grew every fix and Q ∝ dt⁴
        // exploded the covariance: accuracy went 1,117m → 152,277,180m in 16
        // minutes, and the server's >1000m garbage guard rejected EVERY ping
        // (live pin frozen). The coast path must degrade honestly: bounded
        // accuracy (last known position ± ~1km), never an absurd sigma.
        val f = LocationFilter()
        val lat = 6.5
        val lng = 3.4
        f.update(fix(lat, lng, 5f, 0L))
        val mPerDeg = mPerDeg()

        // A cell fix 500m off every ~3s for 10 minutes (parked phone, GPS
        // gone). Every fix is a physically impossible jump -> rejected.
        var ts = 0L
        var last: LocationFilter.Estimate? = null
        repeat(200) { i ->
            ts += 3000L
            last = f.update(fix(lat + 500.0 / mPerDeg, lng, 400f, ts))
        }
        val estimate = last ?: error("filter never produced an estimate")
        assertTrue("rejected fix must be flagged as outlier", estimate.outlier)
        assertTrue(
            "accuracy must stay bounded (honest ±~1km), got ${estimate.accuracyMeters}m",
            estimate.accuracyMeters < 1000.0,
        )
        // The position itself must NOT chase the 500m-off cell centroid.
        val drift = hypot((estimate.lat - lat) * mPerDeg, (estimate.lng - lng) * mPerDeg)
        assertTrue("coasted position must hold the last good fix, drifted ${drift}m", drift < 50.0)

        // And the filter must recover instantly when GPS returns.
        val recovered = f.update(fix(lat + 5.0 / mPerDeg, lng, 5f, ts + 1000L))!!
        assertFalse("good fix after GPS return must be accepted", recovered.outlier)
        val moved = hypot((recovered.lat - lat) * mPerDeg, (recovered.lng - lng) * mPerDeg)
        assertTrue("filter must snap back to the real fix, moved ${moved}m", moved < 30.0)
    }

    @Test
    fun `long time gap does not teleport the track`() {
        val f = LocationFilter()
        f.update(fix(6.5, 3.4, 5f, 0L))
        // 30 minutes later a fix 400m away (person drove) — dt is capped at
        // 120s so the implied-speed gate still evaluates sanely and the fix
        // is either accepted with a large innovation or gated; either way the
        // output must not be NaN or an absurd jump.
        val mPerDeg = mPerDeg()
        val e = f.update(fix(6.5 + 400.0 / mPerDeg, 3.4, 8f, 30L * 60 * 1000))!!
        assertTrue(e.lat.isFinite() && e.lng.isFinite())
        val moved = hypot((e.lat - 6.5) * mPerDeg, (e.lng - 3.4) * mPerDeg)
        assertTrue("no teleport on gap: moved ${moved}m", moved < 450.0)
    }
}
