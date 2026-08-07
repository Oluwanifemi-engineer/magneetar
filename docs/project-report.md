# MAGNEETAR

## An Integrated Anti-Theft Mobile Security Ecosystem — Design, Implementation, and Evaluation

**Project Report · Magneetar Engineering Program (MEP)**

| | |
|---|---|
| **Author** | Oluwanifemi Tinubu — Electronic & Electrical Engineering |
| **Version** | 1.4.0 (report revision 1.0) |
| **Date** | August 7, 2026 |
| **Repository** | https://github.com/Oluwanifemi-engineer/magneetar |
| **License** | Business Source License 1.1 (converts to Apache 2.0 on 2030-08-01) |

---

## Abstract

Smartphone theft is one of the most pervasive crimes in the developing world — the National Bureau of Statistics estimates more than **25 million phones are stolen in Nigeria every year** (one every ~1.2 seconds), with fewer than **12% ever recovered**. Existing solutions are either closed ecosystems with no remote-command depth, paid subscriptions, or apps that fail silently on modern Android platforms and on low-cost OEM devices.

Magneetar is an end-to-end, self-hosted anti-theft ecosystem built from scratch across **three cooperating subsystems**: a native **Android application** (Kotlin, ~6,100 lines), a **FastAPI backend** (Python, ~10,600 lines), and a **Next.js tactical dashboard** (TypeScript, ~15,000 lines). The system delivers continuous Kalman-fused tracking, an intelligent theft-detection engine (Sentinel) with false-positive prevention, offline SMS command relay, camera/audio evidence capture from a locked screen, uninstall resistance via Device Admin, multi-user device ownership, a community Guardian Network, TOTP two-factor authentication, and a real-time WebSocket dashboard — all verified by **573 automated tests** and **measured load benchmarks** that were run against a production-equivalent 4-worker deployment.

This report documents the full journey: problem analysis, requirements engineering, architecture, per-subsystem implementation, security design, testing, measured performance (including the engineering ceiling and the evidence behind it), deployment, operational hardening, and a step-by-step **build-from-scratch guide** in the appendix.

---

## 1. Introduction

### 1.1 Background

The smartphone is no longer a luxury — it is the primary device for banking, identity, communication, and navigation. In Nigeria, the phone is often the single most valuable portable asset a person owns, yet it is also the most frequently stolen. When a phone is stolen:

- the **owner loses** the device's value, their data, and access to accounts;
- **tracking attempts fail** because the thief switches off the device, removes the SIM, or the phone's own "find my phone" features are disabled by the same platform that is supposed to protect it;
- **evidence is destroyed** — by the time authorities are involved, the device has been wiped and reflashed;
- **recovery is rare** — police rarely have the device-level intelligence to act.

Existing commercial anti-theft products (Google Find My Device, Cerberus, Prey, Avast Anti-Theft) share structural weaknesses: they are closed-source, subscription-based, or dependent on a single vendor's cloud; they frequently fail to run reliably in the background on Android (where aggressive OEM battery optimizers kill tracking services); and they rarely expose the raw telemetry and evidence chain a law-enforcement case needs.

### 1.2 Problem Statement

Design and build a complete, self-hosted, real-world-usable anti-theft system that:

1. **Tracks** a device continuously and accurately even in the background on budget Android devices common in Africa (Tecno, Infinix, Itel, Xiaomi, Oppo, Vivo, Huawei).
2. **Detects** theft intelligently from telemetry rather than reacting only to user action.
3. **Commands** the device remotely — lock, wipe, siren, photo, audio — **even when the device has no internet** (offline SMS relay).
4. **Collects admissible evidence** with a cryptographic chain of custody.
5. **Resists uninstallation** by a thief within what the Android platform permits.
6. **Presents** everything on a real-time web dashboard that a non-technical owner can operate.
7. Remains **self-hostable and privacy-preserving** — the operator owns the data plane.

### 1.3 Objectives

| # | Objective | Fulfilled by |
|---|---|---|
| O1 | Continuous, accurate background tracking on stock Android | `TrackingService` + dual-service redundancy + Kalman fusion |
| O2 | Automatic theft detection with low false positives | Sentinel engine (weighted signals + confirmation gate) |
| O3 | Remote commands that work online and offline | Poll/ack command protocol + SMS relay (`RECEIVE_SMS`) |
| O4 | Evidence capture from a locked screen on Android 14/15 | `MediaCaptureService` camera/mic foreground service |
| O5 | Theft evidence with chain of custody | SHA-256 evidence chain + PDF case reports |
| O6 | Multi-user ownership and account security | Milestone 2 ownership model + TOTP 2FA |
| O7 | Real-time monitoring dashboard | Next.js dashboard + Redis-backed WebSocket bus |
| O8 | Operational readiness (deploy, backup, monitor, recover) | Docker Compose + Cloudflare Tunnel + cron backups + recovery drills |
| O9 | Measurable scalability | Load-tested 4-worker stack, batched writes, documented ceiling |

### 1.4 Scope

**In scope:** Android application, REST + WebSocket backend, web dashboard, SQLite (and a documented Postgres path), alerting (SMS/WhatsApp/push), evidence management, multi-user ownership, Guardian Network, deployment and operations tooling.

**Out of scope (documented in the SRS):** iOS, dedicated embedded hardware (future), AI-driven behavioral analysis (future), multi-region cloud, enterprise multi-tenancy.

### 1.5 Methodology

The project followed a **documentation-driven, requirements-first engineering process**:

1. **SRS** (`docs/requirements/SRS.md`) — functional and non-functional requirements.
2. **Architecture Document** (`docs/architecture.md`) — component responsibilities, data flow, security principles.
3. **Architecture Decision Records (ADRs)** — `0001` documentation-driven development, `0002` backend single-source-of-truth, `0003` API-first architecture, `0004` event-driven notifications.
4. **Implementation** in milestone order (M1 core loop → M2 multi-user → M3 Guardian → M4 hardening).
5. **Verification** — continuous test suites, CI gates, and later **measured load tests** against production-equivalent deployments.
6. **Operations** — deploy scripts, health checks, backup/restore drills, recovery drills.

