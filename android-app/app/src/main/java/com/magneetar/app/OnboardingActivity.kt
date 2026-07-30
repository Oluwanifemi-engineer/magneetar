package com.magneetar.app

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

/**
 * Welcome/Onboarding screen shown on first launch.
 * Guides the user to create an account or sign in.
 */
class OnboardingActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_onboarding)

        findViewById<android.widget.Button>(R.id.btn_get_started).setOnClickListener {
            startActivity(Intent(this, SignUpActivity::class.java))
        }

        findViewById<android.widget.Button>(R.id.btn_sign_in).setOnClickListener {
            startActivity(Intent(this, SignInActivity::class.java))
        }
    }
}
