# Changelog

All notable changes to Magneetar are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

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

### Fixed

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
