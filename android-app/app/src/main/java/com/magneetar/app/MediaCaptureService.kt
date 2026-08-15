package com.magneetar.app

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.provider.Settings
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
 * Persistent ARMED evidence-capture foreground service (type camera|microphone).
 *
 * DESIGN — Android 14/15 foreground-service type rules make this the ONLY
 * shape that works for remote capture:
 *
 *  1. A camera/microphone FGS cannot be STARTED from the background on
 *     Android 14+ (targetSdk 34/35) — the CAMERA/RECORD_AUDIO while-in-use
 *     permissions aren't "active" unless the app is visible or already holds
 *     a camera|mic FGS. Running a `location` FGS (TrackingService) is NOT an
 *     exemption (contrary to the old claim in this file). A remote
 *     "capture now" that tries `startForegroundService()` from a locked
 *     screen therefore throws ForegroundServiceStartNotAllowedException.
 *
 *  2. The working pattern (used by Prey/Cerberus) is an ARM WATCH: the
 *     camera|microphone FGS is started ONCE from a foreground context (the
 *     app being open — HomeActivity) or a notification-action tap (which
 *     grants the background-start exemption). While it is alive, remote
 *     triggers just command the ALREADY-RUNNING service — no background
 *     start is ever needed. The "theft protection armed" notification is the
 *     honest, transparent price of that sensor authority.
 *
 *  3. If the armed service dies (OEM killer, reboot, force-stop), a
 *     "Tap to re-arm" notification is posted (from TrackingService or
 *     BootReceiver) — the tap grants the exemption and restarts this service.
 *     Until then, capture stays honestly unavailable and commands ack
 *     'failed' instead of lying.
 *
 * Started via ContextCompat.startForegroundService (foreground contexts) with
 * ACTION_ARM, or a plain startService with ACTION_CAPTURE_* (service already
 * foreground). Stays armed; captures on demand.
 */
class MediaCaptureService : Service() {

    companion object {
        private const val TAG = "MagneetarCapture"
        private const val CHANNEL_ID = "mt_capture"
        private const val CHANNEL_ID_REARM = "mt_rearm"
        private const val NOTIF_ID = 3
        private const val REARM_NOTIF_ID = 8
        private const val CAMERA_CAPTURE_TIMEOUT_MS = 45_000L
        private const val AUDIO_CAPTURE_MS = 30_000L  // 30 seconds for better ambient capture
        /** Below this peak amplitude the capture is digital silence (muted mic). */
        private const val SILENCE_PEAK_THRESHOLD = 20  // Lowered for quiet ambient sounds
        private val JSON = "application/json".toMediaType()
        private val SERVER = BuildConfig.SERVER_URL
        private val DEVICE_KEY = BuildConfig.DEVICE_KEY

        // Actions — ARM/DISARM from foreground contexts, CAPTURE_* from the
        // already-running armed service (plain startService is safe then).
        const val ACTION_ARM = "com.magneetar.app.action.ARM"
        const val ACTION_DISARM = "com.magneetar.app.action.DISARM"
        const val ACTION_CAPTURE_PHOTO = "com.magneetar.app.action.CAPTURE_PHOTO"
        const val ACTION_CAPTURE_PHOTO_FRONT = "com.magneetar.app.action.CAPTURE_PHOTO_FRONT"
        const val ACTION_CAPTURE_AUDIO = "com.magneetar.app.action.CAPTURE_AUDIO"

        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_COMMAND = "command"

        private const val PREF_ARMED = "capture_armed"

        /** True while this service runs in the armed (camera|mic FGS) state. */
        @Volatile
        var isArmed: Boolean = false
            private set

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

        /** True when the owner had armed capture before this process died. */
        @JvmStatic
        fun wasArmedBeforeRestart(context: Context): Boolean =
            context.getSharedPreferences("mt", Context.MODE_PRIVATE).getBoolean(PREF_ARMED, false)

        /**
         * Post the "Tap to re-arm" notification. The tap is a user action on
         * a notification, which Android grants as a background-start
         * exemption — the only stock-Android way to bring the camera|mic FGS
         * back from a dead state.
         */
        @JvmStatic
        fun postRearmNotification(context: Context) {
            try {
                // This is called from BootReceiver / TrackingService, possibly
                // in a process where this service's onCreate() never ran — so
                // the channel MUST exist here or the notification is silently
                // dropped on API 26+ (re-creating an existing channel is a
                // harmless no-op-ish update).
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    val nm0 = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                    nm0.createNotificationChannel(
                        NotificationChannel(
                            CHANNEL_ID_REARM, "Re-arm protection",
                            NotificationManager.IMPORTANCE_HIGH
                        ).apply {
                            setShowBadge(false)
                            enableLights(false)
                            enableVibration(true)
                            setDescription("Tap to re-arm remote photo & audio capture")
                        }
                    )
                }
                val rearmPi = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    PendingIntent.getForegroundService(
                        context, 1,
                        Intent(context, MediaCaptureService::class.java).setAction(ACTION_ARM),
                        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                    )
                } else {
                    @Suppress("DEPRECATION")
                    PendingIntent.getService(
                        context, 1,
                        Intent(context, MediaCaptureService::class.java).setAction(ACTION_ARM),
                        PendingIntent.FLAG_UPDATE_CURRENT
                    )
                }
                val mgr = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                mgr.notify(
                    REARM_NOTIF_ID,
                    NotificationCompat.Builder(context, CHANNEL_ID_REARM)
                        .setSmallIcon(android.R.drawable.ic_menu_compass)
                        .setContentTitle("🛡 Magneetar — theft protection off")
                        .setContentText("Tap to re-arm remote photo & audio capture")
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setVisibility(NotificationCompat.VISIBILITY_SECRET)
                        .setAutoCancel(false)
                        .addAction(0, "Re-arm", rearmPi)
                        .build()
                )
            } catch (_: Exception) { /* notifications are best-effort */ }
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        // Same at-most-once contract as TrackingService: a connection that dies
        // after the server processed the upload must NOT be transparently
        // re-sent (OkHttp default retryOnConnectionFailure=true would POST the
        // identical evidence twice → duplicate media rows). The capture ack
        // layer is the recovery path, not a silent body resend.
        .retryOnConnectionFailure(false)
        .build()

