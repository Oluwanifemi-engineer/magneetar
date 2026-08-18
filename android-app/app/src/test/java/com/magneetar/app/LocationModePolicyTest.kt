package com.magneetar.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * G1-17: location-mode nudge policy tests.
 *
 * Battery-saving (network-only) and GPS-only modes silently degrade the
 * tracker to 100-500m fixes (or no fixes indoors) while "location enabled"
 * still reads true — the old on/off check never caught them. The policy
 * decides which modes are degraded and how often the user is nudged.
 */
class LocationModePolicyTest {

    @Test
    fun `battery saving and gps-only are accuracy-degraded`() {
        assertTrue(LocationModePolicy.isAccuracyDegraded(LocationMode.BATTERY_SAVING))
        assertTrue(LocationModePolicy.isAccuracyDegraded(LocationMode.SENSORS_ONLY))
    }

    @Test
    fun `high accuracy and off are NOT nudge-worthy`() {
        // High accuracy is the goal; OFF means the tracker is (correctly)
        // signalling location_disabled on the heartbeat already — a separate,
        // stronger signal that must not be diluted by an accuracy nudge.
        assertFalse(LocationModePolicy.isAccuracyDegraded(LocationMode.HIGH_ACCURACY))
        assertFalse(LocationModePolicy.isAccuracyDegraded(LocationMode.OFF))
        assertFalse(LocationModePolicy.isAccuracyDegraded(LocationMode.UNKNOWN))
    }

    @Test
    fun `nudge is due after the throttle interval`() {
        val intervalMs = 24L * 60 * 60 * 1000
        assertTrue(LocationModePolicy.nudgeDue(0L, intervalMs, intervalMs))
        assertTrue(LocationModePolicy.nudgeDue(0L, intervalMs + 1L, intervalMs))
    }

    @Test
    fun `nudge is NOT due within the throttle interval`() {
        val intervalMs = 24L * 60 * 60 * 1000
        assertFalse(LocationModePolicy.nudgeDue(0L, intervalMs - 1L, intervalMs))
        assertFalse(LocationModePolicy.nudgeDue(100L, 100L + intervalMs / 2, intervalMs))
    }
}
