package com.magneetar.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Offline Outbox — the return channel for the Offline Command Relay.
 *
 * When a command is executed over SMS while the phone has NO data, the ack
 * (and any captured location) cannot reach the server immediately. This outbox
 * queues them on disk (app-private JSON file) and TrackingService flushes them
 * the moment connectivity returns. Without it, an offline-executed command
 * would stay PENDING on the dashboard forever even though the phone ran it.
 *
 * Thread-safety: TrackingService calls enqueue/flush from Dispatchers.IO
 * coroutines; every method synchronizes on a single lock and reads/writes the
 * whole file atomically (small payloads — a handful of acks at a time).
 */
object OfflineOutbox {

    private const val FILE_NAME = "offline_outbox.json"
    private val lock = Any()

    private fun file(context: Context) = context.getFileStreamPath(FILE_NAME)

    @Synchronized
    fun enqueueAck(context: Context, commandId: Int, status: String) {
        synchronized(lock) {
            try {
                val root = readRoot(context)
                val acks = root.optJSONArray("acks") ?: JSONArray()
                val entry = JSONObject().apply {
                    put("command_id", commandId)
                    put("status", status)
                    put("queued_at", System.currentTimeMillis())
                }
                // Don't double-queue the same command ack (idempotent retries).
                for (i in 0 until acks.length()) {
                    if (acks.getJSONObject(i).optInt("command_id") == commandId) {
                        acks.put(i, entry)
                        writeRoot(context, root)
                        return
                    }
                }
                acks.put(entry)
                root.put("acks", acks)
                writeRoot(context, root)
            } catch (e: Exception) {
                // Never crash the command path over a local write failure.
            }
        }
    }

    @Synchronized
    fun enqueueLocation(context: Context, ping: JSONObject) {
        synchronized(lock) {
            try {
                val root = readRoot(context)
                val locations = root.optJSONArray("locations") ?: JSONArray()
                locations.put(ping)
                root.put("locations", locations)
                writeRoot(context, root)
            } catch (e: Exception) {
                // Best-effort.
            }
        }
    }

    /** Snapshot of queued acks + locations (JSON) and clear them. */
    @Synchronized
    fun take(context: Context): Pair<JSONArray, JSONArray>? {
        synchronized(lock) {
            return try {
                val root = readRoot(context)
                val acks = root.optJSONArray("acks") ?: JSONArray()
                val locations = root.optJSONArray("locations") ?: JSONArray()
                if (acks.length() == 0 && locations.length() == 0) {
                    null
                } else {
                    writeRoot(context, JSONObject())  // clear the file
                    Pair(acks, locations)
                }
            } catch (e: Exception) {
                null
            }
        }
    }

    /** True when any entries are queued. */
    @Synchronized
    fun isEmpty(context: Context): Boolean {
        synchronized(lock) {
            return try {
                val root = readRoot(context)
                (root.optJSONArray("acks")?.length() ?: 0) == 0 &&
                    (root.optJSONArray("locations")?.length() ?: 0) == 0
            } catch (e: Exception) {
                true
            }
        }
    }

    private fun readRoot(context: Context): JSONObject {
        return try {
            val raw = context.openFileInput(FILE_NAME).bufferedReader().use { it.readText() }
            if (raw.isBlank()) JSONObject() else JSONObject(raw)
        } catch (e: Exception) {
            JSONObject()
        }
    }

    private fun writeRoot(context: Context, root: JSONObject) {
        context.openFileOutput(FILE_NAME, Context.MODE_PRIVATE).use { fos ->
            fos.write(root.toString().toByteArray(Charsets.UTF_8))
        }
    }
}