Every release was committed with a conventional-commit message, recorded in `CHANGELOG.md`, and — from v1.3 onward — **deployed and verified live** rather than left as unverified code.

---

## 2. Related Work & Technical Background

### 2.1 Existing Anti-Theft Solutions

| Solution | Strengths | Weaknesses vs. Magneetar |
|---|---|---|
| Google Find My Device | Built into Android, zero install | Closed ecosystem; limited command set; offline network-dependent; no evidence case; no multi-user |
| Cerberus | Deep remote command set | Paid subscription; closed-source; aggressive-Permission profile can trigger Play blocks |
| Prey | Multi-device, open-source core | Backend cloud dependency; weaker Nigeria-market OEM survival; simpler Sentinel logic |
| Apple Find My / AirTag | Huge crowdsourced network | iOS-only; no remote wipe/siren depth on Android |

**Gap addressed:** a self-hosted, transparent, evidence-first system whose tracking survives the OEM battery killers that dominate the African market, whose commands work with **zero internet** (SMS), and whose owner is the single data plane.

### 2.2 Key Platform Constraints That Shaped the Design

- **Android background-execution limits (8.0+)**: `START_STICKY` alone is insufficient; OEM battery managers (Transsion HiOS/XOS, MIUI, ColorOS, EMUI) aggressively kill background services. → `BootReceiver` + `WatchdogReceiver` (AlarmManager) + `HealthCheckWorker` (WorkManager) + `EnvironmentReceiver` (restart on power/connectivity/time/unlock events) + OEM-specific guidance (`OEMUtils`).
- **Android 14/15 foreground-service rules**: a `camera|microphone` FGS **cannot be started from the background**. → the "armed capture" pattern (see §6.4).
- **Play Protect on sideloads**: apps declaring `RECEIVE_SMS` + Device Admin + background location are deterministically blocked when sideloaded. → distribution-flavor split (`sideload` vs `play`), documented consumer mitigation, and the strategic move to Play Store distribution (§9.6).
- **Desktop browser geolocation**: `navigator.geolocation` on a desktop laptop is IP/Wi-Fi derived (1–5 km error, sometimes 10–100 km); `enableHighAccuracy` is a no-op on desktop. → the dashboard now renders accuracy circles, gates distance/route on accuracy, and tells the operator to use a phone browser (§8.3).

---

## 3. Requirements Analysis (from the SRS)

The SRS (MAG-SRS-001) defines the system as **six cooperating components**: Android application, backend platform, web dashboard, data platform, notification services, and (future) hardware platform.

### 3.1 Functional Requirements (summary)

| Area | Key requirements |
|---|---|
| Asset management | Register/view/update/remove protected devices; per-user device limits |
| User management | Registration, email/password login, **TOTP 2FA**, password reset, email verification, account deletion |
| Monitoring & tracking | Continuous telemetry, location history, offline detection, battery/network state |
| Security | Authentication, authorization, ownership scoping, secure communication, audit logging |
| Notifications | SMS, WhatsApp, push, email channels; per-device channel/type/quiet-hours preferences; emergency alerts always deliver |
| Evidence | Photo/audio capture, storage, SHA-256 chain, PDF case reports, step-up-gated deletion |
| Guardian network | Opt-in, blurred sightings, recovery-request lifecycle |

### 3.2 Non-Functional Requirements

| NFR | Requirement | Evidence |
|---|---|---|
| Security | Defense-in-depth, least privilege, encrypted transport, no plaintext secrets in repo | §9; key-split audit found and fixed a real master-key exposure |
| Reliability | Survive restarts, OEM kills, network loss; bounded resources | 69 reliability tests; WS limits; circuit breakers; offline queue |
| Performance | < 500 ms p95 telemetry ingestion at 100 pings/s; graceful degradation at ceiling | §11 measured |
| Scalability | Support 2,000+ active devices on one host; documented growth path | §11, §15 |
| Maintainability | Documentation-driven, lint-gated, modular | §10, §12 |
| Usability | A non-technical owner can operate the dashboard | §8 |

### 3.3 Actors

- **Owner / End user** — registers, monitors, commands their devices.
- **Guardian** — opted-in community member who can submit blurred sightings.
- **Administrator** — dashboard admin (master API key), sees all devices.
- **System** — scheduled loops (offline monitor, archive, retention, heartbeat) run exactly once via the leader lock.

---

## 4. System Architecture

### 4.1 High-Level View

```
┌──────────────────┐   HTTPS/REST   ┌──────────────────────┐   ┌───────────────┐
│   Android App    │ ─────────────▶ │   Magneetar API      │──▶│  SQLite (WAL) │
│  (Kotlin, min    │                │   FastAPI + Uvicorn  │   │  single data  │
│   API 24, target │ ◀───────────── │   × 4 workers        │   │  plane        │
│   API 36)        │   poll/ack     └──────────┬───────────┘   └───────────────┘
└────────┬─────────┘            commands       │                    ▲
         │                                     │ WebSocket (Redis   │
         │ SMS (offline relay)                 │  pub/sub bus)      │
         ▼                                     ▼                    │
┌──────────────────┐   ┌─────────────────────────────┐   ┌──────────┴────────┐
│ Twilio / Termii  │   │  Next.js Dashboard (Nginx)  │   │ Redis 7          │
│ SMS + WhatsApp   │   │  landing · auth · map · cmd │   │ (bus + leader    │
└──────────────────┘   └─────────────────────────────┘   │  lock + rate)    │
                                                          └───────────────────┘
```

All clients talk **only** to the backend API. The database is never exposed. Every external interface is HTTPS via a Cloudflare Tunnel; WebSocket upgrades terminate at the API.

### 4.2 Architectural Principles (ADRs)

1. **Backend is the single source of truth** (ADR-0002): all business logic, validation, and data access live in the server; clients are thin.
2. **API-first** (ADR-0003): every feature is defined as an endpoint with Pydantic validation; the Android app and dashboard are independent consumers of the same contract.
3. **Event-driven notifications** (ADR-0004): alerting is asynchronous, retried, and channel-agnostic.
4. **Documentation-driven development** (ADR-0001): the SRS → architecture → ADR chain must exist before implementation.

