# Magneetar — Project Status Report

**Generated:** August 4, 2026  
**Version:** 1.3.1  
**Status:** 🟢 Production Ready

---

## Executive Summary

Magneetar is a fully functional anti-theft tracking system with:
- **Android app** — stealth tracking, evidence capture, remote commands, multi-user device linking
- **Backend API** — FastAPI with intelligent theft detection (Sentinel AI) and full device-ownership scoping
- **Dashboard** — Next.js tactical command center with a premium landing + auth experience
- **Production deployment** — Docker Compose + Cloudflare Tunnel (SQLite on the persisted volume is the live data plane)

All **495 tests pass consistently** (342 backend + 153 dashboard). The latest round fixed the **command re-execution loop / stuck-PENDING bug** end-to-end: new Android `RecentCommandTracker` enforces at-most-once execution (a lost ack now converges via an idempotent re-ack instead of re-running the siren/capture every 10s), the command loop flushes the ack outbox before each poll, and the dashboard's `command_ack` WebSocket handler updates the row instantly (the empty handler is why successful commands looked PENDING for up to 10s). The system is hardened with reliability improvements (WebSocket connection limits, alert circuit breakers, per-device recipients, CI alert verification), and **Milestone 2 (Multi-User & Device Ownership) P0s are now complete**: devices link to accounts on Android at registration and via a claim endpoint, every dashboard endpoint is scoped by ownership, WebSocket broadcasts are owner-filtered, and per-user device limits are enforced. **Guardian Network (Milestone 3 P0)** is also live: opt-in guardians, blurred nearby scans, sighting reports, and recovery-request lifecycle — all verified end-to-end in production. The latest round landed **step-up-password media deletion**, **working remote commands** (wipe CONFIRMED_WIPE + hardened Android command loop), the **Trail Replay Invalid-Date fix**, the **Settings modal portal fix**, premium command buttons, and the **magenta-tile white-M brand refresh** (web + Android launcher). **v1.3.0** adds **uninstall protection** (active Device Admin blocks uninstall until deactivated — warning + instant server theft-signal on disable; device/profile-owner mode adds the hard `setUninstallBlocked(true)`; onboarding now routes through Device Admin by default with an explicit, informed skip; `scripts/enable-uninstall-protection.sh` provisions device-owner via adb; `docs/security.md`), **background camera/audio capture fixed** (new `MediaCaptureService` camera|microphone FGS — photo/front/audio now work from a locked screen on Android 14/15 and ack honestly), and the **bold solid white-M logo** (Moniepoint-style) across web + Android.

---

## Test Results

| Test Suite | Count | Status |
|------------|-------|--------|
| API Tests (`test_api.py`) | 60 | ✅ All pass |
| Auth Tests (`test_auth.py`) | 15 | ✅ All pass |
| Sentinel Tests (`test_sentinel.py`) | 17 | ✅ All pass (incl. confirmation-gate regressions for the theft-unlock fix) |
| E2E Tests (`test_e2e.py`) | 11 | ✅ All pass |
| Offline Monitor Tests (`test_offline_monitor.py`) | 6 | ✅ All pass |
| Reliability Tests (`test_reliability.py`) | 69 | ✅ All pass (WebSocket limits, live WS integration, full auth-path matrix incl. expired/revoked/tampered/missing-type, REST revocation, circuit breaker, per-device recipients) |
| **Multi-User Tests** (`test_multi_user.py`) | **36** | ✅ **All pass** (register-with-user-token linking, claim endpoint by key/id, ownership scoping across all dashboard endpoints, per-user device limits, idempotent re-claims, **ghost-owner recovery**: claimable orphaned devices, stale deleted-account tokens rejected) |
| **Guardian Tests** (`test_guardian.py`) | **23** | ✅ **All pass** (opt-in, recovery launch/close, blurred scans, rate-limited sightings, ownership isolation) |
| **Heartbeat/Theft Tests** (`test_heartbeat_theft.py`) | **3** | ✅ **All pass** (heartbeat w/ admin inactive → 200 + last_seen advances + no stolen-mode; sub-threshold activation is a no-op) |
| **Alert Settings Tests** (`test_alert_settings.py`) | **13** | ✅ **All pass** (per-device channels, enabled types, quiet hours, emergency always-deliver, dedup-row regression) |
| **Media Delete Tests** (`test_media_delete.py`) | **11** | ✅ **All pass** (step-up password gate: user password + admin API key, wrong-password 401, rate limit 429, ownership 403, evidence counter fix-up) |
| **Backend Total** | **342** | **✅ All pass** |
| **Dashboard Tests** | **153** | **✅ All pass** (18 suites, `tsc --noEmit` clean, incl. `MediaGallery.test.tsx` password-gated deletion, `SettingsModal.test.tsx` portal regression, `CommandPanel.test.tsx` wipe/front/burst, timestamp regressions, `useWebSocket.test.tsx` command_ack instant-update) |
| **Grand Total** | **495** | **✅ All pass** |

