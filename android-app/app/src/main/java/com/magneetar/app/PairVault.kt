package com.magneetar.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Offline Device Network (docs/offline-network-design.md §4) — storage for
 * the owner's paired-device secrets.
 *
 * Each pairing (pair_id) binds two of the owner's device ids with a shared
 * 32-byte pair_secret minted by the server after the single-use code
 * bootstrap. This vault persists those secrets on BOTH devices so they can
 * discover + authenticate each other fully offline. Same shape as
 * TokenVault: AES-256-GCM under an AndroidKeyStore key (a separate alias, so
 * clearing the session tokens never clears pairings and vice versa); the key
 * never leaves the device.
 *
 * Multiple pairings are supported (a phone can pair with a tablet and a
 * second phone), each stored as:
 *   pair_id -> { secret: hex, device_a, device_b, created_at }
 *
 * Degradation: if the Keystore key is gone (data cleared / reinstall), the
 * vault returns an empty list and the Offline Find screen shows "no paired
 * devices — pair again" instead of crashing.
 */
object PairVault {

    private const val KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "magneetar_pair_vault_key"
    private const val PREF_FILE = "mt_pair_vault"
    private const val PREF_BLOB = "pairs_v1"
    private const val GCM_TAG_BITS = 128

    /** One stored pairing. */
    data class Pairing(
        val pairId: String,
        val deviceA: String,
        val deviceB: String,
        val secret: ByteArray,
        val createdAt: Long,
    )

    private fun getOrCreateKey(): SecretKey? = try {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getKey(KEY_ALIAS, null) as? SecretKey) ?: run {
            val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
            generator.init(
                KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build()
            )
            generator.generateKey()
        }
    } catch (e: Exception) {
        null
    }

    private fun encrypt(key: SecretKey, plain: String): String? = try {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val ct = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + "." + Base64.encodeToString(ct, Base64.NO_WRAP)
    } catch (e: Exception) {
        null
    }

    private fun decrypt(key: SecretKey, blob: String): String? = try {
        val parts = blob.split(".", limit = 2)
        if (parts.size != 2) null
        else {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                GCMParameterSpec(GCM_TAG_BITS, Base64.decode(parts[0], Base64.NO_WRAP))
            )
            String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), Charsets.UTF_8)
        }
    } catch (e: Exception) {
        null
    }

    /**
     * Store or update a pairing. Idempotent: re-saving the same pair_id
     * refreshes the secret (e.g. re-pairing after a code expiry).
     */
    fun save(context: Context, pairing: Pairing) {
        val key = getOrCreateKey() ?: return
        val prefs = context.getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val current = readPlain(prefs) ?: JSONObject()
        val obj = JSONObject().apply {
            put("pair_id", pairing.pairId)
            put("device_a", pairing.deviceA)
            put("device_b", pairing.deviceB)
            put("secret", pairing.secret.toHex())
            put("created_at", pairing.createdAt)
        }
        current.put(pairing.pairId, obj)
        encrypt(key, current.toString())?.let { blob ->
            prefs.edit().putString(PREF_BLOB, blob).apply()
        }
    }

    /** All stored pairings (empty on any failure — never throws). */
    fun list(context: Context): List<Pairing> {
        return try {
            val key = getOrCreateKey() ?: return emptyList()
            val prefs = context.getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
            val blob = prefs.getString(PREF_BLOB, "") ?: ""
            if (blob.isEmpty()) return emptyList()
            val json = decrypt(key, blob) ?: return emptyList()
            val obj = JSONObject(json)
            val out = mutableListOf<Pairing>()
            val keys = obj.keys()
            while (keys.hasNext()) {
                val pairId = keys.next()
                val o = obj.optJSONObject(pairId) ?: continue
                out.add(
                    Pairing(
                        pairId = pairId,
                        deviceA = o.optString("device_a", ""),
                        deviceB = o.optString("device_b", ""),
                        secret = o.optString("secret", "").hexToBytes(),
                        createdAt = o.optLong("created_at", 0L),
                    )
                )
            }
            out.sortedByDescending { it.createdAt }
        } catch (e: Exception) {
            emptyList()
        }
    }

    /** Delete a pairing (e.g. owner unpairs from the dashboard). */
    fun remove(context: Context, pairId: String) {
        val key = getOrCreateKey() ?: return
        val prefs = context.getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        val current = readPlain(prefs) ?: return
        current.remove(pairId)
        encrypt(key, current.toString())?.let { blob ->
            prefs.edit().putString(PREF_BLOB, blob).apply()
        }
    }

    private fun readPlain(prefs: android.content.SharedPreferences): JSONObject? {
        val key = getOrCreateKey() ?: return null
        val blob = prefs.getString(PREF_BLOB, "") ?: ""
        if (blob.isEmpty()) return JSONObject()
        val json = decrypt(key, blob) ?: return null
        return try {
            JSONObject(json)
        } catch (e: Exception) {
            null
        }
    }

    // ── hex helpers ──────────────────────────────────────────────────────────

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    private fun String.hexToBytes(): ByteArray {
        if (length % 2 != 0) return ByteArray(0)
        return ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }

}
