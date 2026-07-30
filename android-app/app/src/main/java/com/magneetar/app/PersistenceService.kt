package com.magneetar.app

import android.app.*
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*

/**
 * Dual-service redundancy layer.
 *
 * This is a second foreground service that runs alongside TrackingService.
 * Its sole purpose is to:
 * 1. Monitor TrackingService health via periodic checks
 * 2. Restart TrackingService if it dies
 * 3. Hold a WakeLock to prevent deep sleep from killing everything
 * 4. Maintain a low-profile notification
 *
 * Chinese OEMs often kill individual services but rarely kill TWO services
 * simultaneously, especially when they run different foreground service types.
 *
 * TrackingService uses foregroundServiceType="location"
 * PersistenceService uses foregroundServiceType="dataSync"
 */
class PersistenceService : Service() {

    companion object {
        private const val TAG = "MagneetarPersistence"
        private const val CHANNEL_ID = "mt_persistence"
        private const val NOTIF_ID = 2
        private const val CHECK_INTERVAL_MS = 60_000L // Check every minute

        /** Runtime flag — true when service is running. */
        @Volatile
        var isRunning: Boolean = false
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var wakeLock: PowerManager.WakeLock? = null

    private fun isActive(): Boolean = scope.isActive

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Persistence service starting...")
        isRunning = true

        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification("Watchdog active"))

        // Acquire WakeLock — use Huawei-whitelisted tag on Huawei/Honor devices
        acquireWakeLock()

        // Start monitoring loop
        scope.launch {
            monitoringLoop()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun acquireWakeLock() {
        try {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager

            // On Huawei/Honor, use a whitelisted system tag to avoid PowerGenie killing us
            // PowerGenie (Huawei's task killer) aggressively terminates wakelocks
            // with non-whitelisted tags held for more than 60 minutes.
            val isHuawei = Build.MANUFACTURER.lowercase().contains("huawei") ||
                    Build.MANUFACTURER.lowercase().contains("honor")

            val tag = if (isHuawei) {
                "LocationManagerService" // Huawei-whitelisted system tag
            } else {
                "Magneetar:PersistenceWakeLock"
            }

            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                tag
            ).apply {
                // Set timeout to avoid holding indefinitely if something goes wrong
                acquire(30 * 60 * 1000L) // 30 minutes max
            }
            Log.d(TAG, "WakeLock acquired (tag=$tag)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to acquire WakeLock: ${e.message}")
        }
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let {
                if (it.isHeld) {
                    it.release()
                }
            }
        } catch (e: Exception) {
            // Ignore
        }
    }

    private suspend fun monitoringLoop() {
        while (isActive()) {
            try {
                if (!isTrackingServiceRunning()) {
                    Log.w(TAG, "TrackingService is dead! Restarting...")
                    restartTrackingService()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Monitoring error: ${e.message}")
            }
            delay(CHECK_INTERVAL_MS)
        }
    }

    private fun isTrackingServiceRunning(): Boolean {
        return TrackingService.isRunning
    }

    private fun restartTrackingService() {
        try {
            val intent = Intent(this, TrackingService::class.java)
            intent.putExtra("restarted_by", "persistence_service")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
            Log.i(TAG, "TrackingService restart triggered")

            // Also re-schedule the AlarmManager watchdog as a backup
            WatchdogReceiver.scheduleWatchdog(this)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to restart TrackingService: ${e.message}")
        }
    }

    // ── Notification ────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Magneetar Protection",
                NotificationManager.IMPORTANCE_MIN  // Lowest importance — no sound, no popup
            ).apply {
                setShowBadge(false)
                enableLights(false)
                enableVibration(false)
                setDescription("Background protection watchdog")
            }
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🛡 Magneetar")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .setOngoing(true)
            .build()
    }

    override fun onDestroy() {
        isRunning = false
        super.onDestroy()
        scope.cancel()
        releaseWakeLock()
        Log.d(TAG, "Persistence service destroyed")

        // If this service is killed, fire the watchdog immediately
        WatchdogReceiver.fireImmediateRestart(this)
    }
}
