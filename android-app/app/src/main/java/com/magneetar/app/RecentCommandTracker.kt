package com.magneetar.app

import android.content.Context

/**
 * At-most-once execution memory for remote commands.
 *
 * WHY THIS EXISTS (the "executes in loops" bug):
 *
 * The command protocol is poll-until-ack: the server re-delivers any command
 * still `pending` every 10s (the device poll), and only stops when the device
 * acks. That re-delivery is what makes the protocol reliable — a device that
 * crashes mid-execution gets the command again. But it has a sharp edge: if an
 * ack is LOST (network blip, auth death, service restart while the ack was in
 * flight), the command stays pending and the device re-EXECUTES it on every
 * poll — a siren replaying, a fresh photo every 10s, a location burst every
 * 10s — until the command expires (5-30 min). The old inFlightCommands guard
 * only prevented CONCURRENT handling within one process; it was released the
 * moment handleCommand returned, so the next poll happily re-ran the command.
 *
 * This tracker is the durable memory that closes that window:
 *   - It records (command id → final status) AFTER every execution attempt,
 *     persisted in SharedPreferences so it survives service restarts (the
 *     watchdog restarts TrackingService aggressively on Chinese OEMs).
 *   - The command loop consults it BEFORE executing: a command recorded
 *     within the retention window is NEVER executed twice. Instead the device
 *     re-sends the recorded ack (idempotent on the server), which converges
 *     the "stuck pending" state as soon as connectivity returns — no second
 *     execution, no infinite loop.
 *
 * Retention is 60 minutes — comfortably longer than the longest poll expiry
 * window (30 min for capture/location/burst; 5 min for wipe/lock/alarm), so a
 * re-delivered command can never fall out of the tracker while the server
 * still considers it pending.
 *
 * Design note: the class is pure JVM (injected StringStore + clock, and a
 * dependency-free "id=status|timestamp;" serialization — deliberately NOT
 * org.json, whose methods are unmocked stubs in local unit tests) so the
 * at-most-once contract is locked by RecentCommandTrackerTest.kt without an
 * emulator. [persistent] provides the SharedPreferences-backed production
 * store.
 *
 * Thread-safety: remember/statusOf can be called from TrackingService's IO
 * coroutine AND MediaCaptureService's thread. SharedPreferences is
 * synchronized internally, so a lost update here degrades to the command
 * being executed one extra time — never a loop, and the poll's in-flight
 * guard makes even that vanishingly rare. Acceptable for a safety net.
 */
class RecentCommandTracker(
    private val store: StringStore,
    private val nowMs: () -> Long = System::currentTimeMillis,
) {
    /**
     * Record that [commandId] reached a definitive outcome ([status]).
     * Idempotent — re-recording the same id just refreshes the timestamp,
     * which is what keeps a re-acked command inside the retention window.
     */
    fun remember(commandId: Int, status: String) {
        val map = read()
        map[commandId.toString()] = "$status|${nowMs()}"
        write(pruned(map))
    }

    /**
     * The last recorded status for [commandId] if it was handled within
     * [retentionMs], otherwise null. A null means "safe to execute again".
     */
    fun statusOf(commandId: Int, retentionMs: Long = DEFAULT_RETENTION_MS): String? {
        val raw = read()[commandId.toString()] ?: return null
        val sep = raw.lastIndexOf('|')
        if (sep <= 0) return null
        val at = raw.substring(sep + 1).toLongOrNull() ?: return null
        if (nowMs() - at > retentionMs) return null
        return raw.substring(0, sep)
    }

    /** Parse "id=status|ts;id=status|ts;..." back into a map. Corrupt input degrades to empty. */
    private fun read(): MutableMap<String, String> {
        val result = LinkedHashMap<String, String>()
        val serialized = store.read()
        if (serialized.isEmpty()) return result
        for (record in serialized.split(';')) {
            if (record.isEmpty()) continue
            val eq = record.indexOf('=')
            if (eq <= 0) continue
            result[record.substring(0, eq)] = record.substring(eq + 1)
        }
        return result
    }

    private fun write(map: Map<String, String>) {
        store.write(map.entries.joinToString(";") { "${it.key}=${it.value}" })
    }

    /** Drop entries older than 2× retention so prefs stay bounded (a handful of keys). */
    private fun pruned(map: MutableMap<String, String>): MutableMap<String, String> {
        val cutoff = nowMs() - DEFAULT_RETENTION_MS * 2
        val stale = map.entries.filter { (_, raw) ->
            val sep = raw.lastIndexOf('|')
            val at = if (sep > 0) raw.substring(sep + 1).toLongOrNull() else null
            at == null || at < cutoff
        }.map { it.key }
        stale.forEach { map.remove(it) }
        return map
    }

    companion object {
        const val DEFAULT_RETENTION_MS = 60L * 60 * 1000L // 60 min

        /** SharedPreferences-backed production store. */
        fun persistent(context: Context): RecentCommandTracker {
            val prefs = context.getSharedPreferences("mt_cmd_tracker", Context.MODE_PRIVATE)
            return RecentCommandTracker(
                object : StringStore {
                    override fun read(): String = prefs.getString("handled", "") ?: ""
                    override fun write(json: String) {
                        prefs.edit().putString("handled", json).apply()
                    }
                }
            )
        }
    }
}

/** Minimal persistence seam so the tracker is testable on the JVM. */
interface StringStore {
    fun read(): String
    fun write(json: String)
}
