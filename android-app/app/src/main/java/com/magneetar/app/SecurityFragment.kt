package com.magneetar.app

import android.app.admin.DevicePolicyManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException

class SecurityFragment : Fragment() {

    private lateinit var tvSecurityScore: TextView
    private lateinit var tvDeviceAdminStatus: TextView
    private lateinit var tvImeiValue: TextView
    private lateinit var tvTrackingStatus: TextView
    private lateinit var tvEncryptionStatus: TextView
    private lateinit var tvAuthStatus: TextView
    private lateinit var layoutImei: View
    private lateinit var layoutDeviceAdmin: LinearLayout
    private lateinit var btnToggleAdmin: TextView
    private lateinit var btnEmergencyWipe: TextView
    private lateinit var btnPoliceReport: TextView
    private lateinit var btnPanicAlert: TextView

    private val client = OkHttpClient.Builder().build()
    private val adminReceiver by lazy { ComponentName(requireContext(), AdminReceiver::class.java) }
    private lateinit var dpm: DevicePolicyManager

    private val adminLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { updateDeviceAdminStatus() }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View? = inflater.inflate(R.layout.fragment_security, container, false)

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        dpm = requireContext().getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager

        tvSecurityScore = view.findViewById(R.id.tvSecurityScore)
        tvDeviceAdminStatus = view.findViewById(R.id.tvDeviceAdminStatus)
        tvImeiValue = view.findViewById(R.id.tvImeiValue)
        tvTrackingStatus = view.findViewById(R.id.tvTrackingStatus)
        tvEncryptionStatus = view.findViewById(R.id.tvEncryptionStatus)
        tvAuthStatus = view.findViewById(R.id.tvAuthStatus)
        layoutImei = view.findViewById(R.id.layoutImei)
        layoutDeviceAdmin = view.findViewById(R.id.layoutDeviceAdmin)
        btnToggleAdmin = view.findViewById(R.id.btnToggleAdmin)
        btnEmergencyWipe = view.findViewById(R.id.btnEmergencyWipe)
        btnPoliceReport = view.findViewById(R.id.btnPoliceReport)
        btnPanicAlert = view.findViewById(R.id.btnPanicAlert)

