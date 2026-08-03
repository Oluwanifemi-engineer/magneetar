package com.magneetar.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Enhanced boot receiver — restarts all services after device reboot.
 *
 * On Chinese OEMs, additional steps are needed to survive aggressive
 * power management after boot (e.g., delaying start slightly to let
 * the system initialize fully).
 */
class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "MagneetarBoot"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == "android.intent.action.QUICKBOOT_POWERON" ||
            intent.action == "android.intent.action.LOCKED_BOOT_COMPLETED"
        ) {
            Log.i(TAG, "Boot detected (${intent.action}). Starting services...")

            // Record boot time for OEM auto-start detection
            context.getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
                .putLong("last_boot_restart", System.currentTimeMillis())
                .apply()

            // Use a short delay on Chinese OEMs to let system services initialize
            if (OEMUtils.isChineseOEM()) {
                Log.d(TAG, "Chinese OEM detected — delaying service start by 10s")
                @Suppress("DEPRECATION")
                android.os.Handler().postDelayed({
                    startServices(context)
                }, 10_000)
            } else {
                startServices(context)
            }
        }
    }

    private fun startServices(context: Context) {
        try {
            // Start the main tracking service
            val trackingIntent = Intent(context, TrackingService::class.java)
            ContextCompat.startForegroundService(context, trackingIntent)

            // Start the dual-service persistence layer
            val persistenceIntent = Intent(context, PersistenceService::class.java)
            ContextCompat.startForegroundService(context, persistenceIntent)

            // Re-arm remote capture if it was armed before the reboot.
            // A camera|microphone FGS cannot be started from BOOT_COMPLETED on
            // Android 15+, so post the tap-to-re-arm notification — the tap is
            // a user action that grants the background-start exemption.
            if (MediaCaptureService.wasArmedBeforeRestart(context)) {
                MediaCaptureService.postRearmNotification(context)
            }

            Log.i(TAG, "Services started successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start services: ${e.message}")

            // Retry after a delay if first attempt failed
            @Suppress("DEPRECATION")
            android.os.Handler().postDelayed({
                try {
                    val trackingIntent = Intent(context, TrackingService::class.java)
                    ContextCompat.startForegroundService(context, trackingIntent)
                } catch (_: Exception) {}
            }, 30_000)
        }
    }
}
