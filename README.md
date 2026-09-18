# Magneetar

> **Anti-theft tracking for Android.** When your phone is stolen, Magneetar keeps reporting its location, captures evidence, and lets you lock or alarm it remotely.

![Status](https://img.shields.io/badge/status-active%20development-blue)
![Tests](https://img.shields.io/badge/tests-653%20backend%20%2B%20209%20dashboard-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.140-green)
![Kotlin](https://img.shields.io/badge/kotlin-Android-orange)

---

## The Problem

Every year, thousands of phones are stolen at universities across Nigeria and Africa. Students lose contact with families, and recovery attempts cost ₦45,000+ with no guarantee. Google Find My Device and Samsung Find My Mobile fail when the device is wiped or offline.

Magneetar solves this by making the phone fight back — even after it's stolen.

## What it does

| Feature | How it works |
|---------|-------------|
| **Real-time tracking** | GPS fix every 3 seconds while moving — auto-drops to 30s when stationary, 60s below 15% battery (adaptive cadence, battery-aware) |
| **Theft detection** | Sentinel scores suspicious activity (SIM change, failed unlocks, device admin disabled) |
| **Evidence capture** | Auto-photos and audio when theft is detected |
| **Remote commands** | Lock, siren alarm, front-camera photo, audio recording, remote wipe (requires Device Admin enabled on the device — otherwise app data is cleared and Lost Mode engages; the dashboard shows the true outcome) |
| **SMS relay** | Commands arrive via SMS when phone is offline — optional; if you skip SMS permissions or the device can't send SMS, commands still arrive through the app's network check |
| **Geofencing** | Safe zones with exit alerts and auto-actions |
| **Push alerts** | Theft, SIM change, geofence exit → instant notification |
| **Web dashboard** | See your devices on a live map from any browser |
| **Family / guardian circles** | _In development_ — shared location tracking is planned but not live in this release |
| **IMEI vault** | _In development_ — secure IMEI storage and police-report helper is planned but not live in this release |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Android App    │────▶│  Magneetar API   │────▶│  PostgreSQL │
│  (Kotlin)       │     │  (FastAPI)       │     │  Postgres   │
│                 │◀────│                  │◀────│             │
│  - Tracking     │     │  - Auth (JWT)    │     └─────────────┘
│  - Commands     │     │  - Device mgmt   │
│  - Sentinel     │     │  - WebSocket     │     ┌─────────────┐
│  - Evidence     │     │  - Alerts        │────▶│  Redis      │
└─────────────────┘     └──────────────────┘     │  (cache +   │
                           │                     │  pub/sub)   │
                           ▼                     └─────────────┘
                    ┌──────────────────┐
                    │  Next.js Dashboard│
                    │  (TypeScript)     │
                    │                   │
                    │  - Live map       │
                    │  - Device cards   │
                    │  - Alert feed     │
                    │  - Remote commands│
                    └──────────────────┘
```

| Component | Technology | Status |
|-----------|-----------|--------|
| Server | Python 3.12, FastAPI, Pydantic | ✅ Deployed at api.magneetar.me |
| Database | PostgreSQL + Redis — self-hosted in the Docker stack (managed Postgres, e.g. Neon, also supported) | ✅ Live |
| Dashboard | Next.js 14, TypeScript, Tailwind, Leaflet | ✅ Live |
| Android | Kotlin, Jetpack, Material Design 3 | 🔧 Functional beta — tracking, commands, detection all work |
| CI/CD | GitHub Actions (8 workflows) | ✅ Automated |

## Quick Start

### For Testers

1. Download the APK from the releases page
2. Enable "Install from unknown sources" on your Android device
3. Open Magneetar → Sign Up → grant permissions
4. The app runs silently in the background

### For Developers

```bash
# Clone
git clone <repo-url> && cd magneetar

# Server
cd server
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest  # Run 653 tests

# Dashboard
cd ../dashboard
npm install
npm run dev

# Android
# Open android-app/ in Android Studio
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed setup and coding conventions.

## Project Structure

```
magneetar/
├── server/                    # FastAPI backend (~80 Python files, 25K+ lines)
│   ├── main.py               # App entry point (224 lines — init + route registration)
│   ├── infrastructure/       # Middleware, lifespan, WebSocket handlers, APK routes
│   ├── routes/               # API modules (auth, devices, dashboard, commands)
│   ├── models.py             # Pydantic schemas (raw-SQL storage layer)
│   ├── config.py             # Environment configuration
│   └── tests/                # 653 pytest tests
│
├── android-app/               # Android app (~108 Kotlin files, 24K+ lines)
│   └── app/src/main/java/com/magneetar/app/
│       ├── MainActivity.kt           # Onboarding router
│       ├── SignInActivity.kt         # Biometric auth (Opay-style)
│       ├── PermissionsActivity.kt    # Step-by-step permission flow
│       ├── DashboardActivity.kt      # Main dashboard
│       ├── HomeFragment.kt           # Security score, quick actions
│       ├── MapFragment.kt            # OSMDroid live map
│       ├── DevicesFragment.kt        # Device cards with commands
│       ├── AlertsFragment.kt         # Activity feed
│       ├── SecurityFragment.kt       # IMEI vault, emergency actions
│       ├── TrackingService.kt        # Foreground service, location, heartbeat
│       ├── SentinelEngine.kt         # Theft detection scoring
│       └── CommandExecutor.kt        # Remote command handling
│
├── dashboard/                 # Next.js web dashboard (~146 TypeScript files, 26K+ lines)
│   └── src/
│       ├── app/              # Pages (landing, login, dashboard)
│       ├── components/       # React components
│       ├── hooks/            # Custom hooks
│       └── lib/              # API client, utilities
│
├── tests/                     # Integration tests
├── scripts/                   # Deployment and utilities
├── docs/                      # Documentation
└── .github/workflows/         # 8 CI/CD workflows
```

## API Endpoints

**Device-facing (phone → server):**
- `POST /api/device/register` — register device, get JWT
- `POST /api/device/location` — telemetry ping
- `POST /api/device/heartbeat` — heartbeat
- `POST /api/device/media` — upload evidence
- `GET /api/device/commands/{id}` — poll commands
- `POST /api/device/commands/{id}/ack` — acknowledge command

**Dashboard-facing (web → server):**
- `POST /api/auth/login` — dashboard login
- `GET /api/dashboard/devices` — list devices with locations
- `POST /api/dashboard/command` — issue remote command
- `GET /api/dashboard/evidence/{id}` — evidence cases
- `POST /api/dashboard/geofence` — create geofence
- `GET /api/dashboard/locations/{id}/export/csv` — location export

## What We Need

We're looking for contributors to help with:

| Role | What you'd do | Priority |
|------|--------------|----------|
| **Android UI Designer** | Rebuild app layouts in Jetpack Compose matching Figma designs | 🔴 Critical |
| **Android Developer** | Improve tracking reliability, add features, fix bugs | 🟡 High |
| **Backend Developer** | API improvements, scaling, new endpoints | 🟡 High |
| **Dashboard Developer** | UI improvements, new features | 🟢 Medium |
| **QA Tester** | Test on different Android devices, report bugs | 🟢 Medium |

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started.

## Security

- **Device key auth:** Each device generates its own 256-bit secret key
- **JWT tokens:** Short-lived access tokens, long-lived refresh tokens
- **Encrypted at rest:** AES-256-GCM for sensitive data
- **Rate limiting:** Per-endpoint rate limits prevent abuse
- **Device Admin:** Prevents unauthorized app uninstallation

## License

Business Source License 1.1 — source-available, non-commercial use allowed.
Converts to Apache 2.0 on 2030-08-01.

## Author

Oluwanifemi Tinubu — Electronic and Electrical Engineering, Obafemi Awolowo University
