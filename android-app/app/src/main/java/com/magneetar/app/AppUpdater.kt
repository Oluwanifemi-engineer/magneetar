package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import java.io.File
import java.security.MessageDigest

/**
 * In-app self-updater support — the piece that makes upgrades never depend on
 * a manual sideload (the failure mode documented in G1 issue #1: "App not
 * installed" when an old protected install lingers).
 *
 * Flow (see AppUpdaterService): the app learns of a newer version via
 * /api/config, the user taps "Update now", and the service downloads the
 * verified APK from the official server and hands it to Android's
 * PackageInstaller — the same system component the Play Store uses, which
 * handles installing over an existing (even admin-protected) install.
 *
 * Security model:
 *  - The download URL is the same HMAC-ticketed /apk/download endpoint the
 *    web page uses — a bad ticket gets no bytes.
 *  - The APK must hash to the SHA-256 that /apk/checksum reports for the
 *    EXACT bytes /apk/download serves; a mismatch aborts (never installs).
 *  - Install is always explicit: the user taps the notification, and Android
 *    shows its own "Update Magneetar?" confirmation before applying.
 *  - Never touches the install path when the app came from Google Play —
 *    Play delivers updates itself (see isInstalledViaPlayStore).
 */
object AppUpdater {

    /** Streaming SHA-256 hex digest of a file (never loads it into memory). */
    fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    /**
     * True only when the file's size AND SHA-256 match what the server
     * reported for the bytes it serves. A size mismatch or any hash drift
     * rejects the download — truncation and tampering both fail closed.
     */
    fun verify(file: File, expectedSha256: String, expectedSizeBytes: Long): Boolean {
        if (expectedSizeBytes > 0 && file.length() != expectedSizeBytes) return false
        val expected = expectedSha256.trim().lowercase()
        return expected.isNotEmpty() && sha256(file) == expected
    }

    /**
     * True when this app was installed via Google Play (installer package
     * "com.android.vending"). Play delivers updates itself — the in-app
     * updater stays silent there (self-installing APKs from outside Play is
     * also a Play policy violation, so this check is the policy guard too).
     */
    fun isInstalledViaPlayStore(context: Context): Boolean {
        return try {
            context.packageManager.getInstallerPackageName(context.packageName) == "com.android.vending"
        } catch (_: Exception) {
            false
        }
    }

    /**
     * True when the app may install other packages (the per-app "Allow from
     * this source" grant, Android 8+). Without it PackageInstaller refuses.
     */
    fun canRequestInstalls(context: Context): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.packageManager.canRequestPackageInstalls()
            } else {
                true // pre-O: a single global "Unknown sources" toggle exists
            }
        } catch (_: Exception) {
            false
        }
    }

    /** The Settings screen where the user grants "Allow from this source". */
    fun unknownSourcesSettingsIntent(context: Context): Intent {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}")
            )
        } else {
            Intent(Settings.ACTION_SECURITY_SETTINGS)
        }
    }
}
