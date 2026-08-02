package com.magneetar.app

import android.Manifest
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
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
    }

    private lateinit var devicePolicyManager: DevicePolicyManager
    private lateinit var adminComponent: ComponentName

    private lateinit var permLocationStatus: TextView
    private lateinit var permCameraStatus: TextView
    private lateinit var permMicStatus: TextView
    private lateinit var permNotificationsStatus: TextView
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
    }

    private fun updateStatusViews() {
        setStatus(permLocationStatus, hasLocation())
        setStatus(permCameraStatus, hasCamera())
        setStatus(permMicStatus, hasMic())
        setStatus(permNotificationsStatus, hasNotifications())
        setStatus(permAdminStatus, isDeviceAdmin())
        setStatus(permBatteryStatus, isBatteryOk())
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

        // Not all done yet
        if (!runtimeOk) {
            btnAction.text = "GRANT PERMISSIONS (${countMissingRuntime()} remaining)"
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

    private fun onActionClick() {
        // Step 1: Request runtime permissions
        if (!hasLocation() || !hasCamera() || !hasMic() || !hasNotifications()) {
            val missing = mutableListOf<String>()
            if (!hasLocation()) {
                missing.add(Manifest.permission.ACCESS_FINE_LOCATION)
                missing.add(Manifest.permission.ACCESS_COARSE_LOCATION)
            }
            if (!hasCamera()) missing.add(Manifest.permission.CAMERA)
            if (!hasMic()) missing.add(Manifest.permission.RECORD_AUDIO)
            // Android 13+ requires POST_NOTIFICATIONS for FCM alert delivery
            if (!hasNotifications()) missing.add(Manifest.permission.POST_NOTIFICATIONS)

            ActivityCompat.requestPermissions(
                this, missing.toTypedArray(), PERM_REQUEST_CODE
            )
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