---

## Features Implemented

### ✅ Multi-User & Device Ownership (Milestone 2 — P0 Complete)

| Feature | Details |
|---------|---------|
| Device → User linking | `POST /api/device/register` accepts a user bearer token alongside the API key and sets `owner_id` |
| Claim endpoint | `POST /api/device/claim` links an existing device to the signed-in account (by device key or id; 403 for cross-account claims) |
| Multi-device dashboard | Dashboard device lists filtered by the authenticated user; admins see all |
| Ownership scoping | Locations, commands, media, alerts, geofences, evidence, alias, recover, and stats return **403 to non-owners**; error-log endpoints are admin-only |
| WebSocket scoping | Broadcasts filtered per device owner via an in-memory `device→owner` cache (hydrated from the DB on connect, survives restarts) |
| Per-user device limits | `MAX_DEVICES_PER_USER` enforced at register (new links) and claim; same-owner re-register/re-claim stays idempotent |
| Android account linking | `TrackingService` registers with the signed-in user's token (with plain-registration fallback); new `DeviceLinker` fires `/api/device/claim` after sign-in/sign-up |

### ✅ Reliability & Resilience (v1.1.0)

| Feature | Details |
|---------|---------|
| WebSocket Connection Limit | Max 100 concurrent dashboard connections, oldest-connection eviction |
| Stale Connection Heartbeat | 30s ping + 90s pong timeout, prunes dead/unresponsive clients |
| Alert Circuit Breaker | Auto-recovery after 5min cooldown, half-open probe state |
| Command Expiry | Unacknowledged PENDING commands auto-marked `expired` (5 min wipe/lock/alarm, 30 min otherwise); device poll skips them via `datetime()`-normalized comparison |
| Stats Data-Plane Fix | `/api/dashboard/stats` reads the SQLite data plane like every other endpoint (was the only endpoint querying the empty Docker Postgres → 0/0/0 counters); active counts use `datetime()`-normalized timestamps |
| Alert Retry with Jitter | 1 retry per channel with 1-2s random backoff |
| Request Timeout Middleware | 30s default, returns 504 on hang |
| Health Endpoint with DB Check | Returns `status: "degraded"` when DB unreachable |
| Graceful WS Shutdown | Broadcasts `reconnect: true` to clients before shutdown |
| DB Connection Resilience | SQLite `PRAGMA busy_timeout=5000` for concurrent access |
| Startup Validation Script | Pre-flight checks: env vars, DB writability, ports, deps |
| E2E Reliability Test Script | Shell-based integration test suite |
| Per-Device Alert Recipients | Per-device `alert_phone`/`alert_email` (fallback to env defaults) |
| CI Alert Credential Check | Read-only Twilio auth check on every push (non-blocking) |
| CI Alert Smoke Test | Manual `workflow_dispatch` — sends 1 real WhatsApp + SMS |

