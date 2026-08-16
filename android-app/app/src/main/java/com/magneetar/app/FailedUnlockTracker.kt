package com.magneetar.app

/**
 * Failed-unlock ("theftie") counter — the on-device half of the
 * COMPETITOR_AUDIT P1 #4 gap.
 *
 * Repeated failed unlock attempts strongly suggest a stranger in possession
 * of the phone. This tracker counts them since the last successful unlock;
 * the app reports the count on every telemetry ping and heartbeat, Sentinel
 * scores it (+20), and the server queues an automatic front-photo + audio
 * evidence capture when it crosses MT_FAILED_UNLOCK_THRESHOLD (default 5).
 *
 * The heuristic (permission-free, works on every build — the Play flavor
 * strips the DPC permissions):
 *
 *   - SCREEN_ON with the keyguard still locked opens a "locked session".
 *   - SCREEN_OFF while that session is still open = one failed attempt
 *     (the user never got in), and the session closes.
 *   - USER_PRESENT (a successful unlock) resets the count to zero and
 *     closes any open session.
 *   - `record()` lets the DevicePolicyManager's authoritative count
 *     (getCurrentFailedPasswordAttempts, exact and zero-resetting on
 *     success) overwrite the heuristic when the app holds device-admin /
 *     device-owner privileges.
 *
 * KNOWN LIMITS (heuristic mode, documented honestly): several wrong PINs
 * inside ONE screen-on session collapse into a single failed attempt, and a
 * device with no secure lock screen never opens a session (no false
 * positives). The DPM path — which the app's uninstall-protection device
 * owner provisioning activates — reports the exact OS count instead.
 *
 * Design note: the class is pure JVM (injected StringStore + clock, and a
 * dependency-free "count|session" serialization — deliberately NOT
 * org.json, whose methods are unmocked stubs in local unit tests) so the
 * counting contract is locked by FailedUnlockTrackerTest.kt without an
 * emulator. [FailedUnlockMonitor] provides the SharedPreferences-backed
 * production store and the Android glue (keyguard + DPM reads).
 */
class FailedUnlockTracker(
    private val store: StringStore,
) {
    private var count: Int = 0
    private var sessionOpen: Boolean = false

    init {
        // Parse the persisted state ("count|session") — a corrupt/empty blob
        // degrades to a clean slate rather than crashing the service.
        val raw = store.read().trim()
        if (raw.isNotEmpty()) {
            val parts = raw.split("|")
            count = parts.getOrNull(0)?.toIntOrNull()?.coerceAtLeast(0) ?: 0
            sessionOpen = parts.getOrNull(1) == "1"
        }
    }

    private fun persist() {
        store.write("$count|${if (sessionOpen) 1 else 0}")
    }

    /** Failed attempts since the last successful unlock. */
    fun count(): Int = count

    /**
     * A screen-on event. Pass `locked=true` when the keyguard is still
     * showing (from KeyguardManager.isKeyguardLocked); opens a locked
     * session unless one is already open.
     *
     * MUST persist: production callers build a fresh tracker instance per
     * event (FailedUnlockMonitor.tracker()), so an in-memory-only flag would
     * be lost before the next SCREEN_OFF arrives and the attempt would never
     * count (G1-8 — found in the real-theft-signal field test: SCREEN_ON/OFF
     * received, count stayed 0 forever).
     */
    @Synchronized
    fun onScreenOn(locked: Boolean) {
        if (locked && !sessionOpen) {
            sessionOpen = true
            persist()
        }
    }

    /**
     * A screen-off event. If a locked session was open (the screen lit up
     * behind the keyguard and nobody got in), that session counts as one
     * failed attempt and closes. No session = nothing (screen was showing
     * an unlocked app).
     */
    @Synchronized
    fun onScreenOff() {
        if (sessionOpen) {
            count += 1
            sessionOpen = false
            persist()
        }
    }

    /** A successful unlock (ACTION_USER_PRESENT) — resets the counter. */
    @Synchronized
    fun onUserPresent() {
        count = 0
        sessionOpen = false
        persist()
    }

    /**
     * Overwrite the heuristic count with an authoritative source (the
     * DevicePolicyManager's exact failed-attempts count, which is also
     * zero-reset by the OS on a successful unlock). Ignored when the source
     * cannot be read (null) so the heuristic survives.
     *
     * No-op writes are skipped: this is called from the telemetry/heartbeat
     * hot path, and persisting an identical state on every ping would write
     * SharedPreferences every ~3s forever (the file's own convention — see
     * TrackingService's SimChangeMonitor comment — is to do no wasteful work
     * on the 3s location path).
     */
    @Synchronized
    fun record(exact: Int?) {
        if (exact == null) return
        val next = exact.coerceAtLeast(0)
        // An exact zero means the OS saw a successful unlock — clear any
        // open session so a stale one can't bump the count later.
        val nextSession = sessionOpen && exact != 0
        if (next == count && nextSession == sessionOpen) return  // nothing changed
        count = next
        sessionOpen = nextSession
        persist()
    }

    companion object {
        /**
         * SharedPreferences-backed production store, keyed by the given
         * prefs file + key so the caller (FailedUnlockMonitor) owns its
         * namespace.
         */
        fun persistent(context: android.content.Context, prefsName: String, key: String): FailedUnlockTracker {
            val prefs = context.getSharedPreferences(prefsName, android.content.Context.MODE_PRIVATE)
            return FailedUnlockTracker(
                object : StringStore {
                    override fun read(): String = prefs.getString(key, "") ?: ""
                    override fun write(json: String) {
                        prefs.edit().putString(key, json).apply()
                    }
                }
            )
        }
    }
}
