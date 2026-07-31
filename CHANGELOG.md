# Changelog

All notable changes to Magneetar are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Removed

- **Dead scripts**: Removed 4 zero-referenced scripts from `scripts/` that were superseded or obsolete: `configure-sentry.sh` (Sentry skipped for cost), `install.sh` (legacy curl|bash installer, superseded by `make setup`), `setup-firebase.sh` (duplicate of the automated `firebase-setup.sh`), and `start.sh` (superseded by `deploy.sh` + docker-compose). Verified zero references across the repo before removal.

### Fixed

- **Hanging WebSocket tests**: The two `@pytest.mark.slow` tests in `test_reliability.py` used Starlette's sync `TestClient.websocket_connect()` against the persistent `/ws/dashboard` receive loop, which deadlocks (documented Starlette limitation) — `make test-all` hung forever. Rewritten as **live integration tests** using a real uvicorn server in a background thread + the `websockets` client (ping/pong roundtrip, capacity eviction with close code 1013). The `-k "not slow"` exclusion is now removed from CI, the Makefile, and docs — all 121 backend tests run everywhere.

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
