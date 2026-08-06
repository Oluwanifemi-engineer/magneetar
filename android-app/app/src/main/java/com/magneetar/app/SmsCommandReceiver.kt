package com.magneetar.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Telephony
import android.util.Log

/**
 * Offline Command Relay — the phone-side receiver for SMS commands.
 *
 * When a Magneetar device is offline (no data), the dashboard can still reach
 * it over the cellular SMS channel. The server SMSes the command to the
 * phone's SIM number (MAGNET <code> CMD <id> <command> [params]); this
 * receiver verifies the pairing code AND the sender, then hands the command
 * to TrackingService for local execution, exactly as if it had arrived via
 * the network poll.
 *
 * Security (defense in depth):
 * - Sender allowlist: only the server's relay number (TWILIO_SMS_FROM, learned
 *   from /api/config) or the Termii alphanumeric "Magneetar" sender may issue
 *   commands — a leaked/intercepted pairing code can't be replayed from a
 *   random number. Degrades to code-only when no relay number is configured.
 * - The pairing code (first 8 hex of SHA-256(device_key)) is the second auth
 *   gate. A random SMS can never trigger a command without it.
 * - Brute-force protection: after FAILED_CODES_BEFORE_COOLDOWN bad codes
 *   within the cooldown window, ALL SMS commands are ignored for 24h — each
 *   guess costs a real SMS (visible to the owner) and the window makes
 *   guessing 2^32 codes impractical.
 * - The receiver only acts when the owner ENABLED offline SMS commands in the
 *   app (SMS_COMMANDS_ENABLED pref, DEFAULT OFF — SMS interception is
 *   sensitive, so it is opt-in, mirroring the dashboard-side toggle).
 *
 * NOTE: this receiver is a wake-up point, not a worker — it starts
 * TrackingService (which holds the command loop, outbox, and network
 * plumbing) and returns immediately.
 */
class SmsCommandReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "MagneetarSms"
        private const val PREF_SMS_ENABLED = "sms_commands_enabled"
        private const val PREF_RELAY_NUMBER = "sms_relay_number"
        private const val PREF_FAILURES = "sms_cmd_failures"
        private const val PREF_FAILURES_AT = "sms_cmd_failures_at"
        private const val MAX_FAILURES = 5
        private const val COOLDOWN_MS = 24L * 60 * 60 * 1000 // 24h

        /** Intent action used to hand a verified SMS command to TrackingService. */
        const val ACTION_SMS_COMMAND = "com.magneetar.app.action.SMS_COMMAND"
        const val EXTRA_COMMAND_ID = "command_id"
        const val EXTRA_COMMAND = "command"
        const val EXTRA_PARAMS = "params"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        // SMS interception is sensitive — opt-in, default OFF (aligned with the
        // dashboard-side toggle, which also defaults off).
        if (!prefs.getBoolean(PREF_SMS_ENABLED, false)) {
            Log.d(TAG, "SMS commands disabled in app — ignoring")
            return
        }
        if (isInCooldown(prefs)) {
            Log.w(TAG, "SMS command cooldown active — ignoring")
            return
        }

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return
        val sender = messages.firstOrNull()?.originatingAddress ?: ""

        // Sender allowlist (defense in depth alongside the pairing code): only
        // the server's relay number or the Termii alphanumeric may issue
        // commands. Falls back to code-only when no relay number is configured.
        val relayNumber = prefs.getString(PREF_RELAY_NUMBER, "") ?: ""
        if (!SmsCommand.isSenderAllowed(sender, relayNumber)) {
            recordFailure(prefs)
            Log.w(TAG, "SMS command rejected (sender not in allowlist): $sender")
            return
        }

        val deviceKey = prefs.getString("device_key", "") ?: return
        val expectedCode = PairingCode.of(deviceKey)

        val fullBody = messages.joinToString("\n") { it.displayMessageBody ?: it.messageBody ?: "" }
        if (fullBody.isBlank()) return

        val parsed = SmsCommand.parse(fullBody, expectedCode)
        if (parsed == null) {
            recordFailure(prefs)
            Log.w(TAG, "SMS command rejected (bad code / malformed)")
            return
        }

        // Valid command — clear the failure counter and hand it off.
        clearFailures(prefs)
        Log.i(TAG, "SMS command verified: #${parsed.commandId} ${parsed.command}")

        // Remember the sender so TrackingService can best-effort SMS-reply the
        // ack to the same number (the offline relay's return channel).
        if (sender.isNotEmpty()) {
            prefs.edit().putString("sms_last_sender", sender).apply()
        }

        try {
            val serviceIntent = Intent(context, TrackingService::class.java).apply {
                action = ACTION_SMS_COMMAND
                putExtra(EXTRA_COMMAND_ID, parsed.commandId)
                putExtra(EXTRA_COMMAND, parsed.command)
                putExtra(EXTRA_PARAMS, parsed.params)
            }
            // TrackingService is a foreground service; starting it from a
            // broadcast receiver is fine on modern Android (the service calls
            // startForeground in onCreate). startForegroundService is API 26+;
            // on older devices plain startService is the only option (and is
            // still legal — the background-start ban arrived with API 26).
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                @Suppress("DEPRECATION")
                context.startService(serviceIntent)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Could not hand SMS command to TrackingService: ${e.message}")
        }
    }

    private fun isInCooldown(prefs: android.content.SharedPreferences): Boolean {
        val failures = prefs.getInt(PREF_FAILURES, 0)
        if (failures < MAX_FAILURES) return false
        val at = prefs.getLong(PREF_FAILURES_AT, 0L)
        return System.currentTimeMillis() - at < COOLDOWN_MS
    }

    private fun recordFailure(prefs: android.content.SharedPreferences) {
        val now = System.currentTimeMillis()
        val failures = prefs.getInt(PREF_FAILURES, 0)
        val lastAt = prefs.getLong(PREF_FAILURES_AT, 0L)
        // Reset the window if the last failure was long ago.
        val newFailures = if (now - lastAt > 60 * 60 * 1000L) 1 else failures + 1
        prefs.edit().putInt(PREF_FAILURES, newFailures).putLong(PREF_FAILURES_AT, now).apply()
        if (newFailures >= MAX_FAILURES) {
            Log.w(TAG, "SMS command cooldown engaged after $newFailures bad codes")
        }
    }

    private fun clearFailures(prefs: android.content.SharedPreferences) {
        prefs.edit().remove(PREF_FAILURES).remove(PREF_FAILURES_AT).apply()
    }
}
