package com.magneetar.app

import android.content.Context
import android.provider.Settings

/**
 * System location mode — the value of Settings.Secure.LOCATION_MODE.
 * Labels are wire-friendly (sent verbatim on the heartbeat).
 */
enum class LocationMode(val label: String) {
    OFF("off"),
    /** GPS only — no WiFi/cell scanning, so no fixes indoors at all. */
    SENSORS_ONLY("gps_only"),
    /** Network only — no GPS, so 100-500m fixes even outdoors. */
    BATTERY_SAVING("battery_saving"),
    /** GPS + WiFi/cell scanning — the only mode that can deliver 3-15m fixes. */
    HIGH_ACCURACY("high_accuracy"),
    UNKNOWN("unknown"),
}

/**
 * G1-17: reads Settings.Secure.LOCATION_MODE so the app can tell "battery
 * saving" (network-only fixes, 100-500m) apart from "high accuracy"
 * (GPS + WiFi/cell scanning). The old code only knew location on/off — a
 * user in Battery-saving mode silently handed the tracker 100-500m fixes
 * all day, which is exactly the "accuracy not topnotch" complaint class.
 *
 * Pure wrapper over one Settings.Secure read; the nudge POLICY lives in
 * LocationModePolicy (pure JVM, unit-tested) so the decision logic is
 * testable without Robolectric.
 */
object LocationModeReader {
    // Settings.Secure.LOCATION_MODE constants (API 19+; minSdk is 24).
    private const val MODE_OFF = 0
    private const val MODE_SENSORS_ONLY = 1
    private const val MODE_BATTERY_SAVING = 2
    private const val MODE_HIGH_ACCURACY = 3

    fun current(context: Context): LocationMode {
        return try {
            when (Settings.Secure.getInt(context.contentResolver, Settings.Secure.LOCATION_MODE, MODE_OFF)) {
                MODE_OFF -> LocationMode.OFF
                MODE_SENSORS_ONLY -> LocationMode.SENSORS_ONLY
                MODE_BATTERY_SAVING -> LocationMode.BATTERY_SAVING
                MODE_HIGH_ACCURACY -> LocationMode.HIGH_ACCURACY
                else -> LocationMode.UNKNOWN
            }
        } catch (e: Exception) {
            // Content-resolver read failed (rare) — degrade to UNKNOWN,
            // never crash the heartbeat path.
            LocationMode.UNKNOWN
        }
    }

    /** True only in full high-accuracy mode (GPS + WiFi/cell scanning). */
    fun isHighAccuracy(context: Context): Boolean =
        current(context) == LocationMode.HIGH_ACCURACY
}
