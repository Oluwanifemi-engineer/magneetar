# Magneetar iOS — Capability Map (v1.0)

The Android app is the full anti-theft product. iOS is a different platform
with hard OS-level limits that no app can cross on stock (non-MDM) devices.
This map records, feature by feature, what the iOS port ships, what it
deliberately cannot do, and the honest replacement where one exists.

Scope decision (2026-08-16): **iOS-honest scope** — a real product, not a
1:1 port that lies about its capabilities. Both roles ship (owner dashboard +
protected iPhone).

## Feature matrix

| Feature | Android | iOS v1 | Notes / honest replacement |
|---|---|---|---|
| Owner dashboard (device list, map) | ✅ | ✅ | Same endpoints, same data |
| Live dashboard updates (WS) | ✅ | ✅ | `/ws/dashboard?token=` with reconnect |
| Login / register / 2FA | ✅ | ✅ | Full 2FA challenge flow |
| Issue commands (ping, locate, siren, photo, audio, lost mode) | ✅ | ✅ | Role-gated (viewer can't control) |
| Geofences (create/list/delete, auto-action) | ✅ | ✅ | Server-side alert engine shared |
| **Geofence monitoring on the tracked device** | ✅ | ✅ | CLRegion monitoring; exit → server alert |
| Background location | ✅ (FGS + GPS) | ✅ (significant-change + visits) | iOS keeps it working after termination, near-zero battery; coarser fix |
| Heartbeat + location reporting | ✅ | ✅ | 60s cadence while app alive |
| Remote siren | ✅ | ✅ | Bundled dual-tone WAV, plays locked |
| Remote photo / audio capture (background) | ✅ (FGS) | ⛔ | iOS forbids background mic/camera. Foreground capture via UI hook; background commands → "open the app" notification |
| Audio evidence (armed watch, pre-roll, VAD) | ✅ | ⛔ | Requires continuous background mic — impossible on iOS |
| SMS command relay (offline) | ✅ | ⛔ | No SMS API for third-party apps. iOS covers this with push + poll |
| Anti-uninstall guard (accessibility) | ✅ (sideload flavor) | ⛔ | Impossible without MDM |
| Device admin / overlay / boot-time stealth | ✅ | ⛔ | Not available to App Store apps |
| Remote lock | ✅ (device admin) | ⛔ (honest ack) | iOS has no MDM-less lock; command acks with explanation |
| Remote wipe / factory reset | ✅ (device admin) | ⛔ (failed ack) | Requires MDM enrollment; ack carries the reason |
| Lost mode | ✅ | ✅ (notification) | iOS cannot lock the screen, so lost mode = loud notification |
| FCM push delivery | ✅ | ✅ | Server already routes FCM v1 → APNs (platform=ios); needs Firebase project + plist |
| Offline media queue + evidence chain | ✅ | ⛔ | No background capture to queue; media view is read-only |

## Key security parity

- Tokens live in the **Keychain** (never UserDefaults) — mirrors Android's
  Keystore-backed vault.
- Device routes use the **per-device secret key** (`x-device-key`), stored in
  the Keychain; the embedded shared key only unlocks registration.
- Pairing code = `sha256(device_key)[:8]` — byte-identical to the server's
  derivation, so linking works cross-platform.
- WS auth: token mandatory, anonymous → close 4408 (server-enforced, F-01).
- Viewers/device_only shares see stripped data — enforced server-side, the
  iOS UI just reflects `access_role`.

## Battery & privacy posture

- Significant-change + visit monitoring: no green indicator, near-zero
  battery — a deliberate improvement over the Android GPS stream.
- No always-on microphone (impossible on iOS; the green dot problem from the
  Android side simply doesn't exist here).
- Location is encrypted at rest server-side; iOS never caches coordinates
  beyond the last fix in memory.

## Rollout path

1. Mac + Xcode + Apple Developer account ($99/yr) required to build/sign.
2. `xcodegen generate` → open project → set Config.xcconfig → build.
3. Add Firebase (`GoogleService-Info.plist`) for push.
4. TestFlight for the beta cohort (same G1 testers as Android).

## Non-goals (v1)

- 1:1 feature parity with the Android app (impossible on stock iOS).
- Jailbreak/enterprise-MDM tiers (L5 in the Android research) — separate
  product decision, requires MDM infrastructure.
