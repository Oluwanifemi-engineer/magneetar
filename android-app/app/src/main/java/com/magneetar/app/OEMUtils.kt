package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings

/**
 * OEM-specific utilities for background persistence.
 * Detects Chinese phone manufacturers and provides guidance
 * for enabling auto-start, locking apps, and disabling battery optimization.
 */
object OEMUtils {

    /** Manufacturer identifiers for Chinese OEMs */
    private val CHINESE_OEM_MANUFACTURERS = setOf(
        "xiaomi", "redmi", "poco", "huawei", "honor", "oppo",
        "realme", "vivo", "oneplus", "meizu", "lenovo", "zte",
        "nubia", "coolpad", "gionee", "letv", "smartisan",
        // Transsion — Tecno / Infinix / Itel are the dominant brands in Nigeria
        // and much of Africa; their HiOS/XOS battery killers are aggressive.
        "tecno", "infinix", "itel", "tcl", "transsion"
    )

    /** Whether this device is from a Chinese OEM */
    fun isChineseOEM(): Boolean {
        val manufacturer = Build.MANUFACTURER.lowercase().replace(" ", "")
        return CHINESE_OEM_MANUFACTURERS.any { manufacturer.contains(it) }
    }

    /** OEM display name for user-facing messages */
    fun getOEMName(): String {
        return when {
            Build.MANUFACTURER.lowercase().contains("xiaomi") || Build.MANUFACTURER.lowercase().contains("redmi") -> "Xiaomi MIUI/HyperOS"
            Build.MANUFACTURER.lowercase().contains("huawei") || Build.MANUFACTURER.lowercase().contains("honor") -> "Huawei EMUI/HarmonyOS"
            Build.MANUFACTURER.lowercase().contains("oppo") -> "Oppo ColorOS"
            Build.MANUFACTURER.lowercase().contains("realme") -> "Realme UI"
            Build.MANUFACTURER.lowercase().contains("vivo") -> "Vivo Funtouch OS"
            Build.MANUFACTURER.lowercase().contains("oneplus") -> "OnePlus OxygenOS/ColorOS"
            Build.MANUFACTURER.lowercase().contains("meizu") -> "Meizu Flyme"
            Build.MANUFACTURER.lowercase().contains("tecno") || Build.MANUFACTURER.lowercase().contains("infinix") ||
                Build.MANUFACTURER.lowercase().contains("itel") || Build.MANUFACTURER.lowercase().contains("transsion") ->
                "Transsion HiOS/XOS (Tecno/Infinix/Itel)"
            else -> "${Build.MANUFACTURER} ${Build.BRAND}"
        }
    }

    /**
     * Returns step-by-step guidance for enabling auto-start on this device.
     * Used in the onboarding flow and on the home screen.
     */
    fun getAutoStartGuidance(): String {
        val manufacturer = Build.MANUFACTURER.lowercase()
        return when {
            manufacturer.contains("xiaomi") || manufacturer.contains("redmi") ->
                "1. Open Settings → Apps → Manage apps\n" +
                "2. Find Magneetar → toggle \"Auto-start\" ON\n" +
                "3. Also lock Magneetar in the Recent Apps tray (pull the app card down)"

            manufacturer.contains("huawei") || manufacturer.contains("honor") ->
                "1. Open Phone Manager → App Launch\n" +
                "2. Find Magneetar → toggle \"Manage automatically\" ON\n" +
                "3. Also go to Settings → Battery → Launch → tap Magneetar → toggle ON"

            manufacturer.contains("oppo") || manufacturer.contains("realme") ->
                "1. Open Settings → Apps → App Management\n" +
                "2. Find Magneetar → tap → Background Freeze → toggle OFF\n" +
                "3. Also open Phone Manager → Permissions → Auto-launch → enable Magneetar"

            manufacturer.contains("vivo") ->
                "1. Open Settings → More Settings → Apps → Autostart\n" +
                "2. Enable Magneetar\n" +
                "3. Also go to Settings → Battery → Background power consumption → select Magneetar → choose \"Allow\""

            manufacturer.contains("oneplus") ->
                "1. Open Settings → Battery → Battery Optimization\n" +
                "2. Find Magneetar → select \"Don't optimize\"\n" +
                "3. Also open Recent Apps and lock Magneetar"

            manufacturer.contains("tecno") || manufacturer.contains("infinix") ||
                manufacturer.contains("itel") || manufacturer.contains("transsion") ->
                "1. Open the Phone Manager app → Autostart (or Auto-launch)\n" +
                "2. Find Magneetar → toggle ON\n" +
                "3. Also open Settings → Battery → App Power Saver → Magneetar → select \"Allow background running\"\n" +
                "4. Lock Magneetar in Recent Apps (pull the app card down)"

            else ->
                "1. Open Settings → Apps → Magneetar → Battery → Unrestricted\n" +
                "2. Also enable \"Auto-start\" if available\n" +
                "3. Lock the app in Recent Apps (pull the app card down)"
        }
    }

