# Changelog

All notable changes to Magneetar are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.0] — 2026-08-02

### Added

- **Uninstall protection (anti-tamper)**: Magneetar now defends itself against being removed from a stolen phone. Layer 1 — an **active Device Admin** makes Android refuse to uninstall the app until the admin is deactivated; deactivation is gated behind a system dialog carrying a plain-language `DISABLE_WARNING`, and if it still happens `AdminReceiver.onDisabled` fires an **immediate heartbeat** with `device_admin_active=false` so the dashboard's Sentinel score jumps to ≥40 (admin removal is a weighted theft signal) instead of waiting for the next scheduled heartbeat. Onboarding now routes through Device Admin by default — skipping requires an explicit informed acknowledgement, and `MainActivity` re-sends users to the permissions screen if admin protection is later removed without it. Layer 2 — the **hard block**: when the app runs as device/profile owner, `UninstallProtection` calls `setUninstallBlocked(true)` (Settings Uninstall disabled, `adb uninstall` fails), re-asserted on every launch, admin activation, and service start. New `scripts/enable-uninstall-protection.sh` provisions device-owner mode via `adb shell dpm set-device-owner`; new `docs/security.md` explains the two layers and the honest platform limitation (Android has no API for a custom uninstall password). The Home screen shows live protection status with an "Activate Device Admin" button when off.
- **Remote commands actually work end-to-end — camera/audio capture from a locked screen**: the missing piece was Android 14/15's foreground-service type rules. `TrackingService` is a `location`-only FGS, which **cannot** open the camera or microphone while backgrounded — capture silently threw and the dashboard was lied to. New `MediaCaptureService` is a dedicated short-lived `camera|microphone` FGS (Android explicitly permits starting one from the background while a location FGS is running), owns all photo / front-photo / audio capture via Camera2 + MediaRecorder, uploads the evidence, and **acks honestly** (`executed` only when media uploaded, `failed` otherwise — the server already validates both statuses). A shared `activeCaptureIds` set prevents the 10s command poll from spawning duplicate captures of a still-pending command, released in `finally` so a mid-capture service kill can't hang it. `lock`/`alarm` now ack `executed` only on genuine success; `wipe` still acks before wiping (the phone may factory-reset). Manifest adds `FOREGROUND_SERVICE_CAMERA`/`MICROPHONE` and the service declaration. Kotlin compiles clean (JDK 21).
- **Brand refresh v2 — bold solid M**: the logo/app-icon is now a **thick, rounded, solid white M with a down-dipping V** (Moniepoint-style) on the magenta gradient tile with a soft glow + hairline ring — replacing the previous thin "bent" stroke M. Applied to web `m-logo.svg`/`favicon.svg`/`logo.svg`, the login/signup inline marks, the Android **adaptive icon** foreground, all five legacy PNG mipmaps, and new magenta `logo_tile` tiles on the splash + onboarding screens.

## [1.2.0] — 2026-08-02

### Added

