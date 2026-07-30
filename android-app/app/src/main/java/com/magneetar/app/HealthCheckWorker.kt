package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.content.ContextCompat
import androidx.work.*

/**
 * WorkManager-based periodic health check.
 *
 * This is a third layer of redundancy (beyond the foreground services
 * and AlarmManager watchdog). WorkManager is the most battery-friendly
 * scheduling mechanism because Android/Google Play Services manages
 * it centrally.
 *
 * While WorkManager can't ensure real-time execution, it provides a
 * reliable fallback that even aggressive OEMs have difficulty blocking
 * (since WorkManager is part of Jetpack and has system-level reliability).
 */
class HealthCheckWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "MagneetarHealthCheck"
        private const val WORK_NAME = "magneetar_health_check"

        /**
         * Schedule periodic health checks (every 30 minutes with 15 minute flex).
         */
        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.NOT_REQUIRED)
                .build()

            val request = PeriodicWorkRequestBuilder<HealthCheckWorker>(
                30, java.util.concurrent.TimeUnit.MINUTES,
                15, java.util.concurrent.TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    5, java.util.concurrent.TimeUnit.MINUTES
                )
                .addTag(WORK_NAME)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )

            Log.d(TAG, "Health check worker scheduled every 30 minutes")
        }

        /**
         * Cancel the health check worker.
         */
        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
            Log.d(TAG, "Health check worker cancelled")
        }
    }

    override suspend fun doWork(): Result {
        Log.d(TAG, "Health check executing...")

        return try {
            val isTrackingRunning = isServiceRunning(TrackingService::class.java.name)
            val isPersistenceRunning = isServiceRunning(PersistenceService::class.java.name)

            if (!isTrackingRunning) {
                Log.w(TAG, "TrackingService not running! Restarting...")
                val intent = Intent(applicationContext, TrackingService::class.java)
                ContextCompat.startForegroundService(applicationContext, intent)
            }

            if (!isPersistenceRunning) {
                Log.w(TAG, "PersistenceService not running! Restarting...")
                val intent = Intent(applicationContext, PersistenceService::class.java)
                ContextCompat.startForegroundService(applicationContext, intent)
            }

            if (isTrackingRunning && isPersistenceRunning) {
                Log.d(TAG, "Both services running. Health check passed.")
            }

            // Re-schedule watchdog alarm as backup
            WatchdogReceiver.scheduleWatchdog(applicationContext)

            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Health check failed: ${e.message}")
            Result.retry()
        }
    }

    private fun isServiceRunning(className: String): Boolean {
        return when (className) {
            TrackingService::class.java.name -> TrackingService.isRunning
            PersistenceService::class.java.name -> PersistenceService.isRunning
            else -> false
        }
    }
}
