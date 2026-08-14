package com.magneetar.app

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Find Network (COMPETITOR_AUDIT P1 #6, Phase 1) — the guardian's beacon
 * scanner.
 *
 * An opted-in guardian's phone passively scans for Magneetar SOS beacons
 * (other people's stolen devices advertising their recovery token over BLE).
 * On a valid beacon:
 *   1. decode the token (SosBeacon.tokenFromServiceUuid — magic-verified);
 *   2. check the cooldown tracker (SosBeaconTracker) so repeated BLE
 *      advertisements of the SAME beacon don't spam the sighting endpoint —
 *      the server rate-limits guardians to 10/hour, and one beacon advertises
 *      many times a second;
 *   3. report a sighting to `POST /api/recovery/sightings` with the token
 *      (never the request id), the guardian's own location, and the user's
 *      account token (a sighting requires an opted-in real account).
 *
 * Privacy: the guardian reports their OWN coordinates (where the beacon was
 * seen), never the stolen device's. The scanner only starts for accounts
 * that opted in as guardians (the caller checks `GET /api/guardian/profile`).
 *
 * Runs as a dataSync foreground service with a low-profile notification.
 */
class GuardianBeaconScanner : Service() {

    companion object {
        private const val TAG = "MagneetarGuardianScan"
        private const val CHANNEL_ID = "mt_guardian_scan"
        private const val NOTIF_ID = 4949
        private const val SCAN_PERIOD_MS = 30_000L // 30s of scanning
        private const val SCAN_PAUSE_MS = 60_000L // then 60s of rest (battery)

        // ── Battery-aware pacing (Find Network followup) ────────────────────
        // The scanner must never be the reason a guardian's phone dies. The
        // pause between scan bursts grows with battery pressure and screen
        // state, and scanning stops entirely at critical battery:
        //   normal (screen on / charging)  -> 60s pause
        //   screen off                     -> 5 min pause (idle phone)
        //   low battery (< 15%)            -> 10 min pause
        //   critical battery (< 5%)        -> paused until charging
        private const val BATTERY_LOW_PCT = 15
        private const val BATTERY_CRITICAL_PCT = 5
        private const val SCAN_PAUSE_SCREEN_OFF_MS = 5 * 60_000L
        private const val SCAN_PAUSE_LOW_BATTERY_MS = 10 * 60_000L

        /** Start (or re-arm) the scanner. Safe to call repeatedly. */
        fun start(context: Context) {
            try {
                androidx.core.content.ContextCompat.startForegroundService(
                    context,
                    Intent(context, GuardianBeaconScanner::class.java),
                )
            } catch (e: Exception) {
                Log.w(TAG, "startForegroundService failed: ${e.message}")
            }
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
    private val tracker by lazy { SosBeaconTracker.persistent(this) }

    @SuppressLint("ForegroundServiceType")
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification("Find Network scan on"))
        scope.launch { scanLoop() }
    }

    /** GET /api/guardian/profile with the user token — opted_in gate. */
    private suspend fun guardianOptedIn(): Boolean {
        val userToken = TokenVault.accessToken(this)
        if (userToken.isEmpty()) return false
        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/guardian/profile")
            .get()
            .addHeader("Authorization", "Bearer $userToken")
            .build()
        return try {
            client.newCall(request).execute().use { resp ->
                if (resp.code != 200) return false
                JSONObject(resp.body?.string() ?: "{}").optBoolean("opted_in", false)
            }
        } catch (e: Exception) {
            Log.w(TAG, "guardian profile check failed: ${e.message}")
            false
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    override fun onDestroy() {
        stopScan()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private suspend fun scanLoop() {
        var optedIn = false
        while (scope.isActive) {
            try {
                // Only scan for accounts that actually opted in as guardians —
                // otherwise the scanner would burn battery for nothing (and
                // every sighting would 403 server-side anyway). Re-checked each
                // cycle so an owner who opts in later starts scanning without
                // a service restart.
                optedIn = guardianOptedIn()
                if (optedIn && !isBatteryCritical()) {
                    scanOnce()
                }
            } catch (e: Exception) {
                Log.w(TAG, "scan cycle failed: ${e.message}")
            }
            kotlinx.coroutines.delay(nextPauseMs())
        }
    }

    /**
     * Battery-aware pause between scan bursts. The scan itself is already
     * LOW_POWER mode and short (30s per minute of rest); this widens the rest
     * window as battery pressure grows, and stops scanning entirely below the
     * critical threshold (checked before scanOnce above).
     */
    private fun nextPauseMs(): Long {
        val battery = batteryPercent()
        if (battery != null && battery < BATTERY_CRITICAL_PCT && !isCharging()) {
            // Critical — pause until the phone is charging again; the loop
            // keeps running (cheap) and re-checks on every tick.
            return SCAN_PAUSE_LOW_BATTERY_MS
        }
        if (battery != null && battery < BATTERY_LOW_PCT && !isCharging()) {
            return SCAN_PAUSE_LOW_BATTERY_MS
        }
        // Screen off (or locked): the phone is idle and nobody is looking at
        // a beacon — scan far less often. Charging or screen on: normal pace.
        if (!isCharging() && !isScreenInteractive()) {
            return SCAN_PAUSE_SCREEN_OFF_MS
        }
        return SCAN_PAUSE_MS
    }

    private fun isBatteryCritical(): Boolean {
        val pct = batteryPercent() ?: return false
        return pct < BATTERY_CRITICAL_PCT && !isCharging()
    }

    /** Current battery percent (0-100), or null if unknown. */
    private fun batteryPercent(): Int? {
        return try {
            val bm = getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return null
            bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY).let {
                if (it in 0..100) it else null
            }
        } catch (e: Exception) {
            null
        }
    }

    private fun isCharging(): Boolean {
        return try {
            val sticky = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
                ?: return false
            val status = sticky.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
            status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL
        } catch (e: Exception) {
            false
        }
    }

    private fun isScreenInteractive(): Boolean {
        return try {
            val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return true
            pm.isInteractive
        } catch (e: Exception) {
            true // unknown — assume interactive (scan at normal pace)
        }
    }

    // BLUETOOTH_SCAN is checked in hasScanPermission() before this runs —
    // lint can't see the runtime guard (same pattern as TrackingService).
    @SuppressLint("MissingPermission")
    private fun scanOnce() {
        val scanner = leScanner() ?: return
        if (!hasScanPermission()) return
        try {
            val settings = ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_POWER)
                .build()
            scanner.startScan(null, settings, scanCallback)
            // Scan for SCAN_PERIOD_MS, then stop (the loop's pause handles the rest).
            scope.launch {
                kotlinx.coroutines.delay(SCAN_PERIOD_MS)
                stopScan()
            }
        } catch (e: Exception) {
            Log.w(TAG, "scan start failed: ${e.message}")
        }
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult?) {
            val record = result?.scanRecord ?: return
            val uuid = record.serviceUuids?.firstOrNull()?.uuid ?: return
            val token = SosBeacon.tokenFromServiceUuid(uuid) ?: return

            // Cooldown: this beacon was already reported recently — skip.
            if (tracker.isInCooldown(token)) return
            tracker.rememberReported(token)

            scope.launch { reportSighting(token) }
        }

        override fun onScanFailed(errorCode: Int) {
            Log.w(TAG, "scan failed: code $errorCode")
        }
    }

    /**
     * POST /api/recovery/sightings {beacon_token, lat, lng} with the user's
     * account token. Only real opted-in accounts pass the server gate.
     */
    private suspend fun reportSighting(token: String) {
        val userToken = TokenVault.accessToken(this)
        if (userToken.isEmpty()) return // no signed-in account -> cannot report

        val (lat, lng) = lastKnownLocation() ?: run {
            Log.w(TAG, "no location fix — sighting skipped")
            return
        }

        val body = JSONObject().apply {
            put("beacon_token", token)
            put("lat", lat)
            put("lng", lng)
        }.toString().toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/recovery/sightings")
            .post(body)
            .addHeader("Authorization", "Bearer $userToken")
            .build()

        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code in 200..299) {
                    Log.d(TAG, "Sighting reported for token ${token.take(6)}...")
                } else {
                    // 403 = not opted in, 429 = rate limit, 400/404 = closed
                    // request. All are expected non-errors — log quietly.
                    Log.d(TAG, "Sighting skipped (HTTP ${resp.code})")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "sighting report failed: ${e.message}")
        }
    }

    /**
     * The guardian's OWN last known position (coarse is fine for a sighting).
     *
     * NOTE: this needs the LOCATION permission, not the BLE one — on API 31+
     * BLUETOOTH_SCAN and ACCESS_FINE_LOCATION are separate runtime grants, so
     * gating on hasScanPermission() here would let a BLE-granted/
     * location-denied device throw SecurityException (crashing the coroutine).
     */
    @SuppressLint("MissingPermission") // guarded by hasLocationPermission()
    private fun lastKnownLocation(): Pair<Double, Double>? {
        if (!hasLocationPermission()) return null
        return try {
            val lm = getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val loc = lm.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                ?: lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                ?: return null
            loc.latitude to loc.longitude
        } catch (e: SecurityException) {
            Log.w(TAG, "location permission revoked mid-run: ${e.message}")
            null
        }
    }

    private fun hasLocationPermission(): Boolean {
        val fine = checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION)
        val coarse = checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION)
        return fine == PackageManager.PERMISSION_GRANTED || coarse == PackageManager.PERMISSION_GRANTED
    }

    private fun leScanner(): BluetoothLeScanner? = try {
        val manager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        manager.adapter?.bluetoothLeScanner
    } catch (e: Exception) {
        null
    }

    private fun hasScanPermission(): Boolean {
        // BLUETOOTH_SCAN is a runtime permission on API 31+; on older
        // devices scanning rides on location permission (already granted).
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return checkSelfPermission(android.Manifest.permission.BLUETOOTH_SCAN) ==
                PackageManager.PERMISSION_GRANTED
        }
        return checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }

    // Only ever stops a scan this service started (permission already held
    // when scanOnce ran) — lint can't see the runtime guard.
    @SuppressLint("MissingPermission")
    private fun stopScan() {
        try {
            leScanner()?.stopScan(scanCallback)
        } catch (e: Exception) {
            Log.w(TAG, "scan stop failed: ${e.message}")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Find Network", NotificationManager.IMPORTANCE_LOW)
            )
        }
    }

    private fun buildNotification(text: String) =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_m)
            .setContentTitle("Magneetar Find Network")
            .setContentText(text)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
}
