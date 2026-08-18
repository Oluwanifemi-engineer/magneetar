package com.magneetar.app

import android.annotation.SuppressLint
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanRecord
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
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
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
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

        // ── Relay mesh (docs/offline-network-design.md §3.2) ────────────────
        // The relay re-advertises a beacon it saw (hop+1, relayed=1) so the
        // beacon hops onward through phones that never met the lost device.
        // One short burst per scan cycle; RelayOutbox gates how often each
        // beacon is re-advertised (15 min) and stops at MAX_HOP / stale origin.
        private const val RELAY_MANUFACTURER_ID = 0xFFFF // MeshBeacon envelope
        private const val RELAY_ADVERTISE_MS = 10_000L
        // Flush queued offline sightings at most once per ~5 scan cycles so a
        // dead network can't hammer the endpoint every 90s.
        private const val FLUSH_EVERY_CYCLES = 5

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
    private val outbox by lazy { RelayOutbox.persistent(this) }

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
        stopRelayAdvertising()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private suspend fun scanLoop() {
        var optedIn = false
        var cycle = 0
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
                    // Relay pass: re-advertise ONE beacon we saw (hop+1) so
                    // the beacon hops onward through the mesh. Best-effort.
                    relayOnce()
                    // Flush pass: deliver offline-queued sightings when we
                    // have connectivity again (throttled to every 5th cycle).
                    if (cycle % FLUSH_EVERY_CYCLES == 0) flushOutbox()
                    cycle++
                }
            } catch (e: Exception) {
                Log.w(TAG, "scan cycle failed: ${e.message}")
            }
            delay(nextPauseMs())
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

            // Relay metadata (Layer 2): the v2 manufacturer-data envelope tells
            // us how many hops this beacon has survived + when it originated.
            // A Phase-1 beacon without the envelope is a direct sighting
            // (hop 0, unknown origin, not a relay).
            val envelope = decodeRelayEnvelope(record)
            val hop = envelope?.hop ?: 0
            val originTs = envelope?.originUnixSecs ?: 0L
            val relayed = envelope?.relayed ?: false

            // Cooldown: this beacon was already reported recently — skip.
            if (tracker.isInCooldown(token)) return
            tracker.rememberReported(token)

            // Ensure the outbox knows the beacon (relay bookkeeping). The
            // sighting itself is reported live below; if THAT fails (offline),
            // reportSighting queues it for a later flush.
            outbox.queue(token, hop, originTs, 0.0, 0.0, relayed, needsFlush = false)

            scope.launch { reportSighting(token, hop, originTs, relayed) }
        }

        override fun onScanFailed(errorCode: Int) {
            Log.w(TAG, "scan failed: code $errorCode")
        }
    }

    /** Decode the v2 relay envelope from the advertisement's manufacturer data. */
    private fun decodeRelayEnvelope(record: ScanRecord): MeshBeacon.RelayMeta? {
        // getManufacturerSpecificData returns the payload AFTER the 2-byte
        // manufacturer id — which is exactly our envelope (starts "MG").
        val payload = record.getManufacturerSpecificData(RELAY_MANUFACTURER_ID) ?: return null
        return MeshBeacon.decode(payload)
    }

    /**
     * POST /api/recovery/sightings {beacon_token, lat, lng, hop_count,
     * relayed} with the user's account token. Only real opted-in accounts
     * pass the server gate. On a NETWORK failure the sighting is queued in
     * the relay outbox and flushed on a later cycle (offline operation);
     * server rejections (403/429/400/404) are expected non-errors and never
     * queued.
     */
    private suspend fun reportSighting(token: String, hop: Int, originTs: Long, relayed: Boolean) {
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
            put("hop_count", hop)
            put("relayed", relayed)
        }.toString().toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/recovery/sightings")
            .post(body)
            .addHeader("Authorization", "Bearer $userToken")
            .build()

        var delivered = false
        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code in 200..299) {
                    delivered = true
                    Log.d(TAG, "Sighting reported for token ${token.take(6)}... (hop $hop)")
                } else {
                    // 403 = not opted in, 429 = rate limit, 400/404 = closed
                    // request. All are expected non-errors — log quietly.
                    Log.d(TAG, "Sighting skipped (HTTP ${resp.code})")
                }
            }
        } catch (e: Exception) {
            // Network failure = offline. Queue for a later flush; the relay
            // outbox keeps one entry per token and marks it pending.
            Log.w(TAG, "sighting report failed — queued for flush: ${e.message}")
            outbox.queue(token, hop, originTs, lat, lng, relayed, needsFlush = true)
        }
        if (delivered) outbox.markFlushed(token)
    }

    /**
     * Deliver offline-queued sightings now that we have connectivity. Server
     * rejections keep the entry pending (retried next flush cycle); only a
     * 2xx clears it. Stops at the first network failure (still offline).
     */
    private suspend fun flushOutbox() {
        val userToken = TokenVault.accessToken(this)
        if (userToken.isEmpty()) return
        for (entry in outbox.pendingFlush()) {
            val body = JSONObject().apply {
                put("beacon_token", entry.token)
                put("lat", entry.lat)
                put("lng", entry.lng)
                put("hop_count", entry.hop)
                put("relayed", entry.relayed)
            }.toString().toRequestBody("application/json".toMediaType())
            val request = Request.Builder()
                .url("${BuildConfig.SERVER_URL}/api/recovery/sightings")
                .post(body)
                .addHeader("Authorization", "Bearer $userToken")
                .build()
            try {
                client.newCall(request).execute().use { resp ->
                    if (resp.code in 200..299) {
                        outbox.markFlushed(entry.token)
                        Log.d(TAG, "Flushed queued sighting for ${entry.token.take(6)}...")
                    }
                    // else: keep pending (rate limit / closed request) — retry later
                }
            } catch (e: Exception) {
                Log.w(TAG, "flush still offline: ${e.message}")
                break // still no connectivity — try again next flush window
            }
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
        } catch (e: Exception) {
            // Permission revoked mid-run, or a provider that doesn't exist on
            // this device (getLastKnownLocation throws for missing providers
            // on some API levels) — never crash the scan loop.
            Log.w(TAG, "location lookup failed: ${e.message}")
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

    // ── Relay mesh: re-advertise beacons we saw (hop+1, relayed=1) ──────────

    private var relayAdvertiseJob: Job? = null
    private var relayAdvertisingToken: String? = null

    /**
     * Pick ONE beacon from the outbox and re-advertise it (hop+1, relayed=1)
     * so the beacon hops onward through the mesh. The outbox gates frequency
     * (15 min per beacon), hop (MAX_HOP) and freshness (24h origin TTL).
     * Best-effort: any failure just means this beacon isn't relayed this cycle.
     */
    private fun relayOnce() {
        if (relayAdvertisingToken != null) return // one relay at a time
        val entry = outbox.advertiseCandidates().firstOrNull() ?: return
        advertiseRelay(entry)
    }

    /** Advertise the service UUID + v2 envelope for RELAY_ADVERTISE_MS. */
    @SuppressLint("MissingPermission") // guarded by hasAdvertisePermission()
    private fun advertiseRelay(entry: RelayOutbox.RelayEntry) {
        if (!hasAdvertisePermission()) return
        val advertiser = bluetoothLeAdvertiser() ?: return
        val uuid = SosBeacon.serviceUuidFor(entry.token) ?: return
        // Re-anchor unknown origins at the relay's now — a direct beacon the
        // lost device is still advertising right now; bounds mesh lifetime to
        // RELAY_TTL_S from the last direct sighting.
        val originTs = if (entry.originTs > 0) entry.originTs else System.currentTimeMillis() / 1000
        val envelope = MeshBeacon.encode(entry.token, entry.hop + 1, originTs, relayed = true) ?: return

        val data = AdvertiseData.Builder()
            .addServiceUuid(android.os.ParcelUuid(uuid))
            .addManufacturerData(RELAY_MANUFACTURER_ID, envelope)
            .setIncludeDeviceName(false)
            .build()
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(false)
            .build()

        relayAdvertisingToken = entry.token
        relayAdvertiseJob = scope.launch {
            try {
                advertiser.startAdvertising(settings, data, relayAdvertiseCallback)
                delay(RELAY_ADVERTISE_MS)
            } catch (e: Exception) {
                Log.w(TAG, "relay advertise start failed: ${e.message}")
            } finally {
                stopRelayAdvertising()
            }
        }
    }

    private val relayAdvertiseCallback = object : AdvertiseCallback() {
        override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
            Log.d(TAG, "relay advertising ${relayAdvertisingToken?.take(6)}...")
            relayAdvertisingToken?.let { outbox.markAdvertised(it) }
        }

        override fun onStartFailure(errorCode: Int) {
            // e.g. ADVERTISE_FAILED_TOO_MANY_ADVERTISERS (the SOS broadcaster
            // may hold the slot on this device) — skip, try another cycle.
            Log.w(TAG, "relay advertise failed: code $errorCode")
            relayAdvertisingToken = null
        }
    }

    // Only stops a relay advertisement this service started (permission was
    // held when advertiseRelay ran) — lint can't see the runtime guard.
    @SuppressLint("MissingPermission")
    private fun stopRelayAdvertising() {
        val token = relayAdvertisingToken
        if (token == null && relayAdvertiseJob == null) return
        relayAdvertiseJob?.cancel()
        relayAdvertiseJob = null
        try {
            bluetoothLeAdvertiser()?.stopAdvertising(relayAdvertiseCallback)
        } catch (e: Exception) {
            Log.w(TAG, "relay advertise stop failed: ${e.message}")
        }
        relayAdvertisingToken = null
    }

    private fun bluetoothLeAdvertiser(): android.bluetooth.le.BluetoothLeAdvertiser? = try {
        val manager = getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
        manager.adapter?.bluetoothLeAdvertiser
    } catch (e: Exception) {
        null
    }

    private fun hasAdvertisePermission(): Boolean {
        // BLUETOOTH_ADVERTISE is a runtime permission on API 31+; on older
        // devices advertising rides on the classic BLUETOOTH permission.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            return checkSelfPermission(android.Manifest.permission.BLUETOOTH_ADVERTISE) ==
                PackageManager.PERMISSION_GRANTED
        }
        return true
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
