package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Home screen shown after successful setup.
 * Displays protection status, connection state, and quick actions.
 */
class HomeActivity : AppCompatActivity() {

    companion object {
        /** User opt-out for remote capture (set false when they disarm). */
        private const val PREF_AUTO_ARM = "capture_auto_arm"
    }

    private lateinit var tvUninstallStatus: TextView
    private lateinit var btnActivateAdmin: Button
    private lateinit var tvConnectionStatus: TextView
    private lateinit var tvBatteryStatus: TextView
    private lateinit var tvCaptureStatus: TextView
    private lateinit var btnToggleCapture: Button
    private lateinit var tvOemWarning: TextView
    private lateinit var btnOpenDashboard: Button
    private lateinit var btnAutoStart: Button
    private lateinit var btnOptimizeBattery: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        tvUninstallStatus = findViewById(R.id.tv_uninstall_status)
        btnActivateAdmin = findViewById(R.id.btn_activate_admin)
        tvConnectionStatus = findViewById(R.id.tv_connection_status)
        tvBatteryStatus = findViewById(R.id.tv_battery_opt_status)
        tvCaptureStatus = findViewById(R.id.tv_capture_status)
        btnToggleCapture = findViewById(R.id.btn_toggle_capture)
        tvOemWarning = findViewById(R.id.tv_oem_warning)
        btnOpenDashboard = findViewById(R.id.btn_open_dashboard)
        btnAutoStart = findViewById(R.id.btn_auto_start)
        btnOptimizeBattery = findViewById(R.id.btn_optimize_battery)

        btnOpenDashboard.setOnClickListener {
            openDashboard()
        }

        btnAutoStart.setOnClickListener {
            OEMUtils.openAutoStartSettings(this)
        }

        btnOptimizeBattery.setOnClickListener {
            requestBatteryOptimization()
        }

        btnActivateAdmin.setOnClickListener {
            activateDeviceAdmin()
        }

        btnToggleCapture.setOnClickListener {
            toggleCapture()
        }

