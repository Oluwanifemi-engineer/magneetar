package com.magneetar.app

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.camera2.*
import android.media.MediaRecorder
import android.os.*
import android.util.Base64
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

/**
 * Short-lived evidence capture foreground service (type camera|microphone).
 *
 * WHY THIS SERVICE EXISTS — Android 14/15 foreground-service type rules:
 * A foreground service declared `location`-only (TrackingService) CANNOT open
 * the camera or microphone while the app is in the background (screen locked
 * — exactly the anti-theft scenario). The system throws SecurityException /
 * CameraAccessException / MediaRecorder RuntimeException. The documented fix is
 * a dedicated `camera|microphone` foreground service, and Android explicitly
 * permits STARTING one from the background when a location-type foreground
 * service is already running (TrackingService guarantees that). This service
 * therefore owns ALL photo/audio capture, uploads the evidence, and ACKS the
 * originating command honestly — "executed" only when media was uploaded.
 *
 * Started via ContextCompat.startForegroundService from TrackingService's
 * command handler with EXTRA_COMMAND_ID / EXTRA_COMMAND; stops itself.
 */
class MediaCaptureService : Service() {

    companion object {
        private const val TAG = "MagneetarCapture"
        private const val CHANNEL_ID = "mt_capture"
        private const val NOTIF_ID = 3
        private const val CAMERA_CAPTURE_TIMEOUT_MS = 45_000L
        private const val AUDIO_CAPTURE_MS = 20_000L
        private val JSON = "application/json".toMediaType()
        private val SERVER = BuildConfig.SERVER_URL
        private val API_KEY = BuildConfig.API_KEY

        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_COMMAND = "command"

        /**
         * Command ids currently being captured, shared with TrackingService.
         *
         * TrackingService's command poll runs every 10s while a capture can
         * take up to 45s, and the server keeps a command 'pending' until the
         * ack lands. Without this cross-service set, the poll would re-fetch
         * a still-capturing command and spawn duplicate captures (which on
         * many devices fail outright — camera busy). The capture service
         * registers the id on start and removes it only after the ack POST.
         */
        @JvmStatic
        val activeCaptureIds = Collections.synchronizedSet(mutableSetOf<Int>())
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // Auth state (device tokens are persisted by TrackingService on register;
    // we read them so a capture can authenticate even if this short-lived
    // service started after a process restart).
    @Volatile private var accessToken: String? = null
    @Volatile private var refreshToken: String? = null

    override fun onCreate() {
        super.onCreate()
        accessToken = prefs().getString("access_token", "")?.takeIf { it.isNotEmpty() }
        refreshToken = prefs().getString("refresh_token", "")?.takeIf { it.isNotEmpty() }
        createNotificationChannel()
        startForegroundCompat()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val commandId = intent?.getIntExtra(EXTRA_COMMAND_ID, -1) ?: -1
        val command = intent?.getStringExtra(EXTRA_COMMAND) ?: ""
        if (commandId <= 0 || command.isEmpty()) {
            stopSelf(startId)
            return START_NOT_STICKY
        }

        activeCaptureIds.add(commandId)
        scope.launch {
            try {
                var ok = false
                try {
                    when (command) {
                        "capture_photo" -> {
                            capturePhoto()
                            ok = true
                        }
                        "capture_photo_front" -> {
                            capturePhotoFront()
                            ok = true
                        }
                        "capture_audio" -> {
                            captureAudio()
                            ok = true
                        }
                        else -> Log.w(TAG, "Unknown capture command: $command")
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    // Capture failed (camera denied/busy, mic blocked, timeout…).
                    // Ack 'failed' so the dashboard shows the truth instead of
                    // a fake 'executed' with no evidence ever arriving.
                    Log.e(TAG, "Capture '$command' failed: ${e.message}", e)
                }
                // Honest ack — executed only when the media upload completed.
                ackCommand(commandId, if (ok) "executed" else "failed")
            } finally {
                // Release the shared in-flight guard unconditionally — even a
                // cancelled scope (service destroyed mid-capture) must not
                // leave the id stuck, or TrackingService would skip a still-
                // pending command forever (stale-guard hang).
                try {
                    activeCaptureIds.remove(commandId)
                } catch (e: Exception) {}
                stopSelf(startId)
            }
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?) = null

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }

    // ── Foreground / Notification ─────────────────────────────────────────

    private fun prefs() = getSharedPreferences("mt", Context.MODE_PRIVATE)

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Evidence Capture",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                setShowBadge(false)
                enableLights(false)
                enableVibration(false)
                setDescription("Remote photo & audio evidence capture")
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🛡 Magneetar")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .setOngoing(true)
            .build()

    /**
     * Start foreground WITH the camera|microphone type flags. On API 29+ this
     * is what makes camera/mic access legal while backgrounded; on older
     * versions ServiceCompat falls back to the plain two-arg startForeground.
     */
    private fun startForegroundCompat() {
        val notif = buildNotification("Capturing evidence…")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                NOTIF_ID,
                notif,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    // ── Camera (Rear & Front share one capture path) ───────────────────────

    /** Capture a still from the requested lens (back or front). */
    private suspend fun capturePhoto() {
        captureFromLens(CameraCharacteristics.LENS_FACING_BACK, 1280, 720, "CameraThread")
    }

    private suspend fun capturePhotoFront() {
        // No front camera? Fall back to the rear lens so the operator still
        // gets evidence instead of a silent nothing.
        val frontId = cameraIdForLens(CameraCharacteristics.LENS_FACING_FRONT)
        if (frontId == null) {
            captureFromLens(CameraCharacteristics.LENS_FACING_BACK, 1280, 720, "CameraThread")
        } else {
            captureFromLens(CameraCharacteristics.LENS_FACING_FRONT, 640, 480, "CameraFrontThread")
        }
    }

    private fun cameraIdForLens(facing: Int): String? {
        return try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            for (id in cameraManager.cameraIdList) {
                val chars = cameraManager.getCameraCharacteristics(id)
                if (chars.get(CameraCharacteristics.LENS_FACING) == facing) return id
            }
            null
        } catch (e: Exception) { null }
    }

    /**
     * Camera2 still capture: open the lens, configure an ImageReader JPEG
     * surface, capture one frame, upload it. Runs entirely off the main
     * thread; the deferred is completed from camera callbacks.
     *
     * CAMERA permission is requested at runtime in PermissionsActivity before
     * the service can ever be started (capture commands require an onboarded,
     * permission-granted device), and openCamera is additionally wrapped in
     * try/catch below — a SecurityException surfaces as an honest 'failed'
     * ack, never a crash.
     */
    @android.annotation.SuppressLint("MissingPermission")
    private suspend fun captureFromLens(facing: Int, width: Int, height: Int, threadName: String) {
        var camera: CameraDevice? = null
        var reader: android.media.ImageReader? = null
        var handlerThread: HandlerThread? = null
        try {
            val cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            var cameraId = cameraIdForLens(facing)
            if (cameraId == null) {
                // Requested lens missing — any camera is better than nothing.
                cameraId = cameraManager.cameraIdList.firstOrNull()
                    ?: throw IllegalStateException("No camera available on this device")
            }

            handlerThread = HandlerThread(threadName).also { it.start() }
            val handler = Handler(handlerThread.looper)
            reader = android.media.ImageReader.newInstance(width, height, android.graphics.ImageFormat.JPEG, 2)
            val deferred = CompletableDeferred<ByteArray>()

            reader.setOnImageAvailableListener({ r ->
                val image = r.acquireLatestImage()
                if (image != null) {
                    try {
                        val buffer = image.planes[0].buffer
                        val bytes = ByteArray(buffer.remaining())
                        buffer.get(bytes)
                        deferred.complete(bytes)
                    } finally {
                        image.close()
                    }
                } else {
                    deferred.completeExceptionally(Exception("No image captured"))
                }
            }, handler)

            cameraManager.openCamera(cameraId, object : CameraDevice.StateCallback() {
                override fun onOpened(opened: CameraDevice) {
                    camera = opened
                    try {
                        opened.createCaptureSession(
                            listOf(reader!!.surface),
                            object : CameraCaptureSession.StateCallback() {
                                override fun onConfigured(session: CameraCaptureSession) {
                                    val request = opened.createCaptureRequest(
                                        CameraDevice.TEMPLATE_STILL_CAPTURE
                                    ).apply { addTarget(reader!!.surface) }
                                    session.capture(request.build(), null, handler)
                                }
                                override fun onConfigureFailed(session: CameraCaptureSession) {
                                    deferred.completeExceptionally(Exception("Camera config failed"))
                                }
                            },
                            handler
                        )
                    } catch (e: Exception) {
                        deferred.completeExceptionally(e)
                    }
                }
                override fun onDisconnected(opened: CameraDevice) {
                    opened.close()
                    deferred.completeExceptionally(Exception("Camera disconnected"))
                }
                override fun onError(opened: CameraDevice, error: Int) {
                    opened.close()
                    deferred.completeExceptionally(Exception("Camera error $error"))
                }
            }, handler)

            val bytes = withTimeout(CAMERA_CAPTURE_TIMEOUT_MS) { deferred.await() }
            uploadMedia("photo", bytes, lastLat(), lastLng())
        } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
            throw IllegalStateException("Camera capture timed out", e)
        } finally {
            try { reader?.close() } catch (e: Exception) {}
            try { camera?.close() } catch (e: Exception) {}
            try { handlerThread?.quitSafely() } catch (e: Exception) {}
        }
    }

    // ── Audio ───────────────────────────────────────────────────────────────

    private suspend fun captureAudio() {
        val file = File(cacheDir, "mt_audio_${System.currentTimeMillis()}.mp4")
        var recorder: MediaRecorder? = null
        try {
            recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
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
                setOutputFile(file.absolutePath)
                prepare()
                start()
            }
            delay(AUDIO_CAPTURE_MS)
            try {
                recorder.stop()
            } catch (e: RuntimeException) {
                // stop() after a short/failed recording throws — release and
                // let the upload path report the failure honestly.
                throw IllegalStateException("Audio recorder stopped unexpectedly", e)
            }
            recorder.release()
            recorder = null
            uploadMedia("audio", file.readBytes(), lastLat(), lastLng())
        } finally {
            try { recorder?.release() } catch (e: Exception) {}
            try { if (file.exists()) file.delete() } catch (e: Exception) {}
        }
    }