### ✅ Step-Up Media Deletion (security)

| Feature | Details |
|---------|---------|
| Delete gate | `POST /api/dashboard/media/{id}/delete` — user mode verifies the **account password** (bcrypt/PBKDF2), admin mode verifies the **master API key** (`hmac.compare_digest`); a dashboard session alone is never enough |
| Brute-force protection | `check_password_verify_rate_limit` — 10 attempts/min/actor, 429 beyond |
| Evidence integrity | Deleting a linked photo/audio decrements the owning `evidence_cases` photo/audio counters (never goes negative) |
| Ownership | Non-owners get 403; every deletion is audit-logged |
| Dashboard UI | Media Gallery manage mode — multi-select, select-all, portaled password prompt with error feedback |
| Tests | 11 backend + 5 dashboard |

### ✅ Remote Commands & Dashboard Reliability

| Feature | Details |
|---------|---------|
| Wipe fixed | Dashboard now sends `params='CONFIRMED_WIPE'` (the old button 400'd silently and never reached the device) |
| New commands | FRONT-camera + location-BURST buttons in the quick-action grid |
| Error feedback | Every command send surfaces success/error strips instead of failing silently |
| Android command loop | `handleCommand` always acks (executed/failed) — nothing sticks PENDING; camera capture bounded by 45s timeout, `onError`/`onDisconnected` complete the deferred so a broken camera can't stall the loop |
| At-most-once execution | New `RecentCommandTracker` (Android, persisted, 60-min retention) — a command the poll re-delivers after a lost ack is **re-acked (idempotent) instead of re-executed**, ending the siren/capture/burst replay loop; the command loop flushes the ack outbox before each poll so a queued ack lands before the next re-delivery |
| Instant command status | The dashboard `command_ack` WebSocket handler now flips the row's status/failure_reason immediately (was empty → successful commands looked PENDING for up to 10s); new `applyCommandAck` store action merges in place without clobbering `executed_at` |
| Settings modal | Portaled into `document.body` — the old `backdrop-blur` header clipped the `fixed` modal to 56px, making SETTINGS look dead |
| Trail Replay | `parseTimestamp`/`locationTimestamp` normalize ISO + SQLite timestamps — no more "Invalid Date"; stable animation deps |
| Tabs | Horizontal scroll so all seven tabs are reachable in the narrow panel |
| Command buttons | Tone-driven glassy gradient tiles (premium), not the flat cartoon look |

### ✅ Brand — Magenta Tile + White M

| Feature | Details |
|---------|---------|
| Web | `m-logo.svg` / `favicon.svg` / `logo.svg` — capital M in white on the magenta gradient |
| Dashboard + landing | Auth screen, landing nav, footer all use the new tile |
| Android adaptive icon | Magenta gradient `ic_launcher_background` + white M foreground |
| Legacy PNGs | All five mipmaps regenerated (48→192px) via `scripts/gen-launcher-icons.py` |

### ✅ Per-Device Alert Preferences

| Feature | Details |
|---------|---------|
| Channel toggles | Per-device restriction of which channels fire (email/WhatsApp/SMS/push chips; NULL = all four global channels) |
| Alert-type toggles | Per-device enable/disable of non-emergency alert types; **theft, SIM change, and factory reset are locked — they ALWAYS deliver** (bypass both gates) |
| Quiet hours | Suppress non-emergency alerts between configured hours (wraparound-aware, e.g. 22:00→07:00, server-local time) |
| Fail-open design | A DB hiccup while loading per-device prefs degrades to global defaults — an emergency is never silenced by an infra blip |
| Storage | Devices row: `alert_channels`/`enabled_types` (JSON text), `quiet_hours_start`/`end` (INTEGER 0-23); empty/None clears to global defaults |
| Validation | `PATCH .../alert-settings` validates channels/types against `alerts.ALL_CHANNELS`/`ALL_ALERT_TYPES` and hours 0-23 (400 on invalid) |
| Tests | 13 backend (`test_alert_settings.py`) + 6 dashboard (`DevicePanel.test.tsx`) |

### ✅ Backend (Python/FastAPI)

| Feature | File(s) | Details |
|---------|---------|---------|
| Device Registration | `routes/devices.py`, `auth.py` | JWT tokens + device key auth + user-account linking |
| Telemetry Ingestion | `routes/devices.py` | Full TelemetryPing schema |
| Sentinel AI | `sentinel.py` | Theft scoring with false-positive prevention |
| Geofencing | `sentinel.py`, `routes/devices.py` | Safe zones with exit alerts |
| Evidence Chain | `evidence.py` | SHA-256 chain of custody |
| Media Storage | `routes/devices.py` | Photo/audio evidence storage |
| Remote Commands | `routes/devices.py` | Lock, wipe, alarm, capture, burst |
| Offline Queue | `routes/devices.py` | Batch upload of queued pings |
| Alert Engine | `alerts.py` | SMS (Twilio), WhatsApp (Twilio), Push (FCM v1 via firebase-admin); email parked (SendGrid access pending) |
| Push Notifications | `alerts.py`, `MagneetarMessagingService.kt` | Firebase Cloud Messaging (HTTP v1) |
| Rate Limiting | `auth.py` | Per-endpoint rate limits |
| Request Timing | `main.py` | Slow request monitoring + X-Process-Time-Ms header |
| Error Tracking | `database.py`, `main.py` | Built-in error_log table + dashboard viewer |
| User Auth | `user_auth.py` | Email/password registration & login (bcrypt) |
| Dashboard Auth | `main.py`, `auth.py` | API key + JWT for dashboard |
| FCM Token Mgmt | `routes/devices.py` | Device push token registration |
| Modular Routes | `routes/` | API endpoints extracted from main.py into route modules |

### ✅ Android App (Kotlin)

| Feature | File(s) | Details |
|---------|---------|---------|
| Tracking Service | `TrackingService.kt` | Background location, heartbeat, command loop |
| Persistence Service | `PersistenceService.kt` | Dual-service redundancy for reliable background operation |
| Device Key | `TrackingService.kt` | 256-bit unique device key on first launch |
| Account Linking | `TrackingService.kt`, `DeviceLinker.kt` | Device registered with the signed-in user's token; claim on sign-in |
| Camera Capture | `TrackingService.kt` | Front + rear camera evidence |
| Audio Capture | `TrackingService.kt` | 20-second audio evidence |
| Location Burst | `TrackingService.kt` | 5 rapid location updates |
| Siren Alarm | `TrackingService.kt` | Max-volume audio alarm |
| Device Admin | `AdminReceiver.kt`, `TrackingService.kt` | Lock, wipe, admin management |
| Boot Persistence | `BootReceiver.kt` | Auto-start on boot, Chinese OEM delay, `LOCKED_BOOT_COMPLETED` |
| Watchdog Receiver | `WatchdogReceiver.kt` | AlarmManager-based self-healing |
| Health Check Worker | `HealthCheckWorker.kt` | Periodic WorkManager health verification |
| OEM Compatibility | `OEMUtils.kt` | Huawei, Xiaomi, Oppo, Vivo, **Transsion (Tecno/Infinix/Itel)** detection + auto-start workarounds |
| Environment Receiver | `EnvironmentReceiver.kt` | Restarts tracking services on power/connectivity/time/unlock events — the moments OEM battery killers release paused apps |
| WakeLock Management | `TrackingService.kt` | Huawei-whitelisted tags, periodic refresh |
| FCM Service | `MagneetarMessagingService.kt` | Push notifications via Firebase (onNewToken → server registration) |
| Sign Up / Sign In | `SignUpActivity.kt`, `SignInActivity.kt` | Email/password auth flow |
| Telemetry Reliability | `TrackingService.kt` | UTC timestamps (was local-time-without-offset → failed server anti-spoofing check); 2xx-only response handling; **auto re-register when access+refresh tokens die** (no more silent "Connected" while the server hears nothing — the root cause of a frozen "last seen") |
| Onboarding | `OnboardingActivity.kt` | First-launch walkthrough |
| Open Dashboard | `HomeActivity.kt` | Opens the **dashboard login page** (`https://app.<host>/login`, derived from the API server URL with scheme preservation) instead of the API server root; non-`api.*` self-hosted servers fall back to the server URL |
| Permissions | `PermissionsActivity.kt` | Location, camera, audio, notifications (incl. Android 13+ POST_NOTIFICATIONS) |
| Sentry Crash Reporting | `build.gradle.kts`, `MainActivity.kt` | Optional via env/property DSN; disabled safely when empty |
| ProGuard | `proguard-rules.pro` | Code shrinking for release builds |
| Release Signing | `build.gradle.kts` | Production APK signing configuration |

### ✅ Dashboard (Next.js/TypeScript)

| Feature | Details |
|---------|---------|
| Landing Page | Premium SaaS marketing page — twin-pillar positioning ("Protect what you own. Stay close to who you love."), hero, 12-feature grid (incl. Family & Team Circles, Guardian Network), how-it-works, "Built for Africa" (NBS-sourced stats), "Our story" (Built at OAU, verified facts), security, CTA, footer, auth-aware CTAs, direct APK download buttons |
| Login / Signup | Cinematic two-panel auth — animated aurora, live command-center telemetry mockup, social proof, cursor-tracking spotlight glass cards, sliding Account/API Key toggle, password visibility toggle |
| Real-time Map | Leaflet + MapTiler dark tiles (Carto fallback without key), auto-zoom to street level (z17) on device select, offline "last seen" banner, seekable Trail Replay timeline, OSRM route + Google Maps/Waze fallback |
| Device Panel | Device list with status indicators |
| Command Panel | Issue remote commands (ping, capture, lock, wipe) |
| Evidence Panel | View captured media |
| Sentinel Panel | Threat score visualization |
| Device Names | `deviceDisplayName()` fallback alias → model → label in the Sidebar + Device Panel (no more ambiguous "Device" for multiple phones per account) |
| Error Panel | View and filter backend errors |
| Media Gallery | Photo/audio evidence browser |
| ErrorBoundary | Catches React rendering errors gracefully |
| WebSocket Reconnection | Automatic reconnect with state preservation |
| Responsive Design | Tailwind CSS, mobile-friendly sidebar collapse |

### ✅ Deployment

| Component | Status | Details |
|-----------|--------|---------|
| Docker Compose | ✅ Running | server + dashboard, **SQLite-only** (v1.3.1: empty Postgres container removed — SQLite on the persisted volume is the single data plane; optional Postgres adapter logs a startup warning if opted in) |
| Cloudflare Tunnel | ✅ Running | api.magneetar.me → server / app.magneetar.me → dashboard |
| Health Checks | ✅ All pass | All 3 services: DB, server, dashboard |
| DB Backup Script | ✅ Fixed + verified | `bash scripts/backup-db.sh` snapshots the **live SQLite DB** (was dumping empty Postgres); backup → restore round-trip verified, integrity-checked; daily cron installed (3 AM); CI smoke test (`scripts/test-backup-smoke.sh`) in pipeline |
| Startup Validation | ✅ Created | `scripts/validate-startup.sh` with multi-exit codes |
| GitHub Actions CI | ✅ Configured | Tests, typecheck, Docker build, APK build, alert credential check |

---

## Configuration

### Environment Variables (`server/.env`)

| Variable | Required | Purpose |
|----------|----------|---------|
| `MT_API_KEY` | ✅ Yes | Master API key for legacy auth (min 32 chars) |
| `MT_JWT_SECRET` | ✅ Yes | JWT signing secret (min 64 chars) |
| `MT_ENCRYPTION_KEY` | ✅ Yes | Data encryption key (64 hex chars = 32 bytes) |
| `MT_FIREBASE_KEY` | ❌ No | **Service-account JSON path** for firebase-admin (FCM HTTP v1) |
| `MT_TWILIO_SID` / `MT_TWILIO_AUTH_TOKEN` | ❌ No | Twilio API credentials (SMS + WhatsApp) |
| `MT_TWILIO_SMS_FROM` | ❌ No | Twilio SMS-capable sender number |
| `MT_TWILIO_WHATSAPP_FROM` | ❌ No | Twilio WhatsApp sender (sandbox `whatsapp:+14155238886`) |
| `MT_ALERT_EMAIL` | ❌ No | Default email recipient (parked until SendGrid access) |
| `MT_ALERT_PHONE` | ❌ No | Default SMS/WhatsApp recipient |
| `MT_SENDGRID_KEY` | ❌ No | Email alerts via SendGrid (parked — access pending) |
| `MT_SENTRY_DSN` | ❌ No | Sentry DSN (Android `SENTRY_DSN` gradle property fallback) |
| `MT_DATABASE_URL` | ❌ No | PostgreSQL connection string |
| `MT_REQUEST_TIMEOUT` | ❌ No | Request timeout in seconds (default: 30) |
| `CF_TUNNEL_TOKEN` | ❌ No | Cloudflare tunnel token |

---

## Quick Reference

### Start the stack
```bash
bash scripts/deploy.sh
```

### Validate startup
```bash
bash scripts/validate-startup.sh
```

### Run reliability E2E tests
```bash
bash scripts/reliability-test.sh --start
```

### Backup database
```bash
bash scripts/backup-db.sh
```

### Run backend tests
```bash
cd server && ./venv/bin/python -m pytest tests/ -v
```

### Run dashboard tests
```bash
cd dashboard && npx jest --verbose
```

### View server logs
```bash
docker compose logs server -f
```

---

## API Documentation

Interactive API docs available at:
- **Development:** http://localhost:8000/docs
- **Production:** https://api.magneetar.me/docs

---

## Next Steps

### Immediate
- [x] Push v1.1.0 to origin and deploy via docker-compose
- [x] Build and sign Android APK (GitHub Actions `build-apk.yml`)
- [x] Fix pre-commit B008 warnings (FastAPI `Depends()` pattern — ignored via flake8 config)
- [ ] Add repo secrets so CI alert checks run: `MT_TWILIO_SID`, `MT_TWILIO_AUTH_TOKEN`, `MT_TWILIO_SMS_FROM`, `MT_TWILIO_WHATSAPP_FROM`, `MT_ALERT_PHONE`

### Short-term
- [x] Implement multi-user support with device ownership (Milestone 2 P0)
- [x] Set up automatic daily database backups + health monitor via cron (`scripts/install-cron.sh`, idempotent)
- [ ] Run `scripts/firebase-setup.sh` (interactive `firebase login` required) → produces google-services.json + **service-account JSON** for `MT_FIREBASE_KEY`
- [ ] End-to-end FCM push verification (send a real theft alert to a physical device)
- [ ] Set Sentry DSN (`MT_SENTRY_DSN`) and enable ProGuard mapping uploads
- [ ] Configure pre-commit hooks permanently (`pre-commit install`)

### Medium-term
- [ ] Role-based access (admin, viewer, device-only) — Milestone 2 P1
- [ ] Device sharing between accounts — Milestone 2 P1
- [ ] Analytics (crash-free rate, active devices, command success rate)
- [ ] Performance profiling on low-end devices
- [ ] Sentinel ML-based anomaly detection — Milestone 4

### Long-term
- [ ] Guardian Network (community-powered recovery) — Milestone 3
- [ ] BLE beacon integration for proximity alerts
- [ ] Embedded hardware for GPS tracking modules
- [ ] Cross-platform iOS app