- **Media deletion with step-up password (security)**: evidence photos/audio can now be deleted from the Media Gallery, but **only after re-entering the account password** (user mode) or the master API key (admin mode) — a stolen dashboard session alone is never enough to destroy evidence. `POST /api/dashboard/media/{id}/delete` verifies the password server-side (bcrypt/PBKDF2 for users, constant-time `hmac.compare_digest` for the API key), is **rate-limited at 10 attempts/minute/actor** (`check_password_verify_rate_limit`), audit-logs every deletion, fixes up the owning evidence case's photo/audio counters, and enforces device ownership (403 for non-owners). Dashboard Media Gallery gained manage mode — multi-select, select-all, and a portaled password prompt with visible error feedback. 11 backend tests (`test_media_delete.py`) + 5 dashboard tests (`MediaGallery.test.tsx`).
- **Remote commands actually work end-to-end**: the dashboard's WIPE button now sends the required `params='CONFIRMED_WIPE'` wire param (the old button silently 400'd — the server demanded confirmation and the UI never sent it), the command grid gained FRONT-camera and location-BURST buttons, and every send now surfaces explicit success/error feedback instead of failing silently. The Android `TrackingService.handleCommand` is hardened: **every command is always acknowledged** (executed or failed) so nothing sticks PENDING forever, and the camera paths can no longer hang the whole command loop — a missing/crashed camera completes the deferred via `onError`/`onDisconnected` and the capture await is bounded by a 45s `withTimeout`. Kotlin compiles clean (JDK 21).
- **Trail Replay fixed ("Invalid Date" + twitchy animation)**: location rows carry `server_timestamp`/`device_timestamp` but no `timestamp` field — reading `loc.timestamp` directly produced `Invalid Date`. New `parseTimestamp()`/`locationTimestamp()` utilities normalize both the ISO-8601 and SQLite space-separated formats (Safari-safe) and fall back gracefully; the timeline now shows real timestamps and the path animation no longer rebuilds its polyline on every render (stable `useMemo` trail + shared index with the scrubber). New `utils.test.ts` regressions cover the parse/format paths.
- **Settings modal actually opens**: the modal was rendered inside the `<header>`, whose `backdrop-blur` (backdrop-filter) establishes a containing block for `fixed` descendants — the modal was clipped to the 56px header and invisible. It's now rendered through a portal into `document.body`. New `SettingsModal.test.tsx` verifies the portal + the two-step account-deletion guard.
- **Premium command buttons + aligned tabs**: command tiles are now tone-driven glassy gradient buttons (hairline highlight, colored glow, hover lift, loading spinner) instead of the flat cartoon look; the tab strip scrolls horizontally (`overflow-x-auto` + `no-scrollbar`) so all seven tabs are reachable in the narrow right panel instead of being clipped/hidden.
- **Brand refresh — magenta tile + white M**: the logo/app-icon is now a single capital M on the magenta gradient (the dashboard/login aurora colour) everywhere: web `m-logo.svg`/`favicon.svg`/`logo.svg`, the dashboard auth screen, the landing nav + footer, the Android **adaptive icon** (magenta `ic_launcher_background` gradient + white M foreground), and all five **legacy PNG mipmaps** regenerated at 48/72/96/144/192px (`scripts/gen-launcher-icons.py`, PIL).
- **Per-device alert preferences (channels, types, quiet hours)**: each device can now override the global alert defaults from the Device Panel — which channels fire (email/WhatsApp/SMS/push chips), which non-emergency alert types may alert (theft, SIM change, and factory-reset chips are locked: emergencies **always** deliver, bypassing both the enabled-types and quiet-hours gates), and quiet hours that suppress non-emergency alerts overnight (wraparound-aware, e.g. 22:00→07:00, evaluated in server-local time). Stored on the devices row (`alert_channels`/`enabled_types` as JSON text, `quiet_hours_start`/`end` as INTEGER hours; NULL = global defaults, an empty array clears back to defaults). `PATCH /api/dashboard/devices/{id}/alert-settings` validates channels/types against `alerts.ALL_CHANNELS`/`ALL_ALERT_TYPES` and hours 0-23; `AlertEngine.send_all` enforces the gates **fail-open** — a DB hiccup while loading prefs degrades to global defaults so an emergency is never silenced. The quiet-hours migration uses INTEGER column affinity (TEXT affinity would store `22` as the string `'22'`), and the device list coerces legacy string values to ints. 13 backend tests (`test_alert_settings.py`, incl. non-wrapping quiet-window boundaries, partial-pair normalization, bool-hour rejection, and a suppressed-alert dedup-row regression) + 6 dashboard tests (`DevicePanel.test.tsx`, incl. locked emergency chips). Backend suite: **230**, dashboard suite: **109**, grand total: **339**.
- **Dashboard operator fixes (live review round 2)**: stale commands auto-expire — unacknowledged commands are marked `expired` (grey, strikethrough) in history after their window (5 min for wipe/lock/alarm, 30 min otherwise) and the device poll excludes them via a `datetime()`-normalized expiry comparison that finally works across the DB's mixed ISO-8601 and SQLite timestamp formats; the map auto-zooms to street level (z17) when a device is selected, renders a "Last seen Xh ago · coords" banner for offline devices, and gained a video-scrubber **Trail Replay** timeline (seekable, timestamped) with a more prominent REPLAY TRAIL toggle; map tiles switch to **MapTiler `dark-matter`** when `NEXT_PUBLIC_MAPTILER_KEY` is set (far better Nigeria/Africa coverage — no more black-rectangle buildings) with the Carto dark fallback when no key is configured; sidebar device rows now show a **mini Sentinel score chip + bar**, last-known coordinates with a copy button, and battery level; **DELETE ACCOUNT moved out of the header** into a new Settings modal (Account + Danger Zone) so a stressed operator can't delete the account by accident; alert settings stay per-device under Location → Alert Settings (now referenced from the Settings modal).
- **Android survival for Nigerian brands**: `OEMUtils` now detects the **Transsion family (Tecno / Infinix / Itel — the dominant brands in Nigeria)** with HiOS/XOS auto-start guidance and app-settings deep link; new **`EnvironmentReceiver`** restarts the tracking services on power-connected/disconnected, battery-low, connectivity, time-set, timezone, and unlock events (the exact moments OEM battery killers release paused apps), registered in the manifest alongside the existing AlarmManager watchdog + WorkManager health check. Kotlin compile verified (JDK 21).
- **Landing page market positioning + conversion (per launch feedback)**: new **"Built for Africa"** section with NBS-sourced stats (25M+ phones stolen in Nigeria in one year, one stolen every ~1.2s, only 11.7% ever recovered — National Bureau of Statistics, Crime Experience & Security Perception Survey 2024) plus a "Magneetar's answer" trio (Nigerian-network alerts, OEM battery-killer survival, evidence that holds up); "How it works" steps rewritten to be Magneetar-specific ("Install & connect in minutes" → "Stay in sync, always" → "Theft detected — recover it"); prominent **Download APK** buttons in nav (desktop + mobile), hero, CTA, and footer — direct to `/apk/download`, no account required; **"Free plan available · No credit card required"** messaging under the hero and CTA actions; hero test stat corrected from a stale 173 to the current **267**; metadata + keywords retargeted for the Nigerian market ("phone theft Nigeria", "track stolen phone Nigeria"). Landing tests updated for the new copy — dashboard suite stays green.
- **Dual-pillar positioning — protection + connection**: Magneetar is now presented as **two equal value props** ("Protect what you own. Stay close to who you love."): hero headline/subhead, features grid (new **Family & Team Circles** and **Guardian Network** cards alongside the anti-theft arsenal), how-it-works steps, CTA, footer tagline, metadata/keywords ("find my family", "share location with family"), and README tagline all reframed; new **"Our story"** provenance section ("Built at OAU") tells the builder story with verified facts — OAU (est. 1962 as University of Ife, "Great Ife"), Nigeria's first Faculty of Technology (1970), SIWES pioneer, Africa's first MIT-collaboration iLab, CWUR 2026 #5 in Nigeria — with a deliberate **no-fabricated-numbers** footnote (real adoption stats come at campus launch); footer GitHub links fixed to the real repo (`Oluwanifemi-engineer/magneetar`, verified public). Messaging only — product features unchanged.
- **License MIT → Business Source License 1.1 (source-available)**: the repo stays public and readable (credibility/recruiting), but commercial use of the work as a competing anti-theft/tracking/monitoring service is restricted until the Change Date (**2030-08-01**), when it converts to Apache 2.0. New `LICENSE` (BSL 1.1 with parameters: Licensor Magneetar, Additional Use Grant, Change Date, Change License), README badge + License section, `package.json` `license: "BUSL-1.1"`, and dashboard footer all updated. (README's previously-broken `LICENSE` link is now real.)
- **Multi-user & device ownership (Milestone 2 P0)**: `POST /api/device/claim` links an existing device to a user account (by device key or id, 403 on cross-account claims); `POST /api/device/register` accepts a user bearer token and sets `owner_id` at registration; every dashboard endpoint (locations, commands, media, alerts, geofences, evidence, alias, recover, stats) is now scoped by ownership — non-owners get 403, admins see all, error-log endpoints are admin-only; WebSocket broadcasts are filtered per device owner via an in-memory `device→owner` cache that is hydrated from the DB on dashboard connect (survives restarts); per-user device limit (`MAX_DEVICES_PER_USER`) enforced at register-time new links and claim, with same-owner re-claims/re-registers kept idempotent; PostgreSQL stats query parameterized.
- **Android account linking**: `TrackingService` now sends the signed-in user's bearer token at device registration (with a graceful fallback to plain registration when linking is rejected, e.g. on account switch); new `DeviceLinker` posts `/api/device/claim` after sign-in/sign-up so an already-running device links immediately.
- **Multi-user backend tests**: 23 new tests in `server/tests/test_multi_user.py` (register-with-token linking, claim by key/id, ownership scoping across all device endpoints, device limits, idempotent re-claim). Backend suite total: **154**.
- **Guardian Network (Milestone 3 P0)**: `POST /api/guardian/opt-in` (blurred handle + radius), `GET /api/guardian/recovery/{id}` returns **blurred** nearby coordinates (privacy-preserving, ~0.1° jitter verified live), `POST /api/guardian/sighting` (rate-limited, evidence-linked), recovery requests launch from owner or the sentinel's `stolen` mode and close marking the device recovered. 23 tests in `test_guardian.py`.
- **Android phone-test fixes**: `build.gradle.kts` bakes the real `MT_API_KEY` from the env (the placeholder key caused 401s so the command loop never started); `TrackingService` passes `Looper.getMainLooper()` to both location requests (fixes the `Can't create handler inside thread` crash found on a physical Galaxy A03s).
- **Sentinel theft-unlock fix**: the false-positive confirmation gate counted scores against the 80 theft threshold, but capped scores are persisted as 79 — so once any cap applied, theft mode was **mathematically unreachable** (observed live: 8+ consecutive theft pings stuck at 79). The gate now counts scores against the elevated bar (60), so capped 79s contribute to the streak and a sustained theft pattern escalates to `stolen` (live-verified: `Score 100/100 · Mode stolen` + evidence case + capture commands queued). Magic numbers extracted to module constants `ELEVATED_BAR`/`HIGH_BAR`/`CAP_SCORE`/`CAP_AFTER_CONFIRMATION`; 3 new regression tests.
- **Premium auth experience**: rebuilt the landing page, login, and signup — animated aurora ambience, live command-center telemetry mockup (radar, route, ticker), social proof, cursor-tracking spotlight glass cards, sliding Account/API Key toggle, password visibility toggle, staggered entrance choreography, `prefers-reduced-motion` support, and new dashboard tests for all three pages. Dashboard suite total: **62** (9 suites). Grand total: **216**.
- **Backend suite totals (current)**: **193** backend (69 reliability, 36 multi-user, 23 guardian, 22 api, 17 sentinel, 15 auth, 11 e2e) + **74** dashboard (11 suites, `tsc --noEmit` clean) = **267** grand total.
- **Ghost-owner recovery fix**: devices whose `owner_id` points at a deleted/nonexistent account (e.g. after a DB restore) are now claimable — `claim_device` only 403s when the existing owner is a REAL account, and stale tokens from permanently deleted accounts get **401** (no more ghost links created via register *or* claim). Extracted `_user_exists()` helper; 6 new regression tests in `test_multi_user.py`. Live-verified: ghost claim returns 200 + owner set, real-owner 403 guard intact. This unblocks re-linking a phone after account data loss.
- **Android Play readiness**: compileSdk/targetSdk **34 → 35** (AGP 8.3.0 → 8.7.3, Gradle 8.6 → 8.12 — requires JDK 21, host default JDK 25 breaks Gradle 8.12); cleartext now **blocked by default** in release builds (`base-config cleartextTrafficPermitted=false` with localhost/127.0.0.1/10.0.2.2 exceptions, `usesCleartextTraffic="true"` removed) with a **debug-only** override (`src/debug/res/xml/network_security_config.xml`) preserving local http dev; both CI workflows (`ci.yml`, `build-apk.yml`) install `platforms;android-35 build-tools;35.0.0`. Verified: `aapt` reports targetSdk/compileSdk 35, release APK served byte-identical at `/apk/download`.
- **CI backup smoke test**: new `scripts/test-backup-smoke.sh` (seeds a temp SQLite DB, snapshots/restores via the same online-backup API `backup-db.sh` uses, verifies integrity + data) wired as a `test-backup` CI job with shellcheck coverage (shellcheck-py, same as the local gate).

- **Shellcheck gate**: pre-commit now runs `shellcheck` (shellcheck-py `v0.11.0.1`) against all `scripts/*.sh`, catching quoting/portability bugs at commit time.
- **WebSocket auth-path integration tests**: 8 live tests in `test_reliability.py` — valid `dashboard` and `access` tokens accepted (registration + ping/pong + deregistration); invalid token, wrong token type (`device`), **expired token**, **revoked jti**, **tampered signature**, and **missing `type` claim** all rejected with close code 4001. The repeated close-code assertion blocks were factored into a shared `_assert_closed_with_code()` helper.
- **Token revocation (REST)**: 2 tests — a revoked dashboard token gets **401** on `/api/dashboard/devices` (via `require_dashboard_auth`'s revocation check) while a valid token is allowed (200), proving revocation applies beyond the WebSocket path.
- **Dashboard typecheck gate**: pre-commit now runs `tsc --noEmit` on dashboard TS/TSX changes (local system hook) — the same type-safety gate CI already enforces via the `test-dashboard` job.

### Changed

- **`test_e2e.py` sys.modules cleanup** now also evicts `user_auth`, `evidence_pdf`, and `database_postgres` — all modules that bind `config`/`database`. Previously, the stale `user_auth` module (bound to an older `config`/`database` instance) caused "Invalid token" errors on user tokens and registration rate-limits landing in the wrong DB file when the full suite ran after `test_e2e`; the isolated run masked it.
- **`firebase-setup.sh` bash portability**: `TOKEN_ARGS` call sites now use the `"${arr[@]+...}"` expansion idiom, so the script no longer errors on an empty array under `set -u` when run with macOS's default bash 3.2.
- **`reliability-test.sh` pre-flight check**: when the API is unreachable in manual (non-`--start`) mode, the script now prints a clear "start the server first" message instead of a wall of cryptic per-check failures.

- **Makefile `test-all`** is now a single-source-of-truth alias of `make test` (`test-all: test`). After the `-k "not slow"` removal it had become byte-identical to `test-backend`; the alias keeps the two aggregate targets from drifting apart while preserving compatibility for existing docs/habits.
- **Shellcheck remediation across `scripts/`**: fixed all 16 findings — removed unused `PLACEHOLDER` variable, converted the unquoted `$TOKEN_FLAG` string to a properly-quoted `TOKEN_ARGS` array, replaced the `&&`/`||` short-circuit with an explicit `if/else`, grouped consecutive redirects, split `local` declaration from assignment, switched to `trap 'cleanup' EXIT`, and replaced `ls` piping with `find` for APK counting. Remaining `info`-level findings that are intentional (remote path expansion, `ls -lh` display, trap-indirect invocation, dynamic `source`) are suppressed with targeted line-level disables and justification comments.

### Removed

- **Dead scripts**: Removed 4 zero-referenced scripts from `scripts/` that were superseded or obsolete: `configure-sentry.sh` (Sentry skipped for cost), `install.sh` (legacy curl|bash installer, superseded by `make setup`), `setup-firebase.sh` (duplicate of the automated `firebase-setup.sh`), and `start.sh` (superseded by `deploy.sh` + docker-compose). Verified zero references across the repo before removal.

### Added

- **Device names instead of "Device"**: dashboard device lists now render `deviceDisplayName()` — owner alias → registered model → generic label — so un-renamed devices show their hardware (e.g. "Samsung SM-A037F") and multiple phones per account are distinguishable at a glance. The Android app now registers a friendlier default name (manufacturer + model) instead of the bare model code. New `utils.test.ts` covers the fallback (dashboard suite: **82** tests).
- **"Our story" copy reframed**: the OAU section no longer reads like OAU is uniquely theft-prone. It now frames phone theft as a reality on university campuses **across Nigeria** (OAU as the idea's birthplace, not the exception) and staying in touch with family as universal among students — per launch feedback.
- **Heartbeat/theft regression tests**: `server/tests/test_heartbeat_theft.py` (3 tests) — heartbeat with `device_admin_active=False` returns 200, advances `last_seen`, and does NOT activate stolen mode; `auto_activate_theft_mode()` is a no-op below `THEFT_SCORE_THRESHOLD` and activates at the threshold (evidence case + capture commands queued).

### Changed

- **`isoNow()` sends UTC**: the Android service's `device_timestamp` was local time **without an offset**, so devices in UTC+1 (Nigeria) produced reports an hour "in the future" — every location report failed the server's 5-minute anti-spoofing timestamp check. It now emits `...Z` (UTC).

### Fixed

- **Device "last seen" froze while the phone was alive (critical)**: `post_heartbeat` called `sentinel.auto_activate_theft_mode()` **before** committing the request's own writes — the nested sqlite connection blocked on the outer connection's uncommitted transaction and raised `database is locked` (observed repeatedly in production `error_log`), 500-ing the heartbeat and rolling back its `last_seen` update. The heartbeat now commits first; the admin-disabled signal (weight 40) is surfaced via an elevated `sentinel_score` instead of a sub-threshold stolen-mode call.
- **Android telemetry could fail silently — app "Connected" while the server heard nothing**: `post()`/`get()` returned the response body for ANY HTTP status, so a rejected request (401/500) was parsed as a valid response; once both access AND refresh tokens were dead it never re-registered (the phone sat alive for 17h with zero server contact). The client now treats only **2xx as success**, retries once after a token refresh, and **auto re-registers when auth is fully dead** — the dashboard's "last seen" recovers as soon as the phone next connects. `postRaw` returns `(code, body)` so registration can still distinguish a rejected account-link from a network failure.
- **`auto_activate_theft_mode()` accepted any score**: its docstring promises "score >= threshold", but a bare heartbeat passed `score=40` — below the 80 threshold. It now returns early below `THEFT_SCORE_THRESHOLD`, so only the location path's confirmation-gated score can escalate to stolen.
- **GitHub links pointed at a non-existent repo**: the landing footer and README clone URL referenced `github.com/magneetar/magneetar` (404 — the repo actually lives at `Oluwanifemi-engineer/magneetar`, verified public). Both now point at the real repo so visitors land on a live README instead of a GitHub "Not Found" page.

- **Dashboard stats read the wrong database**: `GET /api/dashboard/stats` was the ONLY endpoint that queried PostgreSQL (empty in the Docker stack) while every other endpoint reads the SQLite data plane (`/app/data/magneetar.db`) — the Overview showed **0 total / 0 active / 0 stolen** despite registered devices. The stats endpoint now always reads SQLite like the rest of the app, and active-device counts use `datetime()`-normalized timestamps (the raw string comparison was lexicographically broken: `'T'` sorts after `' '`, so ISO-8601 timestamps always compared as "newer" than SQLite's space-separated `datetime('now')`). 2 new regression tests.
- **Stale PENDING commands never expired — and could execute late**: `issue_command` stores `expires_at` as ISO-8601 (`...T20:34:00.123456+00:00`) but the device poll compared it against SQLite's space-separated `datetime('now')` — `'T' > ' '` meant an expired command always compared as "still in the future", so it stayed PENDING forever AND could be delivered on the next poll. Poll + history now compare `datetime(expires_at)` (SQLite normalizes both formats); the history endpoint marks past-window commands `expired`. 2 new regression tests; `purge_old_data` got the same `datetime()` normalization (its ISO-vs-space comparison silently deleted nothing).
- **Android "Open Dashboard" opened the API server root**: `HomeActivity.openDashboard()` was opening the raw `server_url` (`https://api.magneetar.me` — the API root, not the dashboard). It now derives the dashboard URL from the API host (`https://api.<host>` → `https://app.<host>/login`, preserving the original scheme so self-hosted `http://api.*` deployments still work); non-`api.*` self-hosted servers fall back to the server URL. Verified live: release APK rebuilt and served byte-identical at `/apk/download`, installed on the physical phone, `docs/TEST_PLAN.md` TC-4.5 updated.
- **SQLite data loss on every rebuild (critical)**: `MT_DB_PATH` was relative (`magneetar.db`), resolving against the container `WORKDIR=/app` — the DB lived on the container's **ephemeral layer**, so every `docker compose up -d server` silently wiped all accounts, devices, and telemetry (observed live: the phone's registered device and user account vanished after a rebuild while `/app/data/magneetar.db` sat unused). `docker-compose.yml` now sets `MT_DB_PATH=/app/data/magneetar.db` on the persisted `magneetar-data` volume; verified: a marker account survives a container restart.
- **`backup-db.sh` backed up the wrong database**: it ran `pg_dump` against the Postgres container while the app's live data plane is SQLite (`database.py`/`get_db_context`), so every backup was empty of real data. Rewritten to snapshot `/app/data/magneetar.db` via the SQLite online backup API (`docker exec` + `docker cp` + gzip), with `--restore` gated by a `PRAGMA integrity_check` (aborts before touching the live DB if corrupt), a `trap`-based tmp cleanup, and matching `--list`/rotation globs. Backup → restore round-trip verified with data + integrity intact.
- **Hanging WebSocket tests**: The two `@pytest.mark.slow` tests in `test_reliability.py` used Starlette's sync `TestClient.websocket_connect()` against the persistent `/ws/dashboard` receive loop, which deadlocks (documented Starlette limitation) — `make test-all` hung forever. Rewritten as **live integration tests** using a real uvicorn server in a background thread + the `websockets` client (ping/pong roundtrip, capacity eviction with close code 1013). The `-k "not slow"` exclusion is now removed from CI, the Makefile, and docs — all backend tests (currently 131, incl. the live WebSocket integration tests) run everywhere.

---

## [1.1.0] — 2026-07-30

### Added

#### Reliability & Resilience
- **WebSocket connection limit**: Hard cap of 100 concurrent dashboard connections with oldest-connection eviction when at capacity. Prevents resource exhaustion from excessive or rogue clients.
- **WebSocket heartbeat & stale pruning**: Background task every 30s sends a JSON ping to all connections. Dead sockets (send failure) and unresponsive clients (no pong within 90s) are automatically pruned and logged.
- **Alert circuit breaker with auto-recovery**: After 5 consecutive failures, an alert channel (email/SMS/push/WhatsApp) skips sends for 5 minutes, then automatically allows a probe attempt. If the probe succeeds, the circuit closes. If it fails, the cooldown resets. No more permanently disabled channels.
- **Alert retry with jitter**: Every alert send gets 1 automatic retry with 1–2s random jitter before reporting failure.
- **Request timeout middleware**: Every HTTP request is bounded by a configurable timeout (default 30s). Hanging handlers return 504 Gateway Timeout instead of consuming resources indefinitely.
- **Health endpoint with DB check**: `/health` now runs `SELECT 1` against the database. Returns `status: "degraded"` with `database: false` if the database is unreachable.
- **Graceful WebSocket shutdown**: Before server stops, broadcasts a `{"type": "shutdown", "reconnect": true}` message to all dashboard clients with a 0.5s timeout.
- **Startup DB writability check**: The database is probed for write access during server initialization.
- **Database connection resilience**: SQLite connections use `PRAGMA busy_timeout=5000` to handle concurrent access without immediate failure.

#### Testing & Quality
- **21 reliability integration tests** (`server/tests/test_reliability.py`):
  - 3 health endpoint tests (DB status, degraded mode, no auth required)
  - 8 WebSocket limit tests (capacity, eviction, stale pruning, safe removal, real WS connections)
  - 10 alert engine tests (retry, circuit breaker, recovery, per-channel independence, send_all routing)
- **E2E reliability test script** (`scripts/reliability-test.sh`): Shell-based integration test covering health, DB simulation, concurrent requests, and dashboard reachability.
- **Startup validation script** (`scripts/validate-startup.sh`): Pre-flight check for required env vars, database writability, port availability, Python dependencies, and Node.js health.
- **`pytest.ini`** with registered `slow` marker and deprecation warning suppression.

#### Developer Experience
- **Makefile**: Centralized task runner (`make server`, `make test`, `make lint`, `make format`, etc.).
- **`.pre-commit-config.yaml`**: Automated code quality checks (trailing whitespace, black, isort, flake8, eslint).
- **CI workflow improvements**: Pre-commit hooks run in CI, slow WebSocket tests excluded via `-k "not slow"`, vulture dead-code analysis.

#### Dashboard
- **ErrorBoundary component**: Catches React rendering errors with a fallback UI.
- **Jest configuration** (`jest.config.ts`): Proper test setup with `jsdom` environment and mock paths.
- **ESLint configuration** (`.eslintrc.json`): Consistent code style enforcement.
- **WebSocket hook improvents**: Better reconnection logic and state management.
- **Store refactoring**: Cleaner Zustand store with proper TypeScript types.
- **UI refinements**: Updated login page, sidebar with collapse state, responsive header, improved globals.css.
- **New logo SVG**: Proper magneetar brand logo.

#### Android App
- **Full authentication flow**: Onboarding → Sign Up → Sign In → Permissions → Home activities.
- **Dual-service persistence layer**: `TrackingService` (location) + `PersistenceService` (data sync) for redundant background operation.
- **OEM compatibility**: Detection for Chinese OEMs (Huawei, Honor, Xiaomi, Oppo, Vivo) with delayed boot start and aggressive location strategies.
- **WakeLock management**: Huawei-whitelisted tag usage and periodic refresh to bypass PowerGenie.
- **Watchdog receiver**: AlarmManager-based self-healing for killed services.
- **Health check worker**: Periodic WorkManager task for service health verification.
- **Boot receiver improvements**: Handles `LOCKED_BOOT_COMPLETED`, `MY_PACKAGE_REPLACED`, delayed start on Chinese OEMs.
- **Sentry crash reporting** (optional): Configurable DSN for production error tracking.
- **Release signing configuration**: Production APK signing via environment variables.
- **ProGuard rules**: Code shrinking and obfuscation for release builds.
- **Network security config**: Development cleartext traffic support.
- **Device admin**: Remote lock/wipe capability.

### Changed

- **Server architecture**: Main application (main.py) slimmed down to middleware, lifespan, and route registration. All API endpoints extracted into modular route files under `server/routes/`.
- **WebSocket manager**: Extracted from `main.py` into `server/websocket_manager.py` to avoid circular imports.
- **Authentication**: Password hashing switched to bcrypt for production-grade security.
- **Evidence templates**: Added `location` field to all alert templates (was missing, causing rendering failures).
- **`_channel_failures` state**: Moved from class-level to instance-level in `AlertEngine` for test isolation.
- **Broadcast iteration**: Uses snapshot copy (`list(...)`) to prevent race conditions with concurrent heartbeat pruning.
- **Pong tracking**: New WebSocket connections initialize their pong timestamp at connection time for accurate stale detection.

### Fixed

- **Circuit breaker permanent disable**: Previously, after 5 consecutive failures a channel was permanently disabled until server restart. Now auto-recovers after 5-minute cooldown.
- **Dead code**: Removed unused `_test_connection()` function from `database.py`.
- **Unused imports**: Cleaned up `AsyncGenerator` from `database_postgres.py` and `test_reliability.py`.
- **Deprecation warning**: StarletteDeprecationWarning suppressed in pytest output.
- **Dashboard UI brightness**: Improved color contrast and visual hierarchy.

### Security

- **bcrypt password hashing**: Replaced plaintext password storage with bcrypt.
- **Secrets management**: All API keys and secrets read from environment variables.
- **CORS hardening**: Production mode restricts origins to known domains.

---

## [1.0.0] — 2026-07-29

### Added
- Initial release with full anti-theft tracking system
- Server: FastAPI backend with SQLite/PostgreSQL, WebSocket real-time updates, multi-channel alerts (email/SMS/push/WhatsApp), PDF evidence generation, Sentinel AI theft detection
- Android app: Background tracking service with location, camera, audio capture; Firebase Cloud Messaging; device admin (lock/wipe)
- Dashboard: Next.js dashboard with real-time map, device management, evidence gallery, command panel
- CI/CD: GitHub Actions workflow, Docker deployment, systemd auto-restart
