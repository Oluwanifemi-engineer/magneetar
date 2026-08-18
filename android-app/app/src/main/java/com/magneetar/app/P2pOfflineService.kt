package com.magneetar.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.Log
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.security.SecureRandom

/**
 * Offline Device Network (docs/offline-network-design.md §4) — Layer 3:
 * paired P2P over Nearby Connections `P2P_CLUSTER` (~100 m, mesh topology,
 * encrypted transport channel).
 *
 * Two of the OWNER's devices that completed the online pairing (PairVault
 * holds the shared 32-byte pair_secret) can find each other and exchange
 * data FULLY OFFLINE:
 *   - Discovery: the Nearby service id is derived from the pair secret
 *     (P2pPairing.serviceUuidFor) — only paired devices derive the same id,
 *     so non-paired phones don't even see the traffic.
 *   - Handshake: mutual 16-byte challenge; each side returns
 *     HMAC-SHA256(secret, nonce || idA || idB)[:16] with the two device ids
 *     in lexicographic order (both sides agree). Mismatch → disconnect.
 *   - Messages (P2pMessage, AES-GCM encrypted with the pair secret):
 *     HELLO / LAST_KNOWN / CMD / ACK / SIGHTING_CARRIER.
 *
 * Battery posture (§4.4): NEVER always-on. The service is started explicitly
 * (Offline Find screen / pairing UI) or when a paired device is in lost
 * mode; it stops advertising + discovery when told to stop.
 *
 * Command flow: a CMD from the paired device is deduped by command id
 * (RecentCommandTracker — at-most-once, exactly like the poll path), then
 * executed through TrackingService's existing handlers; the ACK travels
 * back over this P2P channel (the server is never in the data path).
 */
class P2pOfflineService : Service() {

    companion object {
        private const val TAG = "MagneetarP2P"
        private const val CHANNEL_ID = "mt_p2p"
        private const val NOTIF_ID = 7717

        const val ACTION_START = "com.magneetar.app.action.P2P_START"
        const val ACTION_STOP = "com.magneetar.app.action.P2P_STOP"

        /** TrackingService action: execute a verified P2P command. */
        const val ACTION_P2P_COMMAND = "com.magneetar.app.action.P2P_COMMAND"

        /** Prefs key: peer's last-known location (read by Offline Find UI). */
        const val PREF_PEER_LAST_KNOWN = "p2p_peer_last_known"

        /** Start the offline P2P layer (foreground service). */
        fun start(context: Context) {
            val intent = Intent(context, P2pOfflineService::class.java).setAction(ACTION_START)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                @Suppress("DEPRECATION")
                context.startService(intent)
            }
        }

