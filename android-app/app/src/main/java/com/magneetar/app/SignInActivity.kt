package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * User login screen — authenticates via /api/auth/user/login.
 * On success, stores tokens and navigates to PermissionsActivity.
 */
class SignInActivity : AppCompatActivity() {

    private lateinit var etServerUrl: EditText
    private lateinit var etEmail: EditText
    private lateinit var etPassword: EditText
    private lateinit var tvPasswordLabel: TextView
    private lateinit var tv2faLabel: TextView
    private lateinit var tv2faHint: TextView
    private lateinit var et2faCode: EditText
    private lateinit var tvError: TextView
    private lateinit var btnSignIn: android.widget.Button

    /** Two-factor challenge token issued by the server after password login
     *  when the account has TOTP enabled. Non-null → show the code step. */
    private var twoFactorToken: String? = null

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_signin)

        etServerUrl = findViewById(R.id.et_server_url)
        etEmail = findViewById(R.id.et_email)
        etPassword = findViewById(R.id.et_password)
        tvPasswordLabel = findViewById(R.id.tv_password_label)
        tv2faLabel = findViewById(R.id.tv_2fa_label)
        tv2faHint = findViewById(R.id.tv_2fa_hint)
        et2faCode = findViewById(R.id.et_2fa_code)
        tvError = findViewById(R.id.tv_error)
        btnSignIn = findViewById(R.id.btn_signin)

        // Always use BuildConfig.SERVER_URL as default (ignores stale saved prefs)
        // User can still edit; successful connection saves the working URL.
        etServerUrl.setText(BuildConfig.SERVER_URL)

        findViewById<android.widget.ImageView>(R.id.btn_back).setOnClickListener {
            finish()
        }

        findViewById<TextView>(R.id.tv_signup_link).setOnClickListener {
            startActivity(Intent(this, SignUpActivity::class.java))
            finish()
        }

        btnSignIn.setOnClickListener {
            if (twoFactorToken != null) {
                attemptTwoFactorCode()
            } else {
                attemptSignIn()
            }
        }
    }

    /** Swap the password field for the TOTP code field and focus the code. */
    private suspend fun enterTwoFactorStep(serverUrl: String, email: String, challengeToken: String) {
        twoFactorToken = challengeToken
        with(getSharedPreferences("mt", Context.MODE_PRIVATE).edit()) {
            putString("server_url", serverUrl)
            putString("user_email", email)
            apply()
        }
        withContextMain {
            tvPasswordLabel.visibility = android.view.View.GONE
            etPassword.visibility = android.view.View.GONE
            tv2faLabel.visibility = android.view.View.VISIBLE
            tv2faHint.visibility = android.view.View.VISIBLE
            et2faCode.visibility = android.view.View.VISIBLE
            tvError.visibility = android.view.View.GONE
            btnSignIn.text = "VERIFY CODE"
            btnSignIn.isEnabled = true
            et2faCode.requestFocus()
        }
    }

    private suspend fun withContextMain(block: () -> Unit) {
        withContext(Dispatchers.Main) { block() }
    }

    private fun attemptSignIn() {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        val email = etEmail.text.toString().trim()
        val password = etPassword.text.toString()

        // Validate
        if (serverUrl.isEmpty()) {
            showError("Please enter your server URL")
            return
        }
        if (email.isEmpty()) {
            showError("Please enter your email")
            return
        }
        if (password.isEmpty()) {
            showError("Please enter your password")
            return
        }

        tvError.visibility = android.view.View.GONE
        btnSignIn.isEnabled = false
        btnSignIn.text = "SIGNING IN..."

        scope.launch {
            try {
                val json = org.json.JSONObject().apply {
                    put("email", email)
                    put("password", password)
                }

                val client = buildHttpClient()
                val response = client.newCall(
                    okhttp3.Request.Builder()
                        .url("$serverUrl/api/auth/user/login")
                        .post(json.toString().toRequestBody("application/json".toMediaTypeOrNull()!!))
                        .addHeader("Content-Type", "application/json")
                        .build()
                ).execute()
                val body = response.body?.string()

                val httpCode = response.code
                if (response.isSuccessful && body != null) {
                    val jsonResponse = org.json.JSONObject(body)

                    // Two-factor step: the server answers with a challenge
                    // token instead of dashboard credentials.
                    if (jsonResponse.optBoolean("requires_2fa") &&
                        jsonResponse.has("two_factor_token")
                    ) {
                        enterTwoFactorStep(serverUrl, email, jsonResponse.getString("two_factor_token"))
                        return@launch
                    }

                    val token = jsonResponse.getString("token")
                    val refreshToken = jsonResponse.optString("refresh_token", "")

                    // Save credentials
                    with(getSharedPreferences("mt", Context.MODE_PRIVATE).edit()) {
                        putString("server_url", serverUrl)
                        putString("user_token", token)
                        putString("user_refresh_token", refreshToken)
                        putString("user_email", email)
                        putString("auth_method", "user")
                        apply()
                    }

                    // Best-effort: link this device to the signed-in account so
                    // it shows up in the dashboard immediately.
                    scope.launch { DeviceLinker.linkToAccount(this@SignInActivity, serverUrl, token) }

                    withContext(Dispatchers.Main) {
                        navigateToPermissions()
                    }
                } else {
                    val snippet = if (body != null && body.length > 150) body.substring(0, 150) + "..." else (body ?: "(empty)")
                    val detail = "HTTP $httpCode: $snippet"
                    withContext(Dispatchers.Main) {
                        showError(detail)
                    }
                }
            } catch (e: Throwable) {
                val errorMsg = "${e.javaClass.simpleName}: ${e.message ?: "Unknown error"}"
                android.util.Log.e("SignInActivity", "Login failed", e)
                withContext(Dispatchers.Main) {
                    showError(errorMsg)
                }
            } finally {
                withContext(Dispatchers.Main) {
                    if (twoFactorToken == null) {
                        btnSignIn.isEnabled = true
                        btnSignIn.text = "SIGN IN"
                    }
                }
            }
        }
    }

    /** Second login step: exchange the TOTP code + challenge token for real
     *  dashboard credentials via /api/auth/user/login/2fa. */
    private fun attemptTwoFactorCode() {
        val serverUrl = getSharedPreferences("mt", Context.MODE_PRIVATE)
            .getString("server_url", BuildConfig.SERVER_URL)?.trimEnd('/')
            ?: return
        val challengeToken = twoFactorToken ?: return
        val code = et2faCode.text.toString().trim()

        if (code.length != 6) {
            showError("Enter the 6-digit code from your authenticator app")
            return
        }

        tvError.visibility = android.view.View.GONE
        btnSignIn.isEnabled = false
        btnSignIn.text = "VERIFYING..."

        scope.launch {
            try {
                val json = org.json.JSONObject().apply {
                    put("two_factor_token", challengeToken)
                    put("code", code)
                }

                val client = buildHttpClient()
                val response = client.newCall(
                    okhttp3.Request.Builder()
                        .url("$serverUrl/api/auth/user/login/2fa")
                        .post(json.toString().toRequestBody("application/json".toMediaTypeOrNull()!!))
                        .addHeader("Content-Type", "application/json")
                        .build()
                ).execute()
                val body = response.body?.string()

                val httpCode = response.code
                if (response.isSuccessful && body != null) {
                    val jsonResponse = org.json.JSONObject(body)
                    val token = jsonResponse.getString("token")
                    val refreshToken = jsonResponse.optString("refresh_token", "")

                    with(getSharedPreferences("mt", Context.MODE_PRIVATE).edit()) {
                        putString("user_token", token)
                        putString("user_refresh_token", refreshToken)
                        putString("auth_method", "user")
                        apply()
                    }

                    // Best-effort: link this device to the signed-in account.
                    scope.launch { DeviceLinker.linkToAccount(this@SignInActivity, serverUrl, token) }

                    withContext(Dispatchers.Main) {
                        navigateToPermissions()
                    }
                } else {
                    val snippet = if (body != null && body.length > 150) body.substring(0, 150) + "..." else (body ?: "(empty)")
                    val detail = "HTTP $httpCode: $snippet"
                    withContext(Dispatchers.Main) {
                        showError(detail)
                    }
                }
            } catch (e: Throwable) {
                val errorMsg = "${e.javaClass.simpleName}: ${e.message ?: "Unknown error"}"
                android.util.Log.e("SignInActivity", "2FA verification failed", e)
                withContext(Dispatchers.Main) {
                    showError(errorMsg)
                }
            } finally {
                withContext(Dispatchers.Main) {
                    btnSignIn.isEnabled = true
                    btnSignIn.text = "VERIFY CODE"
                }
            }
        }
    }

    private fun buildHttpClient(): okhttp3.OkHttpClient {
        return okhttp3.OkHttpClient.Builder()
            .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
            .build()
    }

    private fun showError(msg: String) {
        tvError.text = msg
        tvError.visibility = android.view.View.VISIBLE
    }

    private fun navigateToPermissions() {
        startActivity(Intent(this, PermissionsActivity::class.java))
        finish()
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }
}
