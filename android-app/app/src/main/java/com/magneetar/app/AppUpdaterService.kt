package com.magneetar.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageInstaller
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * In-app self-updater: downloads the official release APK, verifies it
 * byte-for-byte against the server's checksum, and installs it through
 * Android's PackageInstaller — the same mechanism the Play Store uses.
 *
 * Started from the "Update available" notification (TrackingService). The
 * user's tap is the explicit consent: without it nothing downloads, and
 * Android still shows its own "Update Magneetar?" confirmation before the
 * new version is applied. Installing over an existing install — including
 * one protected by the app's own device-admin/uninstall-guard — is exactly
 * what PackageInstaller is built for, so this path never shows the plain
 * "App not installed" failure of the manual sideload route.
 *
 * Steps (each aborts with a clear notification on failure, never a crash):
 *   1. Gate: app must hold the "Allow installs from this source" grant.
 *   2. /apk/checksum → expected SHA-256 + size of the exact served bytes.
 *   3. /apk/ticket → short-lived signed download URL.
 *   4. Stream /apk/download to cache (foreground progress notification).
 *   5. Reject unless size AND SHA-256 match step 2.
 *   6. PackageInstaller session → Android's own update confirmation.
 */
class AppUpdaterService : Service() {

    companion object {
        private const val TAG = "AppUpdater"
        private const val CHANNEL_ID = "mt_update"
        private const val NOTIF_ID = 40
        private const val RESULT_ACTION = "com.magneetar.app.UPDATE_INSTALL_RESULT"
        const val EXTRA_UPDATE_TO = "extra_update_to"
        private val SERVER = BuildConfig.SERVER_URL

        /** How long to keep the service alive waiting for the install result. */
        private const val INSTALL_RESULT_TIMEOUT_MS = 5 * 60 * 1000L
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    private var installedOk = false

    /** Receives PackageInstaller's result after Android's confirm dialog. */
    private val resultReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val status = intent.getIntExtra(
                PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE
            )
            val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""
            if (status == PackageInstaller.STATUS_SUCCESS) {
                installedOk = true
                val version = intent.getStringExtra(EXTRA_UPDATE_TO).orEmpty()
                terminal(
                    "Magneetar updated",
                    if (version.isNotEmpty()) "Version $version is installed — reopen Magneetar."
                    else "The update is installed — reopen Magneetar."
                )
            } else {
                terminal(
                    "Update failed",
                    message.ifBlank {
                        "The update could not be installed. Try again from the download page."
                    }
                )
            }
            stopSelf()
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(resultReceiver, IntentFilter(RESULT_ACTION), Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(resultReceiver, IntentFilter(RESULT_ACTION))
        }
    }

    override fun onDestroy() {
        try { unregisterReceiver(resultReceiver) } catch (_: Exception) {}
        if (!installedOk) {
            // Session committed but no result arrived (dialog dismissed) — the
            // partial download is worthless; reclaim the space.
            File(cacheDir, "magneetar-update.apk").delete()
        }
        super.onDestroy()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIF_ID, progress("Checking for update…"))

        if (!AppUpdater.canRequestInstalls(this)) {
            // Android 8+: the app itself needs the "Allow from this source"
            // grant before PackageInstaller will work. Surface it (the tap on
            // this notification came from the user, so opening Settings is
            // allowed) and leave a persistent "Update ready" notification to
            // resume once granted.
            notify(
                "Allow app installs",
                "Magneetar needs “Install unknown apps” permission to update itself — tap to grant, then tap Update again.",
                persistent = true
            )
            startActivity(
                AppUpdater.unknownSourcesSettingsIntent(this).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
            stopSelf()
            return START_NOT_STICKY
        }

        Thread {
            runUpdate(intent?.getStringExtra(EXTRA_UPDATE_TO).orEmpty())
        }.start()
        return START_NOT_STICKY
    }

    private fun runUpdate(updateTo: String) {
        val target = File(cacheDir, "magneetar-update.apk")
        try {
            // 1) Expected checksum of the exact bytes the server serves.
            val (expectedSha, expectedSize) = fetchChecksum()
            if (expectedSha.isEmpty()) throw IllegalStateException("server returned no checksum")

            // 2) Short-lived signed download ticket.
            val ticket = fetchTicket()
            if (ticket.isEmpty()) throw IllegalStateException("server returned no download ticket")

            // 3) Stream the APK (progress updates as bytes land).
            val downloaded = download("$SERVER$ticket", target)
            if (downloaded <= 0) throw IllegalStateException("download produced no data")

            // 4) Reject unless size + SHA-256 match the server's own report.
            if (!AppUpdater.verify(target, expectedSha, expectedSize)) {
                target.delete()
                throw IllegalStateException("checksum mismatch — download rejected")
            }

            // 5) Hand to PackageInstaller (Android shows its own confirm UI).
            installApk(target, updateTo)
        } catch (e: Exception) {
            android.util.Log.w(TAG, "Update failed: ${e.message}")
            terminal("Update failed", e.message ?: "Something went wrong downloading the update.")
            stopSelf()
        }
    }

