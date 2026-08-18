package com.magneetar.app

import android.content.Context

/**
 * Offline Device Network (docs/offline-network-design.md §3.2) — the
 * guardian's relay outbox.
 *
 * Two jobs, one persisted store (mirrors SosBeaconTracker's StringStore
 * pattern — pure JVM, dependency-free serialization, tested without an
 * emulator):
 *
 *   1. OFFLINE SIGHTINGS: when a guardian sees a beacon but cannot reach the
 *      server (no internet), the sighting is queued (needsFlush=true) and
 *      flushed to `POST /api/recovery/sightings` on a later cycle when
 *      connectivity returns. Live POSTs (online guardian) never queue.
 *   2. RE-ADVERTISE BOOKKEEPING: entries carry the relay envelope metadata
 *      (hop, originTs, relayed) + lastAdvertisedAt, so the scanner knows
 *      which beacons to relay onward, when, and to stop after MAX_HOP or a
 *      stale origin — without re-advertising every cycle (battery).
 *
 * One entry per token (a fresher hop of the same beacon replaces the older
 * one). Entries are pruned by age (MAX_AGE_MS) and count (MAX_ENTRIES), so
 * prefs stay bounded no matter how dense the mesh gets.
 */
class RelayOutbox(
    private val store: StringStore,
    private val nowMs: () -> Long = System::currentTimeMillis,
) {

    /** One beacon the guardian has seen, with its relay metadata. */
    data class RelayEntry(
        val token: String,
        val hop: Int,
        val originTs: Long,    // 0 = unknown (direct beacon, no envelope)
        val lat: Double,
        val lng: Double,
        val relayed: Boolean,
        val lastAdvAtMs: Long, // 0 = never re-advertised
        val seenAtMs: Long,
        val needsFlush: Boolean,
    )

    /**
     * Record that [token] was seen at (lat, lng) with the given relay
     * metadata. Upserts by token (fresher hop wins); [needsFlush] is set
     * only by the caller that FAILED a live POST. Evicts oldest entries
     * beyond MAX_ENTRIES.
     */
    fun queue(token: String, hop: Int, originTs: Long, lat: Double, lng: Double, relayed: Boolean, needsFlush: Boolean) {
        val map = read()
        val at = nowMs()
        map[token] = RelayEntry(
            token = token,
            hop = hop,
            originTs = originTs,
            lat = lat,
            lng = lng,
            relayed = relayed,
            lastAdvAtMs = map[token]?.lastAdvAtMs ?: 0L,
            seenAtMs = at,
            needsFlush = needsFlush || (map[token]?.needsFlush ?: false),
        )
        write(pruned(map))
    }

    /** All entries with a sighting still pending upload. */
    fun pendingFlush(): List<RelayEntry> = read().values.filter { it.needsFlush }

    /** Entries still worth re-advertising, oldest-first. */
    fun advertiseCandidates(reAdvCooldownMs: Long = RE_ADVERTISE_COOLDOWN_MS): List<RelayEntry> {
        val now = nowMs()
        return read().values
            .filter { MeshBeacon.canRelay(it.hop) }
            .filter { originFresh(it, now) }
            .filter { now - it.lastAdvAtMs >= reAdvCooldownMs }
            .sortedBy { it.lastAdvAtMs }
    }

    /** Record that [token] was re-advertised at this moment. */
    fun markAdvertised(token: String) {
        val map = read()
        val entry = map[token] ?: return
        map[token] = entry.copy(lastAdvAtMs = nowMs())
        write(map)
    }

    /** A sighting for [token] reached the server — clear the pending flag. */
    fun markFlushed(token: String) {
        val map = read()
        val entry = map[token] ?: return
        map[token] = entry.copy(needsFlush = false)
        write(map)
    }

    /** True when [token] is known to the outbox at all. */
    fun contains(token: String): Boolean = read().containsKey(token)

    // originTs is in unix SECONDS (the wire format), nowMs() in milliseconds.
    private fun originFresh(e: RelayEntry, nowMs: Long): Boolean =
        e.originTs <= 0L || !MeshBeacon.isExpired(e.originTs, nowMs / 1000)

    /** Parse "tok|hop|originTs|lat|lng|relayed|lastAdv|seen|flush;..." back into a map. */
    private fun read(): MutableMap<String, RelayEntry> {
        val result = LinkedHashMap<String, RelayEntry>()
        val serialized = store.read()
        if (serialized.isEmpty()) return result
        for (record in serialized.split(';')) {
            if (record.isEmpty()) continue
            val fields = record.split('|')
            if (fields.size != 9) continue
            val token = fields[0]
            if (!SosBeacon.isValidToken(token)) continue
            val hop = fields[1].toIntOrNull() ?: continue
            val originTs = fields[2].toLongOrNull() ?: continue
            val lat = fields[3].toDoubleOrNull() ?: continue
            val lng = fields[4].toDoubleOrNull() ?: continue
            val relayed = fields[5] == "1"
            val lastAdv = fields[6].toLongOrNull() ?: 0L
            val seen = fields[7].toLongOrNull() ?: 0L
            val flush = fields[8] == "1"
            result[token] = RelayEntry(token, hop, originTs, lat, lng, relayed, lastAdv, seen, flush)
        }
        return result
    }

    private fun write(map: Map<String, RelayEntry>) {
        val serialized = map.values.joinToString(";") { e ->
            listOf(
                e.token, e.hop.toString(), e.originTs.toString(), e.lat.toString(), e.lng.toString(),
                if (e.relayed) "1" else "0", e.lastAdvAtMs.toString(), e.seenAtMs.toString(),
                if (e.needsFlush) "1" else "0",
            ).joinToString("|")
        }
        store.write(serialized)
    }

    /** Drop entries older than MAX_AGE_MS, then keep only the MAX_ENTRIES newest. */
    private fun pruned(map: MutableMap<String, RelayEntry>): MutableMap<String, RelayEntry> {
        val cutoff = nowMs() - MAX_AGE_MS
        map.entries.removeAll { it.value.seenAtMs < cutoff }
        val byNewest = map.values.sortedByDescending { it.seenAtMs }
        if (byNewest.size > MAX_ENTRIES) {
            val keep = byNewest.take(MAX_ENTRIES).map { it.token }.toSet()
            map.keys.removeAll { it !in keep }
        }
        return map
    }

    companion object {
        const val MAX_ENTRIES = 500
        const val MAX_AGE_MS = 7L * 24 * 60 * 60 * 1000L // a sighting older than a week is useless
        const val RE_ADVERTISE_COOLDOWN_MS = 15L * 60 * 1000L // at most one relay per beacon per 15 min

        /** SharedPreferences-backed production store. */
        fun persistent(context: Context): RelayOutbox {
            val prefs = context.getSharedPreferences("mt_relay_outbox", Context.MODE_PRIVATE)
            return RelayOutbox(
                object : StringStore {
                    override fun read(): String = prefs.getString("entries", "") ?: ""
                    override fun write(serialized: String) {
                        prefs.edit().putString("entries", serialized).apply()
                    }
                }
            )
        }
    }
}
