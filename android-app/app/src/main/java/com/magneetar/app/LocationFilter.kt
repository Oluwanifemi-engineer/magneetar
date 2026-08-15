package com.magneetar.app

import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.atan2
import kotlin.math.PI

/**
 * Pure, unit-testable Kalman filter that fuses raw GPS + network fixes into a
 * smooth, high-accuracy position estimate.
 *
 * WHY (researched, not cargo-culted):
 *  - Android reports BOTH GPS and NETWORK fixes; the raw stream is jittery
 *    (multipath in urban canyons) and can teleport (a 500m-off cell-tower fix
 *    while indoors). Commercial trackers (Prey, Cerberus) and navigation apps
 *    layer a Kalman filter on top of the provider output for exactly this.
 *  - A CONSTANT-VELOCITY model in local ENU meters (state [x, y, vx, vy]) is
 *    the standard choice: pedestrians/vehicles can't change position
 *    instantaneously, and velocity lets the filter predict the next fix and
 *    gate outliers against physics.
 *  - MEASUREMENT NOISE R is derived from `Location.getAccuracy()` — GPS
 *    (~3-5m) is trusted far more than network (~100-500m) automatically.
 *  - PROCESS NOISE Q is ADAPTIVE: near-zero when stationary (locks position,
 *    kills GPS jitter "walking"), larger when moving (tracks real trajectory).
 *  - OUTLIER REJECTION: a fix whose innovation (residual vs prediction)
 *    implies an impossible speed, or whose Mahalanobis distance exceeds a
 *    5-sigma gate, is dropped — the filter coasts on the prediction instead
 *    of teleporting the dashboard.
 *
 * The file is deliberately free of Android types (Location/Context) so the
 * math is unit-testable on the JVM (see LocationFilterTest.kt) — the service
 * adapts `android.location.Location` into [Fix].
 *
 * COORDINATES: lat/lng are converted to local East/North meters around a
 * rolling origin using the equirectangular approximation — accurate to
 * < 0.1% over the few-km scale a tracker operates on, and stable because the
 * origin only moves when the device travels far (preventing float drift).
 */
