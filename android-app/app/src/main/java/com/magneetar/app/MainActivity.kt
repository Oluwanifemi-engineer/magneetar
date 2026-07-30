package com.magneetar.app

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Bomb-proof entry point — synchronous routing in onCreate.
 * No handlers, no postDelayed, no window dependencies.
 * Just reads prefs and sets the correct content view immediately.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Safe Sentry init (optional, never crashes)
        initSentrySafe()

        // Read state
        val prefs = getSharedPreferences("mt", Context.MODE_PRIVATE)
        val onboardingComplete = prefs.getBoolean("onboarding_complete", false)
        val userToken = prefs.getString("user_token", "") ?: ""

        // Route immediately — no delays, no handlers
        if (!onboardingComplete) {
            // First launch → show onboarding directly
            setContentView(R.layout.activity_onboarding)
            setupOnboardingButtons()
        } else if (userToken.isEmpty() || !hasAllPermissions()) {
            // Signed up but needs permissions
            startActivity(Intent(this, PermissionsActivity::class.java))
            finish()
        } else {
            // Fully authenticated → home
            startServicesSafe()
            startActivity(Intent(this, HomeActivity::class.java))
            finish()
        }
    }

    private fun setupOnboardingButtons() {
        findViewById<Button>(R.id.btn_get_started)?.setOnClickListener {
            startActivity(Intent(this, SignUpActivity::class.java))
        }
        findViewById<Button>(R.id.btn_sign_in)?.setOnClickListener {
            startActivity(Intent(this, SignInActivity::class.java))
        }
    }

    private fun initSentrySafe() {
        try {
            val dsn = try { BuildConfig.SENTRY_DSN } catch (e: Exception) { "" }
            if (dsn.isNotEmpty()) {
                io.sentry.android.core.SentryAndroid.init(this) { options ->
                    options.dsn = dsn
                    options.tracesSampleRate = 0.2
                    options.environment = if (BuildConfig.DEBUG) "development" else "production"
                }
            }
        } catch (t: Throwable) { /* Sentry optional */ }
    }

    private fun hasAllPermissions(): Boolean {
        return try {
            arrayOf(
                android.Manifest.permission.ACCESS_FINE_LOCATION,
                android.Manifest.permission.CAMERA,
                android.Manifest.permission.RECORD_AUDIO
            ).all {
                ContextCompat.checkSelfPermission(this, it) ==
                        android.content.pm.PackageManager.PERMISSION_GRANTED
            }
        } catch (e: Exception) { false }
    }

    private fun startServicesSafe() {
        try {
            ContextCompat.startForegroundService(this, Intent(this, TrackingService::class.java))
            ContextCompat.startForegroundService(this, Intent(this, PersistenceService::class.java))
            try { WatchdogReceiver.scheduleWatchdog(this) } catch (_: Exception) {}
            try { HealthCheckWorker.schedule(this) } catch (_: Exception) {}
            try { requestBatteryOptimization() } catch (_: Exception) {}
        } catch (e: Exception) {
            android.util.Log.e("MainActivity", "Services failed: ${e.message}")
        }
    }

    private fun requestBatteryOptimization() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager
            if (pm != null && !pm.isIgnoringBatteryOptimizations(packageName)) {
                startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = android.net.Uri.parse("package:$packageName")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                })
            }
        }
    }
}
