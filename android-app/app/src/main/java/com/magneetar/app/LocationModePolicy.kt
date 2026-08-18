package com.magneetar.app

/**
 * Pure policy for the location-mode nudge (G1-17) — deliberately free of
 * Android types so the decision logic is JVM-unit-tested
 * (LocationModePolicyTest), mirroring LocationFilter/RawPostThrottle.
 */
object LocationModePolicy {

    /**
     * True when the mode silently degrades fix quality below what the
     * tracker can deliver. Battery-saving = network-only (100-500m, no GPS);
     * GPS-only = no WiFi/cell scanning (no fixes indoors at all). Both keep
     * "location enabled" true, so the old on/off check never caught them.
     */
    fun isAccuracyDegraded(mode: LocationMode): Boolean =
        mode == LocationMode.SENSORS_ONLY || mode == LocationMode.BATTERY_SAVING

    /**
     * The nudge is a notification — it must not nag. At most once per
     * [minIntervalMs] (default 24h, same cadence as the other one-a-day
     * nudges in TrackingService).
     */
    fun nudgeDue(lastNotifiedMs: Long, nowMs: Long, minIntervalMs: Long = 24L * 60 * 60 * 1000): Boolean =
        nowMs - lastNotifiedMs >= minIntervalMs
}