        /** Stop the offline P2P layer. */
        fun stop(context: Context) {
            context.startService(Intent(context, P2pOfflineService::class.java).setAction(ACTION_STOP))
        }
    }

    private lateinit var connectionsClient: ConnectionsClient
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val recentCommands by lazy { RecentCommandTracker.persistent(this) }
    private val outbox by lazy { RelayOutbox.persistent(this) }

    /** endpointId → pair secret (hex) for the connection. */
    private val sessions = HashMap<String, String>()

    /** endpointId → service id the connection was made under (discoverer). */
    private val endpointServiceIds = HashMap<String, String>()

    /** Our own device id (from the pairing/registration prefs). */
    private val ownDeviceId: String
        get() = getSharedPreferences("mt", Context.MODE_PRIVATE).getString("device_id", "") ?: ""

    /** The known peer device id for an endpoint, learned from HELLO. */
    private val peerDeviceIds = HashMap<String, String>()

    /** Endpoints that passed the HMAC handshake. */
    private val authenticated = HashSet<String>()

    /** The challenge nonce we sent to each endpoint (hex), for AUTH verify. */
    private val sentNonces = HashMap<String, String>()

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIF_ID, buildNotification())
        connectionsClient = Nearby.getConnectionsClient(this)
        scope.launch { startAdvertiseAndDiscover() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> stopSelf()
        }
        return START_NOT_STICKY
    }

    private suspend fun startAdvertiseAndDiscover() {
        val pairings = PairVault.list(this)
        if (pairings.isEmpty()) {
            Log.i(TAG, "No paired devices — offline P2P idle")
            return
        }
        for (pairing in pairings) {
            val serviceId = P2pPairing.serviceUuidFor(pairing.secret).toString()
            Log.i(TAG, "P2P advertising+discovering on ${serviceId.take(16)}... (pair ${pairing.pairId.take(12)})")
            try {
                connectionsClient.startAdvertising(
                    ownDeviceId.ifEmpty { "magneetar" },
                    serviceId,
                    connectionLifecycleCallback,
                    AdvertisingOptions.Builder().setStrategy(Strategy.P2P_CLUSTER).build(),
                )
            } catch (e: Exception) {
                Log.w(TAG, "startAdvertising failed: ${e.message}")
            }
            try {
                connectionsClient.startDiscovery(
                    serviceId,
                    endpointDiscoveryCallback,
                    DiscoveryOptions.Builder().setStrategy(Strategy.P2P_CLUSTER).build(),
                )
            } catch (e: Exception) {
                Log.w(TAG, "startDiscovery failed: ${e.message}")
            }
        }
    }

    // ── Connection lifecycle ─────────────────────────────────────────────────

    private val connectionLifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            // Resolve the pair secret BEFORE accepting, so every payload
            // (including our own HELLO) is encrypted under the right key:
            //   - incoming (we advertised): the peer's device id is the
            //     endpointName it passed to requestConnection.
            //   - outgoing (we discovered): we recorded the service id in
            //     onEndpointFound.
            val secret = if (info.isIncomingConnection) {
                resolveSecretByPeerId(info.endpointName)
            } else {
                endpointServiceIds[endpointId]?.let { resolveSecretByServiceId(it) }
            }
            if (secret == null) {
                Log.w(TAG, "Connection from $endpointId has no matching pairing — rejecting")
                connectionsClient.rejectConnection(endpointId)
                return
            }
            sessions[endpointId] = secret.toHex()
            Log.d(TAG, "Connection initiated: $endpointId (${info.endpointName})")
            connectionsClient.acceptConnection(endpointId, payloadCallback)
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            if (resolution.status.isSuccess) {
                Log.i(TAG, "Connected to $endpointId — starting handshake")
                // Both sides send HELLO + CHALLENGE (mutual auth). The secret
                // was resolved at initiation; if it is somehow missing, drop.
                val secret = sessions[endpointId] ?: run {
                    connectionsClient.disconnectFromEndpoint(endpointId)
                    cleanup(endpointId)
                    return
                }
                val nonce = randomNonceHex()
                sentNonces[endpointId] = nonce
                send(endpointId, P2pMessage.Envelope(type = P2pMessage.TYPE_HELLO, deviceId = ownDeviceId))
                send(endpointId, P2pMessage.Envelope(type = P2pMessage.TYPE_CHALLENGE, nonce = nonce))
            } else {
                Log.w(TAG, "Connection to $endpointId failed: ${resolution.status.statusCode}")
                cleanup(endpointId)
            }
        }

        override fun onDisconnected(endpointId: String) {
            Log.i(TAG, "Disconnected from $endpointId")
            cleanup(endpointId)
        }
    }

    private val endpointDiscoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            Log.d(TAG, "Endpoint found: $endpointId (${info.serviceId.take(16)}...)")
            // Only connect to our own derived service ids (the discovery
            // filter already guarantees this, but double-check).
            if (PairVault.list(this@P2pOfflineService).any { P2pPairing.serviceUuidFor(it.secret).toString() == info.serviceId }) {
                endpointServiceIds[endpointId] = info.serviceId
                connectionsClient.requestConnection(
                    ownDeviceId.ifEmpty { "magneetar" },
                    endpointId,
                    connectionLifecycleCallback,
                )
            }
        }

        override fun onEndpointLost(endpointId: String) {
            Log.d(TAG, "Endpoint lost: $endpointId")
            cleanup(endpointId)
        }
    }

    // ── Payloads ─────────────────────────────────────────────────────────────

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            val bytes = payload.asBytes() ?: return
            val secretHex = sessions[endpointId] ?: return
            val secret = secretHex.hexToBytes()
            val envelope = P2pMessage.decrypt(secret, bytes) ?: run {
                Log.w(TAG, "Payload from $endpointId failed to decrypt — dropping")
                return
            }
            scope.launch { handleMessage(endpointId, envelope) }
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) {
            // Bytes payloads are atomic — nothing to do.
        }
    }

    private suspend fun handleMessage(endpointId: String, msg: P2pMessage.Envelope) {
        when (msg.type) {
            P2pMessage.TYPE_HELLO -> {
                peerDeviceIds[endpointId] = msg.deviceId
                // Cross-check the secret the connection was made under: the
                // peer's device id must belong to the same pairing. A HELLO
                // that doesn't match the pairing → drop the connection.
                val expected = sessions[endpointId]?.hexToBytes()
                val actual = resolveSecretByPeerId(msg.deviceId)
                if (expected == null || actual == null || !expected.contentEquals(actual)) {
                    Log.w(TAG, "HELLO from device ${msg.deviceId} does not match the pairing — disconnecting")
                    connectionsClient.disconnectFromEndpoint(endpointId)
                    cleanup(endpointId)
                }
            }

            P2pMessage.TYPE_CHALLENGE -> {
                // Respond with the HMAC over the peer's nonce, ids in
                // lexicographic order (both sides agree on this ordering).
                val myId = ownDeviceId
                val peerId = peerDeviceIds[endpointId] ?: return
                val secret = sessions[endpointId]?.hexToBytes() ?: return
                val (idA, idB) = if (myId <= peerId) myId to peerId else peerId to myId
                val nonceBytes = msg.nonce.hexToBytes()
                if (nonceBytes.size != 16) return
                val mac = P2pPairing.hmacResponse(secret, nonceBytes, idA, idB)
                send(endpointId, P2pMessage.Envelope(type = P2pMessage.TYPE_AUTH, nonce = msg.nonce, mac = mac.toHex()))
            }

            P2pMessage.TYPE_AUTH -> {
                // Verify the peer's AUTH against the nonce we sent.
                val expected = sentNonces[endpointId]
                val secret = sessions[endpointId]?.hexToBytes() ?: return
                val myId = ownDeviceId
                val peerId = peerDeviceIds[endpointId] ?: return
                val (idA, idB) = if (myId <= peerId) myId to peerId else peerId to myId
                val ok = expected != null &&
                    msg.nonce == expected &&
                    P2pPairing.verify(secret, expected.hexToBytes(), idA, idB, msg.mac.hexToBytes())
                if (ok) {
                    authenticated.add(endpointId)
                    Log.i(TAG, "Handshake verified with $endpointId — P2P authenticated")
                } else {
                    Log.w(TAG, "Handshake FAILED with $endpointId — disconnecting")
                    connectionsClient.disconnectFromEndpoint(endpointId)
                    cleanup(endpointId)
                }
            }

            P2pMessage.TYPE_LAST_KNOWN -> {
                if (endpointId !in authenticated) return
                storePeerLastKnown(msg)
            }

            P2pMessage.TYPE_CMD -> {
                if (endpointId !in authenticated) return
                executeOfflineCommand(endpointId, msg)
            }

            P2pMessage.TYPE_SIGHTING_CARRIER -> {
                if (endpointId !in authenticated) return
                carrySighting(msg)
            }
        }
    }

    /**
     * Execute a verified offline command: dedup by command id (at-most-once —
     * a re-sent CMD after a lost ACK re-sends the ack, never re-executes),
     * route to TrackingService's existing handlers, then ack back over P2P
     * with the recorded status.
     */
    private suspend fun executeOfflineCommand(endpointId: String, msg: P2pMessage.Envelope) {
        val cmdId = msg.cmdId
        // Dedup: already handled within retention → re-send the recorded ack.
        val known = recentCommands.statusOf(cmdId)
        if (known != null) {
            send(endpointId, P2pMessage.Envelope(type = P2pMessage.TYPE_ACK, cmdId = cmdId, status = known))
            return
        }
        // Hand to TrackingService (executes through handleCommand, which
        // records the definitive status in RecentCommandTracker).
        val intent = Intent(this, TrackingService::class.java).apply {
            action = ACTION_P2P_COMMAND
            putExtra(SmsCommandReceiver.EXTRA_COMMAND_ID, cmdId)
            putExtra(SmsCommandReceiver.EXTRA_COMMAND, msg.command)
            putExtra(SmsCommandReceiver.EXTRA_PARAMS, msg.params)
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                @Suppress("DEPRECATION")
                startService(intent)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Could not hand P2P command to TrackingService: ${e.message}")
        }
        // Best-effort ack: poll the tracker briefly for the recorded outcome
        // (siren/lock/lost_mode/ping all complete in <1s); on timeout ack
        // "executed" — the sender re-sends until acked, and the dedup above
        // prevents a re-execution.
        var status = "executed"
        for (i in 0 until 20) {
            delay(250)
            val recorded = recentCommands.statusOf(cmdId)
            if (recorded != null) {
                status = recorded
                break
            }
        }
        send(endpointId, P2pMessage.Envelope(type = P2pMessage.TYPE_ACK, cmdId = cmdId, status = status))
    }

    /** SIGHTING_CARRIER: carry a relayed beacon envelope (mesh density). */
    private fun carrySighting(msg: P2pMessage.Envelope) {
        val raw = Base64.decode(msg.beaconEnvelope, Base64.NO_WRAP)
        val meta = MeshBeacon.decode(raw) ?: return
        if (!MeshBeacon.canRelay(meta.hop)) return
        if (MeshBeacon.isExpired(meta.originUnixSecs, System.currentTimeMillis() / 1000)) return
        outbox.queue(
            token = meta.token,
            hop = meta.hop,
            originTs = meta.originUnixSecs,
            lat = msg.lat,
            lng = msg.lng,
            relayed = true,
            needsFlush = true,
        )
        Log.d(TAG, "Carried relayed beacon ${meta.token.take(6)}... hop ${meta.hop}")
    }

    /** Resolve the pair secret whose pairing contains [peerDeviceId]. */
    private fun resolveSecretByPeerId(peerDeviceId: String): ByteArray? {
        val myId = ownDeviceId
        return PairVault.list(this).firstOrNull { p ->
            (p.deviceA == myId && p.deviceB == peerDeviceId) ||
                (p.deviceA == peerDeviceId && p.deviceB == myId)
        }?.secret
    }

    /** Resolve the pair secret whose pairing derives [serviceId]. */
    private fun resolveSecretByServiceId(serviceId: String): ByteArray? =
        PairVault.list(this).firstOrNull { p ->
            P2pPairing.serviceUuidFor(p.secret).toString() == serviceId
        }?.secret

    private fun storePeerLastKnown(msg: P2pMessage.Envelope) {
        val json = JSONObject().apply {
            put("lat", msg.lat)
            put("lng", msg.lng)
            put("accuracy", msg.accuracy)
            put("provider", msg.provider)
            put("timestamp", msg.timestamp)
        }.toString()
        getSharedPreferences("mt", Context.MODE_PRIVATE)
            .edit().putString(PREF_PEER_LAST_KNOWN, json).apply()
        Log.d(TAG, "Peer last-known stored: ${msg.lat},${msg.lng} (acc ${msg.accuracy}m)")
    }

    private fun send(endpointId: String, envelope: P2pMessage.Envelope) {
        val secret = sessions[endpointId]?.hexToBytes() ?: return
        val bytes = P2pMessage.encrypt(secret, envelope) ?: return
        try {
            connectionsClient.sendPayload(endpointId, Payload.fromBytes(bytes))
        } catch (e: Exception) {
            Log.w(TAG, "sendPayload failed: ${e.message}")
        }
    }

    private fun cleanup(endpointId: String) {
        sessions.remove(endpointId)
        peerDeviceIds.remove(endpointId)
        authenticated.remove(endpointId)
        sentNonces.remove(endpointId)
        endpointServiceIds.remove(endpointId)
    }

    private fun randomNonceHex(): String {
        val bytes = ByteArray(16).also { SecureRandom().nextBytes(it) }
        return bytes.toHex()
    }

    // ── Notification ─────────────────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Offline device network",
                NotificationManager.IMPORTANCE_LOW,
            )
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val stopIntent = PendingIntent.getService(
            this, 0,
            Intent(this, P2pOfflineService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Offline device network")
            .setContentText("Paired devices can find this phone nearby")
            .setSmallIcon(android.R.drawable.ic_menu_share)
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopIntent)
            .build()
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            connectionsClient.stopAdvertising()
            connectionsClient.stopDiscovery()
        } catch (e: Exception) {
            // service already torn down
        }
        sessions.clear()
        authenticated.clear()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── hex helpers (shared with PairVault) ─────────────────────────────────

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun String.hexToBytes(): ByteArray {
        if (length % 2 != 0) return ByteArray(0)
        return ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}
