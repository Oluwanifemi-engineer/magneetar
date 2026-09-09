package com.magneetar.app

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Activity tab — alerts feed with working All / Security / Location filters.
 *
 * The filter chips are real controls: the latest payload is cached and
 * re-rendered client-side on selection (no extra network round-trip).
 * Filtering uses the same severity classification the badges display, so
 * "Security" == CRITICAL+WARNING and "Location" == everything else.
 */
class AlertsFragment : Fragment() {

    private lateinit var layoutAlertList: LinearLayout
    private lateinit var tvEmpty: TextView
    private lateinit var tvCriticalCount: TextView

    private var chipAll: TextView? = null
    private var chipSecurity: TextView? = null
    private var chipLocation: TextView? = null
    private var filter = FILTER_ALL
    private var cachedAlerts: JSONArray? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    private val refreshHandler = Handler(Looper.getMainLooper())
    private val refreshRunnable = object : Runnable {
        override fun run() { loadAlerts(); refreshHandler.postDelayed(this, 15_000L) }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View? {
        return inflater.inflate(R.layout.fragment_alerts, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        layoutAlertList = view.findViewById(R.id.layout_alert_list)
        tvEmpty = view.findViewById(R.id.tv_empty)
        tvCriticalCount = view.findViewById(R.id.tv_critical_count)
        chipAll = view.findViewById(R.id.chip_all)
        chipSecurity = view.findViewById(R.id.chip_security)
        chipLocation = view.findViewById(R.id.chip_location)

        chipAll?.setOnClickListener { setFilter(FILTER_ALL) }
        chipSecurity?.setOnClickListener { setFilter(FILTER_SECURITY) }
        chipLocation?.setOnClickListener { setFilter(FILTER_LOCATION) }

        loadAlerts()
        refreshHandler.postDelayed(refreshRunnable, 15_000L)
    }

    override fun onResume() { super.onResume(); loadAlerts() }
    override fun onDestroyView() { super.onDestroyView(); refreshHandler.removeCallbacks(refreshRunnable) }

    private fun setFilter(newFilter: String) {
        filter = newFilter
        renderAlerts()
    }

    private fun loadAlerts() {
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
                        val arr = json.optJSONArray("alerts") ?: return@runOnUiThread
                        cachedAlerts = arr
                        renderAlerts()
                    } catch (_: Exception) {}
                }
            }
        })
    }

    /** Re-render from the cached payload honoring the active filter. */
    private fun renderAlerts() {
        val arr = cachedAlerts ?: return
        val all = (0 until arr.length()).map { arr.getJSONObject(it) }
        val visible = when (filter) {
            FILTER_SECURITY -> all.filter { severityOf(it) != "INFO" }
            FILTER_LOCATION -> all.filter { severityOf(it) == "INFO" }
            else -> all
        }

        layoutAlertList.removeAllViews()

        if (visible.isEmpty()) {
            tvEmpty.text = if (all.isEmpty()) "No alerts yet" else "No alerts in this filter"
            tvEmpty.visibility = View.VISIBLE
            layoutAlertList.visibility = View.GONE
        } else {
            tvEmpty.visibility = View.GONE
            layoutAlertList.visibility = View.VISIBLE
        }

        var criticalCount = 0
        visible.forEachIndexed { i, alert ->
            if (severityOf(alert) == "CRITICAL") criticalCount++
            layoutAlertList.addView(createAlertCard(alert))
            if (i < visible.size - 1) {
                val spacer = View(requireContext())
                spacer.layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT, 8)
                layoutAlertList.addView(spacer)
            }
        }

        if (criticalCount > 0) {
            tvCriticalCount.text = "$criticalCount critical"
            tvCriticalCount.visibility = View.VISIBLE
        } else {
            tvCriticalCount.visibility = View.GONE
        }

        // Chip visual states
        val activeRes = R.drawable.filter_active
        val inactiveRes = R.drawable.filter_inactive
        val activeColor = ContextCompat.getColor(requireContext(), R.color.text_primary)
        val inactiveColor = ContextCompat.getColor(requireContext(), R.color.text_secondary)
        chipAll?.setBackgroundResource(if (filter == FILTER_ALL) activeRes else inactiveRes)
        chipAll?.setTextColor(if (filter == FILTER_ALL) activeColor else inactiveColor)
        chipSecurity?.setBackgroundResource(if (filter == FILTER_SECURITY) activeRes else inactiveRes)
        chipSecurity?.setTextColor(if (filter == FILTER_SECURITY) activeColor else inactiveColor)
        chipLocation?.setBackgroundResource(if (filter == FILTER_LOCATION) activeRes else inactiveRes)
        chipLocation?.setTextColor(if (filter == FILTER_LOCATION) activeColor else inactiveColor)
    }

    private fun severityOf(alert: JSONObject): String = when {
        alert.optString("type", "unknown").contains("theft") ||
            alert.optString("type", "unknown").contains("critical") -> "CRITICAL"
        alert.optString("type", "unknown").contains("sim") ||
            alert.optString("type", "unknown").contains("offline") ||
            alert.optString("type", "unknown").contains("unlock") -> "WARNING"
        else -> "INFO"
    }

    private fun createAlertCard(alert: JSONObject): View {
        val view = LayoutInflater.from(requireContext()).inflate(R.layout.item_alert_card, layoutAlertList, false)

        val severity = severityOf(alert)
        val message = alert.optString("message", alert.optString("details", "Alert received"))
        val createdAt = alert.optString("created_at", "")

        val colorRes = when (severity) {
            "CRITICAL" -> R.color.alert_critical
            "WARNING" -> R.color.alert_warning
            else -> R.color.alert_info
        }

        view.findViewById<TextView>(R.id.tv_alert_type).text = severity
        view.findViewById<TextView>(R.id.tv_alert_type).setTextColor(
            ContextCompat.getColor(requireContext(), colorRes))
        // Severity stripe matches the badge — status color as status only.
        view.findViewById<View>(R.id.alert_stripe).setBackgroundColor(
            ContextCompat.getColor(requireContext(), colorRes))
        view.findViewById<TextView>(R.id.tv_alert_message).text = message
        view.findViewById<TextView>(R.id.tv_alert_time).text = formatTime(createdAt)

        return view
    }

    private fun formatTime(iso: String): String {
        return try {
            val parts = iso.split("T")
            if (parts.size > 1) parts[1].take(5) else iso.take(10)
        } catch (_: Exception) { iso }
    }

    companion object {
        private const val FILTER_ALL = "all"
        private const val FILTER_SECURITY = "security"
        private const val FILTER_LOCATION = "location"
    }
}
