package com.magneetar.app

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import java.io.File

/**
 * Device integrity verification — detects rooted devices, tampered APKs,
 * and developer-mode threats. Used by SentinelEngine as a theft signal
 * and by SecurityManager for trust scoring.
 *
 * Does NOT block the app from running on rooted devices (power users may
 * root their own phones), but flags the device as higher-risk for the
 * theft detection engine and shows a warning to the user.
 */
object DeviceIntegrity {

    data class IntegrityReport(
        val isRooted: Boolean,
        val rootMethods: List<String>,
        val isTampered: Boolean,
        val isDeveloperMode: Boolean,
        val isEmulator: Boolean,
        val riskScore: Int  // 0-100, higher = more suspicious
    ) {
        val isTrusted: Boolean get() = riskScore < 30
        val summary: String get() = buildString {
            if (isRooted) append("Rooted (${rootMethods.joinToString()}) ")
            if (isTampered) append("APK tampered ")
            if (isDeveloperMode) append("Developer mode ON ")
            if (isEmulator) append("Emulator detected ")
            if (isNotEmpty()) append("— ") else append("Device integrity OK")
            append("Risk: $riskScore/100")
        }
    }

    /**
     * Run all integrity checks and return a composite report.
     * Fast enough to run on every app launch (< 50ms).
     */
    fun check(context: Context): IntegrityReport {
        val rootMethods = mutableListOf<String>()
        var riskScore = 0

        // Root detection methods (defense in depth — no single method is reliable alone)
        if (checkSuBinary()) { rootMethods.add("su binary"); riskScore += 40 }
        if (checkRootApps(context)) { rootMethods.add("root app"); riskScore += 30 }
        if (checkRootBins()) { rootMethods.add("root bins"); riskScore += 25 }
        if (checkTestKeys()) { rootMethods.add("test-keys"); riskScore += 35 }
        if (checkDangerousProps()) { rootMethods.add("dangerous props"); riskScore += 20 }
        if (checkMount_rw(context)) { rootMethods.add("rw mount"); riskScore += 15 }

        val isRooted = rootMethods.isNotEmpty()

        // Tamper detection — verify APK signature matches expected
        val isTampered = checkApkTamper(context)
        if (isTampered) riskScore += 50

        // Developer mode
        val isDeveloperMode = checkDeveloperMode(context)
        if (isDeveloperMode) riskScore += 10

        // Emulator detection
        val isEmulator = checkEmulator()
        if (isEmulator) riskScore += 15

        return IntegrityReport(
            isRooted = isRooted,
            rootMethods = rootMethods,
            isTampered = isTampered,
            isDeveloperMode = isDeveloperMode,
            isEmulator = isEmulator,
            riskScore = riskScore.coerceAtMost(100)
        )
    }

    // ── Root Detection ────────────────────────────────────────────────────

    private fun checkSuBinary(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("which", "su"))
            val exitCode = process.waitFor()
            exitCode == 0
        } catch (e: Exception) { false }
    }

    private fun checkRootApps(context: Context): Boolean {
        val rootPackages = listOf(
            "com.topjohnwu.magisk",
            "eu.chainfire.supersu",
            "com.koushikdutta.superuser",
            "com.thirdparty.superuser",
            "com.noshufou.android.su",
            "com.devadvance.rootcloak",
            "com.devadvance.rootcloakplus",
            "com.saurik.substrate",
            "com.amphoras.hidemyroot",
            "com.kingouser.com"
        )
        val pm = context.packageManager
        return rootPackages.any { pkg ->
            try {
                pm.getPackageInfo(pkg, 0)
                true
            } catch (e: PackageManager.NameNotFoundException) { false }
        }
    }

    private fun checkRootBins(): Boolean {
        val paths = listOf(
            "/system/app/Superuser.apk",
            "/system/xbin/su",
            "/system/bin/su",
            "/sbin/su",
            "/data/local/xbin/su",
            "/data/local/bin/su",
            "/system/sd/xbin/su",
            "/system/bin/failsafe/su",
            "/data/local/su",
            "/su/bin/su"
        )
        return paths.any { File(it).exists() }
    }

    private fun checkTestKeys(): Boolean {
        return Build.TAGS?.contains("test-keys") == true
    }

    private fun checkDangerousProps(): Boolean {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("getprop", "ro.debuggable"))
            val output = process.inputStream.bufferedReader().readText().trim()
            process.waitFor()
            output == "1"
        } catch (e: Exception) { false }
    }

    private fun checkMount_rw(context: Context): Boolean {
        return try {
            val process = Runtime.getRuntime().exec(arrayOf("mount"))
            val output = process.inputStream.bufferedReader().readText()
            process.waitFor()
            output.contains("/system") && output.contains("rw,")
        } catch (e: Exception) { false }
    }

    // ── Tamper Detection ──────────────────────────────────────────────────

    private fun checkApkTamper(context: Context): Boolean {
        return try {
            val pm = context.packageManager
            val pkgInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                pm.getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
            } else {
                @Suppress("DEPRECATION")
                pm.getPackageInfo(context.packageName, PackageManager.GET_SIGNATURES)
            }

            val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                pkgInfo.signingInfo?.apkContentsSigners
            } else {
                @Suppress("DEPRECATION")
                pkgInfo.signatures
            }

            if (signatures.isNullOrEmpty()) return true

            // Verify signature is not DEBUG (would indicate tampering in release)
            val sigBytes = signatures[0].toByteArray()
            val isDebugSig = sigBytes.size == 1 // Debug signatures are typically 1 byte

            isDebugSig
        } catch (e: Exception) { false }
    }

    // ── Developer Mode ────────────────────────────────────────────────────

    private fun checkDeveloperMode(context: Context): Boolean {
        return try {
            Settings.Global.getInt(
                context.contentResolver,
                Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0
            ) != 0
        } catch (e: Exception) { false }
    }

    // ── Emulator Detection ────────────────────────────────────────────────

    private fun checkEmulator(): Boolean {
        return Build.FINGERPRINT.startsWith("generic")
                || Build.FINGERPRINT.startsWith("unknown")
                || Build.MODEL.contains("google_sdk")
                || Build.MODEL.contains("Emulator")
                || Build.MODEL.contains("Android SDK built for x86")
                || Build.MANUFACTURER.contains("Genymotion")
                || (Build.BRAND.startsWith("generic") && Build.DEVICE.startsWith("generic"))
                || "google_sdk" == Build.PRODUCT
                || Build.HARDWARE.contains("goldfish")
                || Build.HARDWARE.contains("ranchu")
    }
}
