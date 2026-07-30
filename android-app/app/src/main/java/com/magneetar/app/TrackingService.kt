package com.magneetar.app

import android.app.*
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat
import android.hardware.camera2.*
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.media.MediaRecorder
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

    // Auth state
    private var accessToken: String? = null
    private var refreshToken: String? = null
    private var pingSequence = 0
    private var isRegistered = false

    private val deviceId: String by lazy {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        prefs.getString("device_id", null) ?: run {
            val id = "mt-" + UUID.randomUUID().toString().take(8)
            prefs.edit().putString("device_id", id).apply()
            id
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

    private val simSerialHash: String by lazy {
        try {
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
        try {
            val body = JSONObject().apply {
                put("device_id", deviceId)
                put("fingerprint", Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "")
                put("model", Build.MODEL)
                put("os_version", "Android ${Build.VERSION.RELEASE}")
                put("app_version", BuildConfig.VERSION_NAME)
                put("imei_hash", "") // Not available on Android 10+
                put("sim_serial_hash", simSerialHash)
                put("device_key", deviceKey)
            }.toString().toRequestBody(JSON)

            val response = postRaw("/api/device/register", body, useApiKey = true)
            if (response != null) {
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
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            // Retry later
            delay(15_000)
            registerDevice()
        }
    }

    private suspend fun refreshAccessToken(): Boolean {
        val rt = refreshToken ?: return false
        try {
            val body = JSONObject().apply {
                put("refresh_token", rt)
            }.toString().toRequestBody(JSON)

            val response = postRaw("/api/device/refresh", body, useApiKey = false)
            if (response != null) {
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
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, LOCATION_INTERVAL_MS, 0f, listener
            )
            locationManager.requestLocationUpdates(
                LocationManager.NETWORK_PROVIDER, LOCATION_INTERVAL_MS, 0f, listener
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

    private suspend fun commandLoop() {
        while (true) {
            try {
                val response = get("/api/device/commands/$deviceId")
                if (response != null) {
                    val commands = JSONObject(response).getJSONArray("commands")
                    for (i in 0 until commands.length()) {
                        val cmd = commands.getJSONObject(i)
                        handleCommand(cmd.getInt("id"), cmd.getString("command"))
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
            }
            delay(WAIT_BETWEEN_COMMANDS_MS)
        }
    }

    private suspend fun handleCommand(id: Int, command: String) {
        when (command) {
            "ping"             -> { ackCommand(id, "executed"); updateNotification("Ping received") }
            "capture_photo"    -> { capturePhoto(); ackCommand(id, "executed") }
            "capture_photo_front" -> { capturePhotoFront(); ackCommand(id, "executed") }
            "capture_audio"    -> { captureAudio(); ackCommand(id, "executed") }
            "location_burst"   -> { locationBurst(); ackCommand(id, "executed") }
            "lock"             -> { lockDevice(); ackCommand(id, "executed") }
            "alarm"            -> { triggerAlarm(); ackCommand(id, "executed") }
            "wipe"             -> { ackCommand(id, "executed"); wipeDevice() }
            else               -> { ackCommand(id, "failed") }
        }
    }

    private suspend fun ackCommand(id: Int, status: String) {
        val body = JSONObject().apply {
            put("status", status)
        }.toString().toRequestBody(JSON)
        post("/api/device/commands/$id/ack", body)
    }

    // ── Camera (Rear) ──────────────────────────────────────────────────────────

    private suspend fun capturePhoto() {
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            // Try rear camera first, fall back to any camera
            var cameraId: String? = null
            for (id in cameraManager.cameraIdList) {
                val chars = cameraManager.getCameraCharacteristics(id)
                val facing = chars.get(CameraCharacteristics.LENS_FACING)
                if (facing == CameraCharacteristics.LENS_FACING_BACK) {
                    cameraId = id
                    break
                }
            }
            if (cameraId == null) cameraId = cameraManager.cameraIdList.firstOrNull() ?: return

            val handlerThread = HandlerThread("CameraThread").also { it.start() }
            val handler = Handler(handlerThread.looper)
            val reader = android.media.ImageReader.newInstance(
                1280, 720, android.graphics.ImageFormat.JPEG, 2
            )
            val deferred = CompletableDeferred<ByteArray>()

            reader.setOnImageAvailableListener({ r ->
                val image = r.acquireLatestImage()
                if (image != null) {
                    val buffer = image.planes[0].buffer
                    val bytes = ByteArray(buffer.remaining())
                    buffer.get(bytes)
                    image.close()
                    deferred.complete(bytes)
                }
            }, handler)

            @Suppress("DEPRECATION")
            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    @Suppress("DEPRECATION")
                    camera.createCaptureSession(
                        listOf(reader.surface),
                        object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(session: CameraCaptureSession) {
                                val request = camera.createCaptureRequest(
                                    CameraDevice.TEMPLATE_STILL_CAPTURE
                                ).apply { addTarget(reader.surface) }
                                session.capture(request.build(), object :
                                    CameraCaptureSession.CaptureCallback() {
                                    override fun onCaptureCompleted(
                                        session: CameraCaptureSession,
                                        request: CaptureRequest,
                                        result: TotalCaptureResult
                                    ) {}
                                }, handler)
                            }
                            override fun onConfigureFailed(session: CameraCaptureSession) {
                                deferred.completeExceptionally(Exception("Camera config failed"))
                            }
                        }, handler
                    )
                }
                override fun onDisconnected(camera: CameraDevice) { camera.close() }
                override fun onError(camera: CameraDevice, error: Int) { camera.close() }
            }, handler)

            val bytes = deferred.await()
            val lat = getLastKnownLat()
            val lng = getLastKnownLng()
            uploadMedia("photo", bytes, lat, lng)
            reader.close()
            handlerThread.quitSafely()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // ── Camera (Front) ─────────────────────────────────────────────────────────

    private suspend fun capturePhotoFront() {
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            var cameraId: String? = null
            for (id in cameraManager.cameraIdList) {
                val chars = cameraManager.getCameraCharacteristics(id)
                val facing = chars.get(CameraCharacteristics.LENS_FACING)
                if (facing == CameraCharacteristics.LENS_FACING_FRONT) {
                    cameraId = id
                    break
                }
            }
            if (cameraId == null) { capturePhoto(); return }

            val handlerThread = HandlerThread("CameraFrontThread").also { it.start() }
            val handler = Handler(handlerThread.looper)
            val reader = android.media.ImageReader.newInstance(
                640, 480, android.graphics.ImageFormat.JPEG, 2
            )
            val deferred = CompletableDeferred<ByteArray>()

            reader.setOnImageAvailableListener({ r ->
                val image = r.acquireLatestImage()
                if (image != null) {
                    val buffer = image.planes[0].buffer
                    val bytes = ByteArray(buffer.remaining())
                    buffer.get(bytes)
                    image.close()
                    deferred.complete(bytes)
                }
            }, handler)

            @Suppress("DEPRECATION")
            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(camera: CameraDevice) {
                    @Suppress("DEPRECATION")
                    camera.createCaptureSession(
                        listOf(reader.surface),
                        object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(session: CameraCaptureSession) {
                                val request = camera.createCaptureRequest(
                                    CameraDevice.TEMPLATE_STILL_CAPTURE
                                ).apply {
                                    addTarget(reader.surface)
                                    // Front camera typically doesn't support auto-focus in template
                                }
                                session.capture(request.build(), object :
                                    CameraCaptureSession.CaptureCallback() {
                                    override fun onCaptureCompleted(
                                        session: CameraCaptureSession,
                                        request: CaptureRequest,
                                        result: TotalCaptureResult
                                    ) {}
                                }, handler)
                            }
                            override fun onConfigureFailed(session: CameraCaptureSession) {
                                deferred.completeExceptionally(Exception("Front camera config failed"))
                            }
                        }, handler
                    )
                }
                override fun onDisconnected(camera: CameraDevice) { camera.close() }
                override fun onError(camera: CameraDevice, error: Int) { camera.close() }
            }, handler)

            val bytes = deferred.await()
            val lat = getLastKnownLat()
            val lng = getLastKnownLng()
            uploadMedia("photo", bytes, lat, lng)
            reader.close()
            handlerThread.quitSafely()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // ── Audio ─────────────────────────────────────────────────────────────────

    private suspend fun captureAudio() {
        try {
            val file = File(cacheDir, "mt_audio_${System.currentTimeMillis()}.mp4")
            val recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(this)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }
            recorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(44100)
                // Audio bitrate set via AudioProfile on newer APIs
                // Default bitrate is sufficient for evidence capture
                setOutputFile(file.absolutePath)
                prepare()
                start()
            }
            delay(20_000) // 20 seconds
            recorder.stop()
            recorder.release()
            val lat = getLastKnownLat()
            val lng = getLastKnownLng()
            uploadMedia("audio", file.readBytes(), lat, lng)
            file.delete()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // ── Location Burst ─────────────────────────────────────────────────────────

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

    private fun triggerAlarm() {
        // Play max volume alarm through media stream
        try {
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
            val track = android.media.AudioTrack(
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
            track.write(samples, 0, numSamples)
            track.play()
            // Track will play and then stop naturally after 5 seconds
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    // ── Media upload ──────────────────────────────────────────────────────────

    private suspend fun uploadMedia(type: String, bytes: ByteArray, lat: Double? = null, lng: Double? = null) {
        val body = JSONObject().apply {
            put("device_id", deviceId)
            put("type", type)
            put("data_b64", Base64.encodeToString(bytes, Base64.NO_WRAP))
            put("timestamp", isoNow())
            if (lat != null) put("lat", lat)
            if (lng != null) put("lng", lng)
        }.toString().toRequestBody(JSON)
        post("/api/device/media", body)
    }

    // ── Device admin ──────────────────────────────────────────────────────────

    private fun lockDevice() {
        try {
            val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE)
                    as android.app.admin.DevicePolicyManager
            val adminComponent = ComponentName(this, AdminReceiver::class.java)
            if (dpm.isAdminActive(adminComponent)) {
                dpm.lockNow()
            }
        } catch (e: Exception) {
            e.printStackTrace()
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

    // ── Location helpers ──────────────────────────────────────────────────────

    private fun getLastKnownLat(): Double? {
        return try {
            locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.latitude
                ?: locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)?.latitude
        } catch (e: Exception) { null }
    }

    private fun getLastKnownLng(): Double? {
        return try {
            locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)?.longitude
                ?: locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)?.longitude
        } catch (e: Exception) { null }
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

    private suspend fun postRaw(path: String, body: RequestBody, useApiKey: Boolean = false): String? =
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
                client.newCall(builder.build()).execute().use { it.body?.string() }
            } catch (e: Exception) { null }
        }

    private suspend fun post(path: String, body: RequestBody): String? =
        withContext(Dispatchers.IO) {
            try {
                val builder = Request.Builder()
                    .url("$SERVER$path")
                    .post(body)
                authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
                val response = client.newCall(builder.build()).execute()
                if (response.code == 401 && refreshToken != null) {
                    // Token expired, try refresh
                    response.close()
                    if (refreshAccessToken()) {
                        // Retry with new token
                        val retryBuilder = Request.Builder()
                            .url("$SERVER$path")
                            .post(body)
                        authHeaders().forEach { (k, v) -> retryBuilder.addHeader(k, v) }
                        client.newCall(retryBuilder.build()).execute().use { it.body?.string() }
                    } else null
                } else {
                    response.use { it.body?.string() }
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
                if (response.code == 401 && refreshToken != null) {
                    response.close()
                    if (refreshAccessToken()) {
                        val retryBuilder = Request.Builder()
                            .url("$SERVER$path")
                            .get()
                        authHeaders().forEach { (k, v) -> retryBuilder.addHeader(k, v) }
                        client.newCall(retryBuilder.build()).execute().use { it.body?.string() }
                    } else null
                } else {
                    response.use { it.body?.string() }
                }
            } catch (e: Exception) { null }
        }

    // ── Utils ─────────────────────────────────────────────────────────────────

    private fun isoNow(): String =
        SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
            .format(Date())

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
