package com.magneetar.app

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.net.wifi.rtt.RangingRequest
import android.net.wifi.rtt.RangingResult
import android.net.wifi.rtt.RangingResultCallback
import android.net.wifi.rtt.WifiRttManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import java.util.concurrent.Executor
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.max

/**
 * G1-17: Wi-Fi RTT (802.11mc) ranging — 1-2m indoor fixes.
 *
 * WHY (research-backed — see docs/location-accuracy-research.md): when GPS
 * is dead indoors, the only fixes are cell/WiFi fingerprint fixes at
 * 100-500m. Android's Wi-Fi RTT API (API 28+) measures the round-trip time
 * to nearby RTT-capable access points and, on API 29+, the AP itself
 * reports its own position (ResponderLocation / LCI-LCR). Ranging to >=3
 * such APs and trilaterating (RttTrilateration) yields a fix accurate to
 * 1-2m — real measured distances instead of a fingerprint lookup.
 *
 * HONEST CEILINGS (why this is a graceful no-op most of the time):
 *  - Requires API 28+ hardware with FEATURE_WIFI_RTT (checked by the caller
 *    via [isSupported]).
 *  - Requires the AP to answer FTM (802.11mc) AND report LCI/LCR (API 29+).
 *    API 28-only APs almost never report a position, so no fix is produced
 *    — by design, never a fake one.
 *  - Requires location services ON and Wi-Fi scanning ON (Settings >
 *    Location > Wi-Fi scanning).
 *  - Requires NEARBY_WIFI_DEVICES (API 33+) / ACCESS_FINE_LOCATION (<33)
 *    granted at runtime.
 *  - RTT is throttled for background apps, but TrackingService is a
 *    foreground location service — ranging is permitted.
 *
 * Every failure is a silent no-op: the tracker keeps its existing
 * fused/GPS/network streams exactly as before.
 */
class WifiRttLocator(private val context: Context) {

    /** A trilaterated fix, handed to the caller to route through the Kalman. */
    data class Fix(val lat: Double, val lng: Double, val accuracyMeters: Double)

    companion object {
        private const val MAX_APS = 8
        /** Accept a trilateration only when the fitted residuals are this tight (m). */
        private const val MAX_RESIDUAL_M = 10.0
        /** Accuracy floor — RTT is ~1-2m; never claim better than 3m. */
        private const val ACCURACY_FLOOR_M = 3.0
        /** A 2D fix is only meaningful when the anchors span at least this (m). */
        private const val MIN_ANCHOR_SPAN_M = 5.0
        /** Ranges beyond this are suspect (bad multipath) — reject. */
        private const val MAX_RANGE_M = 300.0
    }

    private val wifiManager: WifiManager =
        context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val rttManager: WifiRttManager? =
        context.applicationContext.getSystemService(Context.WIFI_RTT_RANGING_SERVICE) as? WifiRttManager

    /**
     * True when the device advertises RTT support. Checks the package
     * feature (FEATURE_WIFI_RTT) and that the service is reachable.
     */
    fun isSupported(): Boolean {
        if (rttManager == null) return false
        return try {
            context.packageManager.hasSystemFeature(
                android.content.pm.PackageManager.FEATURE_WIFI_RTT
            )
        } catch (e: Exception) {
            false
        }
    }

    /** RTT availability can change (WiFi off, SoftAP active) — re-check each attempt. */
    private fun isAvailable(): Boolean {
        return try {
            rttManager?.isAvailable == true
        } catch (e: Exception) {
            false
        }
    }