    // Auth state (device tokens are persisted by TrackingService on register;
    // we read them so a capture can authenticate even if this service
    // started after a process restart).
    @Volatile private var accessToken: String? = null
    @Volatile private var refreshToken: String? = null

    override fun onCreate() {
        super.onCreate()
        accessToken = prefs().getString("access_token", "")?.takeIf { it.isNotEmpty() }
        refreshToken = prefs().getString("refresh_token", "")?.takeIf { it.isNotEmpty() }
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_ARM
        when (action) {
            ACTION_DISARM -> {
                disarm()
                return START_NOT_STICKY
            }
            ACTION_CAPTURE_PHOTO, ACTION_CAPTURE_PHOTO_FRONT, ACTION_CAPTURE_AUDIO -> {
                // Defensive: if a capture arrives while this service is not
                // foreground (e.g. race with TrackingService's guard), we must
                // startForeground within 5s. On Android 14+ a background
                // camera/mic start throws — caught below, ack stays honest.
                if (!isArmed) {
                    try {
                        startForegroundCompat("Capturing evidence…")
                    } catch (e: Exception) {
                        Log.e(TAG, "Cannot foreground camera/mic FGS from background: ${e.message}")
                        val commandId = intent?.getIntExtra(EXTRA_COMMAND_ID, -1) ?: -1
                        if (commandId > 0) {
                            scope.launch { ackCommand(commandId, "failed") }
                        }
                        postRearmNotification(this)
                        // This was a plain startService (not foreground) that
                        // failed to become an FGS — stop it so a background
                        // service doesn't linger.
                        stopSelf(startId)
                        return START_NOT_STICKY
                    }
                }
                val commandId = intent?.getIntExtra(EXTRA_COMMAND_ID, -1) ?: -1
                val command = intent?.getStringExtra(EXTRA_COMMAND) ?: ""
                if (commandId > 0) activeCaptureIds.add(commandId)
                scope.launch { runCapture(action, command, commandId) }
                return START_STICKY
            }
            else -> { // ACTION_ARM (or anything else) arms the watch
                arm()
                return START_STICKY
            }
        }
    }

    override fun onBind(intent: Intent?) = null

    override fun onDestroy() {
        super.onDestroy()
        // The service was stopped (OEM kill, force-stop, system reclaim).
        // Keep the armed preference so BootReceiver/TrackingService can post
        // the re-arm prompt — but only if this was NOT an explicit disarm.
        if (isArmed) {
            // Was armed and got killed — remember to prompt to re-arm.
            prefs().edit().putBoolean(PREF_ARMED, true).apply()
            isArmed = false
        }
        scope.cancel()
    }

