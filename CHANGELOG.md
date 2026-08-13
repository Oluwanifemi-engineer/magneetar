# Changelog

All notable changes to Magneetar are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — 2026-08-12

### Security & hygiene (2026-08-13 — hardening pass)

- **`/metrics` + `/metrics/json` are no longer public**: both leaked operational
  intelligence (registered user/device counts, DB health, and which external
  alert providers are configured) to anyone who could reach the API. They now
  require a dashboard/admin JWT and reject regular user accounts (401 anon /
  403 user / 200 operator) — matching the `/api/dashboard/errors` admin gate.
- **Real Firebase client config removed from the public repo**: the committed
  `android-app/app/google-services.json` contained the live project id +
  API key (the repo is public). It is now untracked + gitignored; a safe
  placeholder template ships as `google-services.json.example` and the APK
  CI workflow copies it when the `GOOGLE_SERVICES_JSON` secret is unset (the
  real file is preserved locally at `backups/google-services.json.real`). The
  dead placeholder duplicate at `android-app/google-services.json` was deleted.
- **`.gitignore` hardened**: `android-app/**/google-services.json`, stray
  firebase-service-account paths, and the empty leftover
  `server/firebase-service-account.json` dir (removed) are all covered now.
- **Stale artifacts removed from the publicly-served static dir**: 10 `.bak`
  APKs + `logo-preview*.html` dev previews deleted from `server/static/`;
  the `/apk/download` + checksum endpoints still resolve the same v1.4.1 file.
- **Redundant root `.env` deleted**: it duplicated `server/.env` secrets
  (Twilio creds, DB password) plus a deprecated `CF_TUNNEL_TOKEN` and was
  consumed by nothing (compose uses `server/.env` via `env_file`;
  `scripts/test-e2e.sh` now prefers `server/.env` too).
- **Stale dev artifacts removed**: `backups/dev-artifacts-2026-08-12/`
  (two old v1.0 APKs + a dev SQLite dump) deleted; scheduled
  `backups/magneetar_*.db.gz` / media archives untouched.
- **Real Firebase client values purged from git history**: the values were
  committed in v1.0.0 (`ded841b`) and existed in the public repo until
  scrubbed to a placeholder (`60e9e31`). History rewritten with
  `git filter-repo --replace-text` (all values → placeholders, 160 commits
  preserved, verified 0 matches in every ref + raw object scan) and
  force-pushed. All stale worktrees/reflogs pruned and objects garbage
  collected locally so no trace remains on disk.
- **FCM push fixed in production (deploy round)**: `MT_FIREBASE_KEY` points
  to `./firebase-key.json` (container path `/app/firebase-key.json`) but the
  compose mount provided a different filename — firebase-admin never
  initialized, so push alerts silently did nothing. The mount now provides
  the real gitignored service-account key at the loaded path.
- **Production deployed (2026-08-13)**: server + dashboard images rebuilt
  and rolled out via docker compose. Live checks confirm: `/metrics` returns
  401 to anonymous callers, the dead API-docs links are gone from the
  dashboard footer, the FCM key is mounted, and the server starts with no
  config warnings.

### Fixed (2026-08-13 — full customer-journey QA pass)

- **Password reset / email verification were dead ends without SendGrid**: with
  `MT_SENDGRID_KEY` unset (the current production state) the reset/verify links
  were never emailed AND never logged — the raw token was only stored hashed in
  the DB, so a customer clicking "Forgot password" could never recover their
  account. `send_transactional_email` now logs the FULL email body (containing
  the single-use, short-lived link) when no provider is configured, so a
  self-hosted operator can retrieve and deliver it. Covered by a new regression
  test proving the logged link completes a real reset (old password rejected,
  replay rejected).
- **Dead API-docs links removed from the customer-facing UI**: the Footer and
  dashboard Sidebar linked to `https://api.magneetar.me/docs` and
  `/redoc` — hardcoded to the production host where the docs are deliberately
  disabled (`docs_url=None` in production), so every click 404'd. Both links
  removed; "System Status" (`/health`) and "Responsible Disclosure" remain.
  `LandingPage.test.tsx` updated to assert the dead links are gone.

### Added (v1.6 — navigation + Find Network visibility round)

- **Interactive map navigation (dashboard)**: the YOU/DEVICE chips in the
  distance overlay and both map markers are now click-to-fly — clicking YOU
  flies to your position and pauses device follow (the per-second re-centre
  can no longer yank the view away), clicking DEVICE flies to the device and
  resumes follow, and the FOLLOW button now also flies straight to the device
  the moment it's turned on. No more waiting for the poll cycle to restore a
  manual view.
- **Trail replay no longer fights follow (dashboard)**: opening the replay
  timeline pauses device follow (restored on close), and the live re-centre
  yields while the timeline is open — scrubbing/playing the trail now pans to
  each point without being yanked back on the next poll tick.
- **Battery-aware Find Network scanning (Android)**: the guardian beacon
  scanner now paces itself — screen off → 5 min rest, battery < 15% → 10 min,
  battery < 5% → paused until charging (re-checked every cycle). The scan was
  already LOW_POWER/30s-per-minute; this widens the rest window instead of
  letting community scanning drain a guardian's phone.
- **Find Network status card (dashboard, Guardian tab)**: a two-state panel
  shows the selected device's Owner Beacon (BROADCASTING while a recovery
  request is active, else STANDBY) and this account's Guardian Scanner
  (SCANNING when opted in, else OFF) — so the operator can see at a glance
  whether their stolen phone is actively broadcasting an SOS beacon and
  whether their own phone is helping others.
- **BLE runtime permission flow (Android onboarding)**: PermissionsActivity
  now requests BLUETOOTH_SCAN/ADVERTISE/CONNECT on API 31+ alongside the
  other runtime permissions, with its own status row ("Granted ✓"/"Optional")
  — optional and non-blocking, matching the SMS pattern; on older Android
  the permissions are install-time and always read as satisfied.

### Added (v1.6 — family sharing round)

- **Device sharing + RBAC (Milestone 2 P1)**: owners can grant another
  account access to a device with one of three roles — `admin` (full
  control: commands, geofences, settings), `viewer` (full read: locations,
  media, evidence, history), or `device_only` (status glance only — no
  location, evidence, or commands; the privacy tier). New `device_shares`
  table (SQLite + Postgres parity, cascade cleanup on device delete),
  `POST/GET/DELETE /api/dashboard/devices/{id}/shares` (grant by email with
  idempotent upsert, list, revoke — account-owner only), and every device
  endpoint now enforces a role floor via the centralized
  `_assert_device_access(db, id, auth, min_role)` choke point (read=viewer,
  control=admin, destroy/share-manage=owner). The device list tags each row
  with the caller's `access_role`/`is_owner` and strips coordinates + PII
  for `device_only`.
- **Family-sharing dashboard UI (Milestone 2 P1, UI)**: "Sharing" card in
  the device panel (invite by email, role picker, revoke, role badges),
  shared-access chips in the sidebar, and role-aware control gating
  (commands, zones, media delete, settings, tabs hidden for `device_only`).
  Live updates for shared devices ride the WebSocket: each connection now
  carries an allowed-device set (owned + viewer/admin grants) resolved at
  connect time.
- **WebSocket privacy fix**: `device_only` grants never receive live
  location broadcasts (the set excludes them server-side), matching the
  REST redaction.

