# Magneetar iOS

iOS companion app for the Magneetar anti-theft platform — one app, two roles:

- **Owner dashboard** — live device map, commands (siren, locate, photo/audio
  capture, lost mode), geofences with auto-reactions, alert history, evidence
  media. Mirrors the Android dashboard, minus what iOS forbids.
- **Protected iPhone** — register this iPhone as a tracked device: background
  location (significant-change + visit monitoring, keeps working after the app
  is terminated), server-pushed geofences with exit alerts, and a 10s command
  poll that runs the siren and notifies on theft commands.

## Status

**Implemented (v1 — honest iOS scope).** Builds with XcodeGen + Xcode on a Mac.

## iOS-honest scope (what iOS will NOT do)

These Android features are platform-banned on stock iOS and are deliberately
absent (see `docs/ios-port-capability-map.md` for the full matrix):

| Android feature          | iOS reality |
|--------------------------|-------------|
| Background mic/camera    | Foreground-only capture; background capture commands surface a "open the app" notification |
| SMS command relay        | No SMS send/read API for third-party apps |
| Anti-uninstall guard     | Impossible without MDM |
| Device admin / overlay   | Not available to App Store apps |
| Remote lock / wipe       | Requires MDM; `lock`/`wipe` commands ack honestly (lock → notification, wipe → failed ack with reason) |
| Continuous GPS streaming | Significant-change + visit monitoring instead (near-zero battery, still works when terminated) |

Everything that matters still works: the iPhone stays locatable in the
background, geofence exits alert the server, and the owner can siren/locate it
from any device.

## Building (macOS only)

Xcode is macOS-only — the project is committed as an **XcodeGen spec** so
opening it on a Mac is one command:

```bash
brew install xcodegen
cd ios-app
cp Config.xcconfig.example Config.xcconfig   # then set real values (below)
xcodegen generate
open Magneetar.xcodeproj
```

The `.xcodeproj` is generated and never committed (gitignored).

### Config.xcconfig (required)

| Key | Value |
|-----|-------|
| `MAGNEETAR_SERVER_URL` | API origin, e.g. `https://api.magneetar.me` |
| `MAGNEETAR_DEVICE_KEY` | The LOW-PRIVILEGE device key — must match the server's `MT_DEVICE_KEY`. **Never** the master `MT_API_KEY` |

A pre-build script fails the build if these are missing (same fail-fast rule
as the Android app's release build). Config.xcconfig is gitignored.

### Push notifications (optional but recommended)

The server already delivers push via FCM v1, which reaches iOS through APNs
when the token's `platform` is `ios`. To enable:

1. Create a Firebase project, add an iOS app (`com.magneetar.app`), download
   `GoogleService-Info.plist` into `ios-app/Magneetar/`.
2. Configure APNs in Firebase (upload the APNs key from your Apple Developer
   account).
3. Build — the app configures Firebase only when the plist is present, so
   plain builds never crash.

Without push, the app still works fully: commands arrive via the 10s poll and
alerts are visible on open.

## Architecture

```
Magneetar/
├── MagneetarApp.swift        # entry + APNs bridge + root routing
├── Config.swift              # build-time config (Info.plist injected)
├── Core/
│   ├── APIClient.swift       # async HTTP client (Bearer + x-device-key auth)
│   ├── Models.swift          # Codable mirrors of the server API
│   ├── Session.swift         # auth store: register/login/2FA/refresh (Keychain)
│   ├── KeychainStore.swift   # tokens never touch UserDefaults
│   └── DeviceIdentity.swift  # per-install device id + secret key
├── Device/
│   ├── LocationService.swift # background location + geofence regions
│   ├── BeaconService.swift   # heartbeat + location reports
│   ├── CommandPoller.swift   # 10s poll → execute → ack
│   ├── SirenPlayer.swift     # bundled dual-tone siren
│   └── PushService.swift     # FCM token registration + command pushes
├── Dashboard/
│   └── DashboardSocket.swift # live WS feed (wss://…/ws/dashboard?token=…)
├── Views/                    # SwiftUI: auth, device list, detail, settings
└── Resources/siren.wav       # generated dual-tone siren
```

## Testing

`MagneetarTests` covers the offline core: API contract decoding (snake_case →
camelCase), the pairing-code derivation (must match the server's
`sha256(device_key)[:8]`), and display formatting. Run via Xcode
(`Cmd+U`) or `xcodebuild test -scheme Magneetar`.

## License

Proprietary — all rights reserved.
