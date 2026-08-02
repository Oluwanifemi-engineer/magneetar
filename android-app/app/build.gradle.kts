plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.gms.google-services")
    id("io.sentry.android.gradle")
}

// Read the app version from the repo-root VERSION file (single source of
// truth — the server's APP_VERSION and the /apk/download filename use it too).
val appVersion: String = run {
    val versionFile = rootProject.projectDir.parentFile.resolve("VERSION")
    if (versionFile.exists()) versionFile.readText().trim() else "1.0.0"
}

android {
    namespace = "com.magneetar.app"
    // Android 15 — required by Google Play for new apps/updates since Aug 31,
    // 2025 (targetSdk 35+). Existing-app availability also requires 35+.
    // Bump to 36 (Android 16) before Aug 31, 2026 (needs AGP 8.9.1+/Gradle 8.11.1+).
    compileSdk = 35

    defaultConfig {
        applicationId = "com.magneetar.app"
        minSdk = 24
        targetSdk = 35
        // versionName is read from the repo-root VERSION file at build time
        // (same value the server reports and the APK filename uses).
        // versionCode must strictly increase on every Play release.
        versionCode = 3
        versionName = appVersion

        // takeIf { it.isNotBlank() } so an empty -P value falls back to the default
        val serverUrl = (project.findProperty("SERVER_URL") as String?)
            ?.takeIf { it.isNotBlank() } ?: "https://api.magneetar.me"
        val apiKey = (project.findProperty("API_KEY") as String?)
            ?.takeIf { it.isNotBlank() }
            ?: System.getenv("MT_API_KEY")?.takeIf { it.isNotBlank() } ?: "changeme-set-in-env"
        val sentryDsn = (project.findProperty("SENTRY_DSN") as String?)
            ?.takeIf { it.isNotBlank() }
            ?: System.getenv("MT_SENTRY_DSN")?.takeIf { it.isNotBlank() } ?: ""

        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        buildConfigField("String", "API_KEY", "\"$apiKey\"")
        buildConfigField("String", "SENTRY_DSN", "\"$sentryDsn\"")
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            storeFile = rootProject.projectDir.resolve("release.keystore")
            storePassword = System.getenv("MT_KEYSTORE_PASS") ?: project.findProperty("KEYSTORE_PASS") as String? ?: "magneetar123"
            keyAlias = System.getenv("MT_KEY_ALIAS") ?: project.findProperty("KEY_ALIAS") as String? ?: "magneetar"
            keyPassword = System.getenv("MT_KEY_ALIAS_PASS") ?: project.findProperty("KEY_ALIAS_PASS") as String? ?: "magneetar123"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }
}

// Sentry configuration — disable auto-upload when no DSN is configured
sentry {
    // Set to false until a Sentry project and DSN are configured
    autoUploadProguardMapping = false
    uploadNativeSymbols = false
    includeProguardMapping = false
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.0")
    implementation("androidx.work:work-runtime-ktx:2.9.0")
    implementation(platform("com.google.firebase:firebase-bom:33.0.0"))
    implementation("com.google.firebase:firebase-messaging-ktx")

    // Sentry crash reporting
    implementation("io.sentry:sentry-android:7.14.0")
}
