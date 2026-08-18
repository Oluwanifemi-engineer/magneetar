package com.magneetar.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.hypot

/**
 * G1-17: Wi-Fi RTT trilateration solver tests.
 *
 * The solver turns N measured AP distances into a 2D position. It must
 * recover the true position from clean geometry, tolerate the ±1-2m noise of
 * real RTT measurements, and refuse degenerate geometry instead of emitting
 * a garbage fix (the caller falls back to its existing streams).
 */
class RttTrilaterationTest {

    private val eps = 0.5 // meters — solver tolerance for clean geometry

    private fun anchor(east: Double, north: Double, dist: Double) =
        RttTrilateration.Anchor(east, north, dist)

    private fun distTo(px: Double, py: Double, ax: Double, ay: Double) = hypot(px - ax, py - ay)

    @Test
    fun `recovers the true position from three clean anchors`() {
        // True device position: (10, 10).
        val anchors = listOf(
            anchor(0.0, 0.0, distTo(10.0, 10.0, 0.0, 0.0)),
            anchor(20.0, 0.0, distTo(10.0, 10.0, 20.0, 0.0)),
            anchor(0.0, 20.0, distTo(10.0, 10.0, 0.0, 20.0)),
        )
        val sol = RttTrilateration.solve(anchors)
        assertNotNull("clean triangle must solve", sol)
        assertEquals(10.0, sol!!.first, eps)
        assertEquals(10.0, sol.second, eps)
        assertTrue(RttTrilateration.residualMeters(anchors, sol) < 1e-6)
    }

    @Test
    fun `overdetermined four-anchor set with noise stays close to truth`() {
        // True position (5, 8); each distance perturbed by ±1.5m (RTT-class noise).
        val anchors = listOf(
            anchor(0.0, 0.0, distTo(5.0, 8.0, 0.0, 0.0) + 1.2),
            anchor(15.0, 0.0, distTo(5.0, 8.0, 15.0, 0.0) - 0.8),
            anchor(0.0, 15.0, distTo(5.0, 8.0, 0.0, 15.0) + 1.5),
            anchor(15.0, 15.0, distTo(5.0, 8.0, 15.0, 15.0) - 1.1),
        )
        val sol = RttTrilateration.solve(anchors)
        assertNotNull(sol)
        assertEquals(5.0, sol!!.first, 2.5)
        assertEquals(8.0, sol.second, 2.5)
        // RMS residual should be in the noise range, not meters of disagreement.
        assertTrue(RttTrilateration.residualMeters(anchors, sol) < 2.0)
    }

    @Test
    fun `refuses fewer than three anchors`() {
        assertNull(RttTrilateration.solve(listOf(anchor(0.0, 0.0, 5.0), anchor(10.0, 0.0, 5.0))))
        assertNull(RttTrilateration.solve(emptyList()))
    }

    @Test
    fun `refuses collinear degenerate geometry`() {
        // All anchors on one line — the normal matrix is singular.
        val anchors = listOf(
            anchor(0.0, 0.0, 10.0),
            anchor(10.0, 0.0, 10.0),
            anchor(20.0, 0.0, 10.0),
        )
        assertNull(RttTrilateration.solve(anchors))
    }

    @Test
    fun `refuses coincident anchors`() {
        val anchors = listOf(
            anchor(5.0, 5.0, 8.0),
            anchor(5.0, 5.0, 9.0),
            anchor(5.0, 5.0, 7.0),
        )
        assertNull(RttTrilateration.solve(anchors))
    }

    @Test
    fun `residual is zero for a perfect fit`() {
        val anchors = listOf(
            anchor(0.0, 0.0, distTo(3.0, 4.0, 0.0, 0.0)),
            anchor(6.0, 0.0, distTo(3.0, 4.0, 6.0, 0.0)),
            anchor(0.0, 8.0, distTo(3.0, 4.0, 0.0, 8.0)),
        )
        val sol = RttTrilateration.solve(anchors)!!
        assertEquals(0.0, RttTrilateration.residualMeters(anchors, sol), 1e-6)
    }
}