### Added (v1.6 — recovery dossier round, COMPETITOR_AUDIT P0 #3 closed)

- **Recovery Dossier — one-click police/insurer PDF (P0 gap-closer #3)**: the
  evidence PDF is now a true action dossier. `compile_pdf_data` feeds the
  owner's **command timeline** (lock / siren / wipe / capture with
  issued-at, params, status, executed-at) and the device **alias** into the
  report; `evidence_pdf.py` renders a new COMMAND TIMELINE section (the
  recovery actions taken, not just where the device went) and now embeds
  **every** photo inline (it previously re-fetched media rows per item and
  embedded only the first). The dashboard Evidence panel button is renamed
  **EXPORT RECOVERY DOSSIER (PDF)**, always enabled (the server auto-creates
  a case, so a pre-theft dossier — device info + alias + location trail +
  command history — is exportable), and now gives real feedback: success /
  error toasts + an inline error strip (the old handler only
  `console.error`'d, so failures looked like a dead button).
- **RBAC for the dossier (enforced, now tested)**: the generate-pdf endpoint
  was already `viewer`-floored via `_assert_device_access`; new tests lock
  it — a `device_only` share gets **403** (no coordinates → no PDF) while a
  `viewer` share downloads the PDF, and `compile_pdf_data` returns the
  command timeline + alias. Tests: 4 API/Sentinel-file + 2 multi-user
  (device_only 403, viewer 200) + 5 dashboard (`EvidencePanel.test.tsx`: case
  summary, empty state with enabled button, success toast, error toast +
  inline error, re-enable after failure).

### Added (v1.6 — Find Network Phase 1, COMPETITOR_AUDIT P1 #6 started)

- **SOS beacon protocol (server)**: `recovery_requests` gains an opaque
  per-request `beacon_token` (`secrets.token_hex(8)`, minted at launch,
  never exposed in owner/guardian request views). New device-facing
  `GET /api/device/recovery/beacon` returns the device's OWN active token
  (device JWT or x-device-key auth; the shared API key is rejected — anyone
  holding the public APK key can't probe other phones' tokens; null when no
  active request). `POST /api/recovery/sightings` now resolves a sighting by
  `beacon_token` OR `request_id` — a guardian reports the token picked up
  over BLE, so the request id itself never goes on the air. Schema
  migration (guarded ALTER + `ensure_initialized` staleness check — the
  device_shares no-op bug class) + Postgres adapter parity.
- **Find Network Android (Phase 1)**: the stolen phone's
  `SosBeaconBroadcaster` (dataSync FGS) polls the beacon endpoint and
  BLE-advertises the token as a service UUID while a recovery request is
  active; the guardian's `GuardianBeaconScanner` (dataSync FGS, self-gating
  on the account's guardian opt-in each cycle) BLE-scans, decodes the
  token, dedups via the persisted `SosBeaconTracker` (2h cooldown — a
  beacon advertises many times a second and guardians are rate-limited to
  10 sightings/hour), and reports a sighting with the guardian's OWN
  coordinates. Both degrade gracefully without BLE/permissions and never
  fake availability. Wire contract locked by JVM tests (`SosBeaconTest`
  round-trips the `token_hex(8)` format, rejects foreign UUIDs;
  `SosBeaconTrackerTest` cooldown/dedup) mirroring the server's format.
  New manifest permissions (BLUETOOTH_SCAN/ADVERTISE, `neverForLocation`;
  classic perms ≤ API 30) + optional `bluetooth_le` feature. Tests: 12
  backend (`TestFindNetworkBeacon` — token mint, device fetch, own-token
  isolation, API-key rejection, token-never-leaks, sighting-by-token
  resolves, unknown/closed/missing-resolution 404/400/422, migration) + 2
  JVM suites (16 tests). Honest scope: on-air BLE is Phase 1 — mesh
  scale-out, beacon-permission UX, and battery-aware scheduling are the
  documented follow-ups.

### Added (v1.5 — expert review round)

- **Geofence auto-actions (P0 gap-closer #1)**: per-zone `auto_action`
  policy (`capture` = queue front-photo + audio evidence commands, `siren` =
  queue the max-volume alarm) fired exactly once on an EXIT transition, plus
  the alert. `POST /api/dashboard/geofence` accepts `auto_action`
  (validated), `GET .../geofences` returns it. Includes schema migration +
  Postgres-parity column.
- **Geofence Zones dashboard UI (P0 gap-closer #1, UI)**: new "Zones" tab
  (`GeofencePanel`) to manage per-device zones — create (name, center
  prefilled from the latest fix, radius, safe/restricted toggle, auto-action
  policy picker), list with policy + safe-zone badges, and two-click-confirm
  delete. `createGeofence` now types/sends `auto_action`; `getGeofences` is
  fully typed.
- **Geofence exit detection FIXED (previously dead code)**: the persisted
  `last_inside` state now makes `check_geofences` report an exit transition
  exactly once. The old code never wrote the state, so `was_inside` was
  always False and `exited` events — and the exit alert — could never fire.
  The alert condition was also inverted (`not is_safe_zone` vs the template's
  'safe zone'): safe-zone exits now alert as the template and product
  semantics intend.
- **Location history CSV export (P0 gap-closer #5)**: `GET
  /api/dashboard/locations/{device_id}/export/csv` — ownership-gated,
  decrypted coordinates (at-rest-encryption safe), UTF-8 BOM for Excel,
  capped at 10k rows; dashboard "Export Location History (CSV)" button.
- **Lost Mode (P0 gap-closer #2)**: new `lost_mode` command end-to-end —
  server (validated, priority-1, not step-up gated), dashboard LOST MODE
  button, Android `LostModeActivity` (full-screen `showWhenLocked` recovery
  message + one-tap call button) driven by `LostModeManager` (persistent
  state, high-priority notification as the reliable background path per
  Android 10+ activity-start rules, re-posts on service restart).
- **Postgres migration formally FROZEN**: `docs/postgres-migration.md`
  carries an explicit DECISION (SQLite is the production architecture; the
  adapter is experimental, Phase 2b not scheduled); ADR-0005 status, the
  `kubernetes/` README, and the adapter module docstrings all say so.
- **Failed-unlock "theftie" auto-capture (P1 gap-closer #4)**: repeated
  failed unlock attempts now trigger the same automatic evidence capture as
  a geofence exit. Android: new `FailedUnlockMonitor` reports the count of
  failed unlocks since the last successful unlock on every telemetry ping
  and heartbeat — the DPC's authoritative `getCurrentFailedPasswordAttempts`
  when the app is device admin/owner, else a permission-free keyguard
  heuristic (a screen-on behind the keyguard that ends without
  `ACTION_USER_PRESENT` = one failure; a successful unlock resets). New
  manifest `FailedUnlockReceiver` (SCREEN_ON/SCREEN_OFF/USER_PRESENT),
  fresh-install baseline. Server: `TelemetryPing.failed_unlock_count` /
  `HeartbeatPacket.failed_unlock_count` (validated ≥ 0), Sentinel now
  actually scores the previously-dead `failed_unlocks` anomaly (+20) when
  the count crosses `MT_FAILED_UNLOCK_THRESHOLD` (default 5), and both the
  location and heartbeat paths queue `capture_photo_front` +
  `capture_audio` (priority 1, deduped) and fire an always-deliver
  `failed_unlock_attempts` alert (10-minute dedup — reads the same current
  DB module `send_all` writes to, so eviction-order runs stay truthful).
  Tests: 4 API (threshold reaction + alert, dedup, below-threshold/absent
  inert, heartbeat path) + 3 Sentinel scoring + 11 Android
  `FailedUnlockTrackerTest` (counting contract, reset, DPC overwrite,
  persistence).

### Fixed (v1.5)

- **Command queue/alert lock contention**: the geofence block now commits
  state + queued auto-action commands BEFORE `alert_engine.send_all()`
  (whose nested connection writes alert rows), mirroring the heartbeat
  path's documented "commit before nested writes" rule — previously the
  nested writes blocked on the request transaction and "database is
  locked"-failed silently after busy_timeout.

### Changed (v1.5)

- **Repo hygiene**: stale root build artifacts (`magneetar.db`, v1.0 release
  APKs) moved to `backups/dev-artifacts-2026-08-12/`; all three remain
  gitignored.

### Fixed

- **Admin-scope writes to a missing device return 404, not 500**: the admin
  branch of `_assert_device_access` skipped the device-existence check, so
  `POST /api/dashboard/command` and `/api/dashboard/geofence` for a
  nonexistent device raised an unhandled `FOREIGN KEY constraint failed`
  (500 + ASGI traceback) instead of a clean 404. Existence is now verified
  for both scopes. Found by the live-system probe; regression tests added in
  `test_api.py` (command + geofence on a missing device → 404).

### Distribution

- **`docs/DISTRIBUTION_PLAN.md` added**: channel strategy (Play primary,
  download page interim then fallback), phased submission timeline
  (pre-flight → app content → closed testing → production access → staged
  rollout), rollback plan, 30-day post-launch monitoring, and risk
  mitigations. Key research input: **new developer accounts must complete 14
  days of closed testing with ≥12 active testers before production access**,
  so the plan front-loads tester recruitment.

### Verified (this session)

- **Signature chain proven**: `release.keystore` (alias `magneetar`) →
  `app-play-release.aab` (v1.4.1, versionCode 7) → sideload APK all carry the
  same cert (SHA-256 `02:4C:BB:34…0A:7F`), via `keytool`/`jarsigner`/
  `apksigner`.
- **Play flavor is Play-clean**: merged `playRelease` manifest has ZERO
  accessibility matches and no `UninstallGuard`; device-admin receiver
  present for the declared Permissions Declaration path.
- **Keystore backed up off-machine**: `~/Documents/
  magneetar-keystore-backup-2026-08-12/` with `release.keystore` (SHA-256
  `f70481129f…2a7a5`, byte-identical to source) + `RECOVERY.md` (identity,
  hashes, restore procedure, hard rules).
- **All public URLs live**: magneetar.me, /privacy, /terms, /download,
  /login = 200; api.magneetar.me/api/config reports 1.4.1.
- Full suites re-verified: backend **454 passed / 4 skipped**, dashboard
  **177 passed + tsc clean**.

### Fixed (test suite — full-suite order hazard closed)

- **Backend full suite is green again in one process (454 passed, 4 skipped)**: CI runs every
  test file in a single pytest process, and `test_e2e.py` / `test_sim_change.py` evict
  `config/database/main/auth/alerts/websocket_manager/routes` from `sys.modules` at import
  time (re-importing them with their own env). Test files imported **before** that eviction
  kept stale module-level bindings — a dead module instance pointing at their temp DB while
  app modules resolve the CURRENT module at call time — so 17 tests failed in the full suite
  while passing individually. Closed with the codebase's documented lazy-resolution convention:
  - `test_reliability.py` (9 failures: health DB check, WebSocket eviction/capacity/revoked-
    token, `alerts.logger` patch misses, per-device recipients): a module-scoped autouse
    fixture (`_align_to_current_modules`) re-points the module's bindings to the current
    generation at run time — after collection, so after any eviction.
  - `test_offline_monitor.py` (3) and `test_encryption_at_rest.py` (4): all helpers resolve
    `client`/`database`/`api_key` lazily at call time.
  - `test_guardian.py` (1, sighting rate-limit): the monkeypatch now targets the live POST
    handler's `__globals__` via the app's `_IncludedRouter.original_router` — a fresh
    `import routes.guardian` after eviction can resolve to a different module object than the
    one the app's handlers call.

---

## [Unreleased] — 2026-08-11

### Fixed (Android — live-tested on Samsung SM-A037F)

- **`capture_audio` failed with "Audio file not found after recording" —
  `setMaxDuration` race removed**: `MediaCaptureService.captureAudio()` set
  `setMaxDuration(30s)` AND its own polling loop waited exactly 30s before
  calling `stop()` — when the OS auto-stop at max duration fired at the same
  moment the app called `stop()`, Samsung's MediaRecorder finalized the file
  and removed it, so the post-recording `file.exists()` check threw. The
  duplicate 30s timer is gone (the app-side loop alone owns the window), so
  `stop()` is always the only stop and the file is always kept. Same flaky
  signature seen live on the fleet phone (worked 08-09, failed 08-11). Fixed
  APK rebuilt (`assembleSideloadRelease`, JDK 21 — host JDK 25 is
  incompatible with Gradle 8.12), verified in the dex (`setMaxDuration` gone,
  error string intact), deployed to `server/static/apk/` (all aliases),
  live `/apk/checksum` = `cefdc203…33b` matching the exact bytes
  `/apk/download` serves (7,506,533 bytes). Owners must re-download +
  reinstall to pick up the fix.

### Changed (download page)

- **Play Protect block warning removed from the download page (owner decision)**: the amber "If Google shows App blocked…" notice (the three install workarounds) was deleted from `dashboard/src/app/download/page.tsx` — a public warning that the app is blocked read like a scam move to would-be installers. The page keeps the clean install steps, checksum verification, and OEM battery notes; the Play Protect workarounds now live ONLY in `docs/play-store-checklist.md` + `docs/PHONE_TEST_CHECKLIST.md` (  internal). No functional change to the ticket → download → checksum flow. `docs/play-store-checklist.md` and `docs/PHONE_TEST_CHECKLIST.md` updated to say the notice is gone.
- **Subtle install-help FAQ added to the download page**: a collapsed **"Having trouble installing?"** accordion (native `<details>`/`<summary>`, no JS) now sits below the OEM battery notes — 4 items: download won't start (refresh + re-mint tip), the "Install unknown apps" permission (Play Protect pause path lives here as an answer, not a warning banner), dashboard OFFLINE fix (covert-mode re-open + background settings), and SHA-256 verification. Removed an unused `ExternalLink` import.

### Deployed / Android

- **Release APK built + verified with the device key**: full release pipeline
  green (lint 0 errors → `assembleSideloadRelease` → `bundlePlayRelease` →
  signature verify). The sideload APK embeds `BuildConfig.DEVICE_KEY` =
  the server's `MT_DEVICE_KEY` (verified inside the dex; `SERVER_URL`
  confirmed) — the fleet can authenticate after the legacy-key retirement.
  Artifacts: `Magneetar-v1.4.0-b6-<ts>.apk` + `Magneetar-v1.4.0-b6.aab`.
- **Android lint gate fixed (5 errors → 0)**: one real `MissingPermission`
  (`fusedClient.requestLocationUpdates` — already wrapped in
  try/catch(Exception), lint can't see it) and four `ForegroundServiceType`
  false positives that fire ONLY on the `play` flavor (the merged manifest
  declares `android:foregroundServiceType` on Tracking/Persistence/
  MediaCapture services; the play overlay's `tools:node="remove"` trips the
  check — sideload variants lint clean with identical code). All five now
  carry documented `@SuppressLint` annotations.
- **APK download ticket self-heals (dead links can't 403 anymore)**: the
  download page pre-mints a 10-minute HMAC ticket into the button's `href`;
  a long-press / new-tab / stale saved link used to dead-end on the server's
  raw `403 {"detail":"Missing or expired download ticket"}` JSON. The page
  now refreshes the href every 4 minutes + on tab re-focus and re-mints on
  click (`lib/downloadTicket.ts` — `pickDownloadUrl` falls back to a
  still-valid href only), and the SERVER now answers an invalid/expired
  ticket with a **302 redirect to the download page** (which mints a fresh
  one) instead of raw JSON — verified live (302 → page 200 → fresh ticket →
  APK bytes). Security unchanged: bytes still require a valid HMAC ticket;
  the redirect only changes the error UX. Tests updated in
  `test_api.py::TestApkChecksum` (302 + Location asserted, valid ticket still
  downloads).
- **Play Protect hard block — diagnosis corrected, download page serves the
  Play-clean APK + honest guidance (2026-08-11)**: Google's sideload block
  has no bypass on current Android ("App blocked to protect your device"
  with only an **OK** button — the old "More details → Install anyway" flow
  no longer exists). First fix: the download page began serving the
  **`play`-flavor release APK** (built with `assemblePlayRelease`, JDK 21)
  — same signing key, same device key, **zero SMS/phone permissions**
  (verified with `aapt`), deployed to `server/static/apk/` (all aliases),
  live `/apk/checksum` = `5958bbb4…a003`. **Correction (user-verified
  on-device): the SMS-free build is STILL hard-blocked** — `BIND_DEVICE_ADMIN`
  (kept in both flavors for thief-resistant uninstall + remote lock/wipe) is
  itself a deterministic sideload trigger, so **no permission profile that
  keeps Magneetar's anti-theft features can be sideloaded on current
  Android**. The download page's earlier "Play Protect friendly — it should
  install without it" notice was **replaced** (2026-08-11) with honest
  guidance + the real test paths: (1) temporarily pause Play Protect
  scanning (`Settings → Security & privacy → App security → Google Play
  Protect → ⚙️ → off`), (2) `adb install` for developers, (3) the Play Store
  listing (the only friction-free channel). Trade-off of the served build:
  offline SMS command relay unavailable (network/FCM + offline queue still
  work); the SMS-capable sideload APK stays backed up in
  `server/static/apk/magneetar-latest.apk.sideload-<ts>`.
  `docs/play-store-checklist.md` + `docs/PHONE_TEST_CHECKLIST.md` updated.

### Database (PostgreSQL storage facade — ADR-0005 Phase 2a)

- **Storage interface landed (`server/storage.py`)**: `SqliteStore` (wraps
  the sqlite3 connection — the zero-risk default) and `PgStore` (sync
  facade over asyncpg via `run_coroutine_threadsafe`). Setting
  `MT_DATABASE_URL` now makes `get_db()`/`get_db_context()` return
  `PgStore` — routes are untouched for the switch itself.
- **Dialect + strictness handling in the facade**: `?`→`$n` placeholder
  translation (quoted literals skipped), plain INSERTs rewritten with
  `RETURNING id` so `lastrowid` keeps working, bool 0/1 → Python bool and
  ISO strings → `datetime` for timestamp columns (asyncpg strictness, same
  tolerance SQLite had), and row-value normalization back to SQLite
  semantics (bool → 0/1, timestamps → ISO strings) so route code behaves
  identically on both backends.
- **Validated live against Postgres 16** (scratch container):
  `tests/test_storage_facade.py` (22 tests) — translator, INSERT rewrite,
  coercions, SqliteStore scenario, and PgStore schema/`lastrowid`/
  `rowcount`/identical-row-parity scenarios. App-level smoke on the
  pg-backed facade confirmed dashboard reads return decrypted coordinates.
- **Honest remaining gap recorded**: the Phase 2b SQL portability pass
  (`datetime()` dialect calls in ~35 sites across routes/database.py —
  register adoption, login rate-limit purge, metrics counts, retention
  purges; plus `INSERT OR REPLACE`) still fails on pg and is documented in
  `docs/postgres-migration.md` §6.4 with the recommended facade-level
  rewrite design. Production keeps SQLite; `MT_DATABASE_URL` stays unset in
  the Docker stack until 2b lands.

### Security

- **Location telemetry encrypted at rest (v1.5 — the E2E todo, wired for
  real)**: every ingest path (`_persist_location`, `/api/device/location/simple`,
  offline-queue) now AES-256-GCM-encrypts lat/lng with a per-device
  HKDF-derived key when `MT_ENCRYPTION_KEY` is set — rows store ciphertext in
  the new `locations.location_data` column with `location_encrypted=1` and
  0.0 placeholders in the NOT NULL lat/lng (plaintext never touches the DB).
  Every reader (dashboard list/map/replay/live, guardian recovery, offline
  monitor, GDPR export, evidence PDF, Sentinel history) decrypts via the new
  `encrypt_location_for_store()`/`decrypt_location_row()` helpers; legacy
  plaintext rows stay readable forever (dual-mode). Sentinel/geofences/WS
  still run on the in-memory payload, so theft detection is unaffected.
  `location_data` added to the pg adapter (parity test enforced) and to
  `ensure_initialized`'s staleness check so existing DBs migrate. New
  `tests/test_encryption_at_rest.py` (15 tests: ciphertext-not-plaintext,
  every read path, legacy rows, offline alerts, evidence PDF, export,
  guardian snapshot, simple-path parity, ciphertext-never-leaks). `docs/secret-rotation.md` updated
  (rotating the key now affects encrypted locations). Code-review hardening:
  API/export/evidence payloads strip `location_data` (raw ciphertext never
  leaves the server), and decrypt failures log a warning so key-rotation
  breakage is visible instead of silent null coords.

### Changed (honest security claims — audit round 2)

- **Remaining overstated encryption claims corrected**: `SECURITY.md`,
  `docs/CONTRIBUTING.md`, `docs/play-store-checklist.md`, `docs/play-store-
  submission.md`, `docs/deployment.md`, `docs/FINAL_EXECUTION_REPORT.md`,
  `docs/DEEP_ANALYSIS_REPORT.md`, `docs/LIMITATIONS_RESOLVED.md`, `docs/REAL_
  WORLD_READINESS.md`, `docs/postgres-migration.md`, `docs/COMPLETE_
  IMPROVEMENTS.md` and the `server/encryption.py` docstring now state exactly
  what is true: account secrets (TOTP) AES-256-GCM at rest, location
  plaintext-with-TLS until this release, no blanket "encryption at rest"
  for telemetry, E2E = scaffold/not-shipped (roadmap items remain roadmap).
  User-facing copy was already honest (2026-08-10); this pass closed the
  docs gap.

### Database (PostgreSQL path)

- **Storage-interface conversion plan + ADR**: `docs/postgres-migration.md`
  §6 now specifies the concrete Phase-2 design — a **sync facade over
  asyncpg** (`SqliteStore`/`PgStore`, `get_db()` selects by env) with a
  `?`→`$n` param translator, the audited portability-gap inventory
  (`datetime()` string compares, `last_insert_rowid()` → `RETURNING`,
  `INSERT OR REPLACE`, boolean 0/1, `LIKE`→`ILIKE`), phased delivery
  (facade → portability pass → dual-write week), and a pg CI job.
  New `docs/adr/0005-postgres-storage-interface.md` records the decision
  (sync facade over asyncpg, not an async route rewrite) and the rejected
  alternatives.

---

## [Unreleased] — 2026-08-11

### Added

- **SIM-change detection (Prey-class, permission-free)**: `SimChangeMonitor`
  fingerprints the SIM with `TelephonyManager.getSimOperator()`/
  `getSimOperatorName()` — NO `READ_PHONE_STATE`/`READ_PHONE_NUMBERS`, so it
  works identically on the Play and sideload flavors. `SimChangeReceiver`
  listens for `ACTION_SIM_STATE_CHANGED`; the telemetry + heartbeat paths
  compare against a persisted baseline (first run baselines silently; a
  reinstall never false-alerts) and report the change exactly once. Server:
  `sim_changed` now fires its own **always-deliver** alert immediately from
  both the location and heartbeat handlers (previously the alert type existed
  but was never dispatched — a lone SIM swap scored 35/80 and alerted nobody),
  with a 10-minute dedup so queued/offline replays can't re-alert. Sentinel
  still scores it (+35). Tests: new `tests/test_sim_change.py` (immediate
  alert, dedup, no false positives, heartbeat path). Version bumped to 1.4.1.

### Fixed

- **Download page was serving the sideload-flavor APK** (carrying
  `RECEIVE_SMS`, the deterministic Play Protect hard-block trigger per
  Google's Enhanced Fraud Protection criteria). The served build is restored
  to the play flavor (no SMS/phone-state permissions, same signing key,
  same device key) per the 2026-08-11 decision in
  `docs/play-store-checklist.md`. See `docs/PLAY_POLICY_ANALYSIS.md` for the
  full per-feature policy analysis.
- **`docker-compose.yml` hardcoded `APP_VERSION=1.4.0`** as the server image
  build arg — every rebuild baked a stale `/VERSION`, so `/api/config` and
  the APK resolver (which prefers `magneetar-v{APP_VERSION}-release.apk`)
  served stale files after a version bump. Now reads 1.4.1 (server arg +
  dashboard `NEXT_PUBLIC_APP_VERSION` fallback); live checksum matches the
  served play-clean v1.4.1 bytes.

---

## [Unreleased] — 2026-08-12

### Fixed

- **Alert retry storm (21s device-request stall)**: `_send_with_retry`
  retried EVERY channel failure — including permanent credential rejections
  (Twilio 401/403, SendGrid 401/403, stale FCM `NotRegistered` tokens) —
  serially, with 1–2s backoff per attempt. With two misconfigured Twilio
  channels, a single `sim_changed` alert blocked the device's location POST
  for ~21s. New `ChannelPermanentError` (alerts.py) makes providers raise on
  permanent rejections and the retry wrapper fail fast (still recording the
  circuit-breaker failure); transient failures (timeouts, 5xx, network)
  keep their existing retry. Live-verified: the request now completes in
  Twilio's own round-trip latency instead of retry backoff. New
  `tests/test_alert_retry.py` (7 tests) locks the contract; the
  `test_reliability.py` SMS-rejection test updated to the new contract and
  made robust to the test_e2e module-eviction collection order.

### Operations

- **Twilio 401 diagnosed (needs credentials)**: the SID/token pair in
  `server/.env` is rejected at the Twilio API level (error 20003
  "Authenticate") — a rotated token or changed SID, not a config-format
  bug (format validates clean). SMS + WhatsApp alert delivery is currently
  down; FCM push is the only working channel (email also has no
  sender/recipient configured). `docs/PLAY_READINESS_VERDICT.md` records the
  fix path: paste valid `MT_TWILIO_SID`/`MT_TWILIO_AUTH_TOKEN` from the
  Twilio console.

### Play Store readiness

- **`docs/PLAY_READINESS_VERDICT.md` added** — honest, evidence-backed
  verdict (~85% submission-ready): fresh v1.4.1 AAB now built
  (`bundlePlayRelease`, signed, versionName 1.4.1), privacy page live (200),
  play flavor permission-clean (zero SMS/phone-state, verified via aapt).
  Remaining gaps: store-listing assets (feature graphic + 6–8 screenshots),
  Play Console declaration forms, keystore off-machine backup + password
  rotation.

### Play Store readiness — executed (2026-08-12, round 2)

- **G1 closed — fresh v1.4.1 AAB built + signature-proven**: `bundlePlayRelease`
  re-run (5.9 MB, v1.4.1 / versionCode 7). `jarsigner -verify` → jar verified;
  signer SHA-256 `02:4C:BB:34:DB:44:…` matches `android-app/release.keystore`
  (alias `magneetar`, PKCS12 — NOT the stale `magneetar-release.keystore`).
  Upload path + keystore warning documented in the verdict doc §G1.
- **G2 closed — store-listing assets generated**: `docs/play-assets/` now has
  `feature-graphic-1024x500.png` (aqua→emerald gradient, M logo, wordmark +
  5 feature bullets — rebuilt with a fixed-row measured layout after two
  overlapping drafts; verified in-browser, zero overlaps) and `icon-512.png`
  (dark rounded tile, aqua ring, white M, emerald accent). Generator:
  `scripts/gen-play-assets.py` (PIL, brand colors from tailwind config).
  Remaining asset gap: 6–8 real-phone screenshots (cannot be generated).
- **`docs/PLAY_STORE_LISTING.md` added** — copy-paste-ready short/full
  descriptions, data-safety + permissions declaration answers, IARC rating
  guidance, and the upload walkthrough.

### Verification tooling

- **`scripts/verify-sim-swap-live.py` (new) — one-shot live SIM-swap probe**:
  registers a throwaway device through the public API (x-api-key =
  `MT_DEVICE_KEY`, the same key the APK embeds), fires a `sim_changed=true`
  location ping, polls the server DB (docker exec) for the always-deliver
  alert rows, then **self-cleans every row it creates** — including the
  `audit_log` `device_registered` entry (reviewer-caught leak) and all
  device_id-keyed tables. Exit codes: 0 = all delivered, 1 = didn't fire,
  2 = couldn't verify (docker unreachable), 3 = fired but channels failed.
  **Live-proven in production**: push delivered=1; email/WhatsApp/SMS fail
  only because the Twilio account is suspended (the known 20003 issue).
  Used together with `scripts/twilio-config-check.py` +
  `scripts/alert-smoke-test.py` to verify the full alert stack once Twilio
  is recharged.

---

## [Unreleased] — 2026-08-10

### Fixed

- **Dashboard test suite green again (2 suites)**: `LandingPage.test.tsx`
  asserted `24/7` as a single text node, but the premium redesign's
  `AnimatedCounter` renders the value and suffix separately — the assertion
  now targets the stable hero stat labels. `DashboardLayout.test.tsx`
  failed with "expected app router to be mounted" because the layout now
  calls `useRouter()` from `next/navigation` (mocked in the test) and
  re-renders when `mounted` flips (data-layer spies now assert
  `toHaveBeenCalled()`). Full dashboard suite: **173 passed**.

### Security

- **`MT_LEGACY_DEVICE_KEY` retired (rotation grace closed)**: the pre-split
  master key is removed from `config.py` and `auth.py` — device-scope auth
  now accepts the master and device keys ONLY. `generate-env.sh`, README,
  `docs/deployment.md`, `docs/PROJECT_STATUS.md`, the secret-rotation
  runbook, and ADR-0002 updated; `test_device_key_separation.py` now
  asserts a legacy-style key is REJECTED for device scope and registration.
  In-the-wild APKs still presenting the old master key must be upgraded to
  an APK embedding `BuildConfig.DEVICE_KEY`.

### Changed (honest security claims)

- **Overstated encryption claims corrected**: location telemetry is stored
  plaintext (only account secrets — TOTP — are AES-256-GCM encrypted at
  rest), so the landing hero stat now reads SHA-256 chain-of-custody
  hashing, the Security section's "encryption at rest" bullet and AES-256
  chip were corrected (TLS in transit + bcrypt/AES-256-GCM for secrets +
  TOTP 2FA), the dashboard loading badge and login page no longer claim
  AES-256, the Terms page no longer claims location data is encrypted at
  rest, and the Play Store listing's "end-to-end encryption for all data"
  was replaced with the real mechanisms. `server/e2e_encryption.py` is
  documented as experimental scaffold, not a shipped feature.

### Infrastructure

- **Dependabot added** (`.github/dependabot.yml`): weekly update PRs for
  pip (server), npm (dashboard), GitHub Actions, and Gradle (android-app) —
  CI gates every bump; Next/React majors are manual.

### Database (PostgreSQL path)

- **`database_postgres.py` schema re-synced with SQLite**: added the missing
  `users`, `fcm_tokens`, `error_log`, `password_reset_tokens`,
  `email_verify_tokens`, and `cell_location_cache` tables plus the drifted
  devices/commands/media columns (`device_key_hash`, alert prefs, SMS
  relay, `failure_reason`, `delivery_channel`, `file_path`, `file_size`).
  New `tests/test_postgres_adapter_parity.py` enforces table + column
  parity between the SQLite schema (CREATE + ALTER DDL) and the pg adapter,
  so the adapter can never silently lag again. The adapter remains NOT
  wired into application routes — the storage interface conversion is the
  remaining migration work.

---

## [Unreleased] — 2026-08-07

### Fixed

- **Cloudflare tunnel flapping ("cannot access the dashboard")**: the host has
  no IPv6 route, so cloudflared kept dialing IPv6 edge addresses (`network is
  unreachable`), dropping connections and canceling in-flight streams — pages
  hung or refused to load while the server itself was healthy. The tunnel now
  runs with `--edge-ip-version 4` and `protocol: http2` (TCP only, no QUIC/
  IPv6). Live-verified: 0 tunnel errors, public `/health` and `/login` return
  200, browser check clean.

### Changed

- **Dashboard operator position — tap-to-pin replaces "open on your phone"**:
  in the real theft scenario the GPS phone is the one that was stolen, so the
  old IP-derived accuracy gate telling the operator to open the dashboard on
  their phone was a dead-end. The map now has a **PIN POSITION** button: the
  operator taps the map to mark where they actually are (persisted in
  localStorage); the pinned position beats the browser fix for distance and
  OSRM routing; distance shows from any position with a fix-quality annotation
  (e.g. `±1.5 km IP fix`) instead of being hidden; the IP-derived banner now
  points to the pin. 173/173 dashboard tests, `tsc` clean, markers live-verified
  in the served bundle (`page-c299eaac…`).

### Performance & scale (deployed live)

- **4 uvicorn workers (was 1)**: the 16-core host was running a single Python worker; `server/Dockerfile` now runs `--workers 4`, giving ~4× the CPU headroom for sentinel scoring, geofence checks, and WebSocket fan-out. Live-verified: 4× "Application startup complete" in the container.
- **Redis realtime broadcast bus**: with multiple workers each holding their own in-memory WebSocket registry, cross-worker fan-out was impossible — broadcasts now publish to a shared `magneetar:ws` channel (`websocket_manager.py`) and every worker's subscriber delivers to its local connections (exactly-once). Falls back to direct local delivery without Redis or during hiccups, so dashboards never go dark (3s polling remains the safety net). New `redis` compose service + `MT_REDIS_URL`; deploy.sh ensures it's up (its `--no-deps` step never starts dependencies). Live-verified: **4 subscribers on the bus, zero reconnect storms, messages delivered exactly-once** (integration-tested against real Redis, incl. 5s-idle stability).
- **Fix: Redis listener reconnect storm**: `pubsub.listen()` blocks on a socket read and the shared client's `socket_timeout=2` turned an idle channel into a `Timeout reading` every 2s, dropping the subscriber and breaking cross-worker fan-out. The long-lived listener now uses a dedicated connection with **no read timeout** (shared client keeps its short timeout for publishes). Verified against real Redis: subscriber survives idle, publishes delivered.
- **In-memory telemetry rate limiting (`memory_rate_limit.py`)**: every location/heartbeat/media/command-poll ping did 4 rate-limit DB writes + commit on top of its own insert (~2/3 of hot-path write cost). The four telemetry checks (≥2s location spacing, 10/min heartbeats, 5/min media, 30/min command poll) now use a threaded sliding-window limiter — identical 429 semantics, zero DB writes. Security-sensitive limits (login/claim/step-up/APK ticket) stay DB-backed. e2e rate-limit test still green.
- **WebSocket cap 100 → 250/worker** (`MT_MAX_WS_CONNECTIONS`): 4 workers now allow up to ~1,000 concurrent live dashboards instead of 100 — the old hard cap was the first ceiling hit under load.
- **Leader lock (`leader_lock.py`)**: offline alerting, archive sweeps, and rate-limit cleanup all tick on 60s loops — with 4 workers they run 4× concurrently, so the first device crossing the offline threshold would have been **quadruple-SMS'd** (the alerts-table dedup row is only written *after* sending). A Redis `SETNX` + Lua compare-and-delete lock now ensures exactly one worker runs side-effect loops; without Redis the lock degrades to a no-op (single-worker semantics). Verified against real Redis: mutual exclusion, non-holder release safety, stale-token protection.

### Dashboard location accuracy (operator's own position)

- **"My location varies with browser" — diagnosed and fixed**: the operator's "YOU" marker, distance readout, and GET ROUTE all used raw `navigator.geolocation` — which is GPS on phones (3–15 m) but **IP/Wi-Fi-derived on desktop browsers (1–5 km+, sometimes 10–100 km off)**, with `enableHighAccuracy` a no-op on desktop. The map now: renders an **accuracy circle** scaled to `coords.accuracy`, gates distance/route features on an accuracy threshold (with an explicit reason when too coarse), shows a **banner when the fix looks IP-derived** (telling the operator to use a phone browser or move to a window), and surfaces a permission-denied banner instead of silently failing. All markers live-verified in the served bundle (`enableHighAccuracy`, `IP-derived`, accuracy gating present in `page-03d0af9d…`).

### Deployed

- **v1.4.0 perf+accuracy stack live**: server + dashboard images rebuilt (`3ee042d`, `a18aaaf`), DB backed up pre-deploy, health-gated. `/health` → `online · 1.4.0 · database true`; dashboard serving the new bundle; `wss://api.magneetar.me/ws/dashboard` handshake verified through the Cloudflare tunnel (anonymous connections correctly rejected with `4408 Authentication required` — the F-01 gate). Server suite **395/395**, dashboard **173/173**, flake8/black clean.
- **Deploy reliability**: the first rollout attempt timed out at 25 min — root cause was first-time base-image pulls + the new `redis==5.2.1` pip install (155s) inside the build, not a script bug. Images are now cached; re-running `deploy.sh` completes in minutes.

---

## [Unreleased] — 2026-08-06

### Play Store readiness

- **targetSdk/compileSdk 36 (Android 16)**: Google requires ALL new apps and updates to target API 36 from Aug 31, 2026 — bumped from 35 with AGP 8.7.3→8.10.1 + Kotlin 1.9.23→2.0.21 (Gradle 8.12, JDK 21). Verified locally: `assembleRelease` + `bundleRelease` + unit tests + lint all green; `aapt` confirms targetSdkVersion 36.
- **Distribution flavors (`sideload` / `play`)**: the Play Store build strips the restricted SMS permissions (`RECEIVE_SMS`, `SEND_SMS`, `READ_PHONE_STATE` — Google Play's SMS policy requires default-SMS-handler status) via `src/play/AndroidManifest.xml`; the sideload build keeps the full offline SMS relay. Verified: play merged manifest has zero SMS permission elements; sideload keeps all three. The app treats SMS as optional everywhere (denial never blocks onboarding) — no code changes needed.
- **Play AAB builds**: Play accepts only App Bundles for new apps — `build-release.sh` and `build-apk.yml` now build `bundlePlayRelease` (Play AAB) alongside `assembleSideloadRelease` (download-page APK) and upload the AAB artifact. Play-store-checklist updated with researched policy findings (API-36 deadline, AAB requirement, Play Protect recognition does NOT follow sideloads, Device-management declaration is enterprise-only).

### Security

- **Master/device key split (critical fix)**: the master admin key was proven extractable from the public APK with a plain `strings` scan — it minted dashboard-admin JWTs, so anyone who sideloaded the app could view every user's locations/evidence and issue WIPE/LOCK to any device. The shared key is now split: `MT_API_KEY` (master, server-side only — dashboard `/api/auth/login` + step-up hard-gated to it alone), `MT_DEVICE_KEY` (low-privilege device key — the ONLY key embedded in APKs via `BuildConfig.DEVICE_KEY`, scoped to device endpoints), and `MT_LEGACY_DEVICE_KEY` (the pre-split master accepted for device-scope auth only, so installed APKs keep working during the grace window). Production startup now fails if `MT_DEVICE_KEY` is missing or equals the master key. Android build (`-PDEVICE_KEY`), CI (`DEVICE_KEY` secret), `build-release.sh`, and all docs updated. Master rotated in `server/.env`; old master demoted to legacy device scope. 14 new regression tests in `tests/test_device_key_separation.py`; full server suite **395 passed**.

## [Unreleased] — 2026-08-05

### Added

- **Account security suite — TOTP 2FA, password reset, email verification**: per-account TOTP with a full lifecycle (`POST /api/auth/2fa/setup` returns a QR data-URI; `/enable` verifies a live code — replay-safe, `/disable` requires the account password). Logins on 2FA-enabled accounts answer `{requires_2fa, two_factor_token}` and finish at the new `/api/auth/user/login/2fa`; brute-force lockout (5 bad codes → 10-min cooldown) + per-token replay guard. `/api/auth/forgot-password` (rate-limited, response identical whether or not the email exists — no account enumeration) → single-use 30-min token → `/api/auth/reset-password` (strong-password validation). `/api/auth/verify-email` + `/resend`; `/api/auth/me` exposes `email_verified`. **Security fix found in review:** the 2FA challenge JWT previously passed `get_current_user` (only the `user:` subject prefix was checked) — `auth.py` now requires the exact `type` claim so a challenge token can never be spent as a dashboard session. 24 new tests in `test_user_security.py`.
- **Dashboard account-security UI**: login page gains a 2FA code step (auto-switches when the server answers `requires_2fa`); new `/forgot-password` and `/reset-password` pages; Settings modal gains a Security panel (enable 2FA with inline QR, resend/verify email, status chips). `api.ts` + types extended (2FA/reset/verify methods). 32 new tests across 4 suites (LoginPage 2FA, SettingsModal security, ForgotPasswordPage, ResetPasswordPage).
- **Android 2FA sign-in step**: `SignInActivity` swaps the password field for a 6-digit TOTP field when login returns a challenge, then exchanges code + token at `/api/auth/user/login/2fa` before storing tokens and linking the device (same DeviceLinker + navigation path as plain login).
- **Unowned-device registration cap (F-07 abuse)**: the master API key ships inside every APK, so unlinked device rows used to be unbounded — `MAX_UNOWNED_DEVICES` (default 250) now 403s registrations past the cap (no row created); account-linked registrations stay bounded by the per-user limit instead. New `TestUnownedDeviceCap` tests.
- **Evidence-safe retention purge**: `purge_old_data` no longer deletes media belonging to **active** evidence cases — only stale evidence beyond the retention window dies, so an open investigation keeps its photos/audio. New `TestEvidenceRetentionPurge` tests (tolerant of suite-level media rows).
- **Media + off-site backups**: `backup-db.sh` now also snapshots the media evidence directory (gzipped tarball, `--restore-media`, matching rotation/listing) and pushes both artifacts off-site via optional `rclone` (`MT_RCLONE_REMOTE`, graceful skip when unconfigured) — 3-2-1 for the DB *and* the evidence. `test-backup-smoke.sh` extended to seed + round-trip media files.
- **Play Store policy cleanup (Android)**: `USE_EXACT_ALARM` removed from the manifest (restricted to calendar/alarm apps — a denied review would block the release); the watchdog now checks `canScheduleExactAlarms()` and falls back to inexact `set()` in the same window (`WatchdogReceiver`). **Prominent disclosure** for background location ships in-app — `PermissionsActivity` shows a one-time "Location access for theft protection" dialog before the first location request (states background use, data-only-to-own-account, never-sold, how to revoke) and now requests `ACCESS_BACKGROUND_LOCATION` in the same dialog as foreground location (Play-required pattern for targetSdk 30+); the manifest carries the disclosure rationale next to the permission. Bytecode target upgraded to **Java 17** (compileOptions + `kotlinOptions.jvmTarget`).
- **Real-world readiness review**: `docs/readiness-review.md` — the full-stack audit (strengths, fixes in this release, verification results, open items, suggested v1.4.0 cut).

### Changed

- `test_e2e.py` sys.modules eviction list now also evicts `user_security` and `media_store` (module-level `config`/`database` binders) so full-suite runs can't mix DB instances; the server suite is green at **381 passed** across all files.
- `play-store-checklist.md` updated: `USE_EXACT_ALARM` removal recorded, prominent disclosure marked implemented, Java 17 toolchain noted, gate checklist updated.

### Deployed — v1.4.0 release cut + live (2026-08-05)

- **v1.4.0 release**: `VERSION` bumped to 1.4.0 (versionCode 6), recovery drill **12/12 PASS** against a throwaway local instance, signed release APK rebuilt with the same certificate as v1.3.1 (`024cbb34…` — in-place upgrades safe; SHA-256 `0e3206f4…`, 7,493,752 bytes), staged to `server/static/apk/` (`magneetar-v1.4.0-release.apk` + `magneetar-latest.apk`, bind-mounted into the live server) + `dashboard/public/apk/` for image builds. `docker-compose.yml` `APP_VERSION` build arg bumped to 1.4.0 (the version is a **build arg** baked to `/VERSION` — a compose-edit alone doesn't change it; the image must be rebuilt). `docs/PROJECT_STATUS.md` totals refreshed (381 backend + 173 dashboard = 554).
- **Deployed to production**: server + dashboard images rebuilt and recreated; `/health` reports `1.4.0`, `/apk/checksum` serves the v1.4.0 APK. New endpoints verified live: 2FA setup (401 unauth), forgot-password (200 anti-enumeration response), verify-email (401 bad token), login (401 unknown account).
- **Fix found during release prep**: the emailed verification link pointed at a dashboard route that did not exist — `/verify-email` 404'd. New `dashboard/src/app/verify-email/page.tsx` (auto-verifies the token, with verified / broken-link / expired / error states) + 4 tests. Live route returns 200.
- **Live 2FA lifecycle smoke on production** (self-cleaning throwaway account): register → setup (QR) → enable with a live pyotp code → login returns challenge (no session token) → challenge token rejected as a session (401) → wrong code 401 → TOTP login issues real tokens → disable (password step-up) → account deleted (200) and login on the deleted account fails (401). Zero residue.

- **v1.3.1 release APK shipped + deployed (production was serving a stale build)**: the live download endpoint was still serving the **v1.3.0 APK built Aug 4 09:02** — built *before* the SMS offline relay, the command-loop (at-most-once) fix, and Kalman fusion landed — so every fresh install had none of the new behavior. Root cause of "I can't see any of the changes": the API (`/health` → 1.3.1) and dashboard bundle were deployed and current, but the **Android binary users download was stale**. A fresh signed `assembleRelease` was built from the current tree (versionName read from repo `VERSION` → 1.3.1, versionCode 5), **verified signed with the same certificate** as the previous APK (SHA-256 `024cbb34…` — upgrades install in place, no data loss), and deployed to `server/static/apk/` as `magneetar-v1.3.1-release.apk` + `magneetar-latest.apk` (bind-mounted live into the server container) and `dashboard/public/apk/` for future image builds. Verified live: `/apk/checksum` now reports the new SHA-256 (`9d34fd75…`, 7,493,412 bytes), `/apk/download` enforces its ticket gate (403 unauthenticated), and `app.magneetar.me/download` serves 200. Users must **re-download + install the APK** from the dashboard download page to pick up the new features.

### Fixed

- **Google Play Protect blocks sideloaded installs (diagnosed + consumer mitigation)**: users installing the APK from the download page hit Play Protect's hard block ("This app can request access to sensitive data"). Root cause: Magneetar's manifest legitimately declares the permission profile malware abuses — `RECEIVE_SMS` (offline command relay), `SEND_SMS`, `READ_PHONE_STATE`, Device Admin (uninstall resistance), `ACCESS_BACKGROUND_LOCATION`, `CAMERA`/`RECORD_AUDIO` — and the release key is new with zero install history, so Google blocks every sideload deterministically. **The app is not malware** — a code audit confirmed real defense-in-depth (SMS sender allowlist + SHA-256 pairing code + 24h brute-force cooldown, device-admin user consent, TLS-only release builds). **The core trade-off is structural: the SMS relay needs `RECEIVE_SMS`, and `RECEIVE_SMS` is the strongest sideload-block trigger — sideloading and the relay cannot both be frictionless; the full fix is Play Store distribution** (trust baseline + permission declarations + Data Safety form). Consumer mitigation shipped: the download page now has a "Android says Play Protect blocked this app?" guide (why the warning appears, the exact **More details → Install anyway** flow, and checksum/signature verification as the trust mechanism). Full root-cause table + remediation options (Play distribution, trigger-surface reduction, split builds, appeal) recorded in `docs/play-store-checklist.md`.

### Added

- **Offline Command Relay (SMS) — commands that work with ZERO internet**: the game-changer for stolen phones with no data plan. When a device is offline, the dashboard can still command it over the cellular SMS channel — every phone receives SMS even with no data. The server texts the command to the phone's SIM number in the `MAGNET <pairing-code> CMD <id> <command>` wire format; the app intercepts it (`RECEIVE_SMS`), verifies the per-device pairing code **and** the sender, and executes it through the exact same `handleCommand` path as a polled command — siren, lock, wipe, location burst all work offline. Location comes back as a coarse **cell-tower fingerprint** (MCC/MNC/TAC/CID, captured with zero internet, resolved server-side by the pluggable cell-locate endpoint with graceful degradation) plus the exact GPS fix uploaded the moment any connectivity returns (OfflineOutbox store-and-forward). Commands are **opt-in per device** (`sms_phone` + `sms_commands_enabled`, E.164 validated), cost-controlled (per-device 5 SMS/min cap + only relayed when actually offline), sender-allowlisted (only the server's Twilio number or the Termii alphanumeric may issue — a leaked pairing code can't be replayed from a random number), and the app-side receiver is **default OFF** with an in-app toggle + optional SMS permissions in onboarding. The SMS reply return channel (`MT-ACK`) is ingested by a Twilio-signature-verified `/api/sms/inbound` webhook that matches the sender to the device's number before acking.
- **SMS relay reliability fixes from code review**: a failed SMS send no longer strands the command — it falls back to `delivery_channel='poll'` (with the poll expiry) so the command stays deliverable when the device returns; keyless devices (no `device_key_hash`) are never SMS-routed; the Android ack only queues the offline outbox on genuine network failure / auth death (not server rejections); and `/api/config` now exposes `sms_relay_number` for the app's sender allowlist.

### Fixed

- **Command re-execution loop + stuck PENDING (production bug)**: the protocol is poll-until-ack — the server re-delivers any still-`pending` command every 10s and only stops when the device acks. A **lost ack** (network blip, auth death, service restart mid-ack) left the command pending, and the device **re-executed it on every poll** — a siren replaying, a fresh photo/burst every 10s — until expiry (5-30 min), while the dashboard kept showing PENDING (its `command_ack` WebSocket handler was empty, so even successes looked stale for up to 10s). Fixes, all locked by tests:
  - **At-most-once execution (Android)**: new `RecentCommandTracker` (pure-JVM, SharedPreferences-persisted, 60-min retention > the 30-min max poll expiry) records every command outcome. The command loop consults it before executing: a re-delivered command is **re-acked with its recorded status (idempotent server-side) instead of re-executed** — the loop converges the moment connectivity returns, with zero second executions. Restart-safe, so the aggressive watchdog restarts on Chinese OEMs can't reintroduce the loop. 8 new JVM unit tests.
  - **Outbox flush before poll**: the command loop now flushes the offline ack outbox before each poll, so a queued ack lands before the next poll could re-deliver the command (OfflineOutbox.take is synchronized — concurrent heartbeat flush is safe; enqueueAck dedupes by command id).
  - **Instant dashboard status**: `command_ack` WebSocket messages now flip the row's status/failure_reason in place via the new `applyCommandAck` store action (no fabricated client-clock `executed_at` — the next poll fills the server's real timestamp). 2 new `useWebSocket.test.ts` regressions.
  - **Server regression**: `test_reack_is_idempotent_and_never_redelivered` locks the contract — a duplicate ack is accepted (200), the command stays executed, and the poll never re-delivers it.

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
