package com.magneetar.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Encrypted vault for the user's session credentials (the 24h access JWT and
 * the 90-day refresh token).
 *
 * These were previously stored in plain SharedPreferences — readable by
 * anyone with root on a stolen device, which would hand over a full 90-day
 * account session (view all linked devices, issue commands, wipe other
 * devices). They are now wrapped in AES-256-GCM under an AndroidKeyStore
 * key: the key never leaves the device (hardware-backed on modern phones),
 * so even a full extraction of the prefs XML yields only ciphertext.
 *
 * Migration: the first read after an upgrade transparently encrypts any
 * legacy plaintext tokens and deletes the plaintext copies.
 *
 * Degradation: if the Keystore key is gone (app data cleared / reinstall),
 * reads return empty strings and callers degrade to the sign-in screen —
 * never a crash. The key survives app updates and is independent of the
 * lock screen (background services must read it while the phone is locked).
 */
object TokenVault {

    private const val KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "magneetar_session_key"
    private const val PREF_ACCESS = "user_token_v2"
    private const val PREF_REFRESH = "user_refresh_token_v2"
    private const val LEGACY_ACCESS = "user_token"
    private const val LEGACY_REFRESH = "user_refresh_token"
    private const val GCM_TAG_BITS = 128

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
        if (parts.size != 2) {
            null
        } else {
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

    /** Save both session tokens (encrypted). Never leaves plaintext behind. */
    fun save(context: Context, accessToken: String, refreshToken: String) {
        val key = getOrCreateKey() ?: return
        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        prefs.edit().apply {
            encrypt(key, accessToken)?.let { putString(PREF_ACCESS, it) }
            encrypt(key, refreshToken)?.let { putString(PREF_REFRESH, it) }
            remove(LEGACY_ACCESS)
            remove(LEGACY_REFRESH)
        }.apply()
    }

    /** Read both session tokens; transparently migrates legacy plaintext. */
    fun load(context: Context): Pair<String, String> {
        val prefs = context.getSharedPreferences("mt", Context.MODE_PRIVATE)
        var access = prefs.getString(PREF_ACCESS, "") ?: ""
        var refresh = prefs.getString(PREF_REFRESH, "") ?: ""
        if (access.isEmpty() || refresh.isEmpty()) {
            val legacyAccess = prefs.getString(LEGACY_ACCESS, "") ?: ""
            val legacyRefresh = prefs.getString(LEGACY_REFRESH, "") ?: ""
            if (legacyAccess.isNotEmpty() || legacyRefresh.isNotEmpty()) {
                save(context, legacyAccess, legacyRefresh)
                access = prefs.getString(PREF_ACCESS, "") ?: ""
                refresh = prefs.getString(PREF_REFRESH, "") ?: ""
            }
        }
        val key = getOrCreateKey() ?: return Pair("", "")
        return Pair(
            if (access.isNotEmpty()) decrypt(key, access) ?: "" else "",
            if (refresh.isNotEmpty()) decrypt(key, refresh) ?: "" else ""
        )
    }

    /** Convenience: read just the access token. */
    fun accessToken(context: Context): String = load(context).first

    /** Convenience: read just the refresh token. */
    fun refreshToken(context: Context): String = load(context).second
}
