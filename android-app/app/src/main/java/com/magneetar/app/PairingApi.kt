package com.magneetar.app

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Offline Device Network §4.1 — client for the server pairing endpoints.
 *
 * The pairing happens ONCE over the internet (like AirTag setup): this
 * device either initiates (gets a single-use 8-hex code to show the owner)
 * or confirms (owner types the code from the other device). Both devices
 * end up holding the same 32-byte pair_secret, which is then stored in the
 * Keystore-backed PairVault — after that the devices talk fully offline and
 * the server is never in the P2P data path.
 */
object PairingApi {

    private const val TAG = "MagneetarPair"
    private val JSON = "application/json".toMediaType()

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()

    data class InitiateResult(val pairId: String, val pairCode: String, val expiresInS: Int)

    data class ConfirmResult(val pairId: String, val deviceA: String, val deviceB: String, val pairSecret: String)

    data class PairingInfo(val pairId: String, val deviceA: String, val deviceB: String, val pairSecret: String)

    /**
     * POST /api/p2p/pair/initiate — mint a single-use code for THIS device.
     * Returns the code the owner types into the OTHER device.
     */
    suspend fun initiate(context: Context, deviceId: String): InitiateResult? = withContext(Dispatchers.IO) {
        val token = TokenVault.accessToken(context)
        if (token.isEmpty()) return@withContext null
        val body = JSONObject().put("device_id", deviceId).toString().toRequestBody(JSON)
        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/p2p/pair/initiate")
            .post(body)
            .addHeader("Authorization", "Bearer $token")
            .build()
        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code !in 200..299) {
                    Log.w(TAG, "initiate failed: HTTP ${resp.code}")
                    return@use null
                }
                val json = JSONObject(resp.body?.string() ?: "{}")
                InitiateResult(
                    pairId = json.optString("pair_id", ""),
                    pairCode = json.optString("pair_code", ""),
                    expiresInS = json.optInt("expires_in_s", 0),
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "initiate network error: ${e.message}")
            null
        }
    }

    /**
     * POST /api/p2p/pair/confirm — complete the pairing with the code the
     * owner typed in. Returns the shared pair_secret for THIS device.
     */
    suspend fun confirm(context: Context, deviceId: String, pairCode: String): ConfirmResult? = withContext(Dispatchers.IO) {
        val token = TokenVault.accessToken(context)
        if (token.isEmpty()) return@withContext null
        val body = JSONObject()
            .put("device_id", deviceId)
            .put("pair_code", pairCode)
            .toString()
            .toRequestBody(JSON)
        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/p2p/pair/confirm")
            .post(body)
            .addHeader("Authorization", "Bearer $token")
            .build()
        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code !in 200..299) {
                    Log.w(TAG, "confirm failed: HTTP ${resp.code} ${resp.body?.string()}")
                    return@use null
                }
                val json = JSONObject(resp.body?.string() ?: "{}")
                ConfirmResult(
                    pairId = json.optString("pair_id", ""),
                    deviceA = json.optString("device_a", ""),
                    deviceB = json.optString("device_b", ""),
                    pairSecret = json.optString("pair_secret", ""),
                )
            }
        } catch (e: Exception) {
            Log.w(TAG, "confirm network error: ${e.message}")
            null
        }
    }

    /**
     * GET /api/p2p/pair/status — completed pairings involving this device,
     * each with the shared secret (decrypted server-side). The initiating
     * device pulls its secret here after the other device confirms.
     */
    suspend fun status(context: Context, deviceId: String): List<PairingInfo> = withContext(Dispatchers.IO) {
        val token = TokenVault.accessToken(context)
        if (token.isEmpty()) return@withContext emptyList()
        val request = Request.Builder()
            .url("${BuildConfig.SERVER_URL}/api/p2p/pair/status?device_id=$deviceId")
            .get()
            .addHeader("Authorization", "Bearer $token")
            .build()
        try {
            client.newCall(request).execute().use { resp ->
                if (resp.code !in 200..299) return@use emptyList()
                val json = JSONObject(resp.body?.string() ?: "{}")
                val arr = json.optJSONArray("pairings") ?: return@use emptyList()
                val out = mutableListOf<PairingInfo>()
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    out.add(
                        PairingInfo(
                            pairId = o.optString("pair_id", ""),
                            deviceA = o.optString("device_a", ""),
                            deviceB = o.optString("device_b", ""),
                            pairSecret = o.optString("pair_secret", ""),
                        )
                    )
                }
                out
            }
        } catch (e: Exception) {
            Log.w(TAG, "status network error: ${e.message}")
            emptyList()
        }
    }

    /**
     * Pull + persist any completed pairings for this device. Called at app
     * start and after confirming/initiating, so the vault stays in sync with
     * the server (idempotent — re-saving the same pair_id refreshes).
     */
    suspend fun syncToVault(context: Context, deviceId: String) {
        val pairings = status(context, deviceId)
        val now = System.currentTimeMillis()
        for (p in pairings) {
            if (p.pairSecret.isNotEmpty()) {
                PairVault.save(
                    context,
                    PairVault.Pairing(
                        pairId = p.pairId,
                        deviceA = p.deviceA,
                        deviceB = p.deviceB,
                        secret = p.pairSecret.hexToBytes(),
                        createdAt = now,
                    ),
                )
                Log.i(TAG, "Synced pairing ${p.pairId.take(12)} into vault")
            }
        }
    }

    private fun String.hexToBytes(): ByteArray {
        if (length % 2 != 0) return ByteArray(0)
        return ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}
