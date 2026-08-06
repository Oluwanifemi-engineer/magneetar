plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.gms.google-services")
    id("io.sentry.android.gradle")
}

import org.gradle.api.GradleException

// Read the app version from the repo-root VERSION file (single source of
// truth — the server's APP_VERSION and the /apk/download filename use it too).
val appVersion: String = run {
    val versionFile = rootProject.projectDir.parentFile.resolve("VERSION")
    if (versionFile.exists()) versionFile.readText().trim() else "1.0.0"
}

// ── Build-time config resolution ──────────────────────────────────────────
// Priority (highest first):
//   1. -PDEVICE_KEY=... / -PSERVER_URL=... project flags (CI / ad-hoc builds)
//   2. MT_DEVICE_KEY / MT_SENTRY_DSN environment variables
//   3. android-app/local.properties (gitignored — the normal local build)
//
// SECURITY: the APK embeds the LOW-PRIVILEGE device key (server's
// MT_DEVICE_KEY), NEVER the master API key (MT_API_KEY). The master key
// grants dashboard admin access — putting it in the public APK would hand
// platform-admin to anyone who downloads the app. This build config only
// knows about DEVICE_KEY for that reason.
//
// project.findProperty() does NOT read local.properties (only gradle.properties
// and -P flags do), so without this explicit fallback a plain release build
// used to silently bake the placeholder "changeme-set-in-env" key — the server
// then rejected every device request with 401 and devices stayed offline in the
// dashboard even though the phone was alive.

fun localProperty(key: String): String? = try {
    val propsFile = rootProject.file("local.properties")
    if (propsFile.exists()) {
        propsFile.readLines()
            .map { it.trim() }
            .firstOrNull { it.isNotEmpty() && !it.startsWith("#") && it.startsWith("$key=") }
            ?.substringAfter('=')
            ?.trim()
            ?.takeIf { it.isNotEmpty() }
    } else null
} catch (e: Exception) { null }