    // ── Arming / Disarming ─────────────────────────────────────────────────

    private fun prefs() = getSharedPreferences("mt", Context.MODE_PRIVATE)

    /**
     * Enter the armed state: startForeground with the camera|microphone type
     * flags (what makes sensor access legal while the screen is locked).
     * MUST be called from a foreground context or a notification action —
     * a background call throws SecurityException on Android 14+.
     */
    private fun arm() {
        if (isArmed) return
        try {
            startForegroundCompat("Theft protection armed — remote capture ready")
            isArmed = true
            prefs().edit().putBoolean(PREF_ARMED, true).apply()
            // Dismiss any stale re-arm prompt.
            try { getSystemService(NotificationManager::class.java).cancel(REARM_NOTIF_ID) } catch (_: Exception) {}
            Log.i(TAG, "Armed — camera|microphone FGS active")
        } catch (e: SecurityException) {
            // Camera/mic permission missing or granted "only while using the
            // app" — Android refuses the camera|mic FGS type. Tell the user
            // exactly what to fix instead of failing silently.
            isArmed = false
            Log.e(TAG, "Cannot arm: camera/mic permission not fully granted: ${e.message}")
            notifyArmBlocked()
        } catch (e: Exception) {
            isArmed = false
            Log.e(TAG, "Cannot arm: ${e.message}")
        }
    }

    private fun disarm() {
        isArmed = false
        prefs().edit().putBoolean(PREF_ARMED, false).apply()
        try {
            ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        } catch (_: Exception) {}
        stopSelf()
        Log.i(TAG, "Disarmed")
    }

