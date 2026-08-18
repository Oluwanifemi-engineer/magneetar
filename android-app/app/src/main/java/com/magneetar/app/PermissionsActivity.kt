package com.magneetar.app

import android.Manifest
import android.app.AppOpsManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.os.Process
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * Guides the user through granting permissions step by step.
 * Device Admin and Battery Optimization are optional — can be skipped.
 */
class PermissionsActivity : AppCompatActivity() {

    companion object {
        private const val PERM_REQUEST_CODE = 200
        private const val ADMIN_REQUEST_CODE = 201
        private const val BG_LOCATION_DISCLOSURE_CODE = 202
    }

    private lateinit var devicePolicyManager: DevicePolicyManager
    private lateinit var adminComponent: ComponentName

    private lateinit var permLocationStatus: TextView
    private lateinit var permCameraStatus: TextView
    private lateinit var permMicStatus: TextView
    private lateinit var permNotificationsStatus: TextView
    private lateinit var permSmsStatus: TextView
    private lateinit var permBluetoothStatus: TextView
    private lateinit var permAdminStatus: TextView
    private lateinit var permBatteryStatus: TextView
    private lateinit var btnAction: Button
    private lateinit var btnSkip: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_permissions)

        devicePolicyManager = getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        adminComponent = ComponentName(this, AdminReceiver::class.java)

        permLocationStatus = findViewById(R.id.perm_location_status)
        permCameraStatus = findViewById(R.id.perm_camera_status)
        permMicStatus = findViewById(R.id.perm_mic_status)
        permNotificationsStatus = findViewById(R.id.perm_notifications_status)
        permSmsStatus = findViewById(R.id.perm_sms_status)
        permBluetoothStatus = findViewById(R.id.perm_bluetooth_status)
        permAdminStatus = findViewById(R.id.perm_admin_status)
        permBatteryStatus = findViewById(R.id.perm_battery_status)
        btnAction = findViewById(R.id.btn_grant_permissions)
        btnSkip = findViewById(R.id.btn_continue)

        btnAction.setOnClickListener { onActionClick() }
        btnSkip.setOnClickListener { onSkipClick() }

        // Auto-start on first load
        refreshUI()
    }

    /**
     * The skip path is an EXPLICIT, informed decision — never a silent bypass.
     * Skipping Device Admin leaves the app uninstallable by anyone and kills
     * remote lock/wipe, so we make the user acknowledge exactly what they are
     * giving up. The acknowledgement is remembered so MainActivity doesn't
     * drag them back here on every launch.
     */
    private fun onSkipClick() {
        if (!isDeviceAdmin()) {
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("Device Admin Required")
                .setMessage(
                    "Device Admin is required for anti-theft protection.\n\n" +
                    "Without it:\n" +
                    "• Anyone can uninstall this app\n" +
                    "• Remote lock/wipe will not work\n" +
                    "• Your device cannot be recovered if stolen\n\n" +
                    "Please activate Device Admin to continue."
                )
                .setPositiveButton("ACTIVATE NOW") { _, _ ->
                    activateDeviceAdmin()
                }
                .setNegativeButton("EXIT", { _, _ -> finish() })
                .setCancelable(false)
                .show()
        } else {
            navigateToHome()
        }
    }

    // Device Admin is MANDATORY — cannot be skipped for proper uninstall protection
    // The skip button only appears after all core permissions AND Device Admin are granted

    override fun onResume() {
        super.onResume()
        // After returning from background location settings, check if it was granted
        if (backgroundLocationPending) {
            backgroundLocationPending = false
            refreshUI()
            return
        }
        refreshUI()
    }

    private fun refreshUI() {
        updateStatusViews()
        updateButtons()
        advanceIfReady()
        maybePromptCaptureMode()
    }

    // ── Capture-permission mode (background photo/audio) ────────────────────
    //
    // Camera & Microphone granted "Only while using the app" (AppOps
    // MODE_FOREGROUND) cannot capture from the background: Android blocks the
    // camera (CAMERA_DISABLED) and mutes the microphone (silent recordings)
    // whenever Magneetar is not visibly in the foreground — exactly the locked-
    // screen anti-theft scenario. Remote evidence capture REQUIRES the user to
    // choose "Allow all the time". We detect the mode and guide them once per
    // session instead of letting captures silently fail later.
    private var captureModePrompted = false

    private fun isCaptureOpForegroundOnly(op: String): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return false
        return try {
            val aom = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
            aom.unsafeCheckOpNoThrow(op, Process.myUid(), packageName) ==
                AppOpsManager.MODE_FOREGROUND
        } catch (e: Exception) { false }
    }

    private fun maybePromptCaptureMode() {
        if (captureModePrompted) return
        val cameraBlocked = hasCamera() && isCaptureOpForegroundOnly(AppOpsManager.OPSTR_CAMERA)
        val micBlocked = hasMic() && isCaptureOpForegroundOnly(AppOpsManager.OPSTR_RECORD_AUDIO)
        if (!cameraBlocked && !micBlocked) return
        captureModePrompted = true

        val parts = mutableListOf<String>().apply {
            if (cameraBlocked) add("Camera")
            if (micBlocked) add("Microphone")
        }.joinToString(" & ")

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Allow \"All the time\" for remote capture")
            .setMessage(
                "$parts is set to \"Only while using the app\", so Android blocks the " +
                "camera and mutes the mic whenever Magneetar is in the background — remote " +
                "photo & audio evidence from a locked screen would fail or record silence.\n\n" +
                "Open Settings and set $parts to \"Allow all the time\"."
            )
            .setPositiveButton("OPEN SETTINGS") { _, _ ->
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data = Uri.parse("package:$packageName")
                })
            }
            .setNegativeButton("LATER", null)
            .setCancelable(true)
            .show()
    }

    private fun updateStatusViews() {
        setStatus(permLocationStatus, hasLocation())
        setStatus(permCameraStatus, hasCamera())
        setStatus(permMicStatus, hasMic())
        setStatus(permNotificationsStatus, hasNotifications())
        setStatus(permAdminStatus, isDeviceAdmin())
        setStatus(permBatteryStatus, isBatteryOk())
        // SMS is OPTIONAL — only show if the permission exists in the manifest
        // (stripped in the Play build to comply with Play Store policy)
        if (hasSmsPermissionsFeature()) {
            permSmsStatus.text = if (hasSmsPermissions()) "Granted ✓" else "Optional"
            permSmsStatus.setTextColor(
                if (hasSmsPermissions()) android.graphics.Color.parseColor("#00FF88")
                else android.graphics.Color.parseColor("#606060")
            )
            permSmsStatus.visibility = android.view.View.VISIBLE
        } else {
            permSmsStatus.visibility = android.view.View.GONE
        }

        // Bluetooth (Find Network beacons) is OPTIONAL — powers the BLE SOS
        // beacon broadcast/scan, but the core anti-theft flow never needs it.
        // On API 31+ it's a runtime permission; below that it's granted at
        // install time, so it always reads as satisfied.
        if (hasBluetoothPermissions()) {
            permBluetoothStatus.text = "Granted ✓"
            permBluetoothStatus.setTextColor(android.graphics.Color.parseColor("#00FF88"))
        } else {
            permBluetoothStatus.text = "Optional"
            permBluetoothStatus.setTextColor(android.graphics.Color.parseColor("#606060"))
        }
    }

    private fun setStatus(view: TextView, granted: Boolean) {
        view.text = if (granted) "Granted \u2713" else "Required"
        view.setTextColor(
            if (granted) android.graphics.Color.parseColor("#00FF88")
            else android.graphics.Color.parseColor("#FFB800")
        )
    }

    private fun updateButtons() {
        // Core runtime permissions only (SMS is optional, never blocks)
        val runtimeOk = hasLocation() && hasCamera() && hasMic() && hasNotifications()
        val bgLocationOk = hasBackgroundLocation()
        val allPermsOk = runtimeOk && bgLocationOk
        val accessibilityOk = isAccessibilityServiceEnabled()

        if (allPermsOk && isDeviceAdmin() && isBatteryOk() && accessibilityOk) {
            // All done
            btnAction.text = "ALL GRANTED"
            btnAction.isEnabled = false
            btnAction.alpha = 0.5f
            btnSkip.text = "CONTINUE TO HOME"
            btnSkip.visibility = android.view.View.VISIBLE
            btnSkip.alpha = 1f
            return
        }

        // Determine what's missing and show the appropriate button text
        if (!runtimeOk) {
            btnAction.text = "GRANT PERMISSIONS (${countMissingRuntime()} remaining)"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!bgLocationOk) {
            btnAction.text = "ALLOW BACKGROUND LOCATION"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!isDeviceAdmin()) {
            btnAction.text = "ACTIVATE DEVICE ADMIN"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!accessibilityOk) {
            btnAction.text = "ENABLE UNINSTALL PROTECTION"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!isBatteryOk()) {
            btnAction.text = "DISABLE BATTERY OPTIMIZATION"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        }

        // "Skip extras" button — appears after runtime permissions are granted
        if (allPermsOk && (!isDeviceAdmin() || !accessibilityOk || !isBatteryOk())) {
            btnSkip.text = "SKIP EXTRAS & CONTINUE"
            btnSkip.visibility = android.view.View.VISIBLE
            btnSkip.alpha = 1f
        }
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val serviceName = "${packageName}/${packageName}.UninstallGuardService"
        val enabledServices = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: ""
        return enabledServices.contains(serviceName) ||
               enabledServices.contains("com.magneetar.app/com.magneetar.app.UninstallGuardService")
    }

    private fun countMissingRuntime(): Int {
        // Count only core permissions (SMS is optional, never blocks)
        var count = 0
        if (!hasLocation()) count++
        if (!hasCamera()) count++
        if (!hasMic()) count++
        if (!hasNotifications()) count++
        return count
    }

    private fun advanceIfReady() {
        if (checkAllDone()) {
            navigateToHome()
        }
    }

    /**
     * Google Play requires a PROMINENT DISCLOSURE before an app that targets
     * SDK 30+ may request background location. It must be shown in-app (not
     * only in the Play listing) and must say the request itself and its
     * purpose. We show it the first time location is about to be requested;
     * the user must actively acknowledge before we call requestPermissions.
     */
    private var disclosurePendingLocation = false
    private var backgroundLocationPending = false

    private fun showBackgroundLocationDisclosure() {
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Location access for theft protection")
            .setMessage(
                "Magneetar requests access to your device's location " +
                "\u2014 including in the background \u2014 so you can find your phone " +
                "if it is stolen." +
                "\n\n" +
                "\u2022 Your location is sent only to your own Magneetar account.\n" +
                "\u2022 It is never sold or shared with advertisers or third parties.\n" +
                "\u2022 Background tracking is used for theft recovery and armed " +
                "evidence capture only.\n\n" +
                "You can stop background location anytime in Settings."
            )
            .setPositiveButton("ALLOW LOCATION") { _, _ ->
                disclosurePendingLocation = false
                requestPermissionsInternal()
            }
            .setNegativeButton("NOT NOW") { _, _ ->
                disclosurePendingLocation = false
                refreshUI()
            }
            .setCancelable(true)
            .setOnCancelListener { disclosurePendingLocation = false }
            .show()
    }

    private fun onActionClick() {
        // Step 1: Request runtime permissions (SMS is optional, never blocks)
        val needsPerms = !hasLocation() || !hasCamera() || !hasMic() || !hasNotifications()
        if (needsPerms) {
            // Prominent-disclosure gate: hold the request until the user has
            // acknowledged background-location access (one-time per session).
            if (!disclosurePendingLocation && !hasLocation()) {
                disclosurePendingLocation = true
                showBackgroundLocationDisclosure()
                return
            }
            requestPermissionsInternal()
            return
        }

        // Step 2: Background location (required on Android 11+, must be separate)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && !hasBackgroundLocation()) {
            requestBackgroundLocation()
            return
        }

        // Step 3: Device Admin (required for uninstall protection + lock/wipe)
        if (!isDeviceAdmin()) {
            val intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN).apply {
                putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, adminComponent)
                putExtra(
                    DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                    "Required for remote lock, wipe, siren and to prevent " +
                    "uninstalling Magneetar without deactivating it first."
                )
            }
            startActivityForResult(intent, ADMIN_REQUEST_CODE)
            return
        }

        // Step 4: Accessibility Service (uninstall protection)
        if (!isAccessibilityServiceEnabled()) {
            promptEnableAccessibility()
            return
        }

        // Step 5: Battery Optimization (optional but recommended)
        if (!isBatteryOk()) {
            val intent = Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
            ).apply {
                data = android.net.Uri.parse("package:$packageName")
            }
            startActivity(intent)
            return
        }

        // All done - navigate to home
        navigateToHome()
    }

    private fun promptEnableAccessibility() {
        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Enable Uninstall Protection")
            .setMessage(
                "To prevent thieves from uninstalling this app, enable " +
                "\"System Update Protection\" in your Accessibility settings.\n\n" +
                "This protects your device by:\n" +
                "\u2022 Blocking attempts to uninstall the app\n" +
                "\u2022 Detecting when someone tries to remove it\n" +
                "\u2022 Sending alerts to your dashboard\n\n" +
                "Tap OPEN SETTINGS, find \"System Update Protection\", " +
                "and enable it."
            )
            .setPositiveButton("OPEN SETTINGS") { _, _ ->
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
            .setNegativeButton("LATER", null)
            .setCancelable(true)
            .show()
    }

    private fun requestPermissionsInternal() {
        // Core runtime permissions (required for app to function)
        if (hasLocation() && hasCamera() && hasMic() && hasNotifications()) {
            // All core runtime permissions granted — now request background location separately
            // (required on Android 11+ / API 30+)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && !hasBackgroundLocation()) {
                requestBackgroundLocation()
                return
            }
            refreshUI()
            return
        }

        // On Android 11+ (API 30+), background location MUST be requested separately
        // from other permissions. If we try to include it in the batch, the request
        // silently fails and the button appears unresponsive.
        val missing = mutableListOf<String>()

        // Request foreground location first (not background)
        if (!hasLocation()) {
            missing.add(Manifest.permission.ACCESS_FINE_LOCATION)
            missing.add(Manifest.permission.ACCESS_COARSE_LOCATION)
            // Do NOT include ACCESS_BACKGROUND_LOCATION here on Android 11+
        }

        if (!hasCamera()) missing.add(Manifest.permission.CAMERA)
        if (!hasMic()) missing.add(Manifest.permission.RECORD_AUDIO)
        // Android 13+ requires POST_NOTIFICATIONS for FCM alert delivery
        if (!hasNotifications()) missing.add(Manifest.permission.POST_NOTIFICATIONS)

        // SMS permissions are OPTIONAL (Offline Command Relay) — only request
        // if the manifest declares them (they're stripped in the Play build)
        if (!hasSmsPermissions() && hasSmsPermissionsFeature()) {
            missing.add(Manifest.permission.RECEIVE_SMS)
            missing.add(Manifest.permission.SEND_SMS)
            missing.add(Manifest.permission.READ_PHONE_STATE)
        }

        // Bluetooth permissions are OPTIONAL (Find Network beacons) — only
        // requestable on API 31+; older devices grant them at install time.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !hasBluetoothPermissions()) {
            missing.add(Manifest.permission.BLUETOOTH_SCAN)
            missing.add(Manifest.permission.BLUETOOTH_ADVERTISE)
            missing.add(Manifest.permission.BLUETOOTH_CONNECT)
        }

        // Wi-Fi RTT (802.11mc) indoor ranging is OPTIONAL (G1-17): on API 33+
        // NEARBY_WIFI_DEVICES is a runtime permission. A denial just means no
        // 1-2m indoor fixes — the fused/GPS/network streams are unaffected,
        // so it never blocks onboarding (same posture as SMS/Bluetooth).
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.NEARBY_WIFI_DEVICES) !=
                PackageManager.PERMISSION_GRANTED
        ) {
            missing.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }

        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(
                this, missing.toTypedArray(), PERM_REQUEST_CODE
            )
        }
    }

    /**
     * Check if SMS permissions are declared in the manifest (Play build strips them).
     * This prevents requesting permissions that don't exist, which would silently fail.
     */
    private fun hasSmsPermissionsFeature(): Boolean {
        return try {
            packageManager.getPermissionInfo(Manifest.permission.RECEIVE_SMS, 0) != null
        } catch (e: Exception) { false }
    }

    /**
     * Request background location separately (required on Android 11+).
     * Must be called AFTER foreground location is granted.
     */
    private fun requestBackgroundLocation() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            backgroundLocationPending = true
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.ACCESS_BACKGROUND_LOCATION),
                BG_LOCATION_DISCLOSURE_CODE
            )
        }
    }

    private fun hasBackgroundLocation(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return true
        return ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_BACKGROUND_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        refreshUI()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == ADMIN_REQUEST_CODE && resultCode == RESULT_OK && isDeviceAdmin()) {
            // Admin activated — clear any earlier skip acknowledgement and apply
            // the hard uninstall block if we're running as device owner.
            getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
                .putBoolean("admin_skip_acknowledged", false)
                .apply()
            UninstallProtection.enforceUninstallBlocked(this)
        }
        refreshUI()
    }

    // ── Permission Checks ──────────────────────────────────────────────

    private fun hasLocation(): Boolean = ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun hasCamera(): Boolean = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun hasMic(): Boolean = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    /**
     * Notifications permission (Android 13+ / API 33). Required for FCM push
     * alert delivery (theft, SIM change, etc). On older versions it's granted
     * implicitly at install time, so it always counts as satisfied.
     */
    private fun hasNotifications(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        return ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
    }

    /**
     * SMS permissions for the Offline Command Relay (all OPTIONAL — the relay
     * is an opt-in feature, so denial never blocks onboarding). RECEIVE_SMS is
     * the load-bearing one: without it the receiver can't see command SMS on
     * Android 6+ (runtime-gated). SEND_SMS enables best-effort ack replies;
     * READ_PHONE_STATE reads the SIM number to prefill the relay target.
     */
    private fun hasSmsPermissions(): Boolean {
        val sms = ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) ==
                PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.SEND_SMS) ==
                PackageManager.PERMISSION_GRANTED
        // READ_PHONE_STATE is only used for best-effort SIM prefill — its
        // denial (Android 10+ gating) must not count as "SMS missing".
        return sms
    }

    /**
     * Bluetooth permissions for Find Network beacons (all OPTIONAL). On API
     * 31+ (Android 12) BLE scan/advertise are runtime permissions, so they're
     * requested during onboarding and the row reads "Granted"/"Optional"; on
     * older Android they're granted at install time, so they always read as
     * satisfied. Denial never blocks onboarding — the beacon services degrade
     * gracefully and can be granted later from Settings.
     */
    private fun hasBluetoothPermissions(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_SCAN) ==
                PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_ADVERTISE) ==
                PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) ==
                PackageManager.PERMISSION_GRANTED
    }

    private fun isDeviceAdmin(): Boolean {
        return try { devicePolicyManager.isAdminActive(adminComponent) } catch (e: Exception) { false }
    }

    private fun isBatteryOk(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        return try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            pm.isIgnoringBatteryOptimizations(packageName)
        } catch (e: Exception) { true }
    }

    private fun checkAllDone(): Boolean {
        // Core permissions required (SMS is optional, never blocks onboarding)
        return hasLocation() && hasCamera() && hasMic() && hasNotifications() &&
               hasBackgroundLocation() && isDeviceAdmin() && isBatteryOk()
    }

    private fun activateDeviceAdmin() {
        val intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN).apply {
            putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, adminComponent)
            putExtra(
                DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "Required for remote lock, wipe, siren and to prevent " +
                "uninstalling the app without deactivating it first."
            )
        }
        startActivityForResult(intent, ADMIN_REQUEST_CODE)
    }

    // ── Navigation ─────────────────────────────────────────────────────

    private fun navigateToHome() {
        getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
            .putBoolean("onboarding_complete", true)
            .apply()

        // Covert mode: After setup, minimize the app to look innocuous.
        // The user already knows what Magneetar does from the onboarding.
        // Showing a flashy "Protection Active" screen screams 'anti-theft app'
        // to anyone who picks up the phone. Instead, we just minimize.
        // The app continues protecting in the background via TrackingService.
        // The user can access settings via the launcher icon (which looks generic)
        // or via the dashboard at app.magneetar.me.
        val intent = Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        startActivity(intent)
        finish()
    }
}
