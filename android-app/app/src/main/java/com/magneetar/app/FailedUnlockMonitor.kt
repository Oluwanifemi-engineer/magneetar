package com.magneetar.app

import android.app.KeyguardManager
import android.app.admin.DevicePolicyManager
import android.content.Context

/**
 * Failed-unlock ("theftie") detection glue (COMPETITOR_AUDIT P1 #4).
 *
 * Reports the number of failed unlock attempts since the last successful
 * unlock on every telemetry ping and heartbeat. The server reacts: Sentinel
 * scores it (+20) and, once it crosses MT_FAILED_UNLOCK_THRESHOLD (default
 * 5), queues an automatic front-photo + audio evidence capture and fires an
 * always-deliver alert — no manual action needed.
 *
 * Two sources, best-effort, both permission-free:
 *
 *  1. DPC authoritative count: [DevicePolicyManager.getCurrentFailedPasswordAttempts]
 *     returns the exact OS count and is zero-reset by the OS on a successful
 *     unlock. It only works when the app is the **device owner or profile
 *     owner** (per Android docs) — which the app's uninstall-protection
 *     path provisions (device owner via scripts/enable-uninstall-protection.sh).
 *     Any failure (SecurityException on plain builds, absent policy service)
 *     falls through to the heuristic.
 *  2. Keyguard heuristic: [FailedUnlockTracker] counts screen-on sessions
 *     that end without a successful unlock, and resets on
 *     ACTION_USER_PRESENT. Works on every build including the Play flavor.
 *
 * The DPC count is preferred when readable because it is exact; the
 * heuristic backs it up. Repeats (a device pinging from a still-locked
 * screen) are deduped server-side.
 *
 * Hot-path discipline (TrackingService's own convention — see the
 * SimChangeMonitor comment): the 3s location ping must stay cheap, so
 * [currentCount] only reads the persisted state (a prefs read). The DPC
 * binder call happens in [refreshFromDpc], invoked from the 60s heartbeat —
 * the count the telemetry path reports is at most one heartbeat old, which
 * is fine for a threshold-gated reaction.
 */
object FailedUnlockMonitor {

    private const val PREFS = "mt_failed_unlock"
    private const val KEY_STATE = "state"

    private fun tracker(context: Context): FailedUnlockTracker =
        FailedUnlockTracker.persistent(context, PREFS, KEY_STATE)

    /**
     * True when this device has a SECURE lock screen (PIN/pattern/password).
     *
     * G1-8: this must NOT be `isKeyguardLocked`. The SCREEN_ON broadcast
     * arrives while the keyguard is still transitioning in — on many devices
     * (Samsung in particular) the instantaneous check reads false and the
     * locked session never opens, so the counter stays 0 forever (found in
     * the real-theft-signal field test: broadcasts received, count never
     * incremented). On a device with a secure lock screen, a screen-on always
     * means the keyguard is showing (screen-off locks the device), so
     * `isKeyguardSecure` is the reliable gate. Non-secure devices have no
     * keyguard to fail against — never open a session there.
     */
    private fun isLocked(context: Context): Boolean {
        return try {
            val km = context.getSystemService(Context.KEYGUARD_SERVICE) as? KeyguardManager
            km?.isKeyguardSecure ?: false
        } catch (e: Exception) {
            false
        }
    }

    /** Exact failed-attempt count from the DPC, or null when unavailable. */
    private fun dpcCount(context: Context): Int? {
        return try {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
                ?: return null
            // Same admin identity as the rest of the app (HomeActivity /
            // PermissionsActivity / TrackingService all use AdminReceiver).
            // getCurrentFailedPasswordAttempts itself requires device/profile
            // owner; isAdminActive just gates the call cheaply.
            val comp = android.content.ComponentName(context, AdminReceiver::class.java)
            if (dpm.isAdminActive(comp)) {
                dpm.getCurrentFailedPasswordAttempts()
            } else {
                null
            }
        } catch (e: Exception) {
            // SecurityException on non-owner builds, or any DPC quirk — fall
            // back to the heuristic, never crash the receiver.
            null
        }
    }

    /**
     * The count to report on the TELEMETRY path (3s hot path): a cheap prefs
     * read of the persisted state. The DPC exact count lands here via
     * [refreshFromDpc] on the heartbeat; between heartbeats the receiver-fed
     * heuristic state is what is reported.
     */
    fun currentCount(context: Context): Int = tracker(context).count()

    /**
     * Refresh the persisted count from the DPC's authoritative source.
     * Called from the 60s heartbeat ONLY (a binder call — never on the 3s
     * location hot path). When the DPC is unavailable (plain installs),
     * re-recording null is a no-op and the heuristic count survives.
     */
    fun refreshFromDpc(context: Context) {
        tracker(context).record(dpcCount(context))
    }

    /** Screen turned on (keyguard still locked → opens a session). */
    fun onScreenOn(context: Context) {
        tracker(context).onScreenOn(isLocked(context))
    }

    /** Screen turned off — a still-locked session counts as one failure. */
    fun onScreenOff(context: Context) {
        tracker(context).onScreenOff()
    }

    /** Successful unlock — resets the counter. */
    fun onUserPresent(context: Context) {
        tracker(context).onUserPresent()
    }

    /** Fresh install / post-registration reset so a new device never alerts. */
    fun baseline(context: Context) {
        tracker(context).onUserPresent()
    }
}
