package com.magneetar.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class HomeFragment : Fragment() {

    private lateinit var tvSystemStatus: TextView
    private lateinit var tvScoreValue: TextView
    private lateinit var tvScoreLabel: TextView
    private lateinit var tvScoreIssues: TextView
    private lateinit var tvScoreAlert: TextView
    private lateinit var progressScore: ProgressBar
    private lateinit var tvDeviceCount: TextView
    private lateinit var tvDeviceName: TextView
    private lateinit var tvDeviceModel: TextView
    private lateinit var tvDeviceStatusBadge: TextView
    private lateinit var tvBattery: TextView
    private lateinit var tvLocation: TextView
    private lateinit var tvEmptyActivity: TextView
    private lateinit var tvViewAll: TextView

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val refreshHandler = Handler(Looper.getMainLooper())
    private val REFRESH_INTERVAL = 10_000L
    private val refreshRunnable = object : Runnable {
        override fun run() {
            loadDevices()
            loadActivity()
            refreshHandler.postDelayed(this, REFRESH_INTERVAL)
        }
    }

    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ -> }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
        return inflater.inflate(R.layout.fragment_home, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        tvSystemStatus = view.findViewById(R.id.tv_system_status)
        tvScoreValue = view.findViewById(R.id.tv_score_value)
        tvScoreLabel = view.findViewById(R.id.tv_score_label)
        tvScoreIssues = view.findViewById(R.id.tv_score_issues)
        tvScoreAlert = view.findViewById(R.id.tv_score_alert)
        progressScore = view.findViewById(R.id.progress_score)
        tvDeviceCount = view.findViewById(R.id.tv_device_count)
        tvDeviceName = view.findViewById(R.id.tv_device_name)
        tvDeviceModel = view.findViewById(R.id.tv_device_model)
        tvDeviceStatusBadge = view.findViewById(R.id.tv_device_status_badge)
        tvBattery = view.findViewById(R.id.tv_battery)
        tvLocation = view.findViewById(R.id.tv_location)
        tvEmptyActivity = view.findViewById(R.id.tv_empty_activity)
        tvViewAll = view.findViewById(R.id.tv_view_all_alerts)

        // Quick actions
        view.findViewById<View>(R.id.cmd_lock)?.setOnClickListener { sendCommand("lock") }
        view.findViewById<View>(R.id.cmd_alarm)?.setOnClickListener { sendCommand("alarm") }
        view.findViewById<View>(R.id.cmd_locate)?.setOnClickListener { sendCommand("locate") }
        view.findViewById<View>(R.id.cmd_sos)?.setOnClickListener { confirmSOS() }

        tvViewAll.setOnClickListener {
            (activity as? DashboardActivity)?.navigateToTab(R.id.nav_alerts)
        }

        // Battery-optimization attention card: visible only when the OS is
        // still allowed to kill Magneetar's background services. Tapping it
        // routes straight to the system exemption dialog.
        view.findViewById<View>(R.id.card_battery_opt)?.setOnClickListener {
            OEMUtils.requestBatteryOptimizationExemption(requireContext())
        }
        syncBatteryCard(view)

        loadDevices()
        loadActivity()
        refreshHandler.postDelayed(refreshRunnable, REFRESH_INTERVAL)
    }

    override fun onResume() {
        super.onResume()
        loadDevices()
        // Re-check on return from system settings — the user may have just
        // granted (or revoked) the exemption.
        view?.let { syncBatteryCard(it) }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        refreshHandler.removeCallbacks(refreshRunnable)
    }

    /** Show the attention card only when background runs are not exempted. */
    private fun syncBatteryCard(view: View) {
        val card = view.findViewById<View>(R.id.card_battery_opt) ?: return
        card.visibility = if (OEMUtils.isBatteryOptimizationWhitelisted(requireContext())) {
            View.GONE
        } else {
            View.VISIBLE
        }
    }

    private fun loadDevices() {
        val prefs = requireContext().getSharedPreferences("mt", 0)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val userToken = TokenVault.accessToken(requireContext())

        if (serverUrl.isEmpty() || userToken.isEmpty()) {
            tvDeviceName.text = "Not signed in"
            return
        }

        val request = Request.Builder()
            .url("$serverUrl/api/dashboard/devices")
            .addHeader("Authorization", "Bearer $userToken")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string() ?: return
                activity?.runOnUiThread {
                    try {
                        val json = JSONObject(body)
                        val arr = json.optJSONArray("devices") ?: return@runOnUiThread

                        if (arr.length() == 0) {
                            tvDeviceName.text = "No device linked"
                            tvDeviceModel.text = "Install Magneetar on your device"
                            tvDeviceCount.text = "0 devices"
                            tvDeviceStatusBadge.text = "OFFLINE"
                            tvDeviceStatusBadge.setTextColor(ContextCompat.getColor(requireContext(), R.color.status_offline))
                            return@runOnUiThread
                        }

                        val device = arr.getJSONObject(0)
                        val name = device.optString("alias") ?: device.optString("model", "Device")
                        val model = device.optString("model", "")
                        val isOnline = device.optBoolean("is_online", false)
                        val battery = device.optInt("battery_percent", -1)
                        val lat = device.optDouble("lat", 0.0)
                        val lng = device.optDouble("lng", 0.0)

                        tvDeviceName.text = name
                        tvDeviceModel.text = model
                        tvDeviceCount.text = "${arr.length()} device${if (arr.length() > 1) "s" else ""}"

                        if (isOnline) {
                            tvSystemStatus.text = "SYS ACTIVE"
                            tvSystemStatus.setTextColor(ContextCompat.getColor(requireContext(), R.color.status_online))
                            tvDeviceStatusBadge.text = "SECURED"
                            tvDeviceStatusBadge.setTextColor(ContextCompat.getColor(requireContext(), R.color.status_online))
                        } else {
                            tvSystemStatus.text = "OFFLINE"
                            tvSystemStatus.setTextColor(ContextCompat.getColor(requireContext(), R.color.status_offline))
                            tvDeviceStatusBadge.text = "OFFLINE"
                            tvDeviceStatusBadge.setTextColor(ContextCompat.getColor(requireContext(), R.color.status_offline))
                        }

                        tvBattery.text = if (battery >= 0) "$battery%" else "—"

                        if (lat != 0.0 && lng != 0.0) {
                            tvLocation.text = String.format("%.4f°N %.4f°E", lat, lng)
                        } else {
                            tvLocation.text = "Awaiting location fix"
                        }

                        updateSecurityScore(isOnline, battery)

                        // Save for police report
                        prefs.edit()
                            .putFloat("last_lat", lat.toFloat())
                            .putFloat("last_lng", lng.toFloat())
                            .putString("device_model", model)
                            .putString("device_name", name)
                            .apply()

                    } catch (_: Exception) {}
                }
            }
        })
    }

    private fun updateSecurityScore(isOnline: Boolean, battery: Int) {
        var score = 0
        var issues = 0

        score += 30 // IMEI registered
        if (isOnline) score += 30 else issues++
        if (battery > 20) score += 20 else if (battery > 0) score += 10 else issues++
        val prefs = requireContext().getSharedPreferences("mt", 0)
        val lastLat = prefs.getFloat("last_lat", 0f)
        if (lastLat != 0f) score += 20 else issues++

        progressScore.progress = score
        tvScoreValue.text = "$score"
        tvScoreLabel.text = if (score >= 80) "PROTECTED" else if (score >= 50) "PARTIAL" else "AT RISK"
        tvScoreLabel.setTextColor(ContextCompat.getColor(requireContext(),
            if (score >= 80) R.color.status_online else if (score >= 50) R.color.alert_warning else R.color.alert_critical))

        if (issues == 0) {
            tvScoreIssues.text = "All systems operational"
            tvScoreAlert.visibility = View.GONE
        } else {
            tvScoreIssues.text = "$issues issue${if (issues > 1) "s" else ""} require attention"
            tvScoreAlert.visibility = View.VISIBLE
            tvScoreAlert.text = "$issues Device Alert${if (issues > 1) "s" else ""}"
        }
    }

    private fun loadActivity() {
        val prefs = requireContext().getSharedPreferences("mt", 0)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val userToken = TokenVault.accessToken(requireContext())
        if (serverUrl.isEmpty() || userToken.isEmpty()) return

        val request = Request.Builder()
            .url("$serverUrl/api/dashboard/alerts")
            .addHeader("Authorization", "Bearer $userToken")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string() ?: return
                activity?.runOnUiThread {
                    try {
                        val json = JSONObject(body)
                        val arr = json.optJSONArray("alerts")
                        if (arr == null || arr.length() == 0) {
                            tvEmptyActivity.visibility = View.VISIBLE
                        } else {
                            tvEmptyActivity.visibility = View.GONE
                        }
                    } catch (_: Exception) {}
                }
            }
        })
    }

    private fun sendCommand(command: String) {
        val prefs = requireContext().getSharedPreferences("mt", 0)
        val serverUrl = prefs.getString("server_url", "") ?: ""
        val userToken = TokenVault.accessToken(requireContext())
        val deviceId = prefs.getString("selected_device_id", "") ?: ""

        if (serverUrl.isEmpty() || userToken.isEmpty() || deviceId.isEmpty()) return

        val body = JSONObject().apply { put("command", command) }.toString()
        val request = Request.Builder()
            .url("$serverUrl/api/dashboard/devices/$deviceId/commands")
            .addHeader("Authorization", "Bearer $userToken")
            .addHeader("Content-Type", "application/json")
            .post(body.toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) {
                activity?.runOnUiThread {
                    val msg = if (response.isSuccessful) "✓ $command sent" else "✗ Failed"
                    tvEmptyActivity.text = msg
                    tvEmptyActivity.visibility = View.VISIBLE
                    tvEmptyActivity.postDelayed({ tvEmptyActivity.visibility = View.GONE }, 3000)
                }
            }
        })
    }

    private fun confirmSOS() {
        AlertDialog.Builder(requireContext())
            .setTitle("SOS Alert")
            .setMessage("This will send an emergency alert with your location to all trusted contacts. Continue?")
            .setPositiveButton("Send SOS") { _, _ -> sendCommand("siren") }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
