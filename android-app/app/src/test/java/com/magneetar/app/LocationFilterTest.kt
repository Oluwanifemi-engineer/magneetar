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

    // ── G1-13: init guard + escape hatch (the Ile-Ife 55km-pin incident) ──

    @Test
    fun `poor first fix does not anchor - waits for a quality fix`() {
        // A cell centroid (300m "accuracy", actually 55km off) must NOT
        // anchor the filter. The old code absorbed any first fix, locking
        // the pin at the wrong spot forever.
        val f = LocationFilter()
        val bad = f.update(fix(7.7956, 4.1744, 300f, 1000L))
        assertNull("a 300m cell fix must not anchor the filter", bad)
        assertFalse(f.isInitialized)

        // The real GPS fix arrives 55km away — the filter must anchor THERE.
        val good = f.update(fix(7.5179, 4.5287, 8f, 4000L))!!
        assertEquals(7.5179, good.lat, 1e-6)
        assertEquals(4.5287, good.lng, 1e-6)
        assertTrue(good.accuracyMeters <= 10.0)
    }

    @Test
    fun `gps-denied device falls back to best candidate after init timeout`() {
        // If the device genuinely has no GPS (all fixes are 200-400m cell
        // fixes), the init guard must not wait forever: after the timeout it
        // anchors on the best candidate so the device still reports SOMETHING
        // (with honest degraded accuracy).
        val f = LocationFilter()
        var ts = 0L
        var last: LocationFilter.Estimate? = null
        // ~35s of poor fixes at the 3s cadence — past the 30s timeout.
        repeat(12) {
            ts += 3000L
            last = f.update(fix(6.5, 3.4, 250f, ts))
        }
        val estimate = last ?: error("filter must fall back after the init timeout")
        assertTrue(f.isInitialized)
        assertTrue(
            "fallback init must keep honest degraded accuracy, got ${estimate.accuracyMeters}",
            estimate.accuracyMeters > 100.0,
        )
        // And it must still recover instantly when GPS returns.
        val recovered = f.update(fix(6.5, 3.4, 5f, ts + 3000L))!!
        assertFalse(recovered.outlier)
        assertTrue(recovered.accuracyMeters < 30.0)
    }

    @Test
    fun `degraded filter re-anchors on a far good gps fix`() {
        // THE Ile-Ife incident, exactly: the filter is anchored at the wrong
        // spot (7.7956, 4.1744 — ~55km from truth) and has been coasting
        // (accuracy blown up to the 999m clamp) because every real fix was
        // rejected as an outlier. When GPS finally lands a fresh 8m fix at
        // the TRUE location, the escape hatch must snap the anchor there
        // instead of rejecting it a 10,000th time.
        val f = LocationFilter()
        val mPerDeg = mPerDeg()
        // Simulate the wrong anchor: a 5m-accurate cached fix from a
        // different place (this is how the incident started — fused handed
        // over a historical location that claimed high accuracy).
        f.update(fix(7.7956, 4.1744, 5f, 0L))
        // GPS-denied stretch: 500m-off cell fixes get rejected (167 m/s
        // implied), accuracy climbs to the 999m coast clamp (the 15,514-row
        // signature from the incident).
        var ts = 0L
        repeat(80) {
            ts += 3000L
            f.update(fix(7.7956 + 500.0 / mPerDeg, 4.1744, 400f, ts))
        }
        val coasted = f.lastEstimate()!!
        assertTrue("filter must be degraded before the escape fires (acc=${coasted.accuracyMeters})", coasted.accuracyMeters > 200.0)

        // A fresh GPS fix at the TRUE location (Ile-Ife), 55km away.
        val fixed = f.update(fix(7.5179, 4.5287, 8f, ts + 3000L))!!
        assertFalse("re-anchor must NOT be flagged as an outlier", fixed.outlier)
        val dist = hypot((fixed.lat - 7.5179) * mPerDeg, (fixed.lng - 4.5287) * mPerDeg)
        assertTrue(
            "filter must snap to the true location, off by ${dist}m",
            dist < 20.0,
        )
        assertTrue("accuracy must return to GPS scale, got ${fixed.accuracyMeters}m", fixed.accuracyMeters < 30.0)
    }

    @Test
    fun `confident filter re-anchors after two agreeing far gps fixes`() {
        // The wrong-but-confident anchor case: the filter anchored at 5m
        // accuracy on a fresh GPS-class fix that was itself wrong (a cached
        // fix from another place). It is "healthy" (accuracy ~5m), so the
        // degraded-only escape never fires — but the real GPS fixes keep
        // being rejected forever. Two CONSISTENT far GPS-class fixes must
        // prove the anchor is wrong and trigger the confirmation re-anchor.
        val f = LocationFilter()
        val mPerDeg = mPerDeg()
        // Wrong anchor, confidently: 5m accuracy, 55km from the true spot.
        f.update(fix(7.7956, 4.1744, 5f, 0L))
        var ts = 0L
        repeat(3) {
            ts += 3000L
            f.update(fix(7.7956 + 50.0 / mPerDeg, 4.1744, 5f, ts))
        }
        val before = f.lastEstimate()!!
        assertTrue("precondition: filter is confident", before.accuracyMeters < 20.0)

        // First far GPS-class fix at the TRUE location: rejected, remembered.
        val e1 = f.update(fix(7.5179, 4.5287, 8f, ts + 3000L))!!
        assertTrue("first far fix is still an outlier", e1.outlier)
        // Second far GPS-class fix, agreeing within 100m: re-anchor fires.
        val e2 = f.update(fix(7.5180, 4.5287, 8f, ts + 6000L))!!
        assertFalse("second agreeing fix must re-anchor, not reject", e2.outlier)
        val dist = hypot((e2.lat - 7.5180) * mPerDeg, (e2.lng - 4.5287) * mPerDeg)
        assertTrue("must snap to the true location, off by ${dist}m", dist < 20.0)
        assertTrue("accuracy back to GPS scale, got ${e2.accuracyMeters}m", e2.accuracyMeters < 30.0)
    }

    @Test
    fun `single far glitch fix never re-anchors a confident filter`() {
        // One far GPS-class fix (a glitch) while the filter is healthy must
        // be rejected and NOT confirmed by a subsequent fix back at the
        // anchor — the filter stays put.
        val f = LocationFilter()
        val mPerDeg = mPerDeg()
        f.update(fix(6.5, 3.4, 5f, 0L))
        var ts = 0L
        repeat(3) {
            ts += 3000L
            f.update(fix(6.5, 3.4, 5f, ts))
        }
        // A far glitch fix: rejected, becomes a candidate.
        val e1 = f.update(fix(6.5 + 10_000.0 / mPerDeg, 3.4, 5f, ts + 3000L))!!
        assertTrue("far glitch must be rejected", e1.outlier)
        // Next fix is back at the anchor — NOT agreeing with the glitch, so
        // it must be accepted normally and the candidate must clear.
        val e2 = f.update(fix(6.5 + 20.0 / mPerDeg, 3.4, 5f, ts + 6000L))!!
        val drift = hypot((e2.lat - 6.5) * mPerDeg, (e2.lng - 3.4) * mPerDeg)
        assertTrue("filter must hold the anchor, drifted ${drift}m", drift < 100.0)
        // And a later repeat of the same glitch position must NOT re-anchor
        // (the candidate was cleared on the accepted fix).
        val e3 = f.update(fix(6.5 + 10_000.0 / mPerDeg, 3.4, 5f, ts + 9000L))!!
        assertTrue("stale candidate must not confirm a later glitch", e3.outlier)
    }

    @Test
    fun `healthy filter still rejects a far fix without re-anchoring`() {
        // The escape hatch must NOT fire when the filter is healthy: a
        // confident filter (accuracy ~5m) receiving a far "good" fix is
        // seeing a glitch (or genuinely teleported — impossible), and must
        // keep rejecting it rather than snapping to it.
        val f = LocationFilter()
        val mPerDeg = mPerDeg()
        f.update(fix(6.5, 3.4, 5f, 0L))
        // A few steady fixes keep the filter confident.
        var ts = 0L
        repeat(5) {
            ts += 3000L
            f.update(fix(6.5, 3.4, 5f, ts))
        }
        val before = f.lastEstimate()!!
        assertTrue("precondition: filter must be confident (acc=${before.accuracyMeters})", before.accuracyMeters < 30.0)
        // A 10km-away "GPS" fix arrives. Healthy filter -> rejected, no snap.
        val e = f.update(fix(6.5 + 10_000.0 / mPerDeg, 3.4, 5f, ts + 3000L))!!
        assertTrue("far fix must still be gated as an outlier", e.outlier)
        val drift = hypot((e.lat - 6.5) * mPerDeg, (e.lng - 3.4) * mPerDeg)
        assertTrue("healthy filter must hold position, drifted ${drift}m", drift < 50.0)
    }

    @Test
    fun `coast path decays velocity - a gps-lost phone cannot drift 55km`() {
        // G1-15 regression (the Ile-Ife drift): when the phone was moving and
        // then lost GPS, the old coast path kept applying the last-learned
        // velocity forever — the live pin WALKED from 7.52 to 7.87 (55km)
        // over ~90 minutes of coasting. The coast path must bleed velocity
        // to zero so a GPS-denied parked phone holds the last good spot.
        val f = LocationFilter()
        val mPerDeg = mPerDeg()
        // Phone moving north at ~5 m/s, then GPS dies.
        var ts = 0L
        repeat(10) {
            ts += 1000L
            f.update(fix(6.5 + (5.0 / mPerDeg) * it, 3.4, 5f, ts))
        }
        val atLoss = f.lastEstimate()!!
        assertTrue("precondition: filter is moving", atLoss.speedMps > 3.0)

        // GPS lost: 60 rejected far cell fixes over 3 minutes of coasting.
        val anchorLat = atLoss.lat
        var ts2 = ts
        var last: LocationFilter.Estimate? = null
        repeat(60) {
            ts2 += 3000L
            last = f.update(fix(anchorLat + 500.0 / mPerDeg, 3.4, 400f, ts2))
        }
        val coasted = last ?: error("filter must keep producing coasted estimates")
        // The coasted position must NOT wander with the stale velocity: with
        // the decay, max additional drift after 60 steps is small (~5 m/s *
        // 3s * 0.3^k geometric sum ≈ 6m), not the 55km of the incident.
        val drift = (coasted.lat - anchorLat) * mPerDeg
        assertTrue(
            "coasted position must hold, drifted ${drift}m",
            kotlin.math.abs(drift) < 50.0,
        )
        // And it must still recover when GPS returns.
        val recovered = f.update(fix(anchorLat + 5.0 / mPerDeg, 3.4, 5f, ts2 + 1000L))!!
        assertFalse(recovered.outlier)
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
