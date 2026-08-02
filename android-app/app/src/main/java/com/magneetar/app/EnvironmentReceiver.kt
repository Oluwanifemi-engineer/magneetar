package com.magneetar.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Environment-triggered restart receiver.
 *
 * OEM battery killers (especially on Transsion/Xiaomi/Huawei) pause background
 * apps at rest and only release them on events the system can't defer: power
 * plugged in, network regained, time changed, or the user unlocking the phone.
 * Firing a service restart on those events closes the gap between "the OS
 * paused the app" and "the owner notices the device went offline".
 *
 * This is a best-effort companion to the AlarmManager watchdog, WorkManager
 * health check, and the dual foreground services — not a replacement.
 */
class EnvironmentReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "MagneetarEnv"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        val relevant = action == Intent.ACTION_POWER_CONNECTED ||
            action == Intent.ACTION_POWER_DISCONNECTED ||
            action == Intent.ACTION_BATTERY_LOW ||
            action == Intent.ACTION_TIME_CHANGED ||
            action == Intent.ACTION_TIMEZONE_CHANGED ||
            action == ConnectivityManager.CONNECTIVITY_ACTION ||
            action == Intent.ACTION_USER_PRESENT
        if (!relevant) return

        if (TrackingService.isRunning) {
            // Still alive — just keep the watchdog armed.
            WatchdogReceiver.scheduleWatchdog(context)
            return
        }

        // Only restart on connectivity events when the network is actually
        // back — battery/display events can fire before it is.
        if (action == ConnectivityManager.CONNECTIVITY_ACTION) {
            val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            val active = cm?.activeNetworkInfo
            if (active == null || !active.isConnectedOrConnecting) return
        }

        Log.i(TAG, "Restarting services after $action")
        try {
            ContextCompat.startForegroundService(context, Intent(context, TrackingService::class.java))
            ContextCompat.startForegroundService(context, Intent(context, PersistenceService::class.java))
            WatchdogReceiver.scheduleWatchdog(context)
            HealthCheckWorker.schedule(context)
        } catch (e: Exception) {
            Log.e(TAG, "Restart failed: ${e.message}")
        }
    }
}