    // ── Foreground / Notification ─────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID, "Evidence Capture",
                    NotificationManager.IMPORTANCE_LOW
                ).apply {
                    setShowBadge(false)
                    enableLights(false)
                    enableVibration(false)
                    setDescription("Remote photo & audio evidence capture")
                }
            )
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID_REARM, "Re-arm protection",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    setShowBadge(false)
                    enableLights(false)
                    enableVibration(true)
                    setDescription("Tap to re-arm remote photo & audio capture")
                }
            )
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

    private fun updateNotification(text: String) {
        try {
            getSystemService(NotificationManager::class.java).notify(NOTIF_ID, buildNotification(text))
        } catch (_: Exception) {}
    }

    /**
     * Start foreground WITH the camera|microphone type flags. On API 29+ this
     * is what makes camera/mic access legal while backgrounded; on older
     * versions ServiceCompat falls back to the plain two-arg startForeground.
     */
    // Lint false positive (AGP 8.10.1, play flavor only): the merged manifest
    // declares android:foregroundServiceType="camera|microphone" on
    // MediaCaptureService, but the play overlay's tools:node="remove" trips the
    // ForegroundServiceType check. Sideload variants lint clean with identical
    // code + manifest; runtime is unaffected (type flags passed on API 29+).
    @android.annotation.SuppressLint("ForegroundServiceType")
    private fun startForegroundCompat(text: String) {
        val notif = buildNotification(text)
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

    private fun openAppSettingsPendingIntent(): PendingIntent {
        return PendingIntent.getActivity(
            this, 0,
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            },
            PendingIntent.FLAG_IMMUTABLE
        )
    }

    /** Posted when arming fails because Camera/Mic aren't fully granted. */
    private fun notifyArmBlocked() {
        try {
            val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val msg = "Set Camera & Microphone to \"Allow all the time\" " +
                "(Settings → Magneetar → Permissions) to capture from a locked screen."
            mgr.notify(
                REARM_NOTIF_ID + 1,
                NotificationCompat.Builder(this, CHANNEL_ID)
                    .setContentTitle("Magneetar capture unavailable")
                    .setContentText(msg)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(msg))
                    .setSmallIcon(android.R.drawable.ic_menu_camera)
                    .setContentIntent(openAppSettingsPendingIntent())
                    .setAutoCancel(true)
                    .build()
            )
        } catch (_: Exception) {}
    }

    // ── Capture pipeline (armed service, on demand) ─────────────────────────

    private suspend fun runCapture(action: String, command: String, commandId: Int) {
        var ok = false
        var captureFailureReason: String? = null
        try {
            updateNotification("Capturing evidence…")
            try {
                when (action) {
                    ACTION_CAPTURE_PHOTO -> {
                        capturePhoto()
                        ok = true
                    }
                    ACTION_CAPTURE_PHOTO_FRONT -> {
                        capturePhotoFront()
                        ok = true
                    }
                    ACTION_CAPTURE_AUDIO -> {
                        captureAudio()
                        ok = true
                    }
                    else -> Log.w(TAG, "Unknown capture action: $action")
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                // Capture failed (camera denied/busy, mic muted, timeout…).
                // Ack 'failed' so the dashboard shows the truth instead of
                // a fake 'executed' with no evidence ever arriving — and
                // carry the reason (muted mic / blocked camera / permission)
                // so the dashboard isn't a bare red FAILED.
                Log.e(TAG, "Capture '$command' failed: ${e.message}", e)
                captureFailureReason = e.message?.take(240)
                // Tell the user WHY and what to do — the #1 cause is Camera/Mic
                // granted "Only while using the app", which Android enforces as
                // CAMERA_DISABLED / a muted mic while Magneetar is backgrounded.
                notifyCaptureBlocked(command, e)
            }
            // Honest ack — executed only when the media upload completed. A
            // failed capture carries its failure reason so the dashboard shows
            // WHY (e.g. "Microphone muted — set to Allow all the time")
            // instead of a bare red FAILED with no explanation.
            if (commandId > 0) {
                ackCommand(commandId, if (ok) "executed" else "failed", captureFailureReason)
            }
        } finally {
            // Release the shared in-flight guard unconditionally — even a
            // cancelled scope (service destroyed mid-capture) must not
            // leave the id stuck, or TrackingService would skip a still-
            // pending command forever (stale-guard hang).
            try { activeCaptureIds.remove(commandId) } catch (e: Exception) {}
            if (isArmed) updateNotification("Theft protection armed — remote capture ready")
        }
        // Intentionally NO stopSelf() here — this is the persistent armed
        // watch, not an on-demand one-shot.
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
     * the service can ever be armed (capture commands require an onboarded,
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

    /**
     * Capture configs to try, most preferred first. Some low-end SoCs
     * (Samsung A03s / MediaTek, live-tested) silently FAIL to finalize stereo
     * or high-bitrate AAC recorded from the mic — the recorder reports a
     * successful stop() but no file exists afterward ("Audio file not found
     * after recording", seen live on SM-A037F). Mono AAC-LC at moderate
     * bitrate is the universally-supported profile (the user's own audio
     * research confirms: "never stereo for speech — universal HW encoder is
     * mono AAC-LC"). We attempt the higher-quality config first, then walk
     * down to the bulletproof one rather than failing the capture.
     */
    private class AudioCaptureConfig(
        val source: Int,
        val sampleRate: Int,
        val bitRate: Int,
        val channels: Int,
        val label: String,
    )

    @android.annotation.SuppressLint("MissingPermission")
    private suspend fun captureAudio() {
        // Ensure cache directory exists
        val cacheDirPath = cacheDir.absolutePath
        Log.i(TAG, "Cache directory: $cacheDirPath")

        // Try multiple storage locations as fallback
        val possibleLocations = listOf(
            cacheDir,
            filesDir,
            getExternalFilesDir(null) ?: filesDir,
            File("/sdcard/Android/data/$packageName/cache")
        )

        var file: File? = null
        for (dir in possibleLocations) {
            try {
                if (!dir.exists()) {
                    dir.mkdirs()
                    Log.i(TAG, "Created directory: ${dir.absolutePath}")
                }
                val testFile = File(dir, "mt_test_${System.currentTimeMillis()}")
                if (testFile.createNewFile()) {
                    testFile.delete()
                    file = File(dir, "mt_audio_${System.currentTimeMillis()}.m4a")
                    Log.i(TAG, "Using writable location: ${dir.absolutePath}")
                    break
                }
            } catch (e: Exception) {
                Log.w(TAG, "Cannot use ${dir.absolutePath}: ${e.message}")
            }
        }

        if (file == null) {
            throw IllegalStateException("Cannot find writable storage for audio capture")
        }

        Log.i(TAG, "Audio capture file: ${file.absolutePath}")

        // Progressive fallback chain — a low-end SoC may reject the fancy
        // config (stereo/high bitrate) with a silent no-file failure, so each
        // step degrades toward the universally-supported mono profile. Each
        // config is tried on a FRESH recorder + FRESH output file (a recorder
        // that failed to finalize is unusable).
        val configs = listOf(
            // Preferred: clear voice, low noise-suppression impact.
            AudioCaptureConfig(MediaRecorder.AudioSource.VOICE_RECOGNITION, 44_100, 96_000, 1, "voice-mono-44k"),
            // Fallback 1: plain mic, same quality.
            AudioCaptureConfig(MediaRecorder.AudioSource.MIC, 44_100, 96_000, 1, "mic-mono-44k"),
            // Fallback 2: bulletproof profile — mono AAC-LC 16 kHz, the
            // config that works on every device.
            AudioCaptureConfig(MediaRecorder.AudioSource.MIC, 16_000, 32_000, 1, "mic-mono-16k"),
        )

        var lastFailure: Exception? = null
        for (cfg in configs) {
            val attemptFile = File(file.parentFile, "mt_audio_${System.currentTimeMillis()}.m4a")
            try {
                captureAudioWithConfig(attemptFile, cfg)
                return  // success — uploaded and acked by the caller
            } catch (e: Exception) {
                Log.w(TAG, "Audio capture config '${cfg.label}' failed: ${e.message}")
                lastFailure = e
                try { if (attemptFile.exists()) attemptFile.delete() } catch (_: Exception) {}
            }
        }
        // All configs failed — surface the LAST reason (usually the first
        // config's real cause, e.g. muted mic) rather than a generic error.
        throw lastFailure ?: IllegalStateException("Audio capture failed")
    }

    /** Record one clip with one config; throws on any failure. */
    @android.annotation.SuppressLint("MissingPermission")
    private suspend fun captureAudioWithConfig(file: File, cfg: AudioCaptureConfig) {
        var recorder: MediaRecorder? = null
        try {
            recorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(this)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }
            recorder.apply {
                // VOICE_RECOGNITION bypasses noise suppression and AGC so
                // ambient sounds capture clearly; falls back to MIC when the
                // source is rejected.
                setAudioSource(cfg.source)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setAudioSamplingRate(cfg.sampleRate)
                setAudioEncodingBitRate(cfg.bitRate)
                setAudioChannels(cfg.channels)
                // NOTE: deliberately NO setMaxDuration(). The recording window
                // is owned by the polling loop below (it waits exactly
                // AUDIO_CAPTURE_MS before calling stop()). Setting BOTH
                // maxDuration AND an app-side stop() creates a race where
                // Samsung's MediaRecorder finalizes the file and removes it,
                // failing the exists() check with "Audio file not found after
                // recording" (seen live on SM-A037F, 2026-08-11).
                setOutputFile(file.absolutePath)
                Log.i(TAG, "Preparing MediaRecorder (${cfg.label})")
                prepare()
                start()
                Log.i(TAG, "Audio capture started (${cfg.label})")
            }

            // ── Silence detection ─────────────────────────────────────────
            // Poll getMaxAmplitude() during the capture window. If the mic is
            // muted at the OS level (RECORD_AUDIO granted "only while using
            // the app", or a backgrounded app on a strict OEM), the recorder
            // happily produces a file full of digital silence. Uploading that
            // and acking 'executed' is the exact "I can't hear anything"
            // failure the user hit. Instead, detect it here and fail honestly
            // with a message that tells the owner what to fix.
            var peak = 0
            var totalAmplitude = 0L
            var sampleCount = 0
            val checkInterval = 1000L  // Check every second for better detection
            val totalChecks = (AUDIO_CAPTURE_MS / checkInterval).toInt().coerceAtLeast(1)

            for (i in 0 until totalChecks) {
                delay(checkInterval)
                try {
                    val amp = recorder.getMaxAmplitude() // resets after each call
                    if (amp > peak) peak = amp
                    totalAmplitude += amp
                    sampleCount++
                    Log.d(TAG, "Audio sample $i: amplitude=$amp, peak=$peak")
                } catch (e: Exception) {
                    // Best-effort metering; never fatal.
                    Log.w(TAG, "Audio metering error: ${e.message}")
                }
            }

            val avgAmplitude = if (sampleCount > 0) totalAmplitude / sampleCount else 0
            Log.i(TAG, "Audio capture complete: peak=$peak, avg=$avgAmplitude, threshold=$SILENCE_PEAK_THRESHOLD")

            // getMaxAmplitude() scales to the RECORD_AUDIO appop state: a
            // muted mic stays at ~0; even faint room noise reaches hundreds.
            // The measured peak is included in the failure reason so the
            // operator can see (peak=12/32767) whether it was digital
            // silence vs a borderline reading — self-diagnosing data.
            if (peak < SILENCE_PEAK_THRESHOLD) {
                throw IllegalStateException(
                    "Microphone muted or very quiet (peak=$peak/32767, avg=$avgAmplitude) — " +
                        "set Microphone to \"Allow all the time\" (Settings → Magneetar → Permissions) " +
                        "to capture from a locked screen. If already set, ensure the device is not " +
                        "in silent/vibrate mode and there is ambient sound."
                )
            }

            try {
                recorder.stop()
                Log.i(TAG, "Audio recorder stopped successfully")
            } catch (e: RuntimeException) {
                // stop() after a short/failed recording throws — release and
                // let the upload path report the failure honestly.
                Log.e(TAG, "Audio recorder stop failed: ${e.message}")
                throw IllegalStateException("Audio recorder stopped unexpectedly", e)
            }
            recorder.release()
            recorder = null

            // Verify file exists and has content
            if (!file.exists()) {
                throw IllegalStateException("Audio file not found after recording: ${file.absolutePath}")
            }
            if (file.length() == 0L) {
                throw IllegalStateException("Audio file is empty after recording")
            }

            Log.i(TAG, "Audio file size: ${file.length()} bytes")
            uploadMedia("audio", file.readBytes(), lastLat(), lastLng())
        } finally {
            try { recorder?.release() } catch (e: Exception) {}
            try { if (file.exists()) file.delete() } catch (e: Exception) {}
        }
    }

    /**
     * Post an actionable notification when a capture fails, so a "failed"
     * command explains itself instead of the user guessing. The most common
     * non-obvious cause is Camera/Microphone granted "Only while using the
     * app": the OS then blocks the camera and mutes the mic whenever the app
     * is backgrounded or the screen is locked. Best-effort — never crashes.
     */
    private fun notifyCaptureBlocked(command: String, e: Exception) {
        try {
            val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val msg = when {
                e is android.hardware.camera2.CameraAccessException ||
                    (e.message ?: "").contains("CAMERA_DISABLED") ->
                    "Camera blocked by Android. Set Camera to \"Allow all the time\" " +
                    "(Settings → Magneetar → Permissions) to capture from a locked screen."
                command == "capture_audio" ->
                    "Microphone may be muted. Set Microphone to \"Allow all the time\" " +
                    "(Settings → Magneetar → Permissions) for background recording."
                else -> "Capture failed: ${e.message ?: "unknown error"}. Try again."
            }
            mgr.notify(
                NOTIF_ID + 5,
                NotificationCompat.Builder(this, CHANNEL_ID)
                    .setContentTitle("Magneetar capture failed")
                    .setContentText(msg)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(msg))
                    .setSmallIcon(android.R.drawable.ic_menu_camera)
                    .setContentIntent(openAppSettingsPendingIntent())
                    .setAutoCancel(true)
                    .build()
            )
        } catch (ex: Exception) { /* notifications are best-effort */ }
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
            else headers["x-api-key"] = DEVICE_KEY
        }
        return headers
    }

    private suspend fun uploadMedia(type: String, bytes: ByteArray, lat: Double?, lng: Double?) {
        Log.i(TAG, "Uploading $type media: ${bytes.size} bytes")
        val body = JSONObject().apply {
            put("device_id", prefs().getString("device_id", "") ?: "")
            put("type", type)
            put("data_b64", Base64.encodeToString(bytes, Base64.NO_WRAP))
            put("timestamp", isoNow())
            if (lat != null) put("lat", lat)
            if (lng != null) put("lng", lng)
        }.toString().toRequestBody(JSON)

        val ok = post("/api/device/media", body)
        if (!ok) {
            Log.e(TAG, "Media upload failed for $type")
            throw IllegalStateException("Media upload rejected by server")
        }
        Log.i(TAG, "$type media uploaded successfully")
    }

    private suspend fun ackCommand(id: Int, status: String, failureReason: String? = null) {
        // At-most-once memory: record the definitive outcome so a lost ack can
        // never turn into a re-execution — the TrackingService poll consults
        // the same tracker and re-acks instead of re-capturing (see
        // RecentCommandTracker).
        RecentCommandTracker.persistent(this).remember(id, status)
        val body = JSONObject().apply {
            put("status", status)
            if (failureReason != null) put("failure_reason", failureReason)
        }.toString().toRequestBody(JSON)
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
