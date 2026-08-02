plugins {
    // AGP 8.6.0 is the minimum that officially supports compileSdk 35
    // (Android 15); we pin 8.7.3 for headroom. Play requires targetSdk 35+
    // since Aug 2025 and 36 by Aug 31, 2026 (AGP 8.9.1+ + Gradle 8.11.1+
    // when we bump to 36).
    id("com.android.application") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "1.9.23" apply false
    id("com.google.gms.google-services") version "4.4.2" apply false
    id("io.sentry.android.gradle") version "4.10.0" apply false
}
