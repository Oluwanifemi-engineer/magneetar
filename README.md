# Magneetar

> **Protect what you own. Stay close to who you love.**  
> Military-grade anti-theft tracking and live location circles for Android — track, protect, and recover your devices while keeping family, coworkers, and teams in sync.

![Status](https://img.shields.io/badge/status-production-green)
![Tests](https://img.shields.io/badge/tests-507%20backend%20%2B%20197%20dashboard-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Kotlin](https://img.shields.io/badge/kotlin-Android-orange)
![License](https://img.shields.io/badge/license-BSL--1.1-orange)

---

## Architecture Overview

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Android App │────▶│   Magneetar API  │────▶│     SQLite     │
│  (Kotlin/Jet) │     │   (FastAPI/Py)   │     │  (WAL, single  │
└──────┬───────┘     └────────┬─────────┘     │   data plane)  │
       │                      │               └────────────────┘
       │                      │
       │  x-device-key        │  WebSocket
       │  (unique per device) │  (real-time)
       │                      │
       ▼                      ▼
┌──────────────┐     ┌──────────────────┐
│  FCM Push    │     │   Next.js        │
│  Notifications│     │   Dashboard      │
└──────────────┘     └──────────────────┘
```

### Key Features

| Feature | Status | Description |
|---------|--------|-------------|
| **🔐 Device Key Auth** | ✅ Live | Each device generates its own 256-bit secret key — not shared, not in APK |
| **🧠 Sentinel AI** | ✅ Live | Smart theft detection with false-positive prevention |
| **📍 Real-time Tracking** | ✅ Live | GPS + network location with 3-second intervals |
| **📸 Evidence Capture** | ✅ Live | Remote photo/audio capture with SHA-256 chain of custody |
| **📡 Geofencing** | ✅ Live | Safe zones with exit alerts **+ per-zone auto-actions** (auto photo/audio capture or siren on exit) |
| **🛰️ Location Export** | ✅ Live | Full history as CSV (law-enforcement handover, Excel-friendly) |
| **🔒 Lost Mode** | ✅ Live | Remote full-screen recovery lock with one-tap call button |
| **🔔 Push Notifications** | ✅ Live | FCM push alerts on theft, SIM change, geofence exit |
| **📊 Dashboard** | ✅ Live | Next.js tactical command center |
| **🔌 Offline Queue** | ✅ Live | Queues pings when offline, uploads when reconnected |
| **🛡️ Phantom Mode** | ✅ Live | Hidden operation mode for stealth tracking |
| **🚨 Remote Commands** | ✅ Live | Lock, wipe, alarm, capture photo/audio |
| **📋 Evidence Reports** | ✅ Live | PDF evidence packages with cryptographic chain |
| **🔄 Auto-Deploy** | ✅ Live | Docker Compose + Cloudflare Tunnel |
| **📦 Error Tracking** | ✅ Live | Built-in error logger with dashboard viewer |

---

## Quick Start

### Prerequisites

- Python 3.12+
- Docker & Docker Compose (for production)
- An Android device (for the app)
- A Cloudflare account (for public access via Tunnel)

### 1. Clone & Install

```bash
git clone https://github.com/Oluwanifemi-engineer/magneetar.git
cd magneetar
bash scripts/generate-env.sh   # Generate secure secrets
make setup                    # venv + server deps (incl. dev tooling) + npm ci
make pre-commit-install       # install git hooks (black, isort, flake8, eslint)
```

> `make setup` installs both `server/requirements.txt` (runtime) and
> `server/requirements-dev.txt` (pinned lint/test tooling that matches the
> pre-commit hook environment), then runs `npm ci` for the dashboard.
> `make pre-commit-install` wires the quality-gate hooks into your git
> workflow so every commit is checked automatically.

### 2. Configure Environment

Edit `server/.env`:

```env
# Required
MT_API_KEY=your-secure-api-key-here     # MASTER key — dashboard admin ONLY, never in the APK
MT_DEVICE_KEY=your-device-key-here      # LOW-PRIVILEGE key — the only key embedded in the APK

# Alert Services (at least one for theft notifications)
MT_ALERT_EMAIL=your@email.com      # Where alerts go
MT_SENDGRID_API_KEY=...             # Optional: email alerts
MT_FIREBASE_KEY=./firebase-key.json  # Optional: push notifications

# Optional: PostgreSQL (defaults to SQLite)
MT_DATABASE_URL=postgresql://user:pass@localhost:5432/magneetar
```

### 3. Start Development Server

```bash
make server
# Server running at http://localhost:8000 (uvicorn --reload)
```

### 4. Start Dashboard (Development)

```bash
make dashboard
# Dashboard at http://localhost:3000
```

### 5. Run Tests & Quality Gates

```bash
make test          # backend pytest (full suite) + dashboard jest
make validate      # full CI-equivalent gate: lint + typecheck + test + pre-commit
make test-all      # everything — same as make test (alias kept for compatibility)
```

> **507 backend tests + 197 dashboard tests** should pass. `make validate` runs
> every gate that CI enforces, so a green local `make validate` predicts a green
> GitHub Actions run.

---

## Production Deployment

### Docker Compose (Recommended)

```bash
# One-command deploy
bash scripts/deploy.sh

# Or manually:
docker compose up --build -d
```

This starts:
- **Magneetar Server** — FastAPI with uvicorn (port 8002), SQLite on the
  persisted `magneetar-data` volume (the single data plane — WAL mode,
  online-backup via `scripts/backup-db.sh`)
- **Magneetar Dashboard** — Next.js served via Nginx (port 3000)

### Cloudflare Tunnel (Public Access)

```bash
# Configure tunnel (one-time)
cloudflared tunnel create magneetar
cloudflared tunnel route dns magneetar api.magneetar.me
cloudflared tunnel route dns magneetar app.magneetar.me

# Edit ~/.cloudflared/config.yml:
# tunnel: <tunnel-id>
# ingress:
#   - hostname: api.magneetar.me
#     service: http://localhost:8002
#   - hostname: app.magneetar.me
#     service: http://localhost:3000
#   - service: http_status:404

# Start tunnel
cloudflared tunnel run magneetar
```

### Database Backups

```bash
# Create a backup
bash scripts/backup-db.sh

# List available backups
bash scripts/backup-db.sh --list

# Auto-backup via cron (daily at 3am)
crontab -e
0 3 * * * cd /path/to/magneetar && bash scripts/backup-db.sh
```

---

## Security Architecture

### Three auth worlds (who authenticates how)

| World | Credential | How it's presented | Scope |
|---|---|---|---|
| **Dashboard (web)** | Email/password (+2FA) | Login → JWT `type=dashboard` | The user's own account + shared devices |
| **Consumer's phone (app)** | Device key `MT_DEVICE_KEY` (embedded in APK) | `x-api-key` on register → device JWT `type=device`, then `Authorization: Bearer` | Device routes only (location, commands, media) |
| **Operator/admin** | Master key `MT_API_KEY` (server-side only) | `{ "api_key": … }` to `/api/auth/login` | Admin login + step-up |

### Device Key Authentication

Since **v1.4.0** the shared **low-privilege device key** (`MT_DEVICE_KEY`) is
embedded in every APK as `BuildConfig.DEVICE_KEY`. The app presents it only
once, at registration, to obtain a device JWT:

```
App boot → POST /api/device/register { x-api-key: <MT_DEVICE_KEY> }
                  ↓
Server verifies key, stores SHA-256 hash, issues device JWT (24h) + refresh (90d)
                  ↓
All subsequent calls: Authorization: Bearer <device-jwt>
```

**Why this is secure:**
- ✅ The key is **device-scope only** — `x-api-key` can never authenticate
  dashboard or account routes (F-02, regression-tested in `test_api.py`), so
  a public APK can't hand anyone the admin panel
- ✅ Server stores **only SHA-256 hashes** — a DB breach can't leak keys
- ✅ The master key (`MT_API_KEY`) is **never** embedded anywhere
- ✅ A per-device unique key (`x-device-key`) is also accepted for
  re-registration/recovery flows

### Auth Methods for device routes (in priority order)

1. **JWT Bearer token** — from device registration session
2. **x-device-key** — unique per-device secret (reinstall recovery)
3. **x-api-key** — shared key: the low-privilege device key
   (`MT_DEVICE_KEY`), the only key embedded in the APK

### Third-party integrations

Scoped per-account **developer API keys** (`mtk_…`) for external
integrations — alerting scripts, resellers, custom dashboards. Keys are
created in the dashboard (Settings → Developer API Keys) with a password
step-up, carry explicit scopes (`devices:read`, `devices:write`,
`alerts:read`, `media:read`), and are **intersected with your account's own
RBAC rights** — a viewer-shared device stays read-only through a key too.

```
# List devices (scope: devices:read)
curl -s https://api.magneetar.me/api/v1/devices \
  -H "Authorization: Bearer mtk_live_…"

# Issue a command (scope: devices:write, role admin/owner)
curl -s -X POST https://api.magneetar.me/api/v1/devices/<id>/commands \
  -H "Authorization: Bearer mtk_live_…" \
  -d '{"command": "alarm"}'
```

Security properties: the server stores only a 12-char prefix + SHA-256 hash
(the full key is shown once at creation), keys are per-key rate-limited, and
`wipe` is deliberately unavailable through keys (it requires the dashboard
step-up password). Full spec: `docs/developer-api.md`.

---

## API Overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | None | Server health check |
| `POST /api/device/register` | API Key | Register device, get tokens |
| `POST /api/device/location` | JWT/Device Key | Send telemetry ping |
| `POST /api/device/heartbeat` | JWT/Device Key | Send heartbeat |
| `POST /api/device/media` | JWT/Device Key | Upload evidence media |
| `POST /api/device/fcm-token` | Any | Register push token |
| `POST /api/auth/login` | None | Dashboard login with API key |
| `GET /api/dashboard/devices` | Dashboard | List all devices |
| `POST /api/dashboard/command` | Dashboard | Issue remote command |
| `GET /api/dashboard/errors` | Dashboard | View server errors |

Full auto-generated OpenAPI docs are available **locally** in development:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

They are deliberately **disabled in production** (docs_url=None) to reduce the
public attack surface; the live API is documented by this README and the
endpoint tables above.

---

## Android App Setup

### Prerequisites
- Android Studio (for development)
- Android 8.0+ (API 24) device

### Building

```bash
# The real google-services.json is gitignored (it identifies the live Firebase
# project). A safe placeholder template ships as
# android-app/app/google-services.json.example — copy it for a build that
# compiles without Firebase push, or restore your real file (CI injects the
# real one from the GOOGLE_SERVICES_JSON secret; your local real copy lives in
# backups/google-services.json.real).
cp android-app/app/google-services.json.example android-app/app/google-services.json

cd android-app
./gradlew assembleRelease

# With custom server URL:
# DEVICE_KEY = the server's MT_DEVICE_KEY (low-privilege). NEVER bake the
# master MT_API_KEY into the APK — anyone who downloads the app could extract
# it and get dashboard-admin.
SERVER_URL=https://api.magneetar.me \
DEVICE_KEY=your-device-key \
./gradlew assembleRelease
```

### APK Build via GitHub Actions

The CI pipeline automatically builds the APK on push to `main`:
1. Go to your GitHub repo → Actions
2. Select "Build Magneetar APK" workflow
3. Click "Run workflow"

Download the APK artifact and install on your device.

---

## Technology Stack

### Backend
- **Python 3.12+** with **FastAPI**
- **SQLite** (WAL) — the single data plane, backed up via `scripts/backup-db.sh`
- **JWT** + **Device Key** authentication
- **Cloudflare Tunnel** for secure public access
- **Docker Compose** for orchestration
- **Sentry SDK** (optional) for error monitoring

### Frontend
- **Next.js 14** with TypeScript
- **Tailwind CSS** for styling
- **Leaflet** for mapping
- **Nginx** for production serving

### Android
- **Kotlin** with Jetpack/AndroidX
- **Firebase Cloud Messaging** for push
- **Camera2 API** for evidence capture
- **Device Policy Manager** for admin features
- **OkHttp** for networking

### CI/CD
- **GitHub Actions** — test, build, deploy
- **Blocking flake8 lint gate** — full `.flake8` selection, pinned to match pre-commit
- **Multi-stage Docker builds** — optimized images
- **Health checks** on all services

### Developer Tooling
- **`Makefile`** — one-command gates (`make setup`, `make validate`, `make test`, …)
- **`pre-commit`** — black, isort, flake8, eslint run on every commit
- **`server/requirements-dev.txt`** — pinned lint/test tooling, single source of truth
- **`make help`** — list every available target

---

## Project Structure

```
magneetar/
├── server/                  # Python FastAPI backend
│   ├── main.py              # API routes & middleware
│   ├── auth.py              # JWT + device key auth
│   ├── database.py          # SQLite schema & helpers
│   ├── sentinel.py          # Theft detection AI
│   ├── alerts.py            # Push/SMS/Email alerts
│   ├── models.py            # Pydantic models
│   └── tests/               # 507 unit + E2E tests
├── dashboard/               # Next.js web dashboard
│   ├── src/app/             # Pages & layouts
│   ├── src/components/      # UI components
│   └── src/lib/             # API client & utils
├── android-app/             # Android Kotlin app
│   └── app/src/main/java/   # Services & activities
├── scripts/                 # Deployment & utilities
│   ├── deploy.sh            # Auto-deploy script
│   ├── backup-db.sh         # Database backup
│   ├── device_simulator.py  # Theft scenario tester
│   └── test-e2e.sh          # E2E test runner
├── docker-compose.yml       # Production stack
└── docs/                    # Documentation
```

---

## License

**Business Source License 1.1 (source-available)** — see [LICENSE](LICENSE) for details.

The code is publicly readable and may be used for personal, educational, and
non-commercial purposes. Commercial use of the Licensed Work as a competing
anti-theft / tracking / monitoring service is not permitted until the Change
Date (**2030-08-01**), at which point the project converts to the Apache
License 2.0.

---

## Author

**Oluwanifemi Tinubu**  
Electronic and Electrical Engineering Student  
Magneetar — Track · Protect · Recover
