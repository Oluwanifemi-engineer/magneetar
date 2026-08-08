package com.magneetar.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Magneetar Firebase Cloud Messaging Service
 *
 * Handles incoming push notifications and FCM token registration.
 * The FCM token is sent to the server so push alerts (theft, SIM change, etc.)
 * can be delivered to the device.
 */
class MagneetarMessagingService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "MagneetarFCM"
        private const val CHANNEL_ID = "mt_alerts"
        private const val NOTIFICATION_ID_BASE = 1000
        private val JSON = "application/json".toMediaType()
        private var notificationIdCounter = NOTIFICATION_ID_BASE
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private val serverUrl: String
        get() = BuildConfig.SERVER_URL

    private val deviceKey: String
        get() = BuildConfig.DEVICE_KEY

    // ── Token Registration ──────────────────────────────────────────────────

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d(TAG, "New FCM token: ${token.take(16)}...")

        // Send token to server
        scope.launch {
            registerFcmToken(token)
        }
    }

    private suspend fun registerFcmToken(token: String) {
        try {
            // Read device_id and device_key from SharedPreferences (same store as TrackingService)
            val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
            val deviceId = prefs.getString("device_id", "") ?: ""
            val deviceKey = prefs.getString("device_key", "") ?: ""

            val body = JSONObject().apply {
                put("fcm_token", token)
                put("device_id", deviceId)
                put("platform", "android")
            }.toString().toRequestBody(JSON)

            val requestBuilder = okhttp3.Request.Builder()
                .url("$serverUrl/api/device/fcm-token")
                .post(body)

            // Prefer device key (unique per-device secret), fall back to shared API key
            if (deviceKey.isNotEmpty()) {
                requestBuilder.addHeader("x-device-key", deviceKey)
                Log.d(TAG, "Registering FCM with device key auth")
            } else {
                // Use the shared API key (BuildConfig.DEVICE_KEY contains the shared key
                // when no per-device key is set)
                requestBuilder.addHeader("x-api-key", BuildConfig.DEVICE_KEY)
                Log.d(TAG, "Registering FCM with shared API key")
            }

            val response = client.newCall(requestBuilder.build()).execute()
            if (response.isSuccessful) {
                Log.d(TAG, "FCM token registered for device $deviceId")
            } else {
                Log.w(TAG, "FCM token registration failed: ${response.code}")
            }
            response.close()
        } catch (e: Exception) {
            Log.e(TAG, "FCM token registration error: ${e.message}")
        }
    }

    // ── Incoming Notifications ──────────────────────────────────────────────

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        Log.d(TAG, "Push received: ${message.from}")

        // Extract notification data
        val title = message.notification?.title
            ?: message.data["title"]
            ?: "Magneetar Alert"

        val body = message.notification?.body
            ?: message.data["body"]
            ?: "Security alert from your device"

        val alertType = message.data["type"] ?: "general"
        val deviceId = message.data["device_id"]

        // Create notification channel
        createNotificationChannel()

        // Build intent to open dashboard
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("alert_type", alertType)
            putExtra("device_id", deviceId)
        }

        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        // Determine icon based on alert type
        val icon = when (alertType) {
            "theft_detected", "factory_reset" -> android.R.drawable.ic_dialog_alert
            "sim_changed" -> android.R.drawable.ic_lock_lock
            "battery_low" -> android.R.drawable.ic_lock_idle_low_battery
            "device_offline" -> android.R.drawable.ic_menu_close_clear_cancel
            else -> android.R.drawable.ic_menu_compass
        }

        // Priority based on severity
        val priority = when (alertType) {
            "theft_detected", "factory_reset" -> NotificationCompat.PRIORITY_MAX
            "sim_changed", "geofence_exit" -> NotificationCompat.PRIORITY_HIGH
            else -> NotificationCompat.PRIORITY_DEFAULT
        }

        // Build notification
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(icon)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(priority)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .build()

        // Show notification
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(notificationIdCounter++, notification)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Magneetar Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Security alerts from Magneetar"
                enableVibration(true)
                setShowBadge(true)
            }
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.createNotificationChannel(channel)
        }
    }
}
