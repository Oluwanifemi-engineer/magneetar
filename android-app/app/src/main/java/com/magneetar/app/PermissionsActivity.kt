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
                .setTitle("Continue without Device Admin?")
                .setMessage(
                    "Without Device Admin, ANYONE can uninstall Magneetar and " +
                    "remote lock / wipe / siren are disabled.\n\n" +
                    "This significantly weakens your theft protection. " +
                    "Are you sure you want to continue without it?"
                )
                .setPositiveButton("CONTINUE WITHOUT PROTECTION") { _, _ ->
                    getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
                        .putBoolean("admin_skip_acknowledged", true)
                        .apply()
                    navigateToHome()
                }
                .setNegativeButton("ACTIVATE DEVICE ADMIN", null)
                .setCancelable(true)
                .show()
        } else {
            navigateToHome()
        }
    }

    override fun onResume() {
        super.onResume()
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
        // SMS is OPTIONAL (powers the Offline Command Relay when enabled) —
        // it never blocks onboarding, but the status shows the real state.
        permSmsStatus.text = if (hasSmsPermissions()) "Granted ✓" else "Optional"
        permSmsStatus.setTextColor(
            if (hasSmsPermissions()) android.graphics.Color.parseColor("#00FF88")
            else android.graphics.Color.parseColor("#606060")
        )
    }

    private fun setStatus(view: TextView, granted: Boolean) {
        view.text = if (granted) "Granted \u2713" else "Required"
        view.setTextColor(
            if (granted) android.graphics.Color.parseColor("#00FF88")
            else android.graphics.Color.parseColor("#FFB800")
        )
    }

    private fun updateButtons() {
        val runtimeOk = hasLocation() && hasCamera() && hasMic()

        if (runtimeOk && isDeviceAdmin() && isBatteryOk()) {
            // All done
            btnAction.text = "ALL GRANTED"
            btnAction.isEnabled = false
            btnAction.alpha = 0.5f
            btnSkip.text = "CONTINUE TO HOME"
            btnSkip.visibility = android.view.View.VISIBLE
            btnSkip.alpha = 1f
            return
        }

        // Not all done yet. Notifications is a REQUIRED runtime permission
        // (Android 13+ FCM alerts) but is not in runtimeOk (pre-existing
        // quirk) — give it priority over the optional SMS step so the button
        // label matches what the request batch actually asks for.
        if (!runtimeOk || !hasNotifications()) {
            btnAction.text = "GRANT PERMISSIONS (${countMissingRuntime()} remaining)"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!hasSmsPermissions()) {
            // Required perms granted but SMS (the Offline Command Relay) is
            // still missing — offer a dedicated request step so a user who
            // denied it during onboarding can re-request it here instead of
            // the prompt silently becoming unreachable behind admin/battery.
            btnAction.text = "GRANT SMS COMMANDS ACCESS (optional)"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!isDeviceAdmin()) {
            btnAction.text = "ACTIVATE DEVICE ADMIN"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        } else if (!isBatteryOk()) {
            btnAction.text = "DISABLE BATTERY OPTIMIZATION"
            btnAction.isEnabled = true
            btnAction.alpha = 1f
        }

        // "Skip extras" button — appears after runtime permissions are granted
        if (runtimeOk && (!isDeviceAdmin() || !isBatteryOk())) {
            btnSkip.text = "SKIP EXTRAS & CONTINUE"
            btnSkip.visibility = android.view.View.VISIBLE
            btnSkip.alpha = 1f
        }
    }

    private fun countMissingRuntime(): Int {
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
        // Step 1: Request runtime permissions. The SMS permissions are bundled
        // into the same batch — RECEIVE_SMS is what makes the Offline Command
        // Relay work at all on Android 6+ (without a runtime grant the
        // receiver never sees SMS broadcasts). They are OPTIONAL (the relay
        // is an opt-in feature), so they're requested alongside the required
        // ones but never block completion if denied.
        if (!hasLocation() || !hasCamera() || !hasMic() || !hasNotifications() || !hasSmsPermissions()) {
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

        // Step 2: Device Admin (required for uninstall protection + lock/wipe)
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

        // Step 3: Battery Optimization (optional)
        if (!isBatteryOk()) {
            val intent = Intent(
                Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
            ).apply {
                data = android.net.Uri.parse("package:$packageName")
            }
            startActivity(intent)
            return
        }

        // All done
        navigateToHome()
    }

    private fun requestPermissionsInternal() {
        if (hasLocation() && hasCamera() && hasMic() && hasNotifications() && hasSmsPermissions()) {
            refreshUI()
            return
        }
        val missing = mutableListOf<String>()
        if (!hasLocation()) {
            missing.add(Manifest.permission.ACCESS_FINE_LOCATION)
            missing.add(Manifest.permission.ACCESS_COARSE_LOCATION)
            // Background location is requested in the SAME dialog as the
            // foreground permissions — Play requires the permission to be
            // requested together, not separately, for targetSdk 30+.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                missing.add(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
            }
        }
        if (!hasCamera()) missing.add(Manifest.permission.CAMERA)
        if (!hasMic()) missing.add(Manifest.permission.RECORD_AUDIO)
        // Android 13+ requires POST_NOTIFICATIONS for FCM alert delivery
        if (!hasNotifications()) missing.add(Manifest.permission.POST_NOTIFICATIONS)
        // Offline Command Relay (optional): RECEIVE_SMS intercepts command
        // SMS, SEND_SMS enables best-effort ack replies, READ_PHONE_STATE
        // reads the SIM number for the relay's target. Safe to request in
        // the same dialog; the user can deny without blocking setup.
        if (!hasSmsPermissions()) {
            missing.add(Manifest.permission.RECEIVE_SMS)
            missing.add(Manifest.permission.SEND_SMS)
            missing.add(Manifest.permission.READ_PHONE_STATE)
        }

        ActivityCompat.requestPermissions(
            this, missing.toTypedArray(), PERM_REQUEST_CODE
        )
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
        return hasLocation() && hasCamera() && hasMic() && isDeviceAdmin() && isBatteryOk()
    }

    // ── Navigation ─────────────────────────────────────────────────────

    private fun navigateToHome() {
        getSharedPreferences("mt", Context.MODE_PRIVATE).edit()
            .putBoolean("onboarding_complete", true)
            .apply()

        val intent = Intent(this, MainActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }
}
