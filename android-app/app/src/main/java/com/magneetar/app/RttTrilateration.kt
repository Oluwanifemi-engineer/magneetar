package com.magneetar.app

import kotlin.math.hypot
import kotlin.math.sqrt

/**
 * Pure 2D trilateration for Wi-Fi RTT (802.11mc) ranges — JVM-testable
 * (RttTrilaterationTest), deliberately free of Android types like the
 * Kalman filter.
 *
 * Solves for the (east, north) position that best fits N measured distances
 * to anchors with known positions. The linear least-squares start (squared-
 * distance differences vs anchor 0) is a closed-form first guess, then two
 * Gauss-Newton iterations refine it against the non-linear distance model —
 * the combination is robust to the ±1-2m noise of real RTT measurements.
 */
object RttTrilateration {

    /** One AP: its position (local ENU meters) and the measured distance to it. */
    data class Anchor(val eastM: Double, val northM: Double, val distanceM: Double)

    /**
     * Solve for the device position. Returns null when:
     *  - fewer than 3 anchors (a 2D fix needs >=3 ranges), or
     *  - the geometry is degenerate (collinear/coincident anchors → singular
     *    normal matrix — the caller falls back to its existing streams),
     *  - the solution is non-finite (OEM NaN glitches must never propagate).
     */
    fun solve(anchors: List<Anchor>): Pair<Double, Double>? {
        if (anchors.size < 3) return null
        val a0 = anchors[0]

        // ── Linear least squares ─────────────────────────────────────────
        // |p - a_i|^2 = d_i^2  minus the anchor-0 equation cancels the
        // p·p term, leaving 2 unknowns per anchor:
        //   2(x_i - x_0)·x + 2(y_i - y_0)·y =
        //       x_i² - x_0² + y_i² - y_0² - d_i² + d_0²
        // Normal equations (AᵀA p = Aᵀb), accumulated without materializing A.
        var a11 = 0.0; var a12 = 0.0; var a22 = 0.0
        var b1 = 0.0; var b2 = 0.0
        for (i in 1 until anchors.size) {
            val ai = anchors[i]
            val dx = 2.0 * (ai.eastM - a0.eastM)
            val dy = 2.0 * (ai.northM - a0.northM)
            val rhs = ai.eastM * ai.eastM - a0.eastM * a0.eastM +
                ai.northM * ai.northM - a0.northM * a0.northM -
                ai.distanceM * ai.distanceM + a0.distanceM * a0.distanceM
            a11 += dx * dx; a12 += dx * dy; a22 += dy * dy
            b1 += dx * rhs; b2 += dy * rhs
        }
        val det = a11 * a22 - a12 * a12
        if (det <= 1e-9) return null // collinear/coincident anchors
        var x = (b1 * a22 - b2 * a12) / det
        var y = (a11 * b2 - a12 * b1) / det

        // ── Gauss-Newton refinement (2 iterations) ───────────────────────
        // Minimize Σ (d_i - |p - a_i|)². JᵀJ is 2x2; step = (JᵀJ)⁻¹ Jᵀr.
        repeat(2) {
            var j11 = 0.0; var j12 = 0.0; var j22 = 0.0
            var r1 = 0.0; var r2 = 0.0
            for (a in anchors) {
                val ex = x - a.eastM
                val ey = y - a.northM
                val dist = hypot(ex, ey)
                if (dist < 1e-9) continue
                val res = a.distanceM - dist
                val ux = ex / dist
                val uy = ey / dist
                j11 += ux * ux; j12 += ux * uy; j22 += uy * uy
                r1 += ux * res; r2 += uy * res
            }
            val jdet = j11 * j22 - j12 * j12
            if (jdet <= 1e-9) return null
            x += (r1 * j22 - r2 * j12) / jdet
            y += (j11 * r2 - j12 * r1) / jdet
        }

        if (!x.isFinite() || !y.isFinite()) return null
        return x to y
    }

    /**
     * RMS of the per-anchor residuals (fitted distance vs measured), meters.
     * A tight residual means the anchors AGREE on the solution — the honest
     * accuracy proxy the caller reports (a lying AP position blows the
     * residual and the fix is rejected).
     */
    fun residualMeters(anchors: List<Anchor>, solution: Pair<Double, Double>): Double {
        if (anchors.isEmpty()) return Double.POSITIVE_INFINITY
        var sum = 0.0
        for (a in anchors) {
            val err = hypot(solution.first - a.eastM, solution.second - a.northM) - a.distanceM
            sum += err * err
        }
        return sqrt(sum / anchors.size)
    }
}
