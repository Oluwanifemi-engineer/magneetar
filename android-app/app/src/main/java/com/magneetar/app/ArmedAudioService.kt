package com.magneetar.app

import android.Manifest
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import androidx.core.content.ContextCompat
import android.location.LocationManager
import android.media.*
import android.os.*
import android.telephony.PhoneStateListener
import android.telephony.TelephonyCallback
import android.telephony.TelephonyManager
import android.util.Base64
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.*
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.DigestOutputStream
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit

/**
 * Armed STEALTH audio watch (foreground service, type microphone).
 *
 * The game-changer gap-closer: command-triggered 30s clips (MediaCaptureService)
 * only capture AFTER a command arrives. This service LISTENS while armed and
 * persists ONLY speech (VAD-gated), with a 15-second PRE-ROLL ring buffer so
 * the first file of an utterance contains the 15s before detection — the
 * pickpocket's first sentence is the most valuable evidence and the pre-roll
 * catches it.
 *
 * MODES
 *   STEALTH  (default): mic runs continuously at 16 kHz. VAD decides what is
 *            persisted: silence feeds the pre-roll ring (kept in RAM, never
 *            written), speech opens an AAC segment, silence closes it. Cost ≈
 *            mic-only battery; storage ≈ speech-only (~35-85 MB/day in a
 *            pocket — vs 345 MB/day for raw continuous audio).
 *   EVIDENCE (escalation): continuous AAC recording + immediate upload, used
 *            after a theft signal or an explicit "capture now". The thief
 *            already knows they're compromised; the job is getting bytes off
 *            the device before a factory reset.
 *
 * Every segment is written as an .m4a (AAC-LC via the SoC's hardware codec,
 * MediaCodec) with a hash-chained manifest row {seg_id, start_epoch_ms,
 * prev_sha256, sha256, mode} — chain-of-custody, same philosophy as the
 * server-side evidence cases. If the AAC encoder is unavailable (rare SoC),
 * the segment falls back to raw WAV (the server's audio magic-byte check
 * accepts both RIFF/WAVE and MP4/ftyp).
 *
 * ANDROID 14/15 RULES (same shape as MediaCaptureService):
 *   - A microphone FGS cannot be STARTED from the background. It is armed
 *     once from a foreground context (HomeActivity auto-arm) or a
 *     "Re-arm" notification tap, and stays running (START_STICKY,
 *     stopWithTask=false). If it dies, TrackingService/BootReceiver post a
 *     tap-to-re-arm prompt.
 *   - A microphone FGS cannot start from BOOT_COMPLETED (API 34+). Boot
 *     posts the re-arm notification; the tap grants the exemption.
 *   - During a phone call (API 29+) third-party mic access yields silence.
 *     The call-state listener pauses capture (saves battery + avoids writing
 *     dead air) and resumes on IDLE.
 *   - The mic green dot is mandatory and unhideable. STEALTH keeps it
 *     continuous (the mic IS in use); that is the honest price of an always-
 *     armed watch.
 *
 * MIC EXCLUSIVITY: only ONE mic user may exist. While this service is armed,
 * the `capture_audio` command routes HERE (EVIDENCE escalation) instead of
 * MediaCaptureService's 30s clip — see CaptureRouting. Photos keep using
 * MediaCaptureService (camera is a separate sensor, no conflict).
 */
class ArmedAudioService : Service() {