    private fun fetchChecksum(): Pair<String, Long> {
        return client.newCall(Request.Builder().url("$SERVER/apk/checksum").get()
            .header("X-Magneetar-Client", "app-updater")
            .build())
            .execute().use { resp ->
                if (resp.code !in 200..299) throw IllegalStateException("checksum request failed (${resp.code})")
                val json = JSONObject(resp.body?.string() ?: "{}")
                json.optString("sha256", "") to json.optLong("size_bytes", -1L)
            }
    }

    private fun fetchTicket(): String {
        return client.newCall(Request.Builder().url("$SERVER/apk/ticket").get()
            .header("X-Magneetar-Client", "app-updater")
            .build())
            .execute().use { resp ->
                if (resp.code !in 200..299) throw IllegalStateException("ticket request failed (${resp.code})")
                JSONObject(resp.body?.string() ?: "{}").optString("url", "")
            }
    }

    private fun download(url: String, target: File): Long {
        target.delete()
        return client.newCall(Request.Builder().url(url).get()
            .header("X-Magneetar-Client", "app-updater")
            .build())
            .execute().use { resp ->
                if (resp.code !in 200..299) throw IllegalStateException("download failed (${resp.code})")
                val body = resp.body ?: throw IllegalStateException("empty download response")
                val total = resp.body?.contentLength() ?: 0L
                var written = 0L
                var lastUpdate = 0L
                body.byteStream().use { input ->
                    target.outputStream().use { out ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buf)
                            if (n < 0) break
                            out.write(buf, 0, n)
                            written += n
                            // Throttle progress UI to ~every 512 KB.
                            if (written - lastUpdate >= 512 * 1024) {
                                lastUpdate = written
                                val pct = if (total > 0) (written * 100 / total).toInt() else -1
                                progressNotification(
                                    if (pct >= 0) "Downloading update… $pct%"
                                    else "Downloading update… ${written / (1024 * 1024)} MB"
                                )
                            }
                        }
                    }
                }
                written
            }
    }

    private fun installApk(apk: File, updateTo: String) {
        val pm = packageManager
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(packageName)
        }
        val sessionId = pm.packageInstaller.createSession(params)
        val session = pm.packageInstaller.openSession(sessionId)
        try {
            session.openWrite("base.apk", 0, apk.length()).use { out ->
                apk.inputStream().use { it.copyTo(out) }
                session.fsync(out)
            }
            progressNotification("Installing update…")

            val confirm = Intent(RESULT_ACTION)
                .setPackage(packageName)
                .putExtra(EXTRA_UPDATE_TO, updateTo)
            val sender = PendingIntent.getBroadcast(
                this,
                sessionId,
                confirm,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            session.commit(sender.intentSender)
        } finally {
            session.close()
        }
        // Keep the service (and its receiver) alive until the result arrives.
        Handler(Looper.getMainLooper()).postDelayed({ stopSelf() }, INSTALL_RESULT_TIMEOUT_MS)
    }

    // ── Notifications ───────────────────────────────────────────────────────

    private fun createChannel() {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "App updates", NotificationManager.IMPORTANCE_DEFAULT)
        )
    }

    private fun progress(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Magneetar update")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

    private fun progressNotification(text: String) {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(NOTIF_ID, progress(text))
    }

    /** Terminal result — survives service teardown (different id than the FGS). */
    private fun terminal(title: String, text: String) {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(
            NOTIF_ID + 1,
            NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setPriority(NotificationCompat.PRIORITY_DEFAULT)
                .setAutoCancel(true)
                .build()
        )
    }

    /** Persistent prompt (e.g. the missing install-grant gate). */
    private fun notify(title: String, text: String, persistent: Boolean) {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(!persistent)
        if (persistent) {
            val resume = PendingIntent.getService(
                this,
                1,
                Intent(this, AppUpdaterService::class.java),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.setContentIntent(resume)
        }
        mgr.notify(NOTIF_ID + 1, builder.build())
    }
}
