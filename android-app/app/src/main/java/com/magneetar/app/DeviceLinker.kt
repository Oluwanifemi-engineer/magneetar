package com.magneetar.app

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Best-effort helper that links this device to the signed-in user account.
 *
 * When a user signs in while the device is already running unlinked, the
 * device stays ownerless until TrackingService re-registers (which also
 * carries the user token now). This posts /api/device/claim with the user
 * token + device key so the device appears in the user's dashboard
 * immediately. Failures are ignored — TrackingService re-links on its next
 * registration.
 */
object DeviceLinker {

    suspend fun linkToAccount(context: Context, serverUrl: String, userToken: String) {
        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("device_id", "") ?: ""
        val deviceKey = prefs.getString("device_key", "") ?: ""
        if (deviceId.isEmpty() || deviceKey.isEmpty() || userToken.isEmpty()) return

        withContext(Dispatchers.IO) {
            try {
                val body = JSONObject().apply {
                    put("device_id", deviceId)
                }.toString()

                val request = okhttp3.Request.Builder()
                    .url("$serverUrl/api/device/claim")
                    .post(body.toRequestBody("application/json".toMediaType()))
                    .addHeader("Content-Type", "application/json")
                    .addHeader("Authorization", "Bearer $userToken")
                    .addHeader("x-device-key", deviceKey)
                    .build()

                val client = okhttp3.OkHttpClient.Builder()
                    .connectTimeout(10, TimeUnit.SECONDS)
                    .readTimeout(10, TimeUnit.SECONDS)
                    .build()

                client.newCall(request).execute().use { response ->
                    if (response.code == 200) {
                        android.util.Log.d("DeviceLinker", "Device linked to account")
                    } else {
                        android.util.Log.d("DeviceLinker", "Claim skipped (HTTP ${response.code})")
                    }
                }
            } catch (e: Exception) {
                android.util.Log.w("DeviceLinker", "Claim failed: ${e.message}")
            }
        }
    }
}
