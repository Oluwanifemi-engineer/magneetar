package com.magneetar.app

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.os.Build
import android.util.Log

/**
 * Uninstall-protection layer beyond the base Device Admin gate.
 *
 * BASE PROTECTION (works on every device, zero setup):
 *   An active Device Admin makes Android refuse to uninstall the app until
 *   the admin is deactivated in Settings. Deactivation shows our warning
 *   (AdminReceiver.DISABLE_WARNING) and instantly alerts the server.
 *
 * HARD PROTECTION (device/profile owner only):
 *   DevicePolicyManager.setUninstallBlocked(true) makes the OS hard-block
 *   uninstallation entirely — the Settings "Uninstall" entry is disabled and
 *   `adb uninstall` fails. This requires the app to be set as the DEVICE
 *   OWNER via provisioning:
 *       adb shell dpm set-device-owner com.magneetar.app/.AdminReceiver
 *   (requires an unprovisioned device with no accounts, or factory-reset
 *   provisioning via DevicePolicyManager.EXTRA_PROVISIONING_DEVICE_ADMIN_COMPONENT).
 *
 * There is NO public Android API that lets a normal app prompt for a custom
 * password at uninstall time — the strongest supported primitives are the
 * two layers above. This helper applies the hard block whenever the app
 * happens to be running as device/profile owner (best-effort, never fatal).
 */
object UninstallProtection {

    private const val TAG = "MagneetarUninstall"

    /** True when the app is the device owner or a profile owner. */
    fun isOwnerApp(context: Context): Boolean {
        return try {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            dpm.isDeviceOwnerApp(context.packageName) || dpm.isProfileOwnerApp(context.packageName)
        } catch (e: Exception) { false }
    }

    /** True when the hard uninstall block is currently active. */
    fun isUninstallBlocked(context: Context): Boolean {
        if (!isOwnerApp(context)) return false
        return try {
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            val admin = ComponentName(context, AdminReceiver::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                // API 34+: per-user overload; "current" = the active user.
                dpm.isUninstallBlocked(admin, "current")
            } else {
                // API 21-33: 2-arg overload — not present in the API 35 stub,
                // so call it reflectively (still type-safe, wrapped in try).
                @Suppress("DEPRECATION")
                val m = dpm.javaClass.getMethod(
                    "isUninstallBlocked", ComponentName::class.java
                )
                m.invoke(dpm, admin) as? Boolean ?: false
            }
        } catch (e: Exception) { false }
    }

    /**
     * Apply setUninstallBlocked(true) when running as device/profile owner.
     *
     * Safe to call anywhere, anytime: on non-owner devices it's a no-op, and
     * any failure is logged and swallowed so protection can never break the
     * app. Re-asserted on admin activation and at service start so a reinstall
     * or data wipe can't silently drop the block.
     */
    fun enforceUninstallBlocked(context: Context) {
        try {
            if (!isOwnerApp(context)) return
            val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
            val admin = ComponentName(context, AdminReceiver::class.java)

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                if (!dpm.isUninstallBlocked(admin, "current")) {
                    dpm.setUninstallBlocked(admin, "current", true)
                }
            } else {
                // API 21-33: legacy 2-arg overload via reflection (absent from
                // the API 35 compile stub, but present on these devices).
                @Suppress("DEPRECATION")
                val m = dpm.javaClass.getMethod(
                    "setUninstallBlocked", ComponentName::class.java, Boolean::class.javaPrimitiveType
                )
                m.invoke(dpm, admin, true)
            }
            Log.i(TAG, "Hard uninstall block applied (device owner mode)")
        } catch (e: Exception) {
            Log.w(TAG, "Could not apply uninstall block: ${e.message}")
        }
    }
}