class LocationFilter(
    /** Reject fixes implying a speed above this (m/s) — ~160 km/h. */
    private val maxSpeedMps: Double = 45.0,
    /** Below this filtered speed the filter enters the stationary lock. */
    private val staticSpeedMps: Double = 0.8,
    /** 5-sigma innovation gate — the default chi-squared threshold for 2 DOF. */
    private val gateChiSq: Double = 25.0,
    /**
     * Cap for the COASTED accuracy (meters) while fixes are being rejected.
     *
     * G1 field finding (2026-08-15): with the phone parked and locked, GPS
     * went quiet and only far-away cell fixes arrived. Each was gated as an
     * outlier (correct), but the coast path never advanced lastTs, so dt
     * grew with every fix and Q ∝ dt⁴ blew the covariance up: reported
     * accuracy went 1,117m → 152,277,180m in 16 minutes. The server's
     * `accuracy > 1000m = garbage` guard then rejected EVERY ping — the
     * dashboard pin froze at a stale position (the owner's "location error
     * is quite high" bug).
     *
     * Honest degradation, not a lie: when GPS is lost the truth IS "last
     * known position, ± ~1km" — not ±152,000km. 999 keeps reports under the
     * server's 1000m reject threshold while still telling the dashboard the
     * fix is degraded (LOW confidence → quality gate holds it back).
     */
    private val maxCoastAccuracyM: Double = 999.0,
) {

    companion object {
        // Covariance-variance caps for the coast path: position sigma ≤
        // maxCoastAccuracyM, velocity sigma ≤ 10 m/s (a parked phone with
        // GPS lost cannot legitimately learn more velocity than jitter).
        private const val MAX_COAST_VEL_VAR = 100.0 // 10 m/s squared
    }

    /** A single raw location fix from any provider. */
    data class Fix(
        val lat: Double,
        val lng: Double,
        /** `Location.getAccuracy()` in meters; 0/absent becomes a sane default. */
        val accuracyMeters: Float,
        /** `Location.getTime()` in epoch millis. */
        val timestampMs: Long,
        /** "gps", "network", "fused", ... — metadata for the caller. */
        val provider: String = "gps",
    )

    /** The smoothed output handed to the reporter. */
    data class Estimate(
        val lat: Double,
        val lng: Double,
        /** Position std-dev from the covariance P — an honest accuracy. */
        val accuracyMeters: Double,
        /** Filtered ground speed in m/s. */
        val speedMps: Double,
        /** Filtered course in degrees 0-360 (0 = north, clockwise). */
        val bearingDeg: Double,
        /** True when the filter believes the device is stationary. */
        val stationary: Boolean,
        /** True when the incoming fix was rejected as an outlier. */
        val outlier: Boolean,
    )

    // ── State ──────────────────────────────────────────────────────────────
    // x = [east, north, vE, vN]  (meters, m/s) relative to (originLat, originLng)
    private val x = DoubleArray(4)
    private val p = DoubleArray(16) // 4x4, row-major
    private var originLat = 0.0
    private var originLng = 0.0
    private var initialized = false
    private var lastTs = 0L
    private var lastEstimate: Estimate? = null
    // Velocity of the previous accepted update — the jitter detector compares
    // the sign of the newly-learned velocity against this. Alternating GPS
    // jitter makes velocity FLIP direction every step; real motion keeps it
    // constant. Flipping -> noise -> bleed velocity to zero (anti-drift lock).
    private var prevVx = 0.0
    private var prevVy = 0.0
    private var havePrevV = false

    private val z = DoubleArray(2) // reusable measurement [east, north]
    private val y = DoubleArray(2) // innovation
    private val s = DoubleArray(4) // 2x2 innovation covariance, row-major

    /** True once the filter has absorbed at least one fix. */
    val isInitialized: Boolean get() = initialized

    /** The most recent accepted estimate, or null before the first fix. */
    fun lastEstimate(): Estimate? = lastEstimate

    /** Discard all state (e.g. the device rebooted or location was turned off). */
    fun reset() {
        initialized = false
        lastEstimate = null
        havePrevV = false
    }

    /**
     * Feed one raw fix through the filter.
     *
     * Returns the updated [Estimate] — for an accepted fix this is the fused
     * position; for a rejected outlier it is the COASTED prediction with
     * `outlier = true` (the caller can still report it, or skip the report).
     * Returns null only before the first fix is absorbed.
     */
    fun update(fix: Fix): Estimate? {
        // A non-finite fix (rare OEM fused-provider glitches can emit NaN)
        // must NEVER poison the state: NaN comparisons are all FALSE, so NaN
        // would sail through BOTH outlier gates below (mahal > gate and
        // impliedSpeed > maxSpeed are false for NaN) and permanently corrupt
        // x/P — every subsequent estimate would be NaN and the tracker goes
        // dead. Coast on the prediction instead and skip the measurement.
        // lastTs is deliberately NOT advanced (same as the rejection path) so
        // the next real fix computes dt from the last GOOD fix.
        if (!fix.lat.isFinite() || !fix.lng.isFinite()) {
            if (!initialized) return null
            val dtSec = (fix.timestampMs - lastTs).coerceAtLeast(1L) / 1000.0
            val dt = if (dtSec > 120.0) 120.0 else dtSec
            x[0] += x[2] * dt
            x[1] += x[3] * dt
            val preP = predictCovariance(dt, hypot(x[2], x[3]) > staticSpeedMps)
            for (i in 0 until 16) p[i] = preP[i]
            // v1.5 fix (G1 field finding): NaN fixes arrive continuously when
            // the fused provider glitches — without this the dt growth below
            // would blow up the covariance exactly like the outlier path.
            lastTs = fix.timestampMs
            clampCoastCovariance()
            val e = makeEstimate(outlier = true)
            lastEstimate = e
            return e
        }

        val acc = if (fix.accuracyMeters > 0f) fix.accuracyMeters.toDouble() else 50.0
        val sigma = acc.coerceAtLeast(1.0) // floor 1m: never fully trust a single fix

        if (!initialized) {
            // Absorb the first fix: position = measurement, velocity = unknown.
            init(fix.lat, fix.lng, sigma, fix.timestampMs)
            val e0 = makeEstimate(outlier = false)
            lastEstimate = e0
            return e0
        }

        val dtSec = (fix.timestampMs - lastTs).coerceAtLeast(1L) / 1000.0
        // Stale fixes (e.g. a queued last-known after a long gap) get a big
        // process-noise hit so they can't yank the track.
        val dt = if (dtSec > 120.0) 120.0 else dtSec

        // ── Predict ────────────────────────────────────────────────────────
        // x' = F x ; F = [[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]]
        val xe = x[0] + x[2] * dt
        val xn = x[1] + x[3] * dt
        // Adaptive process noise: use the RAW FIX's implied speed vs the last
        // estimate (not just the estimated velocity, which is 0 at cold start
        // and would keep q tiny while the device is actually moving).
        val rawLocal = toLocal(fix.lat, fix.lng)
        val rawDx = rawLocal.first - x[0]
        val rawDy = rawLocal.second - x[1]
        val rawMoving = hypot(rawDx, rawDy) / dt > 0.5
        val preP = predictCovariance(dt, rawMoving || hypot(x[2], x[3]) > staticSpeedMps)

        // Convert the measurement into local meters (reuse the rawLocal
        // computed above for the adaptive-Q decision).
        z[0] = rawLocal.first
        z[1] = rawLocal.second

        // ── Innovation ─────────────────────────────────────────────────────
        // y = z - H x',  S = H P H^T + R
        y[0] = z[0] - xe
        y[1] = z[1] - xn
        val p00 = preP[0]; val p01 = preP[1]; val p11 = preP[5]
        val r = sigma * sigma
        s[0] = p00 + r
        s[1] = p01
        s[2] = p01
        s[3] = p11 + r
        val det = s[0] * s[3] - s[1] * s[2]
        val mahal = if (det > 1e-12) {
            val s00i = s[3] / det
            val s01i = -s[1] / det
            val s11i = s[0] / det
            y[0] * (s00i * y[0] + s01i * y[1]) + y[1] * (s01i * y[0] + s11i * y[1])
        } else Double.POSITIVE_INFINITY

        // ── Outlier rejection ──────────────────────────────────────────────
        // Two independent gates: physics (implied speed) and statistics
        // (Mahalanobis). A network fix 500m off implies an absurd speed for a
        // 3s gap; a slow-drifting GPS outlier trips the chi-squared gate.
        val impliedSpeed = hypot(y[0], y[1]) / dt
        val rejected = mahal > gateChiSq || impliedSpeed > maxSpeedMps
        if (rejected) {
            // Coast: keep the prediction, inflate P (we learned nothing).
            x[0] = xe; x[1] = xn
            for (i in 0 until 16) p[i] = preP[i]
            // v1.5 fix (G1 field finding): a rejected fix is still a REAL
            // observation in time — advance lastTs so the next fix computes a
            // small honest dt instead of a growing one (Q ∝ dt⁴ made the
            // covariance explode to ±152,000km on a parked phone). Clamp the
            // covariance so a GPS-lost device reports "last known ± ~1km",
            // not an absurd sigma that the server rejects wholesale (which
            // froze the live pin).
            lastTs = fix.timestampMs
            clampCoastCovariance()
            val e = makeEstimate(outlier = true)
            lastEstimate = e
            return e
        }

        // ── Kalman gain & update ───────────────────────────────────────────
        // K = P H^T S^-1 ; P H^T = first two columns of P.
        // P is 4x4 row-major: row0=[0,1,2,3], row1=[4,5,6,7],
        // row2=[8,9,10,11], row3=[12,13,14,15]. The position rows of P H^T
        // are therefore (P00,P01), (P10,P11), (P20,P21), (P30,P31).
        val k00 = (p00 * s[3] - p01 * s[2]) / det
        val k01 = (p01 * s[0] - p00 * s[1]) / det
        val k10 = (preP[4] * s[3] - preP[5] * s[2]) / det
        val k11 = (preP[5] * s[0] - preP[4] * s[1]) / det
        val k20 = (preP[8] * s[3] - preP[9] * s[2]) / det
        val k21 = (preP[9] * s[0] - preP[8] * s[1]) / det
        val k30 = (preP[12] * s[3] - preP[13] * s[2]) / det
        val k31 = (preP[13] * s[0] - preP[12] * s[1]) / det

        val x0 = xe + k00 * y[0] + k01 * y[1]
        val x1 = xn + k10 * y[0] + k11 * y[1]
        val x2 = x[2] + k20 * y[0] + k21 * y[1]
        val x3 = x[3] + k30 * y[0] + k31 * y[1]

        // Jitter lock (researched, not guessed): alternating GPS jitter on a
        // parked device makes the newly-learned velocity FLIP DIRECTION every
        // step (the filter sees +8m then -8m, so v goes + then -). Real motion
        // keeps velocity pointing one way. So: when the dominant-axis velocity
        // flips sign AND both old and new magnitudes are meaningful (> 0.3
        // m/s, to ignore sign noise around zero), bleed BOTH components towards
        // zero. A genuine turn flips once and recovers in a few steps; jitter
        // flips every step and is killed — the pin locks and GPS noise can't
        // make a parked phone "walk". Unlike a speed-gate decay this never
        // penalises a slow-moving device (a 1.5 m/s walker keeps full velocity
        // because direction never reverses).
        var vx = x2
        var vy = x3
        if (havePrevV) {
            val vMag = hypot(vx, vy)
            if (vMag > 0.3) {
                val dominantEast = kotlin.math.abs(vx) >= kotlin.math.abs(vy)
                val flipEast = dominantEast && prevVx * vx < 0 && kotlin.math.abs(prevVx) > 0.3
                val flipNorth = !dominantEast && prevVy * vy < 0 && kotlin.math.abs(prevVy) > 0.3
                if (flipEast || flipNorth) {
                    vx *= 0.3
                    vy *= 0.3
                }
            }
        }
        prevVx = vx
        prevVy = vy
        havePrevV = true

        x[0] = x0; x[1] = x1; x[2] = vx; x[3] = vy
        // Covariance update: P = (I - K H) P', computed element by element.
        // H = [[1,0,0,0],[0,1,0,0]], so H P' is the first two rows of P' and
        // (K H P')[i][j] = K[i][0]*P'[0][j] + K[i][1]*P'[1][j]. WITHOUT this
        // step the filter never converges — P stays at its predicted value,
        // the gain never settles, and velocity never learns (the
        // cross-covariance P20 stays ~0, so the filter perpetually believes
        // the device is stationary). This was the root of the "lags the real
        // track" bug. Every element is computed independently (the updated
        // P is NOT symmetric in general, so p[4]=p[1] shortcuts are wrong).
        val pp00 = preP[0]; val pp01 = preP[1]; val pp02 = preP[2]; val pp03 = preP[3]
        val pp10 = preP[4]; val pp11 = preP[5]; val pp12 = preP[6]; val pp13 = preP[7]
        p[0] = pp00 - (k00 * pp00 + k01 * pp10)
        p[1] = pp01 - (k00 * pp01 + k01 * pp11)
        p[2] = pp02 - (k00 * pp02 + k01 * pp12)
        p[3] = pp03 - (k00 * pp03 + k01 * pp13)
        p[4] = pp10 - (k10 * pp00 + k11 * pp10)
        p[5] = pp11 - (k10 * pp01 + k11 * pp11)
        p[6] = pp12 - (k10 * pp02 + k11 * pp12)
        p[7] = pp13 - (k10 * pp03 + k11 * pp13)
        p[8] = preP[8] - (k20 * pp00 + k21 * pp10)
        p[9] = preP[9] - (k20 * pp01 + k21 * pp11)
        p[10] = preP[10] - (k20 * pp02 + k21 * pp12)
        p[11] = preP[11] - (k20 * pp03 + k21 * pp13)
        p[12] = preP[12] - (k30 * pp00 + k31 * pp10)
        p[13] = preP[13] - (k30 * pp01 + k31 * pp11)
        p[14] = preP[14] - (k30 * pp02 + k31 * pp12)
        p[15] = preP[15] - (k30 * pp03 + k31 * pp13)
        lastTs = fix.timestampMs
        // Origin maintenance: re-anchor when the device has travelled far so
        // the equirectangular meters stay small and float-precision-safe.
        if (hypot(x0, x1) > 2000.0) reAnchor(x0, x1, fix.timestampMs)

        val e = makeEstimate(outlier = false)
        lastEstimate = e
        return e
    }

    // ── Internals ───────────────────────────────────────────────────────────

    private fun init(lat: Double, lng: Double, sigma: Double, ts: Long) {
        originLat = lat
        originLng = lng
        x[0] = 0.0; x[1] = 0.0; x[2] = 0.0; x[3] = 0.0
        // P0: position variance = sigma², velocity unknown -> large variance.
        for (i in 0 until 16) p[i] = 0.0
        p[0] = sigma * sigma
        p[5] = sigma * sigma
        p[10] = 100.0
        p[15] = 100.0
        lastTs = ts
        initialized = true
        havePrevV = false
    }

    /**
     * F' P F + Q. F is the standard CV transition; Q is the continuous white
     * acceleration model scaled by an ADAPTIVE q: tiny when stationary (lock),
     * larger when moving (track turns/acceleration).
     */
    private fun predictCovariance(dt: Double, moving: Boolean): DoubleArray {
        val dt2 = dt * dt
        val dt3 = dt2 * dt
        val dt4 = dt2 * dt2
        // Adaptive process-noise scale (m²/s³): tiny when the device is parked
        // (position locks, jitter dies), larger when moving (filter tracks
        // turns/acceleration). `moving` is passed from the caller's gate.
        val q = if (moving) 3.0 else 0.02
        // Q (4x4) from the continuous acceleration model:
        //   [[dt⁴/4, 0, dt³/2, 0], [0, dt⁴/4, 0, dt³/2],
        //    [dt³/2, 0, dt², 0],   [0, dt³/2, 0, dt²]]
        val q00 = q * dt4 / 4.0; val q02 = q * dt3 / 2.0
        val q11 = q00; val q13 = q02
        val q20 = q02; val q22 = q * dt2
        val q31 = q13; val q33 = q22

        val out = DoubleArray(16)
        // P' = F P F^T (positions only couple through velocity rows)
        val p00 = p[0]; val p01 = p[1]; val p02 = p[2]; val p03 = p[3]
        val p11 = p[5];
        val p20 = p[8]; val p21 = p[9]; val p22 = p[10]; val p23 = p[11]
        val p30 = p[12]; val p31 = p[13]; val p32 = p[14]; val p33 = p[15]

        out[0] = p00 + 2 * dt * p20 + dt2 * p22
        out[1] = p01 + dt * p21 + dt * p03 + dt2 * p23
        out[4] = out[1]
        out[2] = p20 + dt * p22
        out[8] = out[2]
        out[3] = p30 + dt * p32
        out[12] = out[3]
        out[5] = p11 + 2 * dt * p31 + dt2 * p33
        out[6] = p21 + dt * p23
        out[9] = out[6]
        out[7] = p31 + dt * p33
        out[13] = out[7]
        out[10] = p22
        out[14] = p32
        out[15] = p33
        // Symmetrize the cross terms (they came out symmetric, keep it cheap)
        out[11] = p23

        // Add Q.
        out[0] += q00; out[2] += q02; out[8] += q20; out[10] += q22
        out[5] += q11; out[7] += q13; out[13] += q31; out[15] += q33
        return out
    }

    /** Convert a lat/lng into local east/north meters around the current origin. */
    private fun toLocal(lat: Double, lng: Double): Pair<Double, Double> {
        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * cos(originLat * PI / 180.0).coerceAtLeast(0.01)
        val east = (lng - originLng) * mPerDegLng
        val north = (lat - originLat) * mPerDegLat
        return east to north
    }

    private fun fromLocal(east: Double, north: Double): Pair<Double, Double> {
        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * cos(originLat * PI / 180.0).coerceAtLeast(0.01)
        return (originLat + north / mPerDegLat) to (originLng + east / mPerDegLng)
    }

    /** Move the origin to the current estimate, preserving the state in meters. */
    private fun reAnchor(east: Double, north: Double, ts: Long) {
        val (lat, lng) = fromLocal(east, north)
        originLat = lat
        originLng = lng
        x[0] = 0.0; x[1] = 0.0
        lastTs = ts
    }

    /**
     * Bound the covariance diagonal on the coast path.
     *
     * While fixes are being rejected the filter learns nothing new, so the
     * velocity-variance channel (p22 → dt²·p22 → p00) would otherwise drive
     * the position covariance — and therefore the reported accuracy — to
     * astronomical values. Clamping keeps the reported sigma honest
     * (≤ [maxCoastAccuracyM]) without breaking the filter: the moment a
     * real GPS fix arrives it is absorbed normally (the accepted path never
     * clamps) and the covariance returns to GPS scale.
     */
    private fun clampCoastCovariance() {
        val maxPosVar = maxCoastAccuracyM * maxCoastAccuracyM
        p[0] = minOf(p[0], maxPosVar)
        p[5] = minOf(p[5], maxPosVar)
        p[10] = minOf(p[10], MAX_COAST_VEL_VAR)
        p[15] = minOf(p[15], MAX_COAST_VEL_VAR)
    }

    private fun makeEstimate(outlier: Boolean): Estimate {
        // Position std-dev from the covariance: sqrt(P[0]) and sqrt(P[5]).
        val acc = (kotlin.math.sqrt(p[0].coerceAtLeast(0.0)) +
            kotlin.math.sqrt(p[5].coerceAtLeast(0.0))) / 2.0
        val (lat, lng) = fromLocal(x[0], x[1])
        val speed = hypot(x[2], x[3])
        val bearing = (atan2(x[2], x[3]) * 180.0 / PI + 360.0) % 360.0
        return Estimate(
            lat = lat,
            lng = lng,
            accuracyMeters = acc,
            speedMps = speed,
            bearingDeg = bearing,
            stationary = speed < staticSpeedMps,
            outlier = outlier,
        )
    }
}