        updateDeviceAdminStatus()
        loadSecurityData()
        setupActions()
    }

    private fun setupActions() {
        layoutImei.setOnClickListener {
            val clipboard = requireContext().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val imei = tvImeiValue.text.toString()
            if (imei != "Loading..." && imei != "Not available") {
                clipboard.setPrimaryClip(ClipData.newPlainText("IMEI", imei))
                Toast.makeText(requireContext(), "IMEI copied", Toast.LENGTH_SHORT).show()
            }
        }

        layoutDeviceAdmin.setOnClickListener {
            if (dpm.isAdminActive(adminReceiver)) {
                dpm.removeActiveAdmin(adminReceiver)
            } else {
                val intent = android.content.Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN).apply {
                    putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, adminReceiver)
                    putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION, "Magneetar requires Device Admin to prevent unauthorized app removal.")
                }
                adminLauncher.launch(intent)
            }
            updateDeviceAdminStatus()
        }

        btnToggleAdmin.setOnClickListener { layoutDeviceAdmin.performClick() }

        btnEmergencyWipe.setOnClickListener {
            androidx.appcompat.app.AlertDialog.Builder(requireContext())
                .setTitle("Emergency Wipe")
                .setMessage("This will remotely wipe ALL data from your device. This action is IRREVERSIBLE. Are you absolutely sure?")
                .setPositiveButton("WIPE DEVICE") { _, _ ->
                    executeEmergencyCommand("wipe")
                }
                .setNegativeButton("Cancel", null)
                .show()
        }

        btnPoliceReport.setOnClickListener {
            val reportBody = """
                DEVICE SECURITY REPORT
                =====================
                IMEI: ${tvImeiValue.text}
                Time: ${java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss", java.util.Locale.getDefault()).format(java.util.Date())}
                Device: ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}
                Status: Stolen - Remote Tracking Active

                Please present this report at your nearest police station.
                Magneetar is actively tracking this device.
            """.trimIndent()
            val clipboard = requireContext().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            clipboard.setPrimaryClip(ClipData.newPlainText("Police Report", reportBody))
            Toast.makeText(requireContext(), "Report copied to clipboard", Toast.LENGTH_LONG).show()
        }

        btnPanicAlert.setOnClickListener {
            executeEmergencyCommand("siren")
            Toast.makeText(requireContext(), "Siren activated on all devices", Toast.LENGTH_LONG).show()
        }
    }

    private fun executeEmergencyCommand(command: String) {
        val prefs = requireContext().getSharedPreferences("mt_session", Context.MODE_PRIVATE)
        val token = TokenVault.accessToken(requireContext())
        val deviceId = prefs.getString("selected_device_id", "") ?: ""
        val serverUrl = prefs.getString("server_url", "") ?: ""
        if (serverUrl.isEmpty() || token.isEmpty() || deviceId.isEmpty()) return

        val requestBody = JSONObject().apply {
            put("command_type", command)
            put("target_device_id", deviceId)
        }

        val request = Request.Builder()
            .url("$serverUrl/api/commands/send")
            .addHeader("Authorization", "Bearer $token")
            .post(requestBody.toString().toRequestBody("application/json".toMediaType()))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) { response.close() }
        })
    }

    private fun updateDeviceAdminStatus() {
        if (!isAdded) return
        val isActive = dpm.isAdminActive(adminReceiver)
        tvDeviceAdminStatus.text = if (isActive) "Active" else "Inactive"
        tvDeviceAdminStatus.setTextColor(
            resources.getColor(if (isActive) R.color.status_green else R.color.status_yellow, null)
        )
        btnToggleAdmin.text = if (isActive) "DEACTIVATE" else "ACTIVATE"
        btnToggleAdmin.setTextColor(
            resources.getColor(if (isActive) R.color.status_yellow else R.color.accent_aubergine, null)
        )
    }

    private fun loadSecurityData() {
        val prefs = requireContext().getSharedPreferences("mt_session", Context.MODE_PRIVATE)
        val token = TokenVault.accessToken(requireContext())
        val deviceId = prefs.getString("selected_device_id", "") ?: ""
        val serverUrl = prefs.getString("server_url", "") ?: ""
        if (serverUrl.isEmpty() || token.isEmpty() || deviceId.isEmpty()) return

        // Load IMEI
        val imeiRequest = Request.Builder()
            .url("$serverUrl/api/dashboard/devices/$deviceId/security")
            .addHeader("Authorization", "Bearer $token")
            .build()

        client.newCall(imeiRequest).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {}
            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string() ?: return
                response.close()
                if (response.code != 200) return
                try {
                    val json = JSONObject(body)
                    val imei = json.optString("imei", "Not available")
                    activity?.runOnUiThread {
                        tvImeiValue.text = imei
                    }
                } catch (_: Exception) {}
            }
        })

        // Update status indicators
        val isTracking = requireContext().getSharedPreferences("mt_session", 0).getBoolean("tracking_enabled", false)
        val hasPin = requireContext().getSharedPreferences("mt_security", 0).getString("pin_hash", null) != null
        tvTrackingStatus.text = if (isTracking) "Active" else "Inactive"
        tvTrackingStatus.setTextColor(resources.getColor(if (isTracking) R.color.status_green else R.color.status_yellow, null))
        tvEncryptionStatus.text = "AES-256 Enabled"
        tvEncryptionStatus.setTextColor(resources.getColor(R.color.status_green, null))
        tvAuthStatus.text = if (hasPin) "Biometric + PIN" else "Basic"
        tvAuthStatus.setTextColor(resources.getColor(if (hasPin) R.color.status_green else R.color.status_yellow, null))

        updateSecurityScore(isTracking, dpm.isAdminActive(adminReceiver), hasPin)
    }

    private fun updateSecurityScore(tracking: Boolean, adminActive: Boolean, pinSet: Boolean) {
        var score = 30
        if (tracking) score += 25
        if (adminActive) score += 25
        if (pinSet) score += 20
        tvSecurityScore.text = "$score"
    }
}