    /**
     * Attempts to open the auto-start settings page for this manufacturer.
     * Returns true if a specific intent was launched.
     */
    fun openAutoStartSettings(context: Context): Boolean {
        return try {
            val intent = when {
                Build.MANUFACTURER.lowercase().contains("xiaomi") -> {
                    Intent().apply {
                        action = "miui.intent.action.OP_AUTO_START"
                        addCategory(Intent.CATEGORY_DEFAULT)
                        putExtra("package_name", context.packageName)
                        putExtra("pkg", context.packageName)
                        `package` = "com.miui.securitycenter"
                    }
                }
                Build.MANUFACTURER.lowercase().contains("huawei") || Build.MANUFACTURER.lowercase().contains("honor") -> {
                    Intent().apply {
                        action = Settings.ACTION_APPLICATION_DETAILS_SETTINGS
                        data = Uri.parse("package:${context.packageName}")
                    }
                }
                Build.MANUFACTURER.lowercase().contains("oppo") || Build.MANUFACTURER.lowercase().contains("realme") -> {
                    Intent().apply {
                        action = Settings.ACTION_APPLICATION_DETAILS_SETTINGS
                        data = Uri.parse("package:${context.packageName}")
                    }
                }
                Build.MANUFACTURER.lowercase().contains("vivo") -> {
                    Intent().apply {
                        action = "com.vivo.safeheart.action.ACTION_AUTOSTART_SETTING"
                        addCategory(Intent.CATEGORY_DEFAULT)
                        putExtra("packageName", context.packageName)
                        putExtra("pkg_name", context.packageName)
                        `package` = "com.iqoo.secure"
                    }
                }
                // Transsion devices gate auto-start inside the stock Phone Manager
                // app; app-details settings is the reliable universal entry point.
                Build.MANUFACTURER.lowercase().let {
                    it.contains("tecno") || it.contains("infinix") ||
                        it.contains("itel") || it.contains("transsion")
                } -> {
                    Intent().apply {
                        action = Settings.ACTION_APPLICATION_DETAILS_SETTINGS
                        data = Uri.parse("package:${context.packageName}")
                    }
                }
                else -> {
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        data = Uri.parse("package:${context.packageName}")
                    }
                }
            }
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
            true
        } catch (e: Exception) {
            // Fallback to app settings
            try {
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:${context.packageName}")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                true
            } catch (_: Exception) {
                false
            }
        }
    }

    /**
     * Returns the autostart permission state based on manufacturer.
     * On Xiaomi/HyperOS, this can check the autostart setting.
     */
    fun isAutoStartEnabled(context: Context): Boolean {
        // Most Chinese OEMs don't expose auto-start state via public API.
        // On Xiaomi we can try to check, but it's unreliable.
        // We use a heuristic: if the app has persisted through a recent reboot
        // (checked via shared prefs timestamp), auto-start is likely enabled.
        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        val lastBootRestart = prefs.getLong("last_boot_restart", 0L)
        val lastManualRestart = prefs.getLong("last_manual_restart", 0L)
        // If we've successfully restarted after boot, auto-start is likely enabled
        return lastBootRestart > 0 && lastBootRestart > lastManualRestart
    }
}