        updateUI()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
        updateCaptureStatus()
        // Auto-arm remote capture while the app is foreground — unless the
        // owner explicitly disarmed it (privacy opt-out). Android 14+ only
        // allows STARTING the camera|microphone foreground service from a
        // foreground context or a notification-action tap, so this is the
        // reliable arm point: once armed, remote "capture now" commands work
        // even from a locked screen. If Camera/Mic aren't fully granted,
        // MediaCaptureService posts a notification with the exact fix.
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        if (prefs.getBoolean(PREF_AUTO_ARM, true)) {
            try {
                val intent = Intent(this, MediaCaptureService::class.java)
                    .setAction(MediaCaptureService.ACTION_ARM)
                ContextCompat.startForegroundService(this, intent)
            } catch (e: Exception) {
                // Best-effort: arming failure must never break the home screen.
            }
        }
    }

    private fun updateUI() {
        // Connection status
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "")
        val email = prefs.getString("user_email", "")

        tvConnectionStatus.text = if (serverUrl.isNullOrEmpty()) {
            "Disconnected"
        } else {
            "Connected — $email"
        }

        // Uninstall protection status — the base gate is an active Device Admin
        // (Android refuses to uninstall the app until it's deactivated).
        val adminActive = isDeviceAdminActive()
        val hardBlock = UninstallProtection.isUninstallBlocked(this)
        tvUninstallStatus.text = when {
            hardBlock -> "🛡 Uninstall protection: HARD BLOCKED (device owner)"
            adminActive -> "🛡 Uninstall protection: ACTIVE (device admin)"
            else -> "⚠ Uninstall protection: OFF — anyone can uninstall Magneetar"
        }
        tvUninstallStatus.setTextColor(
            if (hardBlock || adminActive) android.graphics.Color.parseColor("#00FF88")
            else android.graphics.Color.parseColor("#FFB800")
        )
        btnActivateAdmin.visibility = if (adminActive) android.view.View.GONE else android.view.View.VISIBLE

        // Battery optimization status
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        val isBatteryOptDisabled = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            powerManager.isIgnoringBatteryOptimizations(packageName)
        } else true

        tvBatteryStatus.text = if (isBatteryOptDisabled) {
            "Battery optimization disabled ✓"
        } else {
            "Battery optimization is ON — tap to fix"
        }

        // OEM-specific warning
        if (OEMUtils.isChineseOEM()) {
            tvOemWarning.text = "📱 ${OEMUtils.getOEMName()} detected.\n" +
                    "Enable auto-start to prevent the system from killing Magneetar."
            tvOemWarning.visibility = android.view.View.VISIBLE
            btnAutoStart.visibility = android.view.View.VISIBLE
        } else {
            tvOemWarning.visibility = android.view.View.GONE
            btnAutoStart.visibility = android.view.View.GONE
        }
    }

    /** Arm/disarm remote capture and persist the choice across launches. */
    private fun toggleCapture() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val currentlyArmed = prefs.getBoolean(PREF_AUTO_ARM, true)
        try {
            val intent = Intent(this, MediaCaptureService::class.java).apply {
                action = if (currentlyArmed) {
                    MediaCaptureService.ACTION_DISARM
                } else {
                    MediaCaptureService.ACTION_ARM
                }
            }
            prefs.edit().putBoolean(PREF_AUTO_ARM, !currentlyArmed).apply()
            // Foreground context — safe to start either action.
            ContextCompat.startForegroundService(this, intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Could not toggle remote capture", Toast.LENGTH_SHORT).show()
        }
        updateCaptureStatus()
    }

    private fun updateCaptureStatus() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val armed = prefs.getBoolean(PREF_AUTO_ARM, true)
        if (armed) {
            tvCaptureStatus.text = "📷 Remote capture: ARMED — theft protection active"
            tvCaptureStatus.setTextColor(android.graphics.Color.parseColor("#00FF88"))
            btnToggleCapture.text = "Disarm Remote Capture"
        } else {
            tvCaptureStatus.text = "📷 Remote capture: OFF — tap to arm"
            tvCaptureStatus.setTextColor(android.graphics.Color.parseColor("#FFB800"))
            btnToggleCapture.text = "Arm Remote Capture"
        }
    }

    private fun openDashboard() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "")

        if (serverUrl.isNullOrEmpty()) {
            Toast.makeText(this, "Not connected. Please sign in.", Toast.LENGTH_SHORT).show()
            return
        }

        // The dashboard is a SEPARATE web app from the API server. For the
        // hosted service it lives at https://app.magneetar.me (login page),
        // while server_url is the API endpoint (https://api.magneetar.me).
        // Derive the dashboard URL from the API host:
        //   https://api.<host>  ->  https://app.<host>/login
        // Self-hosted servers that don't follow the api.* pattern fall back
        // to the server URL root so the user still lands somewhere useful.
        val dashboardUrl = try {
            val uri = android.net.Uri.parse(serverUrl)
            val host = uri.host
            if (host != null && host.startsWith("api.")) {
                // Preserve the original scheme (https for hosted, http for self-hosted)
                val scheme = uri.scheme ?: "https"
                "$scheme://app.${host.removePrefix("api.")}/login"
            } else {
                serverUrl
            }
        } catch (e: Exception) {
            serverUrl
        }

        // Open the dashboard in a browser
        try {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                data = android.net.Uri.parse(dashboardUrl)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Cannot open browser", Toast.LENGTH_SHORT).show()
        }
    }

    private fun requestBatteryOptimization() {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                val intent = Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
                ).apply {
                    data = android.net.Uri.parse("package:$packageName")
                }
                startActivity(intent)
            }
        } catch (e: Exception) {
            Toast.makeText(this, "Cannot open battery settings", Toast.LENGTH_SHORT).show()
        }
    }

    private fun isDeviceAdminActive(): Boolean {
        return try {
            val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE)
                    as android.app.admin.DevicePolicyManager
            dpm.isAdminActive(
                android.content.ComponentName(this, AdminReceiver::class.java)
            )
        } catch (e: Exception) { false }
    }

    private fun activateDeviceAdmin() {
        try {
            val admin = android.content.ComponentName(this, AdminReceiver::class.java)
            val intent = Intent(
                android.app.admin.DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN
            ).apply {
                putExtra(
                    android.app.admin.DevicePolicyManager.EXTRA_DEVICE_ADMIN,
                    admin
                )
                putExtra(
                    android.app.admin.DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                    "Required to prevent uninstalling Magneetar without first " +
                    "deactivating it, and for remote lock/wipe."
                )
            }
            startActivity(intent)
        } catch (e: Exception) {
            Toast.makeText(this, "Cannot open device admin settings", Toast.LENGTH_SHORT).show()
        }
    }
}