### 4.3 Data Plane

- **SQLite in WAL mode** is the production data plane — one file, zero-ops, transactional, and fully offline-backup-able while live. `busy_timeout=5000` handles concurrent workers.
- 20 tables: `users`, `devices`, `locations`, `heartbeats`, `commands`, `media`, `alerts`, `evidence_cases`, `geofences`, `fcm_tokens`, `audit_log`, `error_log`, `email_verify_tokens`, `password_reset_tokens`, `cell_location_cache`, and supporting tables.
- **PostgreSQL adapter** (`database_postgres.py`) exists with a documented migration runbook — measured at 75,161 inserts/s (~40× the per-commit SQLite ceiling). The runbook's decision gate says **stay on SQLite until ~2,000–3,000 active devices** (§15).

### 4.4 Key Data Flows

**Tracking flow:** device GPS/network fix → Android Kalman filter → `POST /api/device/location` → auth → anti-spoofing validation → Sentinel scoring → rate limit → (batched) write → Redis publish → dashboard updates live.

**Command flow:** dashboard issues command → `commands` row (pending) → device poll or SMS relay → device executes → ack (executed/failed) → WebSocket `command_ack` → dashboard row flips instantly.

**Theft flow:** Sentinel confirms a streak → `operating_mode=stolen` → evidence case created → high-priority capture commands queued → alerts fired (locked emergency channels) → dashboard switches to stolen view.

---

## 5. Implementation — Android Application (Kotlin)

### 5.1 Module Inventory (main components)

| Module | Responsibility |
|---|---|
| `TrackingService` | The heartbeat of the app: location loop (3 s interval), heartbeat, command poll loop, device-key generation, registration |
| `PersistenceService` | Second independent service for redundancy against OEM kills |
| `LocationFilter` | **Kalman filter** fusing GPS + network fixes; physics-based outlier gating; JVM-unit-tested |
| `MediaCaptureService` | Dedicated `camera\|microphone` FGS — photo / front-photo / audio from a locked screen (Android 14/15 legal path) |
| `CaptureRouting` | Pure JVM module encoding the "honesty contract": armed→capture, unarmed→re-arm prompt, unknown→refuse |
| `SmsCommandReceiver` + `SmsCommand` | Intercepts the `MAGNET <code> CMD <id> <command>` SMS; verifies sender + per-device pairing code |
| `OfflineOutbox` | Store-and-forward: queued pings/acks uploaded on reconnect |
| `UninstallProtection` | `setUninstallBlocked(true)` when device/profile owner |
| `AdminReceiver` | Device Admin; instant theft signal on deactivation |
| `BootReceiver` / `WatchdogReceiver` / `HealthCheckWorker` | Start persistence, AlarmManager self-healing, WorkManager health |
| `EnvironmentReceiver` | Restarts services on power/connectivity/time/unlock events — the exact moments OEM battery killers release paused apps |
| `OEMUtils` | Huawei, Xiaomi, Oppo, Vivo, **Transsion (Tecno/Infinix/Itel)** detection + auto-start guidance |
| `DeviceLinker` / `PairingCode` | Claims the device to the signed-in account; SHA-256 pairing code for SMS relay |
| `RecentCommandTracker` | **At-most-once execution**: re-delivered commands are re-acked, never re-executed |
| `MagneetarMessagingService` | FCM push (HTTP v1) via firebase-admin |
| `SignUpActivity` / `SignInActivity` / `OnboardingActivity` / `PermissionsActivity` / `HomeActivity` | UX flows; 2FA sign-in step; permission disclosure dialogs |

### 5.2 Tracking Loop & Kalman Fusion

Raw Android fixes are noisy: GPS drifts, network fixes jump hundreds of meters, and the fused provider occasionally emits NaN. `LocationFilter.kt` implements a **constant-velocity Kalman filter** in the local east-north frame:

- **Predict** at each new fix using the learned velocity, with process noise tuned for human motion;
- **Update** with the measurement when plausible — outliers are gated against physics (an alternating-sign velocity flicker is rejected as GPS jitter);
- **Coast** on prediction when the fix is non-finite or implausible.

The output is a smoothed position, velocity, and accuracy that the app uploads as telemetry. The filter is pure Kotlin with no Android dependencies — it is unit-tested on the JVM (`LocationFilterTest`).

### 5.3 The Armed-Capture Pattern (Android 14/15)

Android 14+ forbids *starting* a camera/mic foreground service from the background. Magneetar follows the Prey/Cerberus model:

1. **Arm from a foreground context** — the app opens or the user taps a notification action → `MediaCaptureService` starts with `FOREGROUND_SERVICE_TYPE_CAMERA|MICROPHONE` and posts an honest "Theft protection armed" notification.
2. **Command the already-running service** — a remote `capture_photo` / `capture_photo_front` / `capture_audio` command is routed with a plain `startService()` to the armed service (legal — no background *start*).
3. **OEM kill / reboot / force-stop** — `BootReceiver`/`TrackingService` posts a **"Tap to re-arm"** notification (a documented background-start exemption). Until tapped, capture is *honestly* unavailable.
4. **Honest acks** — unarmed capture commands ack `failed` (never a phantom `executed`), and the device reports `capture_armed` on every ping so the dashboard shows **Armed / Unarmed / Unknown** — not what the owner *wishes* were true.

### 5.4 Offline SMS Command Relay

A stolen phone usually has no data plan — but it always receives SMS. Magneetar's offline relay:

- Server texts `MAGNET <pairing-code> CMD <id> <command>` to the device's SIM number when it is offline;
- The app intercepts it, verifies **both** the per-device SHA-256 pairing code **and** the sender allowlist (only the server's Twilio number / Termii alphanumeric), then executes through the exact same `handleCommand` path as a polled command;
- Location returns as a coarse **cell-tower fingerprint** (MCC/MNC/TAC/CID captured with zero internet, resolved server-side with graceful degradation) plus the precise GPS fix uploaded via the offline outbox the moment connectivity returns;
- Safety: opt-in per device, E.164 validated, 5 SMS/min cap, only relayed when actually offline;
- The reply channel (`MT-ACK`) is ingested by a Twilio-signature-verified `/api/sms/inbound` webhook.

### 5.5 Uninstall Resistance

Layered to the platform maximum for a non-root app (documented honestly in `docs/security.md`):

- **Layer 1 — Active Device Admin:** Android refuses uninstall until deactivated; deactivation is gated by a system dialog with a plain-language warning; if it still happens, `onDisabled` fires an immediate heartbeat with `device_admin_active=false` → Sentinel score jumps ≥ 40 instantly (admin-removal is a weighted theft signal).
- **Layer 2 — Device Owner + `setUninstallBlocked(true)`:** Settings "Uninstall" is disabled entirely and `adb uninstall` fails; re-asserted on every launch/activation/service start. Provisioned once via `scripts/enable-uninstall-protection.sh` (`dpm set-device-owner`).

### 5.6 Reliability on the African Market

`EnvironmentReceiver` restarts tracking on power-connected/disconnected, battery-low, connectivity, time-set, timezone, and unlock events; the AlarmManager watchdog and WorkManager health check provide three independent restart paths; `OEMUtils` detects and guides users through Transsion/MIUI/ColorOS/EMUI auto-start settings. Location requests pass the main looper (fixing the real `Can't create handler inside thread` crash observed on a physical Galaxy A03s).

### 5.7 Release Engineering

- `minSdk 24`, `compileSdk/targetSdk 36` (Android 16 — the Aug 31, 2026 Play deadline, already met), JDK 21, AGP 8.10.1, Kotlin 2.0.21.
- **Two distribution flavors**: `sideload` (full SMS permissions for the offline relay) and `play` (SMS permissions stripped via a merged manifest overlay — the Play policy requires default-SMS-handler status for those permissions). Verified: the play manifest has **zero** SMS permission elements.
- Cleartext blocked by default in release; debug-only localhost override; ProGuard shrinking; release signing from env-provided keystore credentials.
- Version read from the repo `VERSION` file; the APK is staged into `server/static/apk/` (bind-mounted into the live server) and the dashboard's download page.

---

## 6. Implementation — Backend Server (Python / FastAPI)

### 6.1 Overview

Uvicorn (4 workers) running FastAPI with modular route files: `routes/devices.py`, `routes/dashboard.py`, `routes/guardian.py`. ~40 configuration knobs via `MT_*` environment variables validated at startup (`validate-startup.sh`). Middleware provides request timeouts (504 on hang), slow-request logging, `X-Process-Time-Ms` headers, and audit logging.

### 6.2 Sentinel Engine — Automatic Theft Detection

The core innovation of the backend. Every telemetry ping is scored by **weighted anomaly signals**:

| Signal | Weight | Meaning |
|---|---|---|
| Factory reset initiated | 50 | Highest-confidence theft act |
| Device admin deactivated | 40 | Thief removing protection |
| SIM changed | 35 | SIM pulled to evade tracking |
| Velocity at vehicle speed | 25 | Rapidly leaving the area |
| Location services disabled | 20 | Thief disabling GPS |
| Failed unlock attempts | 20 | Thief trying to break in |
| Airplane mode on | 15 | Deliberate connectivity cut |
| New Google account added | 15 | Device re-registration attempt |
| Outside all known locations | 15 | Device far from safe zones |
| Running speed | 10 | Suspicious movement |
| Battery critical / unknown network / long queue / unusual 2–5 AM activity | 10 | Contextual aggravators |
| Impossible jump (spoof/teleport) | 15 | GPS spoofing or theft at vehicle speed |

**Levels:** SAFE < 30 → ELEVATED ≥ 30 → HIGH ≥ 60 → CRITICAL ≥ 80.

**False-positive prevention (the confirmation gate):** a single high ping cannot flip a device to `stolen`. The device must hold a **consecutive streak of HIGH-level scores** (`ANOMALY_CONFIRMATION_COUNT`); scores are capped at 79 (`CAP_AFTER_CONFIRMATION`) while the gate holds. A real bug was found and fixed here: the gate originally compared capped scores against the 80 theft threshold, making theft mode **mathematically unreachable** for any device with history — observed live as pings stuck at 79. The gate now counts capped-but-elevated scores against the 60 HIGH bar.

**Theft activation** (`auto_activate_theft_mode`): sets `operating_mode=stolen`, creates an evidence case (`MGT-YYYY-XXXXX`), queues high-priority capture commands (front photo, audio, location burst), fires alerts, and logs the audit trail.

**Anti-spoofing** (`validate_report`): rejects timestamps > 5 min from server time, impossible speeds (> 300 km/h), impossible battery increases without charging, and invalid accuracy values.

**Geofencing**: haversine-based safe zones with entered/exited edge detection.

### 6.3 Alert Engine

Multi-channel delivery (SMS via Twilio/Termii, WhatsApp via Twilio, push via FCM HTTP v1, email via SendGrid) with:

- **Retry + jitter**: 1 automatic retry per channel with 1–2 s random backoff;
- **Per-channel circuit breaker**: 5 consecutive failures open the breaker (channel skipped, no useless timeouts); success resets it;
- **Per-device preferences**: channel toggles, alert-type toggles, and quiet hours — stored on the device row, validated server-side, with **fail-open** semantics (a DB hiccup degrades to global defaults so an emergency is never silenced);
- **Locked emergencies**: theft, SIM change, and factory-reset alerts **always** deliver — they bypass both the enabled-types and quiet-hours gates;
- **Deduplication**: an `alerts` table dedup row prevents double-firing across the 60 s monitor loop.

### 6.4 Offline Monitor & Scheduled Loops

`offline_monitor.py` finds owned, non-stolen devices silent past `OFFLINE_ALERT_MINUTES` (with a floor) and fires theft alerts — dedup-rows written *after* send. Archive sweeps (`archive_monitor.py`, `unarchive_device` on fresh activity) and retention purges run on 60 s loops. Because there are 4 workers, all side-effect loops run under a **Redis leader lock** (`SETNX` + Lua compare-and-delete) so exactly one worker runs them — without it, the first offline device would have been **quadruple-SMS'd**. Without Redis the lock degrades to a no-op (single-worker semantics).

### 6.5 Realtime: Redis Bus + WebSocket Manager

- Each worker holds its own WebSocket registry; broadcasts **publish to a shared Redis `magneetar:ws` channel** and every worker's subscriber delivers to its local connections — **exactly-once** cross-worker fan-out. Falls back to direct local delivery without Redis (the dashboard's 3 s polling remains the safety net).
- A subtle production bug was found and fixed here: `pubsub.listen()` blocks on a socket read, and the shared client's 2 s socket timeout made an idle channel drop the subscriber every 2 s (a reconnect storm). The long-lived listener now uses a **dedicated no-read-timeout connection**.
- Connection cap 250/worker (~1,000 concurrent dashboards across 4 workers); oldest-connection eviction; 30 s heartbeat ping with silent pruning of half-open connections; graceful shutdown broadcasts `{reconnect: true}`.

