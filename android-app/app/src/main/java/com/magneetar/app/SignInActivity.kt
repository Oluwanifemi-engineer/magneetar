package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
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
    private lateinit var tvError: TextView
    private lateinit var btnSignIn: android.widget.Button

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_signin)

        etServerUrl = findViewById(R.id.et_server_url)
        etEmail = findViewById(R.id.et_email)
        etPassword = findViewById(R.id.et_password)
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
            attemptSignIn()
        }
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

                val mediaType = "application/json".toMediaTypeOrNull()
                val requestBody = if (mediaType != null) {
                    json.toString().toRequestBody(mediaType)
                } else {
                    json.toString().toRequestBody("application/json".toMediaTypeOrNull()!!)
                }

                val request = okhttp3.Request.Builder()
                    .url("$serverUrl/api/auth/user/login")
                    .post(requestBody)
                    .addHeader("Content-Type", "application/json")
                    .build()

                val client = okhttp3.OkHttpClient.Builder()
                    .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                    .readTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
                    .build()

                val response = client.newCall(request).execute()
                val body = response.body?.string()

                val httpCode = response.code
                if (response.isSuccessful && body != null) {
                    val jsonResponse = org.json.JSONObject(body)
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
                    btnSignIn.isEnabled = true
                    btnSignIn.text = "SIGN IN"
                }
            }
        }
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
