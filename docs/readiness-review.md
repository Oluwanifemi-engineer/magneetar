# Magneetar — Real-World Readiness Review

**Review date:** 2026-08-05 · **Version reviewed:** 1.3.1 → 1.4.0-dev
**Scope:** full-stack audit (server, dashboard, Android app, scripts, deployment, Play Store readiness)

---

## Verdict

**Substantially production-ready — with account-security and Play-policy gaps closed in this review.** The
core product loop (register → track → theft detection → evidence → remote commands → recovery) is proven
end-to-end and has been running in production. What was missing for a *real-world* product was hardening on
three fronts, all addressed here: **account security** (2FA, password reset, email verification), **deployment
resilience** (evidence-backed backups, registration abuse caps), and **Play Store policy compliance**
(exact-alarm permission, prominent disclosure, modern toolchain).

Remaining before full public launch: see [Open items](#open-items) — they are operational decisions and
manual verifications, not code gaps.

---

## 1. What was already strong (verified, unchanged)

| Area | Evidence |
|---|---|
| Core anti-theft loop | `recovery-drill.sh` 12/12 steps PASS (detect → track → evidence → guardian → recovery) |
| Command reliability | At-most-once execution (`RecentCommandTracker`), honest acks, stuck-PENDING eliminated |
| Theft detection | Sentinel scoring with false-positive confirmation gate, threshold-reachable (79-cap fix) |
| Multi-user ownership | Ownership scoping on every endpoint, WS owner-filtered, per-user device limits, ghost-owner adoption |
| Offline SMS relay | Pairing-code + sender allowlist, rate-capped, opt-in per device |
| Uninstall protection | Active Device Admin + device-owner hard block |
| Evidence integrity | SHA-256 chain of custody, PDF export, step-up-gated deletion |
| Data plane | Single SQLite plane on a persisted volume (no more rebuild wipe-outs) |
| Auth hardening | bcrypt, token revocation, per-endpoint rate limits, WebSocket auth matrix |
| CI/CD | Pre-commit (flake8, tsc, shellcheck), GitHub Actions tests + APK build |

## 2. What this review found and fixed

### 2.1 Account security (server + dashboard + Android) — NEW

- **TOTP two-factor authentication**: per-account `totp_enabled` + encrypted TOTP secret
  (`user_security.py`). Full lifecycle: setup (QR data-URI) → enable (verified code, replay-safe) →
  disable (password step-up) → login challenge. Login answers `{requires_2fa, two_factor_token}`; a
  dedicated `/api/auth/user/login/2fa` exchanges code + challenge for real tokens. **Security fix found
  during review:** the 2FA *challenge* JWT previously passed `get_current_user` (it only checked the
  `user:` subject prefix) — it now requires the exact `type` claim, so a challenge token can never be
  used as a dashboard session. Brute-force lockout (5 failed codes → 10-minute cooldown) + per-token
  replay guard.
- **Password reset**: `/api/auth/forgot-password` (rate-limited, always-same response — no user
  enumeration) → email token → `/api/auth/reset-password` with strong-new-password validation; tokens
  are single-use + 30-minute TTL.
- **Email verification**: `/api/auth/verify-email` + resend; `/me` exposes `email_verified`.
- **Dashboard UI**: login page 2FA step, Settings → Security panel (enable 2FA with QR, verify email,
  manage), `/forgot-password` + `/reset-password` pages. **Android**: `SignInActivity` 2FA code step.
- **Tests**: 24 new backend (`test_user_security.py`) + 8 dashboard suites/32 tests.

### 2.2 Abuse & resource hardening (server) — NEW

- **Unowned-device cap** (`MAX_UNOWNED_DEVICES`, default 250): the master API key ships in every APK,
  so unlinked registrations used to be unbounded storage pollution. Account-linked devices stay bounded
  by the per-user limit instead. 403 + no row when exceeded.
- **Evidence-retention purge**: `purge_old_data` no longer deletes media owned by **active** cases;
  only stale evidence beyond retention dies, so an open investigation keeps its photos/audio.
- **Registration/login abuse**: `MAX_UNOWNED_DEVICES` + existing rate limits + new user-security rate
  caps (2FA attempts, password resets, verify emails) cover the spam surface.

### 2.3 Backup & recovery (scripts) — NEW

- `backup-db.sh` now backs up **media evidence too** (gzipped tarball of `/app/data/media`) alongside
  the SQLite snapshot, with `--restore-media` and matching rotation.
- **Off-site sync**: optional `rclone` push of both artifacts to a remote (`MT_RCLONE_REMOTE`), skipped
  gracefully when rclone or the remote is unconfigured. 3-2-1 backups for the DB *and* the evidence.
- `test-backup-smoke.sh` extended to cover the media tarball round-trip.

### 2.4 Play Store policy & toolchain (Android) — NEW

- **`USE_EXACT_ALARM` removed** (Play restricts it to calendar/alarm apps; a denied review blocks the
  release). The watchdog uses exact alarms only when `canScheduleExactAlarms()` is true and silently
  falls back to inexact `set()` — the survival benefit of exactness is marginal given the dual-FGS +
  WorkManager + OEM-event redundancy layers.
- **Prominent disclosure for background location**: in-app one-time dialog before the first location
  request (purpose, data-only-to-own-account, never-sold, how to revoke) + manifest rationale comment.
  `ACCESS_BACKGROUND_LOCATION` is requested in the same dialog as foreground location (Play-required
  pattern). Screenshots still needed for the Play declaration.
- **Java 17 bytecode target** (compileOptions + `kotlinOptions.jvmTarget`) — current AGP/AndroidX and
  Play 2025+ expectations.
- `SCHEDULE_EXACT_ALARM` kept (user-grantable), `SYSTEM_ALERT_WINDOW` rationale documented.

## 3. Verification

| Check | Result |
|---|---|
| Backend tests (full suite) | **381 passed** + flake8 clean (24 new user-security, 2 new cap/purge) |
| Dashboard | `tsc --noEmit` clean; **106 passed** across 14 suites (32 new auth/2FA tests) |
| Android | `compileDebugKotlin` + `testDebugUnitTest` green (JDK 21; Java 17 target) |
| Scripts | `bash -n` + smoke test green for backup-db (DB + media + restore) |
| Server suite order-safety | `test_e2e` sys.modules eviction list extended for the new module-level-binding modules |

## 4. Open items (operational / manual — not code gaps)

- [ ] **Play Console actions**: Data Safety form (location/photos collection), Permissions Declaration
      (background location, exact alarm, overlay), Device Admin EMM/BYOD declaration decision,
      disclosure screenshots, IARC + 18+ audience, privacy policy at public URL.
- [ ] **Secrets hygiene**: rotate the release-keystore fallback password; back keystore up off-machine.
- [ ] **Email delivery**: verify transactional email (reset/verify links) against the configured
      provider (SendGrid key / provider choice) — `send_transactional_email` is best-effort.
- [ ] **Real-device checks**: background-location + FGS behavior on Android 15 hardware; SMS relay
      round-trip on a physical phone.
- [ ] **Postgres parity**: deletion/retention purge paths documented as SQLite-scoped; a PG-backed
      deployment needs equivalent routes.
- [ ] **Play distribution**: sideload friction (Play Protect block) is only fully solved by listing on
      the Play Store — the fundamental conflict is documented in `play-store-checklist.md`.

## 5. Suggested next release

Cut **v1.4.0** with: 2FA + password reset + email verification, unowned-device cap, evidence-safe
retention purge, media + off-site backups, exact-alarm cleanup, prominent disclosure, Java 17.
Bump `VERSION` to `1.4.0`, rebuild the signed APK, deploy server + dashboard, update
`docs/PROJECT_STATUS.md` totals.