### 6.6 Performance Engineering (measured — see §11)

- **In-memory telemetry rate limiting** (`memory_rate_limit.py`): sliding-window limiter in a thread — the four hot-path checks (2 s location spacing, 10/min heartbeats, 5/min media, 30/min command poll) now cost **zero DB writes** (was 4 rate-limit writes + commit per ping). Security-sensitive limits (login, claim, step-up, APK ticket) stay DB-backed.
- **SQLite write queue** (`write_queue.py`, opt-in `MT_WRITE_BATCH_MS`): one dedicated writer connection per worker accumulates location INSERT + device UPDATE and commits in a single transaction per ~250 ms window. Request handlers become WAL readers — the single-writer lock is out of the request path entirely. Safety fallback: if the writer isn't running, `enqueue_write` returns false and the handler falls back to the synchronous path — telemetry is never silently dropped.

### 6.7 Authentication Matrix

| Method | Used by | Scope |
|---|---|---|
| JWT access/refresh | Device registration session | Device endpoints |
| `x-device-key` | Android (256-bit per-device secret, server stores only SHA-256) | Device endpoints |
| `x-api-key` (device key) | Legacy/shared path | Device endpoints only |
| Master `MT_API_KEY` | Dashboard login + step-up + admin | Dashboard admin (never in APK) |
| User JWT | App account + dashboard | Owner-scoped endpoints |
| TOTP 2FA | All user logins (enabled accounts) | Challenge → session |

A real **security review found and fixed** a master-key exposure: the old single shared key was extractable from the public APK with a plain `strings` scan and could mint dashboard-admin tokens — anyone who sideloaded the app could view every user's locations and issue WIPE to any device. The key was split into master / device / legacy-grace keys, the master was rotated, and the APK now embeds only the low-privilege device key. 14 regression tests lock the separation.

---

## 7. Implementation — Web Dashboard (Next.js / TypeScript)

### 7.1 Pages & Experiences

| Page | Purpose |
|---|---|
| Landing (`/`) | Premium SaaS marketing: twin-pillar positioning, 12-feature grid, "Built for Africa" (NBS-sourced stats), "Our story" (OAU provenance), direct APK download |
| Login / Signup | Cinematic two-panel auth with aurora ambience, live telemetry mockup, **TOTP 2FA step**, Account/API-Key toggle |
| Forgot / Reset password, Verify email | Full account-security flows |
| Dashboard (`/dashboard`) | The tactical command center |
| Download / Terms / Privacy | Trust pages |

### 7.2 The Command Center

- **Device panel** — ownership-scoped device list with Sentinel score chips, last-known coordinates (copy button), battery, `capture_armed` state.
- **Live map** (Leaflet + MapTiler dark tiles, Carto fallback) — auto-zoom to street level (z17), offline "last seen" banner, seekable **Trail Replay** timeline with stable animation, OSRM route + Google Maps/Waze fallback.
- **Command panel** — tone-driven glassy tiles: ping, capture photo/front/audio, lock, wipe (`CONFIRMED_WIPE`), siren, location burst; every send surfaces success/error feedback.
- **Sentinel panel** — threat score visualization; **Guardian panel** — sightings and recovery requests; **Evidence panel / Media Gallery** — photo/audio browser with **step-up-password-gated deletion**; **Error panel** — admin-only server error viewer.
- **Real-time**: WebSocket with automatic reconnection; the `command_ack` handler flips command rows instantly (an empty handler once made successful commands look PENDING for 10 s — fixed and regression-tested).

### 7.3 Operator Location Accuracy (the "varies with browser" fix)

The operator's own "YOU" marker, distance readout, and GET ROUTE previously used raw `navigator.geolocation` — GPS on phones (3–15 m) but **IP/Wi-Fi-derived on desktop browsers** (1–5 km+ error), with `enableHighAccuracy` a no-op on desktop. The map now:

- renders an **accuracy circle** scaled to `coords.accuracy`;
- **gates distance/route features** on an accuracy threshold with an explicit reason when too coarse;
- shows an **"IP-derived fix — use a phone browser"** banner;
- surfaces a **permission-denied banner** instead of failing silently.

All markers verified present in the served production bundle.

### 7.4 State & Store

A typed Zustand store (`useStore`) with `applyCommandAck` in-place merging, device/owner scoping, and WebSocket state preservation across reconnects; `tsc --noEmit` clean; 173 Jest tests across 20 suites.

---

## 8. Security Architecture

### 8.1 Threat Model

| Threat | Mitigation |
|---|---|
| APK reverse engineering → credential extraction | Master key never in APK; per-device runtime keys; device key hash-only storage |
| DB breach → credential disclosure | Passwords bcrypt/PBKDF2; device keys stored as SHA-256; encryption key env-separated |
| Stolen dashboard session | TOTP 2FA; short-lived JWTs with revocation; step-up password for destructive actions |
| Evidence tampering | SHA-256 chain of custody; step-up-gated deletion; audit log |
| SMS-command spoofing | Sender allowlist + SHA-256 pairing code + 24 h brute-force cooldown |
| Telemetry spoofing | Timestamp/speed/battery/accuracy validation |
| Account enumeration | Identical responses for unknown emails on password reset |
| Resource abuse | Per-endpoint rate limits (DB-backed for security paths) |
| Uninstall / tamper | Device Admin layer + `setUninstallBlocked` layer |

