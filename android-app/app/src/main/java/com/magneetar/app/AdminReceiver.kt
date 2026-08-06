package com.magneetar.app

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Device admin receiver — the keystone of uninstall protection.
 *
 * While this receiver is an ACTIVE device administrator, Android refuses to
 * uninstall Magneetar until the admin is deactivated in Settings (a thief
 * cannot simply "Uninstall" the app). Deactivation surfaces our warning via
 * onDisableRequested, and if it still happens we fire an immediate heartbeat
 * so the dashboard's Sentinel score jumps (device admin disabled = theft
 * signal) instead of waiting up to a minute for the next heartbeat.
 */
class AdminReceiver : DeviceAdminReceiver() {

    companion object {
        private const val TAG = "MagneetarAdmin"
        private val JSON = "application/json".toMediaType()

        /**
         * The warning shown in the SYSTEM dialog when someone tries to
         * deactivate Magneetar as a device admin. This is the last line of
         * defence before a phone becomes unprotected (and uninstallable).
         */
        const val DISABLE_WARNING =
            "⚠ Magneetar anti-theft protection\n\n" +
            "Deactivating Device Admin will:\n" +
            "• Allow this app to be UNINSTALLED by anyone\n" +
            "• Disable remote lock, wipe & siren\n" +
            "• Stop intruder camera/audio capture\n" +
            "• Make recovery of a stolen phone impossible\n\n" +
            "Only proceed if you are the verified owner."
    }

    override fun onEnabled(context: Context, intent: Intent) {
        super.onEnabled(context, intent)
        // Re-assert the hard uninstall block on every activation (device-owner
        // mode re-activation after a data wipe, for example).
        UninstallProtection.enforceUninstallBlocked(context)
    }

    override fun onDisabled(context: Context, intent: Intent) {
        super.onDisabled(context, intent)
        // Admin was deactivated — the phone is now uninstallable and remote
        // lock/wipe are dead. Tell the server IMMEDIATELY so the dashboard
        // shows a sharply elevated Sentinel score (device_admin_active=false
        // is a weighted theft signal) rather than waiting ≤60s for the next
        // scheduled heartbeat. Best-effort only: a failed POST is harmless
        // because the regular heartbeat loop reports the same state anyway.
        reportAdminDisabled(context)
    }

    override fun onDisableRequested(context: Context, intent: Intent): CharSequence {
        return DISABLE_WARNING
    }

    /**
     * Fire an immediate heartbeat with device_admin_active=false.
     *
     * Runs on a background coroutine with a hard timeout: a BroadcastReceiver
     * has ~10s of lifetime and must never leak. Uses the persisted device
     * tokens, so it works even if the services were killed by an OEM task
     * killer — the point of this call is exactly that scenario.
     */
    private fun reportAdminDisabled(context: Context) {
        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        // Use BuildConfig.SERVER_URL — the SAME endpoint the rest of the device
        // stack (TrackingService, MediaCaptureService, FCM service) reports to.
        // The prefs server_url is a UI value (dashboard link) and must not be
        // trusted here: the most security-critical alert (admin disabled) has
        // to land on the tracking host or it could be silently lost.
        val server = BuildConfig.SERVER_URL
        val deviceId = prefs.getString("device_id", "")
        if (deviceId.isNullOrEmpty()) return

        val accessToken = prefs.getString("access_token", "")
        val refreshToken = prefs.getString("refresh_token", "")

        val client = OkHttpClient.Builder()
            .connectTimeout(3, TimeUnit.SECONDS)
            .readTimeout(5, TimeUnit.SECONDS)
            .writeTimeout(5, TimeUnit.SECONDS)
            .build()

        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            withTimeoutOrNull(6_000L) {
                try {
                    // Only the fields that are TRUE here: battery/network are
                    // unknown at receiver time, so omit them (HeartbeatPacket
                    // marks them Optional — no fabricated metrics).
                    val body = JSONObject().apply {
                        put("device_id", deviceId)
                        put("app_version", BuildConfig.VERSION_NAME)
                        put("device_admin_active", false)
                    }.toString().toRequestBody(JSON)

                    var builder = Request.Builder().url("$server/api/device/heartbeat").post(body)
                    if (!accessToken.isNullOrEmpty()) {
                        builder.addHeader("Authorization", "Bearer $accessToken")
                    } else {
                        val deviceKey = prefs.getString("device_key", "")
                        if (!deviceKey.isNullOrEmpty()) builder.addHeader("x-device-key", deviceKey)
                        else builder.addHeader("x-api-key", BuildConfig.DEVICE_KEY)
                    }
                    val response = client.newCall(builder.build()).execute()
                    response.close()
                    delay(200) // let the request fully finish before receiver death
                } catch (e: Exception) {
                    // Silent by design — the next heartbeat covers it.
                }
            }
        }
    }
}
