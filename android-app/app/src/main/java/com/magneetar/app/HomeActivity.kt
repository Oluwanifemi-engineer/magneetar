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

/**
 * Home screen shown after successful setup.
 * Displays protection status, connection state, and quick actions.
 */
class HomeActivity : AppCompatActivity() {

    private lateinit var tvConnectionStatus: TextView
    private lateinit var tvBatteryStatus: TextView
    private lateinit var tvOemWarning: TextView
    private lateinit var btnOpenDashboard: Button
    private lateinit var btnAutoStart: Button
    private lateinit var btnOptimizeBattery: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_home)

        tvConnectionStatus = findViewById(R.id.tv_connection_status)
        tvBatteryStatus = findViewById(R.id.tv_battery_opt_status)
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

        updateUI()
    }

    override fun onResume() {
        super.onResume()
        updateUI()
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

    private fun openDashboard() {
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val serverUrl = prefs.getString("server_url", "")

        if (serverUrl.isNullOrEmpty()) {
            Toast.makeText(this, "Not connected. Please sign in.", Toast.LENGTH_SHORT).show()
            return
        }

        // Open the dashboard in a browser
        try {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                data = android.net.Uri.parse(serverUrl)
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
}
