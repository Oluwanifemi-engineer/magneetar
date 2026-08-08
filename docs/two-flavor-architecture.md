# Two-Flavor Architecture: Play Store vs Sideload

## Overview

Magneetar ships two Android build flavors from a single codebase:

| Flavor | Distribution | SMS Commands | Play Protect |
|--------|--------------|--------------|--------------|
| **play** | Google Play Store | ❌ Removed | ✅ No blocking |
| **sideload** | Direct APK download | ✅ Full relay | ⚠️ Requires bypass |

Both flavors share:
- Same server, same account, same encryption
- Same core features (GPS tracking, remote lock/wipe, evidence capture, Sentinel)
- Same UI and user experience
- Same APK signing key

## Why Two Flavors?

Google Play's SMS permission policy (Answer 10208820) explicitly bans:

> **Invalid use cases for SMS permissions include:**
> - Family or device locator
> - Remote control of user phone or other devices

Magneetar's offline SMS command relay falls into both categories. Rather than removing this feature entirely, we maintain it in the sideload flavor for power users who want maximum protection.

## Build Commands

```bash
# Play Store flavor (for Google Play submission)
./gradlew assemblePlayRelease

# Sideload flavor (for direct download)
./gradlew assembleSideloadRelease

# Both flavors
./gradlew assembleRelease
```

## Technical Implementation

### Android Manifest Overlay

The `src/play/AndroidManifest.xml` overlay removes SMS permissions:

```xml
<uses-permission
    android:name="android.permission.RECEIVE_SMS"
    tools:node="remove" />
<uses-permission
    android:name="android.permission.SEND_SMS"
    tools:node="remove" />
<uses-permission
    android:name="android.permission.READ_PHONE_STATE"
    tools:node="remove" />
```

### Code Handling

The app treats SMS as optional everywhere:

```kotlin
// PermissionsActivity.kt
private fun hasSmsPermissions(): Boolean {
    return ContextCompat.checkSelfPermission(this, Manifest.permission.RECEIVE_SMS) ==
        PackageManager.PERMISSION_GRANTED
}

// Denial never blocks onboarding
if (!hasSmsPermissions()) {
    // Show "Optional" badge, continue setup
}
```

```kotlin
// TrackingService.kt
private fun hasSmsSendPermission(): Boolean =
    ContextCompat.checkSelfPermission(
        this, android.Manifest.permission.SEND_SMS
    ) == PackageManager.PERMISSION_GRANTED

// SMS reply falls back to network outbox
if (hasSmsSendPermission()) {
    replyViaSms(...)
} else {
    // Queue in OfflineOutbox for next connectivity
}
```

## Feature Comparison

| Feature | Play Store | Sideload |
|---------|------------|----------|
| GPS tracking | ✅ | ✅ |
| Remote lock | ✅ (FCM) | ✅ (FCM + SMS) |
| Remote wipe | ✅ (FCM) | ✅ (FCM + SMS) |
| Alarm trigger | ✅ (FCM) | ✅ (FCM + SMS) |
| Evidence capture | ✅ (FCM) | ✅ (FCM + SMS) |
| Sentinel detection | ✅ | ✅ |
| Guardian Network | ✅ | ✅ |
| Geofencing | ✅ | ✅ |
| Offline commands | ❌ (requires internet) | ✅ (SMS relay) |
| SIM swap detection | ✅ | ✅ |
| Battery monitoring | ✅ | ✅ |

## Server-Side Handling

The server detects the flavor via the `X-App-Flavor` header:

```python
# In device registration/polling
flavor = request.headers.get("X-App-Flavor", "unknown")
# Server logs flavor for analytics, no behavior difference
```

The SMS relay is only triggered when:
1. Device is offline (no FCM connection)
2. Owner enabled SMS commands for the device
3. SMS relay number is configured

If the Play Store version is used, the server simply waits for FCM reconnection.

## User Experience

### Play Store Version
- Install from Google Play like any app
- No Play Protect warnings
- Automatic updates
- Commands work when device has internet

### Sideload Version
- Download APK from app.magneetar.me/download
- May trigger Play Protect warning (guide provided)
- Manual updates (or use ADB)
- Commands work even without internet (SMS relay)

## Migration Between Flavors

Users can switch between flavors at any time:

1. **Play Store → Sideload:** Uninstall Play Store version, install sideload APK
2. **Sideload → Play Store:** Uninstall sideload version, install from Play Store

No data is lost — all data is stored server-side, tied to the user account.

## Build Configuration

### build.gradle.kts

```kotlin
flavorDimensions += "dist"
productFlavors {
    create("sideload") {
        dimension = "dist"
    }
    create("play") {
        dimension = "dist"
    }
}
```

### APK Naming

- Play Store: `Magneetar-v{version}-play-release.apk`
- Sideload: `Magneetar-v{version}-sideload-release.apk`

## Google Play Submission Checklist

1. ✅ Remove SMS permissions (done via manifest overlay)
2. ✅ Data Safety form declares location collection
3. ✅ Prominent disclosure for background location
4. ✅ Privacy policy link in Play Console
5. ✅ App description explains anti-theft functionality
6. ✅ No hidden/stealth features
7. ✅ Persistent notification when tracking active
8. ⬜ Submit for review (requires Play Console developer account)