val serverUrl = (project.findProperty("SERVER_URL") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: System.getenv("SERVER_URL")?.takeIf { it.isNotBlank() }
    ?: localProperty("SERVER_URL")
    ?: "https://api.magneetar.me"

val deviceKey = (project.findProperty("DEVICE_KEY") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: System.getenv("MT_DEVICE_KEY")?.takeIf { it.isNotBlank() }
    ?: localProperty("DEVICE_KEY")
    ?: "changeme-set-in-env"

val sentryDsn = (project.findProperty("SENTRY_DSN") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: System.getenv("MT_SENTRY_DSN")?.takeIf { it.isNotBlank() }
    ?: localProperty("SENTRY_DSN")
    ?: ""

// ── Release signing credentials ──────────────────────────────────────────
// Never default to a hardcoded password (an attacker who gets the keystore
// file + the repo source would otherwise also have the password). Every
// release build MUST receive the real credentials via env vars or -P flags;
// a missing value fails the build instead of shipping a weak/unsigned APK.
// NOTE: these val names deliberately do NOT match the SigningConfig property
// names (storePassword / keyAlias / keyPassword). Inside the signingConfigs
// lambda the receiver's members shadow outer scope, so `keyAlias = keyAlias`
// would self-assign (alias stays null) — the guard passes but packageRelease
// fails. Distinct names make the assignment unambiguous.
val releaseStorePass = System.getenv("MT_KEYSTORE_PASS")
    ?: (project.findProperty("KEYSTORE_PASS") as String?)
    ?: localProperty("KEYSTORE_PASS")
    ?: ""
val releaseKeyAlias = System.getenv("MT_KEY_ALIAS")
    ?: (project.findProperty("KEY_ALIAS") as String?)
    ?: localProperty("KEY_ALIAS")
    ?: ""
val releaseKeyPass = System.getenv("MT_KEY_ALIAS_PASS")
    ?: (project.findProperty("KEY_ALIAS_PASS") as String?)
    ?: localProperty("KEY_ALIAS_PASS")
    ?: ""

fun isReleaseTask(task: String): Boolean {
    val name = task.lowercase()
    return name.contains("release") ||
        name in listOf("build", "assemble", "bundle", "publish", "install")
}

val wantsRelease = gradle.startParameter.taskNames.any(::isReleaseTask)

// Fail fast: a build that assembles a release APK MUST carry the real DEVICE
// key. Shipping the placeholder makes the server 401 every device request
// (devices stay offline in the dashboard) — catch it at build time, not on a
// user's phone. Check the explicitly requested task names AND the aggregate
// tasks (build/assemble/bundle/publish) that transitively build the release
// variant, so the guard can't be slipped past by an implied task.
//
// The message deliberately steers away from the master key: DEVICE_KEY must be
// the low-privilege server MT_DEVICE_KEY, NOT MT_API_KEY.
if (deviceKey == "changeme-set-in-env" && wantsRelease) {
    throw GradleException(
        "DEVICE_KEY is not configured. Add DEVICE_KEY to android-app/local.properties " +
        "or pass -PDEVICE_KEY=<device key> (must match the server's MT_DEVICE_KEY — " +
        "the LOW-PRIVILEGE device key, NEVER the master MT_API_KEY)."
    )
}

// Release signing guard: keystore + all three credentials must be present.
// The keystore file is gitignored (never in the repo); CI restores it from
// the KEYSTORE_BASE64 secret. Signing with weak/empty credentials silently
// produces an APK nobody can trust — refuse to build it.
val keystoreFile = rootProject.projectDir.resolve("release.keystore")
if (wantsRelease) {
    val missing = buildList {
        if (!keystoreFile.exists()) add("release.keystore file")
        if (releaseStorePass.isBlank()) add("KEYSTORE_PASS (env MT_KEYSTORE_PASS or -PKEYSTORE_PASS)")
        if (releaseKeyAlias.isBlank()) add("KEY_ALIAS (env MT_KEY_ALIAS or -PKEY_ALIAS)")
        if (releaseKeyPass.isBlank()) add("KEY_ALIAS_PASS (env MT_KEY_ALIAS_PASS or -PKEY_ALIAS_PASS)")
    }
    if (missing.isNotEmpty()) {
        throw GradleException(
            "Release signing not configured — missing: ${missing.joinToString(", ")}. " +
            "Provide the release keystore (gitignored) and its credentials so the APK " +
            "is genuinely signed. Refusing to produce an unsigned or weakly-signed release."
        )
    }
}

android {
    namespace = "com.magneetar.app"
    // Android 16 — required by Google Play for ALL new apps and updates since
    // Aug 31, 2026 (targetSdk 36+; extension possible until Nov 1, 2026).
    // compileSdk 36 needs AGP 8.9.1+ (we ship 8.10.1) and Gradle 8.11.1+
    // (we ship 8.12).
    compileSdk = 36

    defaultConfig {
        applicationId = "com.magneetar.app"
        minSdk = 24
        targetSdk = 36
        // versionName is read from the repo-root VERSION file at build time
        // (same value the server reports and the APK filename uses).
        // versionCode must strictly increase on every Play release.
        versionCode = 6
        versionName = appVersion

        buildConfigField("String", "SERVER_URL", "\"$serverUrl\"")
        buildConfigField("String", "DEVICE_KEY", "\"$deviceKey\"")
        buildConfigField("String", "SENTRY_DSN", "\"$sentryDsn\"")
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            storeFile = keystoreFile
            storePassword = releaseStorePass
            keyAlias = releaseKeyAlias
            keyPassword = releaseKeyPass
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
        // Java 17 bytecode target — required by recent AGP/AndroidX releases
        // and the Google Play Console's 2025+ toolchain expectations.
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
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

    // JVM unit tests (pure logic only — e.g. CaptureRoutingTest). No
    // Robolectric: anything touching Android APIs stays out of src/test.
    testImplementation("junit:junit:4.13.2")
}