### 8.2 Defense-in-Depth Stack

1. **Transport**: TLS only; cleartext blocked in release builds; Cloudflare Tunnel (no open ports).
2. **Authentication**: multi-method matrix (§6.7) with strict token-type claims (a 2FA challenge token can never be spent as a session — a found-and-fixed flaw).
3. **Authorization**: ownership scoping on every dashboard endpoint (403 for non-owners); admin-only error endpoints.
4. **Integrity**: evidence hashes, audit log, `hmac.compare_digest` for master-key checks.
5. **Secrets**: `generate-env.sh` produces secure secrets; keystore never committed; CI consumes GitHub secrets.
6. **Play compliance**: permission declarations, Data Safety form mapping, prominent disclosure for background location, distribution flavor that strips SMS permissions for the Play build.

### 8.3 Account Security Suite

TOTP 2FA (setup → QR → enable with replay-safe live code → disable with password), per-token replay guard, 5-bad-code lockout (10-min cooldown), single-use 30-min password-reset tokens, anti-enumeration forgot-password, email verification, and rate-limited verification — 24 tests in `test_user_security.py`, plus a **live 2FA lifecycle smoke test on production** (self-cleaning account) that passed end-to-end.

---

## 9. Testing & Quality Assurance

### 9.1 Test Inventory (current, all green)

| Suite | Count | Covers |
|---|---|---|
| Server (pytest) | **400** | API, auth, Sentinel, e2e, offline monitor, reliability (WS/auth matrix), multi-user, guardian, heartbeat/theft, alert settings, media delete, user security, media store, device-key separation, write queue |
| Dashboard (Jest) | **173** | 20 suites incl. landing, login 2FA, settings security, media gallery step-up, command panel, WebSocket `command_ack`, utils |
| Android (JVM) | 25+ | SmsCommand, RecentCommandTracker, PairingCode, LocationFilter (Kalman), CaptureRouting |
| **Total** | **573+** | All green; `tsc --noEmit` clean; flake8/black/isort/eslint/shellcheck clean |

### 9.2 Quality Gates

- **pre-commit hooks**: black, isort, flake8 (full `.flake8` selection), eslint, tsc, shellcheck on every commit;
- **CI (GitHub Actions)**: backend tests, dashboard tests + typecheck, Docker build, APK build, backup smoke test, alert credential check — all green on every recent commit (one historical failure was a GitHub infrastructure outage, confirmed self-healed);
- **`make validate`** reproduces the full CI gate locally.

### 9.3 Reliability & Recovery Tests

- `scripts/reliability-test.sh` — integration failure-scenario suite against a live instance;
- `scripts/recovery-drill.sh` — **12/12 PASS** against a throwaway instance (full restore + verify);
- `scripts/test-backup-smoke.sh` — backup → restore round-trip **byte-identical** for DB + media.

---

## 10. Performance Engineering (Measured, Not Estimated)

All figures below were produced by load-testing a **production-equivalent local rig**: 4 uvicorn workers, real Redis, scratch SQLite, on the same 16-core host class as production.

### 10.1 Moderate Fleet (300 devices, ~100 pings/s, 60 s)

| Configuration | Success | p50 | p95 | p99 |
|---|---|---|---|---|
| Baseline (sync commits, before batching) | 100% | ~30 ms | **53 ms** | **91 ms** |
| Batched writes (250 ms) | 100% | — | — | **50 ms** |

### 10.2 Heavy Fleet (2,000 devices, ~1,000 pings/s requested)

