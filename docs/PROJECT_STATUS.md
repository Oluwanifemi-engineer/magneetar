# Magneetar — Project Status Report

**Generated:** August 16, 2026  
**Version:** 1.4.4  
**Status:** 🟢 Production Ready — G1 real-world validation in progress; Play submission gated (ADR-0006)

---

## Executive Summary

Magneetar is a production anti-theft platform: **Android app** (stealth
location + Sentinel theft scoring, armed evidence capture, remote commands,
uninstall protection, Find Network), **FastAPI backend** (ownership-scoped,
2FA, encrypted-at-rest evidence, RBAC device sharing, Guardian recovery),
**Next.js dashboard** (live map, command center, geofences, evidence
dossier), **iOS companion app code-complete** (both roles, honest scope,
build pending a Mac), and a **Docker Compose + Cloudflare Tunnel production
deploy** (SQLite data plane, healthy).

**All 769 tests pass** (558 backend + 211 dashboard) plus 43+ Android JVM
tests; typecheck clean; production `/health` green on v1.4.4. Every finding
from the external security review (F-01…F-09, S-6/S-7/S-10/S-12, G1#1) is
closed and re-verified live: WS admin bypass, API-key super-account, FCM
device pollution, /health + config leaks, tampered-download-signature 403,
install-channel fix (Play internal testing), and the marketing-claim
integrity pass (no fake adoption numbers anywhere). Sentry is live.

**Latest (2026-08-17, v1.4.4):**
- **Location accuracy fixed (G1-15)** — the Ile-Ife 55km-pin incident is
  root-caused and live-verified fixed: the Kalman filter now refuses to
  anchor on a garbage first fix (init guard), re-anchors when provably
  lost (escape hatch: degraded filter OR two agreeing GPS-class fixes far
  away), and the fused request never delivers an hours-old cached location
  as "ground truth" (wait-for-accurate + 30s max update age) with a
  2-min monotonic staleness gate on every fix. Live: pin back at Ile-Ife
  (HIGH 10.4m accuracy, continuous 2s pings at GPS scale — was 15,514
  consecutive rows at the 999m coast clamp). versionCode 13.
- **Trigger-first armed audio (G1-11)** — the mic is CLOSED while armed
  (no permanent green dot), opens on theft-signal escalation, auto-closes
  when the window ends; 15s pre-roll stays behind an explicit
  Always-listen toggle. Live-verified end-to-end on the owner's phone.
- **Armed camera burst** — theft escalation runs a 60s front-photo burst
  into the evidence case; verified live.
- **Live validation passed** — recovery drill 12/12, geofence exit +
  capture + siren auto-actions, sharing-RBAC sweep 27/27, 2FA live flow,
  theft-flood network block fixed (G1-9).
- **Play build fixed (G1-14/G1-15)** — Play AAB rebuilt to **versionCode
  13** with all G1 fixes (trigger-first audio + location accuracy);
  download page re-staged to the **play-clean** APK (the sideload flavor
  was being served — the exact profile Play Protect hard-blocks).
- **iOS companion app code-complete** — full SwiftUI app under `ios-app/`
  (owner dashboard + protected-iPhone roles, TOTP 2FA, WS live feed,
  background location, geofence monitoring, siren, FCM/APNs push when
  Firebase is configured); honest iOS scope in
  `docs/ios-port-capability-map.md`. Server needs zero changes. Build +
  TestFlight pending a Mac + Apple Developer account (owner's decision,
  deferred for budget).

---

## Test Results

| Test Suite | Count | Status |
|------------|-------|--------|
| **Backend (server/)** | **558** | ✅ **All pass, 4 skipped** (2026-08-16 run — full suite incl. security: TOTP 2FA lifecycle, step-up password gates, device-share RBAC, geofence auto-actions, evidence chain, rate limits) |
| **Dashboard (dashboard/)** | **211** | ✅ **All pass, 24 suites** (2026-08-16 run, `tsc --noEmit` clean) |
| **Grand Total** | **769** | ✅ **All pass** (558 backend + 211 dashboard) |
| **Android JVM Tests** | **43+** | ✅ **All pass** (both flavors; LostMode, SOS beacon wire contract, etc.) |
| **iOS unit tests** | 6 | ⏳ Written (`MagneetarTests`) — run on first Mac build |
| **Live verification** | — | ✅ Recovery drill 12/12 · sharing-RBAC 27/27 · geofence exit/capture/siren · 2FA flow · theft-flood fix (G1-9) · trigger-first audio lifecycle |

---

### ✅ v1.5 — Expert Review Round (2026-08-12)

| Feature | Details |
|---------|---------|
| Geofence auto-actions | Per-zone `auto_action` (capture → front-photo + audio; siren → alarm) fired exactly once on EXIT; validated + persisted + Postgres-parity + dashboard **Zones tab** UI (create with policy picker, list, two-click delete) (COMPETITOR_AUDIT P0 #1) |
| Geofence exit fix | Persisted `last_inside` makes transitions fire exactly once (exit detection + exit alert were dead code — `was_inside` was never written); safe-zone exit alert condition un-inverted to match the template |
| Location CSV export | `GET /api/dashboard/locations/{id}/export/csv` — ownership-gated, decrypted, Excel BOM, 10k cap + dashboard button (COMPETITOR_AUDIT P0 #5) |
| Lost Mode | `lost_mode` command end-to-end: server (priority 1, no step-up), dashboard button, Android full-screen `showWhenLocked` recovery lock + call button (COMPETITOR_AUDIT P0 #2) |
| Failed-unlock "theftie" | Failed unlocks since last success reported on every ping/heartbeat (Android: DPC exact count when device admin/owner, else permission-free keyguard heuristic via new `FailedUnlockReceiver`); Sentinel scores the previously-dead `failed_unlocks` signal (+20) over `MT_FAILED_UNLOCK_THRESHOLD` (default 5); both telemetry paths queue front-photo + audio evidence capture + fire an always-deliver alert, 10-min dedup (COMPETITOR_AUDIT P1 #4) |
| **Device sharing + RBAC (Milestone 2 P1)** | Owners grant family/partner accounts `admin` / `viewer` / `device_only` access (new `device_shares` table + `POST/GET/DELETE .../shares` endpoints, account-owner only, idempotent upsert). Central `_assert_device_access(db, id, auth, min_role)` enforces role floors on every device endpoint (read=viewer, control=admin, destroy/share=owner); the device list tags `access_role`/`is_owner` and redacts coordinates + PII for `device_only`. WebSocket connections carry an allowed-device set (owned + viewer/admin grants) so shared users get live updates — and `device_only` never receives live location (privacy tier). Dashboard: Sharing card (invite by email, role picker, revoke), sidebar role chips, role-gated controls/tabs. 13 new backend tests + 3 jest |
| **Recovery Dossier (COMPETITOR_AUDIT P0 #3)** | One-click police/insurer PDF export. The evidence PDF now includes the owner's **command timeline** (lock / siren / wipe / capture with issued-at, params, status, executed-at) and the device **alias**, and embeds **every** photo inline (was: first photo only, with per-item media re-fetch). Dashboard Evidence panel: renamed **EXPORT RECOVERY DOSSIER (PDF)**, always enabled (server auto-creates a case — a pre-theft dossier with device info + location trail + command history exports fine), success/error toasts + inline error strip. RBAC locked by tests: `device_only` share → **403** (privacy tier gets no coordinates and no PDF), `viewer` share → **200 PDF**. 4 + 2 backend + 5 dashboard tests |
| **Find Network Phase 1 (COMPETITOR_AUDIT P1 #6)** | SOS beacon protocol live on the Guardian pipeline. Server: per-request `recovery_requests.beacon_token` (minted at launch, never exposed in owner/guardian views), device-facing `GET /api/device/recovery/beacon` (own token only; shared API key rejected), sighting-by-`beacon_token` OR `request_id` on `POST /api/recovery/sightings` — the request id never goes on the air. Migration: guarded ALTER + `ensure_initialized` staleness check + pg adapter parity (the device_shares no-op bug class). Android: `SosBeaconBroadcaster` (stolen phone BLE-advertises the token as a service UUID while a recovery request is active) + `GuardianBeaconScanner` (opt-in guardians scan, decode, dedup via persisted 2h `SosBeaconTracker`, report sightings with their OWN coordinates); both dataSync FGSs degrade gracefully without BLE/permissions. Wire contract locked by JVM tests mirroring the server's `token_hex(8)` format. 12 backend + 16 JVM tests. Scope: Phase 1 — mesh scale-out, beacon-permission UX, battery-aware scheduling remain |
| **Interactive map navigation (v1.6)** | YOU/DEVICE chips + both markers are click-to-fly: YOU flies to the operator's position and pauses device follow (the per-second re-centre can't yank the view back); DEVICE flies to the device and resumes follow; FOLLOW now flies to the device immediately on enable. No poll-cycle wait to restore a manual view |
| **Find Network status card (v1.6)** | Guardian tab gains a two-state panel: Owner Beacon (BROADCASTING while a recovery request is active / STANDBY) + Guardian Scanner (SCANNING when opted in / OFF) — at-a-glance visibility of whether the stolen phone is broadcasting and this phone is helping |
| **BLE onboarding permission flow (v1.6)** | PermissionsActivity requests `BLUETOOTH_SCAN`/`ADVERTISE`/`CONNECT` on API 31+ with its own status row — optional and non-blocking (SMS pattern); pre-31 grants are install-time so it always reads satisfied |
| **Battery-aware Find Network scanning (v1.6)** | GuardianBeaconScanner paces itself: screen off → 5 min rest between scans, battery < 15% → 10 min, battery < 5% → paused until charging (re-checked each cycle). Scans stay LOW_POWER/30s — community scanning never drains a guardian's phone |
| **Trail replay follow yield (v1.6)** | Opening the replay timeline pauses device follow (restored on close) and MapController yields while it's open — scrubbing/playback pans to each point without the poll-tick re-centre yanking the view |
| **Simulated two-phone recovery drill (v1.6)** | Live end-to-end on :8001: owner + stolen device → launch → device fetches beacon token → guardian (second account) opts in and sights by token → owner sees sighting → close revokes beacon; shared API key rejected; zero residue after cleanup |
| Postgres frozen | Explicit DECISION in `docs/postgres-migration.md` + ADR-0005 + `kubernetes/` README: SQLite is the production architecture; adapter experimental |
| Repo hygiene | Stale root APKs/DB moved to `backups/dev-artifacts-2026-08-12/` |

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
| `MT_API_KEY` | ✅ Yes | **Master key** — dashboard admin login + step-up ONLY (min 32 chars, never in the APK) |
| `MT_DEVICE_KEY` | ✅ Yes (prod) | **Low-privilege device key** — the only shared key embedded in the APK (`BuildConfig.DEVICE_KEY`), device-scope auth only, must differ from `MT_API_KEY` |
| `MT_LEGACY_DEVICE_KEY` | ❌ Retired (2026-08-10) | Removed from code/config — the fleet must run APKs embedding `MT_DEVICE_KEY` |
| `MT_JWT_SECRET` | ✅ Yes | JWT signing secret (min 64 chars) |
| `MT_ENCRYPTION_KEY` | ✅ Yes | Data encryption key (64 hex = 32 bytes) — TOTP secrets + location at-rest encryption (v1.5) |
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
> **DONE (this round): Milestone 2 P1 role-based access + device sharing** — see the feature table.


- [x] Role-based access (admin, viewer, device-only) — Milestone 2 P1 ✅ (this round)
- [x] Device sharing between accounts — Milestone 2 P1 ✅ (this round)
- [ ] Analytics (crash-free rate, active devices, command success rate)
- [ ] Performance profiling on low-end devices
- [ ] Sentinel ML-based anomaly detection — Milestone 4

### Long-term
- [ ] Guardian Network (community-powered recovery) — Milestone 3
- [ ] BLE beacon integration for proximity alerts
- [ ] Embedded hardware for GPS tracking modules
- [ ] Cross-platform iOS app