    // ── Location helpers (best-effort, never fatal) ─────────────────────────

    // LOCATION permission is runtime-granted during onboarding (PermissionsActivity);
    // these calls are purely best-effort metadata and are wrapped in try/catch,
    // so a revoked permission degrades to null coordinates — never a crash.
    @android.annotation.SuppressLint("MissingPermission")
    private fun lastLat(): Double? {
        return try {
            val lm = getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
            lm.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)?.latitude
                ?: lm.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)?.latitude
        } catch (e: Exception) { null }
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun lastLng(): Double? {
        return try {
            val lm = getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
            lm.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)?.longitude
                ?: lm.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)?.longitude
        } catch (e: Exception) { null }
    }

    // ── HTTP ────────────────────────────────────────────────────────────────

    private fun authHeaders(): Map<String, String> {
        val headers = mutableMapOf<String, String>()
        if (accessToken != null) {
            headers["Authorization"] = "Bearer $accessToken"
        } else {
            val deviceKey = prefs().getString("device_key", "") ?: ""
            if (deviceKey.isNotEmpty()) headers["x-device-key"] = deviceKey
            else headers["x-api-key"] = API_KEY
        }
        return headers
    }

    private suspend fun uploadMedia(type: String, bytes: ByteArray, lat: Double?, lng: Double?) {
        val body = JSONObject().apply {
            put("device_id", prefs().getString("device_id", "") ?: "")
            put("type", type)
            put("data_b64", Base64.encodeToString(bytes, Base64.NO_WRAP))
            put("timestamp", isoNow())
            if (lat != null) put("lat", lat)
            if (lng != null) put("lng", lng)
        }.toString().toRequestBody(JSON)

        val ok = post("/api/device/media", body)
        if (!ok) throw IllegalStateException("Media upload rejected by server")
    }

    private suspend fun ackCommand(id: Int, status: String) {
        val body = JSONObject().apply { put("status", status) }.toString().toRequestBody(JSON)
        post("/api/device/commands/$id/ack", body)
    }

    private suspend fun post(path: String, body: RequestBody): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val builder = Request.Builder().url("$SERVER$path").post(body)
                authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
                val response = client.newCall(builder.build()).execute()
                if (response.code in 200..299) {
                    response.close()
                    true
                } else if (response.code == 401) {
                    response.close()
                    if (refreshToken != null && refreshAccessToken()) {
                        val retry = Request.Builder().url("$SERVER$path").post(body)
                        authHeaders().forEach { (k, v) -> retry.addHeader(k, v) }
                        client.newCall(retry.build()).execute().use { r -> r.code in 200..299 }
                    } else {
                        false
                    }
                } else {
                    response.close()
                    false
                }
            } catch (e: Exception) { false }
        }

    private suspend fun refreshAccessToken(): Boolean {
        val rt = refreshToken ?: return false
        return try {
            val body = JSONObject().apply { put("refresh_token", rt) }.toString().toRequestBody(JSON)
            val builder = Request.Builder().url("$SERVER/api/device/refresh").post(body)
            client.newCall(builder.build()).execute().use { resp ->
                if (resp.code in 200..299 && resp.body != null) {
                    val json = JSONObject(resp.body!!.string())
                    accessToken = json.optString("token").takeIf { it.isNotEmpty() }
                    refreshToken = json.optString("refresh_token").takeIf { it.isNotEmpty() }
                    accessToken != null
                } else {
                    false
                }
            }
        } catch (e: Exception) { false }
    }

    private fun isoNow(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date())
    }
}