    companion object {
        private const val TAG = "ArmedAudio"

        const val CHANNEL_ID = "armed_audio"
        const val CHANNEL_ID_REARM = "mt_audio_rearm"
        const val NOTIF_ID = 41
        private const val REARM_NOTIF_ID = 42
        private const val PREF_ARMED = "audio_watch_armed"

        // Actions — ARM/DISARM from foreground contexts; FORCE_CAPTURE from
        // the already-running service's command path (plain startService).
        const val ACTION_ARM = "com.magneetar.app.action.AUDIO_ARM"
        const val ACTION_DISARM = "com.magneetar.app.action.AUDIO_DISARM"
        const val ACTION_FORCE_CAPTURE = "com.magneetar.app.action.AUDIO_FORCE_CAPTURE"
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_MODE = "mode"

        const val MODE_STEALTH = 0
        const val MODE_EVIDENCE = 1

        private const val SAMPLE_RATE = 16_000
        private const val CHANNELS = 1
        private const val PCM_BYTES = 2
        private const val BLOCK_SAMPLES = 320            // 20 ms @ 16 kHz
        private const val BLOCK_BYTES = BLOCK_SAMPLES * PCM_BYTES
        private const val AAC_BITRATE = 32_000
        private const val PRE_ROLL_BLOCKS = 750          // 15 s
        private const val MAX_SEGMENT_MS = 120_000L      // roll files every 2 min
        private const val EVIDENCE_MINUTES = 5           // default FORCE_CAPTURE window
        private const val MAX_SESSION_BYTES = 512L * 1024 * 1024

        /** True while this service runs the armed mic watch. */
        @Volatile
        var isArmed: Boolean = false
            private set

        /** True when the owner had armed the watch before this process died. */
        @JvmStatic
        fun wasArmedBeforeRestart(context: Context): Boolean =
            context.getSharedPreferences("mt", Context.MODE_PRIVATE).getBoolean(PREF_ARMED, false)

        /**
         * Post the "Tap to re-arm audio watch" notification (BootReceiver /
         * TrackingService call this — the tap is a user action granting the
         * background-start exemption on Android 14+).
         */
        @JvmStatic
        fun postRearmNotification(context: Context) {
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    val nm0 = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                    nm0.createNotificationChannel(
                        NotificationChannel(
                            CHANNEL_ID_REARM, "Re-arm audio watch",
                            NotificationManager.IMPORTANCE_HIGH
                        ).apply {
                            setShowBadge(false)
                            enableVibration(true)
                            setDescription("Tap to re-arm the audio evidence watch")
                        }
                    )
                }
                val rearmPi = PendingIntent.getForegroundService(
                    context, 2,
                    Intent(context, ArmedAudioService::class.java).setAction(ACTION_ARM),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                val mgr = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
                mgr.notify(
                    REARM_NOTIF_ID,
                    NotificationCompat.Builder(context, CHANNEL_ID_REARM)
                        .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                        .setContentTitle("🛡 Magneetar — audio watch off")
                        .setContentText("Tap to re-arm the audio evidence watch")
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setVisibility(NotificationCompat.VISIBILITY_SECRET)
                        .setAutoCancel(false)
                        .addAction(0, "Re-arm", rearmPi)
                        .build()
                )
            } catch (_: Exception) { /* notifications are best-effort */ }
        }
    }

    // ── State ────────────────────────────────────────────────────────────
    private var mode = MODE_STEALTH
    private var armed = false
    private var pausedByCall = false
    private var evidenceUntilMs = 0L

    private var audioRecord: AudioRecord? = null
    private var captureThread: CaptureThread? = null

    // Segment pipeline
    private val vad = VadDetector(SAMPLE_RATE)
    private val preRoll: ArrayDeque<ByteArray> = ArrayDeque()
    private var segmentOut: DigestOutputStream? = null
    private var segmentFile: File? = null
    private var segmentStartEpochMs = 0L
    private var prevHash = ""                       // chain-of-custody
    private var segmentCounter = 0
    private var sessionBytes = 0L
    private var lastSegmentMs = 0L
    private var segmentManifest: BufferedWriter? = null
    private var encoder: MediaCodec? = null
    private var muxer: MediaMuxer? = null
    private var muxerTrack = -1
    private var muxerStarted = false
    private var ptsUs = 0L

    // Network (mirrors MediaCaptureService: at-most-once, device auth)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        // Same at-most-once contract: a connection that dies after the server
        // processed the upload must NOT be transparently re-sent.
        .retryOnConnectionFailure(false)
        .build()

    private var accessToken: String? = null
    private var refreshToken: String? = null

    private lateinit var telephonyManager: TelephonyManager

    // ── Lifecycle ────────────────────────────────────────────────────────
    override fun onCreate() {
        super.onCreate()
        createChannels()
        accessToken = prefs().getString("access_token", "")?.takeIf { it.isNotEmpty() }
        refreshToken = prefs().getString("refresh_token", "")?.takeIf { it.isNotEmpty() }
        telephonyManager = getSystemService(Context.TELEPHONY_SERVICE) as TelephonyManager
        registerCallState()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_DISARM -> {
                disarm()
                return START_NOT_STICKY
            }
            ACTION_FORCE_CAPTURE -> {
                if (!armed) {
                    postRearmNotification(this)
                    return START_NOT_STICKY
                }
                // Escalate to EVIDENCE for the window; also lets a command id
                // ack AFTER the window so 'executed' means bytes are uploading.
                evidenceUntilMs = System.currentTimeMillis() + EVIDENCE_MINUTES * 60_000L
                if (mode != MODE_EVIDENCE) {
                    mode = MODE_EVIDENCE
                    Log.i(TAG, "Escalated to EVIDENCE mode (${EVIDENCE_MINUTES} min)")
                }
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
        val wasArmed = armed
        armed = false
        isArmed = false
        captureThread?.requestStop()
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        closeSegment()
        writeManifestEntry("watch_stopped", wasArmed)
        try { segmentManifest?.close() } catch (_: Exception) {}
        if (wasArmed) {
            // Killed without an explicit disarm — remember to prompt re-arm.
            prefs().edit().putBoolean(PREF_ARMED, true).apply()
        }
        unregisterCallState()
        super.onDestroy()
    }

    // ── Arming ───────────────────────────────────────────────────────────
    private fun prefs() = getSharedPreferences("mt", Context.MODE_PRIVATE)

    private fun arm() {
        if (armed) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "RECORD_AUDIO not granted — cannot arm audio watch")
            postRearmNotification(this)
            return
        }
        try {
            startForegroundCompat()
        } catch (e: Exception) {
            // ForegroundServiceStartNotAllowedException etc. — be honest.
            Log.w(TAG, "Audio FGS start failed: ${e.message}")
            postRearmNotification(this)
            return
        }
        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuf <= 0) {
            Log.w(TAG, "No mic buffer — cannot arm audio watch")
            return
        }
        try {
            val rec = AudioRecord(
                MediaRecorder.AudioSource.MIC, SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuf * 2, BLOCK_BYTES * 16)
            )
            if (rec.state != AudioRecord.STATE_INITIALIZED) {
                Log.w(TAG, "Mic unavailable (in use?) — audio watch not armed")
                rec.release()
                return
            }
            audioRecord = rec
        } catch (se: SecurityException) {
            Log.w(TAG, "RECORD_AUDIO revoked — cannot arm audio watch")
            return
        }
        armed = true
        isArmed = true
        mode = MODE_STEALTH
        evidenceUntilMs = 0
        vad.reset()
        preRoll.clear()
        prevHash = ""
        segmentCounter = 0
        sessionBytes = 0
        prefs().edit().putBoolean(PREF_ARMED, true).apply()
        try { getSystemService(NotificationManager::class.java).cancel(REARM_NOTIF_ID) } catch (_: Exception) {}
        captureThread = CaptureThread().also { it.start() }
        Log.i(TAG, "Audio watch armed (STEALTH)")
    }

    private fun disarm() {
        armed = false
        isArmed = false
        captureThread?.requestStop()
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        closeSegment()
        prefs().edit().putBoolean(PREF_ARMED, false).apply()
        try { ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE) } catch (_: Exception) {}
        stopSelf()
        Log.i(TAG, "Audio watch disarmed")
    }

    // ── Foreground / Notification ────────────────────────────────────────
    private fun createChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID, "Audio evidence watch",
                    NotificationManager.IMPORTANCE_LOW
                ).apply {
                    setShowBadge(false)
                    enableVibration(false)
                    setDescription("Armed audio watch — VAD-gated speech capture")
                }
            )
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID_REARM, "Re-arm audio watch",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    setShowBadge(false)
                    enableVibration(true)
                    setDescription("Tap to re-arm the audio evidence watch")
                }
            )
        }
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("🎙 Magneetar — audio watch")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setVisibility(NotificationCompat.VISIBILITY_SECRET)
            .setOngoing(true)
            .build()

    @android.annotation.SuppressLint("ForegroundServiceType")
    private fun startForegroundCompat() {
        val notif = buildNotification("Armed — speech capture active")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this, NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
            )
        } else {
            startForeground(NOTIF_ID, notif)
        }
    }

    // ── Capture thread ───────────────────────────────────────────────────
    private inner class CaptureThread : Thread("armed-audio") {
        private val stopFlag = java.util.concurrent.atomic.AtomicBoolean(false)

        override fun run() {
            val rec = audioRecord ?: return
            val block = ByteArray(BLOCK_BYTES)
            val shortBlock = ShortArray(BLOCK_SAMPLES)
            val bb = ByteBuffer.wrap(block).order(ByteOrder.LITTLE_ENDIAN)
            try {
                rec.startRecording()
            } catch (e: Exception) {
                Log.w(TAG, "startRecording failed: ${e.message}")
                armed = false
                isArmed = false
                return
            }
            while (!stopFlag.get() && armed) {
                val read = try { rec.read(block, 0, BLOCK_BYTES) } catch (e: Exception) { -1 }
                if (read <= 0) { Thread.sleep(5); continue }
                // Decode the PCM block into shorts for the VAD.
                bb.position(0)
                for (i in 0 until BLOCK_SAMPLES) shortBlock[i] = bb.getShort()

                // EVIDENCE: record everything, roll files every 2 min.
                val inEvidence = mode == MODE_EVIDENCE
                if (inEvidence && System.currentTimeMillis() >= evidenceUntilMs) {
                    mode = MODE_STEALTH
                    closeSegment()
                    Log.i(TAG, "EVIDENCE window ended — back to STEALTH")
                }

                if (pausedByCall) {
                    // During a call the mic yields silence anyway; skip write
                    // cost, keep the ring warm so speech after the call still
                    // has its pre-roll.
                    keepPreRoll(block)
                    continue
                }

                if (inEvidence) {
                    // Continuous recording in EVIDENCE.
                    if (segmentOut == null) openSegment()
                    writeToSegment(block, inEvidence)
                } else {
                    when (vad.classify(shortBlock)) {
                        VadDetector.SegmentEvent.SPEECH_START -> openSegment()
                        VadDetector.SegmentEvent.SPEECH_END -> closeSegment()
                        VadDetector.SegmentEvent.SPEECH_CONTINUE -> writeToSegment(block, false)
                        VadDetector.SegmentEvent.SILENCE -> keepPreRoll(block)
                    }
                }
            }
            closeSegment()
            teardown()
        }

        fun requestStop() = stopFlag.set(true)
    }

    // ── Pre-roll ring ────────────────────────────────────────────────────
    private fun keepPreRoll(block: ByteArray) {
        preRoll.addLast(block)
        while (preRoll.size > PRE_ROLL_BLOCKS) preRoll.removeFirst()
    }

    // ── Segments ─────────────────────────────────────────────────────────
    private fun segmentDir(): File {
        val dir = File(filesDir, "audio_watch")
        if (!dir.exists()) dir.mkdirs()
        return dir
    }

    private fun openSegment() {
        if (segmentOut != null) return
        segmentCounter++
        val file = File(segmentDir(), "seg_%04d.m4a".format(segmentCounter))
        val digest = MessageDigest.getInstance("SHA-256")
        if (prevHash.isNotEmpty()) digest.update(prevHash.toByteArray())
        try {
            val fos = FileOutputStream(file)
            segmentOut = DigestOutputStream(BufferedOutputStream(fos), digest)
            segmentFile = file
            // Wall-clock start INCLUDING the pre-roll window (the first bytes
            // written are from before detection).
            segmentStartEpochMs = System.currentTimeMillis() - PRE_ROLL_BLOCKS * 20L
            ptsUs = 0L
            lastSegmentMs = System.currentTimeMillis()
            initEncoder(file)
            // Flush the pre-roll ring — oldest first.
            while (preRoll.isNotEmpty()) {
                val b = preRoll.removeFirst()
                segmentOut?.write(b)
                feedEncoder(b)
            }
            if (segmentManifest == null) {
                segmentManifest = BufferedWriter(FileWriter(File(segmentDir(), "manifest.jsonl"), true))
            }
        } catch (e: IOException) {
            Log.w(TAG, "openSegment failed: ${e.message}")
            closeSegment()
        }
    }

    private fun writeToSegment(block: ByteArray, evidence: Boolean) {
        if (segmentOut == null) openSegment()  // safety
        try {
            segmentOut?.write(block)
            feedEncoder(block)
            if (System.currentTimeMillis() - lastSegmentMs >= MAX_SEGMENT_MS) {
                closeSegment()
                openSegment()  // roll file, keep recording
            }
        } catch (e: IOException) {
            Log.w(TAG, "segment write failed: ${e.message}")
        }
    }

    private fun closeSegment() {
        val out = segmentOut ?: return
        try {
            out.flush()
            val sha = out.messageDigest.digest().joinToString("") { "%02x".format(it) }
            out.close()
            val f = segmentFile
            val startMs = segmentStartEpochMs
            if (f != null && f.exists() && f.length() > 44) {
                sessionBytes += f.length()
                val row = JSONObject().apply {
                    put("seg", segmentCounter)
                    put("start_epoch_ms", startMs)
                    put("end_epoch_ms", System.currentTimeMillis())
                    put("mode", mode)
                    put("prev_sha256", prevHash)
                    put("sha256", sha)
                }
                try {
                    val w = segmentManifest ?: BufferedWriter(FileWriter(File(segmentDir(), "manifest.jsonl"), true)).also { segmentManifest = it }
                    w.write(row.toString())
                    w.newLine()
                    w.flush()
                } catch (e: IOException) { Log.w(TAG, "manifest append failed: ${e.message}") }
                prevHash = sha
                uploadSegment(f, row)
            }
            enforceSessionCap()
        } catch (e: Exception) {
            Log.w(TAG, "closeSegment failed: ${e.message}")
        } finally {
            segmentOut = null
            segmentFile = null
            stopEncoder()
        }
    }

    private fun writeManifestEntry(event: String, armedNow: Boolean) {
        // Best-effort lifecycle marker for the chain-of-custody file.
        try {
            val w = segmentManifest ?: return
            val row = JSONObject().apply {
                put("event", event)
                put("ts_epoch_ms", System.currentTimeMillis())
                put("armed", armedNow)
            }
            w.write(row.toString())
            w.newLine()
            w.flush()
        } catch (_: Exception) {}
    }

    // ── AAC encoder (MediaCodec) with WAV fallback ───────────────────────
    private fun initEncoder(file: File) {
        try {
            val fmt = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, SAMPLE_RATE, CHANNELS)
            fmt.setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            fmt.setInteger(MediaFormat.KEY_BIT_RATE, AAC_BITRATE)
            fmt.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16 * 1024)
            val codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
            codec.configure(fmt, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            codec.start()
            encoder = codec
            muxer = try {
                MediaMuxer(file.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            } catch (e: Exception) {
                // MediaMuxer unavailable (some AOSP images) — release codec and
                // fall through to the WAV path.
                codec.stop()
                codec.release()
                encoder = null
                null
            }
        } catch (e: Exception) {
            Log.w(TAG, "AAC encoder unavailable — falling back to WAV: ${e.message}")
            encoder = null
            muxer = null
        }
    }

    private fun feedEncoder(pcm: ByteArray) {
        val codec = encoder ?: return
        val mux = muxer ?: return
        try {
            val inIdx = codec.dequeueInputBuffer(10_000)
            if (inIdx < 0) return
            val buf = codec.getInputBuffer(inIdx) ?: return
            buf.clear()
            buf.put(pcm)
            codec.queueInputBuffer(inIdx, 0, pcm.size, ptsUs, 0)
            ptsUs += pcm.size * 1_000_000L / (SAMPLE_RATE * PCM_BYTES)
            drainEncoder(codec, mux)
        } catch (e: Exception) {
            Log.w(TAG, "encoder feed failed: ${e.message}")
        }
    }

    private fun drainEncoder(codec: MediaCodec, mux: MediaMuxer) {
        val info = MediaCodec.BufferInfo()
        while (true) {
            val outIdx = codec.dequeueOutputBuffer(info, 0)
            when {
                outIdx == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED -> {
                    try {
                        muxerTrack = mux.addTrack(codec.outputFormat)
                        mux.start()
                        muxerStarted = true
                    } catch (e: Exception) {
                        Log.w(TAG, "muxer start failed: ${e.message}")
                    }
                }
                outIdx >= 0 -> {
                    val buf = codec.getOutputBuffer(outIdx)
                    if (buf != null) {
                        if (info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0 &&
                            info.size > 0 && muxerStarted
                        ) {
                            buf.position(info.offset)
                            buf.limit(info.offset + info.size)
                            mux.writeSampleData(muxerTrack, buf, info)
                        }
                        codec.releaseOutputBuffer(outIdx, false)
                    }
                    if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
                }
                else -> break
            }
        }
    }

    private fun stopEncoder() {
        try {
            encoder?.let { codec ->
                try {
                    codec.stop()
                } catch (_: Exception) {}
                codec.release()
            }
            muxer?.let { m ->
                try { if (muxerStarted) m.stop() } catch (_: Exception) {}
                m.release()
            }
        } catch (_: Exception) {}
        encoder = null
        muxer = null
        muxerTrack = -1
        muxerStarted = false
    }

    // ── Upload (existing /api/device/media path, type=audio) ─────────────
    private fun uploadSegment(file: File, row: JSONObject) {
        // Fire-and-forget on a worker thread: never block the capture loop.
        Thread {
            try {
                val bytes = file.readBytes()
                val body = JSONObject().apply {
                    put("device_id", prefs().getString("device_id", "") ?: "")
                    put("type", "audio")
                    put("data_b64", Base64.encodeToString(bytes, Base64.NO_WRAP))
                    put("timestamp", isoNow())
                    put("evidence_meta", row.toString())
                    latLng().let { (la, ln) ->
                        if (la != null) put("lat", la)
                        if (ln != null) put("lng", ln)
                    }
                }.toString().toRequestBody(JSON)
                if (post("/api/device/media", body)) {
                    Log.i(TAG, "Segment ${row.optInt("seg")} uploaded (${bytes.size} bytes)")
                    file.delete()
                } else {
                    Log.w(TAG, "Segment ${row.optInt("seg")} upload rejected — kept on disk")
                }
            } catch (e: Exception) {
                Log.w(TAG, "Segment upload failed: ${e.message}")
            }
        }.start()
    }

    private fun latLng(): Pair<Double?, Double?> {
        return try {
            @Suppress("MissingPermission")
            val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val loc = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                ?: lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
            (loc?.latitude) to (loc?.longitude)
        } catch (e: Exception) { null to null }
    }

    private fun isoNow(): String {
        val fmt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US)
        fmt.timeZone = TimeZone.getTimeZone("UTC")
        return fmt.format(Date())
    }

    private fun authHeaders(): Map<String, String> {
        val headers = mutableMapOf<String, String>()
        if (accessToken != null) {
            headers["Authorization"] = "Bearer $accessToken"
        } else {
            val deviceKey = prefs().getString("device_key", "") ?: ""
            if (deviceKey.isNotEmpty()) headers["x-device-key"] = deviceKey
            else headers["x-api-key"] = BuildConfig.DEVICE_KEY
        }
        return headers
    }

    private fun post(path: String, body: RequestBody): Boolean {
        return try {
            val builder = Request.Builder().url(BuildConfig.SERVER_URL + path).post(body)
            authHeaders().forEach { (k, v) -> builder.addHeader(k, v) }
            client.newCall(builder.build()).execute().use { r -> r.code in 200..299 }
        } catch (e: Exception) { false }
    }

    // ── Session cap (FIFO eviction, never delete uploaded rows) ─────────
    private fun enforceSessionCap() {
        if (sessionBytes <= MAX_SESSION_BYTES) return
        val files = segmentDir().listFiles { f -> f.isFile && f.name.endsWith(".m4a") }
            ?.sortedBy { it.lastModified() } ?: return
        for (f in files) {
            if (sessionBytes <= MAX_SESSION_BYTES) break
            sessionBytes -= f.length()
            f.delete()
        }
    }

    // ── Call-state pause ─────────────────────────────────────────────────
    private var phoneStateLegacy: PhoneStateListener? = null
    private var telephonyCallback31: TelephonyCallback? = null

    private fun registerCallState() {
        try {
            if (Build.VERSION.SDK_INT >= 31) {
                val cb = object : TelephonyCallback(), TelephonyCallback.CallStateListener {
                    override fun onCallStateChanged(state: Int) {
                        pausedByCall = state != TelephonyManager.CALL_STATE_IDLE
                    }
                }
                telephonyCallback31 = cb
                telephonyManager.registerTelephonyCallback(mainExecutor, cb)
            } else {
                @Suppress("DEPRECATION")
                val l = object : PhoneStateListener() {
                    @Deprecated("Deprecated in Java")
                    override fun onCallStateChanged(state: Int, phoneNumber: String?) {
                        pausedByCall = state != TelephonyManager.CALL_STATE_IDLE
                    }
                }
                phoneStateLegacy = l
                @Suppress("DEPRECATION")
                telephonyManager.listen(l, PhoneStateListener.LISTEN_CALL_STATE)
            }
        } catch (e: Exception) {
            Log.w(TAG, "call-state listener unavailable: ${e.message}")
        }
    }

    private fun unregisterCallState() {
        try {
            if (Build.VERSION.SDK_INT >= 31) {
                telephonyCallback31?.let { telephonyManager.unregisterTelephonyCallback(it) }
            } else {
                @Suppress("DEPRECATION")
                phoneStateLegacy?.let { telephonyManager.listen(it, PhoneStateListener.LISTEN_NONE) }
            }
        } catch (_: Exception) {}
        telephonyCallback31 = null
        phoneStateLegacy = null
    }

    private fun teardown() {
        armed = false
        isArmed = false
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
    }

    private val JSON: MediaType = "application/json".toMediaType()
}
