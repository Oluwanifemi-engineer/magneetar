package com.magneetar.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ComponentName
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

    // ── Incoming Messages ────────────────────────────────────────────────

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        Log.d(TAG, "Push received: ${message.from}")

        val data = message.data
        val messageType = data["type"] ?: "general"

        // ── Command execution (FCM fallback when WebSocket is dead) ──────
        // When the server pushes a command via FCM (device offline, no SMS),
        // execute it locally. This is the Doze-mode wake-up path: FCM
        // high-priority data messages bypass Doze and deliver even when the
        // app backgrounded / socket killed.
        if (messageType == "command") {
            val command = data["command"] ?: return
            val commandId = data["command_id"]?.toIntOrNull() ?: 0
            val params = data["params"] ?: ""

            Log.d(TAG, "FCM command received: $command #$commandId")

            scope.launch {
                executeCommand(command, commandId, params)
            }
            return
        }

        // ── Alert notifications (theft, SIM change, etc.) ───────────────
        val title = message.notification?.title
            ?: data["title"]
            ?: "Magneetar Alert"

        val body = message.notification?.body
            ?: data["body"]
            ?: "Security alert from your device"

        val alertType = messageType
        val deviceId = data["device_id"]

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

    // ── FCM Command Execution ───────────────────────────────────────────────
    // Executes commands received via FCM data messages. This is the Doze-mode
    // fallback: when the WebSocket is dead and SMS isn't available, FCM can
    // still wake the app and deliver commands.
    private suspend fun executeCommand(command: String, commandId: Int, params: String) {
        // Set when a command could not be honoured — the ack below carries the
        // reason instead of claiming success.
        var commandFailure: String? = null
        try {
            when (command) {
                "lock" -> {
                    // Execute remote lock via DevicePolicyManager
                    val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
                    val adminComponent = ComponentName(this, AdminReceiver::class.java)
                    if (dpm.isAdminActive(adminComponent)) {
                        dpm.lockNow()
                        Log.i(TAG, "FCM: Device locked via remote command")
                    } else {
                        // Honesty contract: no admin → no lock. Ack failed
                        // instead of letting the dashboard show 'executed'.
                        commandFailure = "Lock NOT applied — Device Admin is not enabled on the device."
                    }
                }
                "alarm", "siren" -> {
                    // Execute max-volume alarm via TrackingService broadcast
                    // The alarm logic lives in TrackingService.triggerAlarm() which
                    // generates a dual-tone siren (800Hz + 1200Hz) that bypasses DND.
                    val alarmIntent = Intent(this, TrackingService::class.java).apply {
                        action = "com.magneetar.app.TRIGGER_ALARM"
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(alarmIntent)
                    } else {
                        startService(alarmIntent)
                    }
                    Log.i(TAG, "FCM: Alarm triggered via remote command")
                }
                "capture_photo", "capture_photo_front" -> {
                    // Trigger evidence capture — start MediaCaptureService if not running
                    val serviceIntent = Intent(this, MediaCaptureService::class.java).apply {
                        putExtra("command", command)
                        putExtra("command_id", commandId)
                        putExtra("params", params)
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(serviceIntent)
                    } else {
                        startService(serviceIntent)
                    }
                    Log.i(TAG, "FCM: Photo capture triggered via remote command")
                }
                "capture_audio" -> {
                    // Trigger audio capture
                    val serviceIntent = Intent(this, MediaCaptureService::class.java).apply {
                        putExtra("command", command)
                        putExtra("command_id", commandId)
                        putExtra("params", params)
                    }
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(serviceIntent)
                    } else {
                        startService(serviceIntent)
                    }
                    Log.i(TAG, "FCM: Audio capture triggered via remote command")
                }
                "wipe" -> {
                    // Real factory reset when Device Admin is active; otherwise
                    // ack 'failed' with the truth — a wipe must never be
                    // silently dropped while the dashboard reports it done.
                    val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
                    val adminComponent = ComponentName(this, AdminReceiver::class.java)
                    if (dpm.isAdminActive(adminComponent)) {
                        Log.i(TAG, "FCM: wipeData issued (factory reset)")
                        dpm.wipeData(0)
                    } else {
                        Log.w(TAG, "FCM: wipe requested but Device Admin is not enabled")
                        commandFailure = "Device Admin is not enabled — factory wipe NOT performed. Use Google Find My Device for a full wipe."
                    }
                }
                "lost_mode" -> {
                    // Activate lost mode — show lock screen with owner message
                    val lostModeIntent = Intent(this, LostModeActivity::class.java).apply {
                        flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        putExtra("message", params)
                    }
                    startActivity(lostModeIntent)
                    Log.i(TAG, "FCM: Lost mode activated via remote command")
                }
                else -> {
                    Log.w(TAG, "FCM: Unknown command: $command")
                }
            }

            // Acknowledge the command back to the server — 'failed' with the
            // reason when the wipe could not be honoured, never a phantom
            // 'executed' (the server persists failure_reason for failed acks).
            if (commandFailure != null) {
                acknowledgeCommand(commandId, "failed", commandFailure)
            } else {
                acknowledgeCommand(commandId, "executed")
            }

        } catch (e: Exception) {
            Log.e(TAG, "FCM command execution failed: $command", e)
            acknowledgeCommand(commandId, "failed", "${e.javaClass.simpleName}: ${e.message ?: "command execution failed"}".take(290))
        }
    }

    /**
     * Send command acknowledgement back to the server via HTTP.
     * Uses the same poll-ack endpoint as the WebSocket path.
     */
    private suspend fun acknowledgeCommand(commandId: Int, status: String, failureReason: String? = null) {
        try {
            val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
            val deviceKey = prefs.getString("device_key", "") ?: ""

            val body = JSONObject().apply {
                put("command_id", commandId)
                put("status", status)
                if (failureReason != null) put("failure_reason", failureReason.take(290))
            }.toString().toRequestBody(JSON)

            val requestBuilder = okhttp3.Request.Builder()
                .url("$serverUrl/api/device/command/$commandId/ack")
                .post(body)

            if (deviceKey.isNotEmpty()) {
                requestBuilder.addHeader("x-device-key", deviceKey)
            }

            val response = client.newCall(requestBuilder.build()).execute()
            response.close()

            Log.d(TAG, "FCM command #$commandId acked: $status")
        } catch (e: Exception) {
            Log.w(TAG, "FCM command ack failed: ${e.message}")
        }
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
