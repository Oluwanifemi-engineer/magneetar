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
 * Account creation screen — registers via /api/auth/register.
 * On success, stores tokens and navigates to PermissionsActivity.
 */
class SignUpActivity : AppCompatActivity() {

    private lateinit var etServerUrl: EditText
    private lateinit var etName: EditText
    private lateinit var etEmail: EditText
    private lateinit var etPassword: EditText
    private lateinit var etConfirmPassword: EditText
    private lateinit var tvError: TextView
    private lateinit var btnSignUp: android.widget.Button

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_signup)

        etServerUrl = findViewById(R.id.et_server_url)
        etName = findViewById(R.id.et_name)
        etEmail = findViewById(R.id.et_email)
        etPassword = findViewById(R.id.et_password)
        etConfirmPassword = findViewById(R.id.et_confirm_password)
        tvError = findViewById(R.id.tv_error)
        btnSignUp = findViewById(R.id.btn_signup)

        // Always use BuildConfig.SERVER_URL as default (ignores stale saved prefs)
        // User can still edit; successful connection saves the working URL.
        etServerUrl.setText(BuildConfig.SERVER_URL)

        findViewById<android.widget.ImageView>(R.id.btn_back).setOnClickListener {
            finish()
        }

        findViewById<TextView>(R.id.tv_signin_link).setOnClickListener {
            startActivity(Intent(this, SignInActivity::class.java))
            finish()
        }

        btnSignUp.setOnClickListener {
            attemptSignUp()
        }
    }

    private fun attemptSignUp() {
        val serverUrl = etServerUrl.text.toString().trim().trimEnd('/')
        val name = etName.text.toString().trim()
        val email = etEmail.text.toString().trim()
        val password = etPassword.text.toString()
        val confirmPassword = etConfirmPassword.text.toString()

        // Validate
        if (serverUrl.isEmpty()) {
            showError("Please enter your server URL")
            return
        }
        if (name.isEmpty()) {
            showError("Please enter your name")
            return
        }
        if (email.isEmpty()) {
            showError("Please enter your email")
            return
        }
        if (password.isEmpty()) {
            showError("Please enter a password")
            return
        }
        if (password.length < 8) {
            showError("Password must be at least 8 characters")
            return
        }
        if (!password.any { it.isUpperCase() } || !password.any { it.isLowerCase() } || !password.any { it.isDigit() }) {
            showError("Password needs uppercase, lowercase, and a digit")
            return
        }
        if (password != confirmPassword) {
            showError("Passwords do not match")
            return
        }

        tvError.visibility = android.view.View.GONE
        btnSignUp.isEnabled = false
        btnSignUp.text = "CREATING ACCOUNT..."

        scope.launch {
            try {
                val json = org.json.JSONObject().apply {
                    put("email", email)
                    put("password", password)
                    put("display_name", name)
                }

                val mediaType = "application/json".toMediaTypeOrNull()
                val requestBody = if (mediaType != null) {
                    json.toString().toRequestBody(mediaType)
                } else {
                    json.toString().toRequestBody("application/json".toMediaTypeOrNull()!!)
                }

                val request = okhttp3.Request.Builder()
                    .url("$serverUrl/api/auth/register")
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
                android.util.Log.e("SignUpActivity", "Registration failed", e)
                withContext(Dispatchers.Main) {
                    showError(errorMsg)
                }
            } finally {
                withContext(Dispatchers.Main) {
                    btnSignUp.isEnabled = true
                    btnSignUp.text = "CREATE ACCOUNT"
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