| Finding | Value |
|---|---|
| Sync-commit ceiling | **~370–400 pings/s sustained**, p50 degrades to ~3 s (requests queue on SQLite's single-writer lock) |
| Bottleneck after batching | **CPU**, not writes — server sat at ~304% CPU (of 400%), 0 slow-request logs, with an async client proving the server (not the client) is the ceiling |
| Raw insert ceilings | SQLite per-commit **~1,900/s**; SQLite batched **~705,000/s**; PostgreSQL **75,161/s** (~40× per-commit SQLite) |

### 10.3 Realtime Bus (verified against real Redis)

4 workers → **4 subscribers on `magneetar:ws`**, messages delivered exactly-once, subscriber survives a 5 s idle channel (the pre-fix storm is gone), WebSocket handshake verified **through the public Cloudflare tunnel** (anonymous connections correctly rejected with close code 4408).

### 10.4 Honest Capacity Statement

On today's single 16-core host with 4 workers:

- **~2,000–3,000 actively-reporting devices** (at ~20 pings/min) with degraded tail latency above the ceiling;
- **~1,000 concurrent live dashboards**;
- comfortable operating point: **~1,500 devices**;
- current production load: **1 device ≈ 0.05% of capacity**.

Beyond the ceiling, the documented growth path is the Postgres adapter + more workers/cores — **not a rewrite**.

---

## 11. Deployment & Operations

### 11.1 Production Topology

- **Docker Compose** on Ubuntu: `server` (FastAPI/uvicorn × 4, port 8002), `dashboard` (Next.js via Nginx, port 3000), `redis` (bus + leader lock), SQLite on a persisted volume.
- **Cloudflare Tunnel** exposes `api.magneetar.me` and `app.magneetar.me` with **no open inbound ports**.
- **Health-gated deploys**: rebuild → recreate → poll `/health` (uptime gate) → verify public endpoints.
- **Live verification after every deploy**: `/health` (online · version · database), served bundle markers, WS handshake, Redis subscribers, write-queue startup lines.

### 11.2 Backups (3-2-1)

- `backup-db.sh` — live SQLite online-backup snapshot + gzipped **media evidence** tarball, integrity-checked, rotation, listing, **optional off-site rclone push** (`MT_RCLONE_REMOTE`, e.g. Backblaze B2); PATH shim exposes user-local rclone to cron;
- **Daily cron at 3:00 AM** (installed idempotently by `install-cron.sh`) plus a health monitor;
- Restore proven by round-trip smoke test and the 12/12 recovery drill.

### 11.3 Observability & Failure Modes

- `/health` with DB connectivity check (`degraded` state);
- Startup validation (`validate-startup.sh`): env completeness, DB writability, ports, dependencies, disk space;
- Request timeouts (504), slow-request logs, `error_log` table with dashboard viewer, optional Sentry;
- Alert circuit breakers, WS eviction/pruning, graceful shutdown with reconnect broadcast.

### 11.4 Release Process

`VERSION` bump → `build-release.sh` (signed APK + Play AAB + staging into `server/static/apk/` and `dashboard/public/apk/`) → compose `APP_VERSION` build arg → rebuild → health-gated deploy → CHANGELOG + commit + push. The version is a **build arg baked to `/VERSION`** — a compose edit alone does not change it, a lesson learned from the stale-download incident (§13).

---

## 12. Engineering Process & Project Management

- **125+ commits** following conventional-commit style (feat / fix / docs / ci / chore / security / perf), each gated by pre-commit and CI.
- **Documentation-driven**: SRS → architecture → ADRs → implementation → verification → deployment — every significant decision recorded before/with implementation.
- **Milestones**: M1 core tracking/command loop → M2 multi-user & ownership (P0 complete) → M3 Guardian Network (P0 complete) → M4 hardening, security, and real-world readiness.
- **Changelog discipline**: every release and behavior change recorded in `CHANGELOG.md` with root-cause write-ups.
- **Real-world readiness reviews**: full-stack audits (`docs/readiness-review.md`), Play Store submission walkthrough (`docs/play-store-checklist.md`), Postgres migration runbook, secret-rotation runbook with executable retirement checklist, CI-secrets inventory.

---

## 13. Challenges & Lessons Learned (Root-Cause Summaries)

| Challenge | Root cause | Fix (verified) |
|---|---|---|
| "I can't see any of the changes" | Production served a **stale APK** (built before the new features) while API/dashboard were current | Rebuild + verify checksums live; bind-mount APKs; version-as-build-arg discipline |
| Play Protect blocks every sideload | Legitimate permission profile (SMS + Device Admin + background location) on a new signing key | Consumer mitigation guide + play flavor (SMS stripped) + strategic Play submission |
| Stuck-PENDING + command replay loop | Lost ack + server re-delivery + no at-most-once guard; empty `command_ack` WS handler | `RecentCommandTracker` idempotent re-ack; outbox flush before poll; instant WS status update |
| Sentinel theft mode unreachable | Confirmation gate compared capped (79) scores against the 80 threshold | Gate counts capped scores against the 60 HIGH bar; 3 regressions |
| Master key in APK | Single shared key baked into APK, extractable by `strings` | Master/device/legacy key split + rotation + 14 regression tests |
| Browser-location variance | Desktop browsers geolocate by IP/Wi-Fi (km-scale) | Accuracy circles, gating, IP-derived banner, permission-denied UX |
| Redis reconnect storm | Shared client's 2 s socket timeout killed idle pubsub listeners | Dedicated no-timeout listener connection |
| Quadruple-SMS risk | 4 workers × 60 s side-effect loops | Redis leader lock (SETNX + Lua) |
| SQLite write ceiling ~400 pings/s | Single-writer lock + per-ping commit | Batched write queue; in-memory rate limiter; documented PG path |
| Fake "armed capture" | Pre-14 capture design silently failed on Android 14/15 | Armed-capture pattern with honest acks + `capture_armed` state |

---

## 14. Limitations & Honest Gaps

1. **Distribution**: Play Protect deterministically blocks sideloads; the Play submission (AAB built, walkthrough written, secrets inventoried) is the #1 unblocked item for real-world adoption.
2. **Single point of failure**: one VPS, SQLite, off-site backups configured-but-credential-pending. Fine for a pilot; not for trust-critical scale.
3. **CI signing secrets**: `KEYSTORE_*`, `DEVICE_KEY` etc. are inventoried and ready to paste but not yet set in GitHub → CI can't yet emit signed release builds.
4. **Per-ping CPU cost** bounds the fleet ceiling (~2–3k devices) — mitigated by batching, then by Postgres + cores.
5. **External dependencies**: Twilio/Termii, FCM, map tiles, and **device-side GPS quality** are honest limits no code fixes.
6. **Android platform ceilings**: no API for a custom uninstall password; background capture requires the armed-FGS pattern; Play's SMS policy forces a permission-stripped play flavor.
7. **Postgres adapter incomplete**: 6 of 20 tables missing — documented as a gap table with a migration drill that proved data moves losslessly (20/20 tables, 0 parity failures).

---

## 15. Future Work

| Priority | Item |
|---|---|
| P0 | Play Store submission; CI secrets; off-site backup credentials (Backblaze B2) |
| P1 | Complete Postgres schema parity + switchover runbook execution at ~2k devices; iOS companion app |
| P1 | Role-based access (admin/viewer/device-only); device sharing between accounts |
| P2 | BLE beacon tags + embedded hardware; ML-based anomaly detection; analytics (crash-free rate, command success rate) |
| P2 | End-to-end encryption of selected evidence; device attestation |

---

## 16. Conclusion

Magneetar was designed, built, tested, deployed, and measured as a **complete system** — not a demo. It delivers the full anti-theft loop: continuous Kalman-fused tracking, honest theft detection with false-positive prevention, remote commands that work even with zero internet, locked-screen evidence capture, uninstall resistance, a real-time command center, multi-user ownership, TOTP-secured accounts, and a community Guardian Network. It is backed by 573+ automated tests, live-verified production deploys, and measured load benchmarks that define its honest engineering ceiling (~2,000–3,000 devices on one 16-core host) and its documented growth path.

The honest verdict: Magneetar is **real-world-ready for a controlled pilot** — dozens to hundreds of users on its own devices — and the remaining gaps are **operational, not technical**: Play Store distribution, CI signing secrets, and off-site backup credentials. Every one of those is a checklist item, not a rewrite. As a platform, Magneetar stands as the complete design-and-implementation story this report set out to document: from a problem statement about 25 million stolen phones, to a running system that can hear a thief's SIM change, fire a siren through the cell network, and hand a police officer a cryptographically chained evidence file.

---

## 17. References

1. Magneetar SRS — `docs/requirements/SRS.md` (MAG-SRS-001)
2. Magneetar Architecture — `docs/architecture.md`
3. Architecture Decision Records — `docs/adr/`
4. Security Notes: Uninstall Protection — `docs/security.md`
5. Deployment & Installation — `docs/deployment.md`, `docs/installation.md`, `docs/activation.md`
6. Play Store Submission Checklist — `docs/play-store-checklist.md`
7. Postgres Migration Runbook — `docs/postgres-migration.md`
8. Secret Rotation Runbook — `docs/secret-rotation.md`
9. Project Status Report — `docs/PROJECT_STATUS.md`
10. Changelog — `CHANGELOG.md`
11. National Bureau of Statistics — *Crime Experience & Security Perception Survey 2024* (as cited on the landing page)
12. Android Documentation — Foreground services, Device Admin / DevicePolicyManager, Play console policies (API 36 deadline, SMS policy, Data Safety, AAB requirement)
13. Google Play Console policy research (2026-08-07) recorded in `docs/play-store-checklist.md`
14. OWASP Application Security Verification Standard (ASVS)

---

## Appendix A — Building Magneetar from Scratch

### A.1 Prerequisites

- Ubuntu 22.04+/Debian host, **Python 3.12+**, Docker & Docker Compose, Node.js 20+ (dashboard), JDK 21 (Android), an Android device (API 24+), a Cloudflare account (tunnel).

### A.2 Backend

```bash
git clone https://github.com/Oluwanifemi-engineer/magneetar.git
cd magneetar
make setup                      # venv + server deps + npm ci
make pre-commit-install         # quality-gate git hooks
bash scripts/generate-env.sh    # secure secrets into server/.env
# Edit server/.env — the four required keys:
#   MT_API_KEY (master, min 32 chars, NEVER in the APK)
#   MT_DEVICE_KEY (low-privilege device key, must differ from master)
#   MT_JWT_SECRET (min 64 chars)  ·  MT_ENCRYPTION_KEY (64 hex chars)
# Optional: MT_REDIS_URL, MT_TWILIO_*, MT_ALERT_*, MT_FIREBASE_KEY
make server                     # uvicorn --reload on :8000
```

### A.3 Dashboard

```bash
make dashboard                  # Next.js dev on :3000
# Optional map tiles: NEXT_PUBLIC_MAPTILER_KEY=<key>
```

### A.4 Android App

```bash
cd android-app
SERVER_URL=https://api.magneetar.me \
DEVICE_KEY=<the server's MT_DEVICE_KEY> \
./gradlew assembleRelease      # sideload flavor with full SMS relay
./gradlew bundlePlayRelease    # Play AAB (SMS permissions stripped)
```

### A.5 Production Deployment

```bash
bash scripts/validate-startup.sh    # pre-flight checks
bash scripts/deploy.sh              # compose build + health-gated up
bash scripts/backup-db.sh           # DB + media snapshot (and off-site if configured)
# Cloudflare Tunnel: cloudflared tunnel create/route/run per README;
#   api.magneetar.me → :8002, app.magneetar.me → :3000
```

### A.6 Verification

```bash
make test          # 400 backend + 173 dashboard tests
make validate      # full CI-equivalent gate (lint + typecheck + test + hooks)
bash scripts/reliability-test.sh --start
bash scripts/recovery-drill.sh
```

## Appendix B — Core API Reference

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | — | Health + DB + version |
| `POST /api/device/register` | API key (+ user token) | Register device, mint tokens, link owner |
| `POST /api/device/location` | device key / JWT | Telemetry ping (scored by Sentinel) |
| `POST /api/device/heartbeat` | device key / JWT | Heartbeat (+ `capture_armed` state) |
| `POST /api/device/media` | device key / JWT | Evidence upload |
| `POST /api/device/offline-queue` | device key / JWT | Batch offline pings |
| `POST /api/device/fcm-token` | any | Register push token |
| `POST /api/device/claim` | user JWT | Link an existing device to the account |
| `POST /api/device/location/simple` | device key | Lightweight location path |
| `GET /api/dashboard/devices` | dashboard | Owner-scoped device list |
| `POST /api/dashboard/command` | dashboard | Issue remote commands |
| `POST /api/dashboard/media/{id}/delete` | dashboard + password/API-key step-up | Evidence deletion |
| `POST /api/auth/login` · `/register` · `/user/login/2fa` · `/forgot-password` · `/reset-password` · `/verify-email` · `/2fa/*` | — | Account security suite |
| `POST /api/guardian/*` | user | Guardian opt-in / sightings / recovery |
| `POST /api/sms/inbound` | Twilio signature | Offline SMS relay acks |

Interactive docs: `/docs` (Swagger) and `/redoc` at the API root.

## Appendix C — Android Module Map

```
com.magneetar.app
├── TrackingService.kt        # location loop · heartbeat · command poll · device key
├── PersistenceService.kt     # redundancy service
├── MediaCaptureService.kt    # camera|mic FGS (armed capture)
├── CaptureRouting.kt         # armed/unarmed honesty contract (pure JVM)
├── LocationFilter.kt         # Kalman fusion (pure JVM, unit-tested)
├── SmsCommandReceiver.kt / SmsCommand.kt   # offline SMS relay
├── OfflineOutbox.kt          # store-and-forward
├── UninstallProtection.kt / AdminReceiver.kt
├── BootReceiver.kt / WatchdogReceiver.kt / HealthCheckWorker.kt / EnvironmentReceiver.kt
├── OEMUtils.kt               # Transsion/Xiaomi/Oppo/Vivo/Huawei
├── DeviceLinker.kt / PairingCode.kt
├── RecentCommandTracker.kt   # at-most-once execution
├── MagneetarMessagingService.kt  # FCM push
├── SignUp/SignIn/Onboarding/Permissions/HomeActivity.kt
└── MainActivity.kt
```