    private fun hasPermission(): Boolean {
        val perm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }
        return ContextCompat.checkSelfPermission(context, perm) == PackageManager.PERMISSION_GRANTED
    }

    private fun locationEnabled(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                val lm = context.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
                lm.isLocationEnabled
            } else {
                Settings.Secure.getInt(context.contentResolver, Settings.Secure.LOCATION_MODE, 0) != 0
            }
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Fire-and-forget ranging attempt. [onFix] runs on [executor] with a
     * fresh RTT fix, or never runs — every failure mode is a silent no-op.
     * Callers should dispatch [onFix] onto the main looper (the Kalman
     * filter is single-threaded, like every other fix source).
     */
    fun tryRangeOnce(executor: Executor, onFix: (Fix) -> Unit) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) return
        val mgr = rttManager ?: return
        if (!isSupported() || !isAvailable()) return
        if (!hasPermission() || !locationEnabled()) return

        // Use the OS's cached scan results (the OS scans periodically while
        // Wi-Fi scanning is on) instead of startScan(): requesting scans
        // aggressively trips WifiManager's scan throttle.
        val aps: List<ScanResult> = try {
            @Suppress("DEPRECATION") // is80211mcResponder stays functional on 33+
            wifiManager.scanResults
                .filter { it.is80211mcResponder }
                .distinctBy { it.BSSID }
                .take(MAX_APS)
        } catch (e: Exception) {
            return
        }
        if (aps.size < 3) return

        val request: RangingRequest = try {
            RangingRequest.Builder().addAccessPoints(aps).build()
        } catch (e: Exception) {
            return
        }

        try {
            mgr.startRanging(request, executor, object : RangingResultCallback() {
                override fun onRangingResults(results: List<RangingResult>) {
                    val fix = computeFix(results) ?: return
                    onFix(fix)
                }

                override fun onRangingFailure(code: Int) {
                    // Silent no-op: throttled / WiFi state changed / transient
                    // failure — the existing streams keep the tracker alive.
                }
            })
        } catch (e: Exception) {
            // SecurityException (permission revoked mid-range), etc.
        }
    }

    /**
     * Turn a batch of ranging results into a single trilaterated fix, or
     * null when the geometry is unusable (never a fake fix).
     */
    private fun computeFix(results: List<RangingResult>): Fix? {
        // AP positions (ResponderLocation) only exist on API 29+. On API 28
        // (Android 9) the AP rarely reports LCI/LCR and we hold no anchor
        // database — no fix, honestly.
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return null

        var originLat = 0.0
        var originLng = 0.0
        var haveOrigin = false
        val anchors = mutableListOf<RttTrilateration.Anchor>()
        for (r in results) {
            if (r.status != RangingResult.STATUS_SUCCESS) continue
            val distanceM = r.distanceMm / 1000.0
            if (distanceM <= 0.0 || distanceM > MAX_RANGE_M) continue
            val apLoc = responderLocation(r) ?: continue
            if (!apLoc.latitude.isFinite() || !apLoc.longitude.isFinite()) continue
            if (!haveOrigin) {
                originLat = apLoc.latitude
                originLng = apLoc.longitude
                haveOrigin = true
            }
            val (east, north) = toLocal(apLoc.latitude, apLoc.longitude, originLat, originLng)
            anchors.add(RttTrilateration.Anchor(east, north, distanceM))
        }
        if (anchors.size < 3) return null
        // Three anchors stacked on top of each other cannot triangulate.
        if (anchorSpanM(anchors) < MIN_ANCHOR_SPAN_M) return null

        val solution = RttTrilateration.solve(anchors) ?: return null
        val residual = RttTrilateration.residualMeters(anchors, solution)
        // A lying AP position (or heavy multipath) blows the residual — the
        // anchors no longer agree on where the device is. Reject.
        if (!residual.isFinite() || residual > MAX_RESIDUAL_M) return null

        val (lat, lng) = fromLocal(solution.first, solution.second, originLat, originLng)
        if (!lat.isFinite() || !lng.isFinite()) return null
        val accuracy = max(ACCURACY_FLOOR_M, 1.5 * residual)
        return Fix(lat, lng, accuracy)
    }

    /** The AP's self-reported position, when it provides LCI/LCR. */
    private fun responderLocation(r: RangingResult): Location? {
        return try {
            // getUnverifiedResponderLocation() (no-arg) exists on API 29+ and
            // wraps the AP-claimed position — unverified by definition, which is
            // why the residual check in computeFix rejects lying anchors. The
            // fill-in (Location) variant was removed from the API surface in
            // Android 15, so the no-arg form is the only portable call.
            r.getUnverifiedResponderLocation()?.toLocation()
        } catch (e: Exception) {
            null
        }
    }

    /** Equirectangular meters around an origin — same convention as LocationFilter. */
    private fun toLocal(lat: Double, lng: Double, originLat: Double, originLng: Double): Pair<Double, Double> {
        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * cos(originLat * PI / 180.0).coerceAtLeast(0.01)
        return (lng - originLng) * mPerDegLng to (lat - originLat) * mPerDegLat
    }

    private fun fromLocal(east: Double, north: Double, originLat: Double, originLng: Double): Pair<Double, Double> {
        val mPerDegLat = 111_320.0
        val mPerDegLng = 111_320.0 * cos(originLat * PI / 180.0).coerceAtLeast(0.01)
        return originLat + north / mPerDegLat to originLng + east / mPerDegLng
    }

    private fun anchorSpanM(anchors: List<RttTrilateration.Anchor>): Double {
        var span = 0.0
        for (i in anchors.indices) {
            for (j in i + 1 until anchors.size) {
                val d = hypot(anchors[i].eastM - anchors[j].eastM, anchors[i].northM - anchors[j].northM)
                if (d > span) span = d
            }
        }
        return span
    }
}
