# Magneetar — Real-World Validation Plan (pre-Play gate)

**Owner decision 2026-08-14 (ADR-0006):** no Play Store production
submission until Magneetar is fully tested in the real world, against
real-world conditions, and **approved by users**. This document defines what
that means operationally: the device matrix, the conditions to exercise, the
feedback loop, and the exit criteria that turn a pass into an approved
launch.

Nothing here replaces the automated gates — those run continuously
(549 backend / 198 dashboard / Android JVM, live E2E against production).
This program tests what automation cannot: real phones, real users, real
days.

---

## 1. Channels during validation

| Channel | Role |
|---|---|
| **magneetar.me/download** | PRIMARY — serves the verified play-clean v1.4.3 APK (`magneetar-v1.4.3-release.apk`, SHA-256 `c4c89e25…`, zero SMS/phone perms). This is how testers install. |
| **Sideload SMS-relay build** | Internal only — `magneetar-v1.4.3-sideload-release.apk` (explicit filename, never the resolver default). Used to validate the offline SMS relay channel on one device. |
| **Google Play** | BLOCKED until G1 AND G2 below both pass. |

---

## 2. Gate G1 — Sideload / download-page real-world validation

### 2.1 Device matrix (target: ≥6 devices, ≥4 OEMs, Android 10 → 15/16)

| # | Class | Why it's in the matrix |
|---|---|---|
| 1 | Samsung A-series (existing fleet phone, e.g. SM-A037F) | Baseline; already live-tested |
| 2 | **Tecno / Infinix / Itel** (Transsion) — 1–2 devices | The core Nigerian/emerging-market segment; aggressive battery killers (OEMUtils covers them) |
| 3 | Xiaomi / Redmi (MIUI) | Battery optimization + autostart quirks |
| 4 | A low-end device (2–3 GB RAM, Android 10–12) | Memory pressure, slow GPS, background death risk |
| 5 | An Android 14/15 device | Foreground-service + background-execution rules (FGS camera/mic) |
| 6 | AOSP/emulator image **without a "network" location provider** | Regression-locks the v1.4.2 provider fix (tracking must not crash-loop) |

Minimum: every device runs the build **2 continuous weeks as a daily
driver** (charges overnight, real commutes, real app usage).

### 2.2 Real-world conditions to exercise (each maps to a pass/fail record)

- **OEM battery killers** — background survival over a full day: tracking
  service still pinging (server `last_seen` fresh) after the phone sits
  unused; no user action needed to keep it alive (Watchdog / Environment /
  HealthCheck workers did their job).
- **Poor / flaky networks** — 2G/3G, dead zones, airplane mode toggle:
  offline queue buffers and syncs on reconnect without gaps or duplicates.
- **SIM swap** — the `sim_changed` always-deliver alert fires (server alert
  row + FCM push; SMS/WhatsApp channels skipped — Twilio on hold).
- **GPS-off / location services disabled** — graceful degradation, no crash
  (the GuardianBeaconScanner + TrackingService v1.4.2 hardening).
- **Low battery / battery saver** — Find Network scanner paces itself;
  tracking continues within OEM rules.
- **Android 14/15 background execution** — evidence capture (front photo +
  audio) from a **locked screen** during an armed theft response; FGS
  notification visible; honest acks.
- **Play Protect** — tester follows the download-page install path; the
  pause-scanning workaround documented there is the known cost of
  sideloading (a Play listing makes it moot — that is the point of G2).
- **Device-admin uninstall protection** — admin deactivation fires the
  server theft-signal; the v1.4.2 whitelist does not block the app's own
  setup dialogs (battery-optimization grant, precise-location change).
- **Recovery drill** — the 12/12 drill (theft → Sentinel → recovery request →
  BLE beacon → guardian sighting → close) on **every** device in the matrix.
- **Geofence auto-actions** — safe-zone exit fires the configured capture /
  siren policy exactly once.
- **Command round-trip latency** — alarm/lock from the dashboard → device
  executes → dashboard shows `executed` (ack path), from real networks.
- **Battery drain** — 48h measurement per device; report mAh/day. Flag any
  device draining > ~15% of battery per day from the app alone.

### 2.3 Users & feedback

- **≥5 real users** (not the developer), spread across the device matrix,
  each running it daily for ≥2 weeks. Recruitment: family/WhatsApp groups
  and the Guardian Network's own user base — the product is literally built
  for this. Copy-paste WhatsApp messages: `docs/tester-recruitment-message.md`.
- **Feedback loop:** weekly check-in via the structured form in
  `docs/tester-feedback-form.md` (bugs, battery life, tracking reliability,
  "would you keep using this?"). Every report is triaged and answered —
  testers who feel heard stay for G2.
- **Tracking:** per-device, per-condition pass/fail log in
  `docs/g1-validation-tracker.md` (roster, condition matrix, drill log,
  battery table, exit checklist).
- **Server-side signals** supplement self-reports: `error_log` table rows,
  `/health` uptime, per-device `last_seen` gaps (silent-tracking-death
  detector), and Sentry crash events (see §5).
- Every report triaged: P0 = silent failure / data loss / theft-response
  broken; P1 = feature broken with a workaround; P2 = cosmetic. P0s are
  fixed and re-deployed before the gate can pass.

### 2.4 G1 exit criteria (ALL must hold)

1. **Zero open P0 bugs** — and no new P0 in the final 7 days.
2. **No silent-tracking-death** — no device shows an unexplained `last_seen`
   gap > 30 min while armed, across the matrix, in the final week.
3. **Recovery drill 12/12 on every device** in the matrix.
4. **Battery drain within band** — no device over the drain budget.
5. **User approval recorded** — ≥80% of testers answer "keep using /
   recommend" and every tester's P1/P2 findings are closed or explicitly
   accepted by the owner.
6. The matrix includes the regression cases that bit us before: a device
   with **no network location provider** (v1.4.2 fix) and an Android 14/15
   device.

Exit is documented (drill logs + feedback-form results + fix list), not
assumed.

---

## 3. Gate G2 — Play closed testing (user approval on the Play channel)

Only after G1 passes:

1. Upload the v1.4.3 AAB (`server/static/apk/magneetar-v1.4.3-play.aab`) to
   **Internal testing** first (~hours) → smoke-test the Play-signed APKs on
   a real device.
2. Promote to **Closed testing** (expect 24–72h review; up to 7d for a new
   account with device-admin). Recruit **≥12 active testers** (the G1
   cohort + new recruits) who keep the app installed for **14 continuous
   days** — this is both Play's hard gate for production access AND the
   real-world user-approval gate.
3. Same exit criteria as G1 applied to the Play-served build, plus:
   crash-free rate ≥ 99.5% over the window (Play Console quality page) and
   **no policy flags** (device-admin / background-location manual-review
   questions answered with G1's real-user evidence).
4. **Tester approval recorded** — explicit sign-off from the tester cohort
   (not just "no crashes").

Only then: apply for production access → staged rollout (1–5% → 10–20% →
50% → 100%, per `docs/DISTRIBUTION_PLAN.md` §3 Phase 4, with the 30-day
monitoring cadence from §5).

---

## 4. What does NOT block this program

- **Play Console prep** (screenshots, declaration forms, listing copy) can
  continue in parallel — `docs/PLAY_STORE_LISTING.md` is already written.
- **Version cadence** — if G1 surfaces fixes, they ship as 1.4.3+ to the
  download page; the AAB uploaded at G2 is the latest validated build
  (versionCode strictly increasing).
- **Twilio** — on hold by owner (no credits); FCM push + Resend email are
  live and cover alerting during validation. Recharge stays a prerequisite
  for launch-day alert coverage only.

---

## 5. Sentry crash visibility (recommended for G1)

> **Status: wired but NOT yet enabled (2026-08-14)** — the build config is
> complete and inert (no DSN configured), so no build is affected. Enable
> whenever ready by following the steps below; until then G1 relies on server
> `error_log` + `last_seen` monitoring + the feedback forms.

Server `error_log` + feedback forms catch what people notice; Sentry catches
what they don't — every uncaught Java/Kotlin crash, with device model, OS
version, breadcrumbs, and a readable stack trace, reported automatically.

The Android app is **already fully wired** (sentry-android 7.14.0, the
Gradle plugin, manual init in `MainActivity.initSentrySafe`, ProGuard keep
rules) and does nothing until a DSN is configured.

**Enable in ~3 minutes:**

1. Create a free Sentry account → new project → **Android** → copy the DSN
   (the `https://...@sentry.io/<project>` string).
2. Add to `android-app/local.properties` (gitignored):
   ```
   SENTRY_DSN=https://<key>@sentry.io/<project>
   # Optional — readable (de-obfuscated) release stack traces:
   SENTRY_AUTH_TOKEN=sntrys_...
   SENTRY_ORG=<your-org-slug>
   SENTRY_PROJECT=<project-slug>
   ```
   (Equivalent env vars: `MT_SENTRY_DSN`, `MT_SENTRY_AUTH_TOKEN`,
   `MT_SENTRY_ORG`, `MT_SENTRY_PROJECT`.)
3. Rebuild the release APK (`assembleSideloadRelease` /
   `assemblePlayRelease`) → install → crashes land in Sentry. When the
   auth token + org + project are set, release builds also **auto-upload
   ProGuard mappings** so traces read like source.

Graded by design (never breaks a build): DSN alone = crash events with
obfuscated release traces; DSN + token + org + project = full mapping
upload. Verify once: force a test crash (or catch a real G1 one) and confirm
the event + (if configured) a readable stack trace in Sentry.

## 6. Definition of done (this plan)

- [ ] Device matrix ≥6 devices / ≥4 OEMs, each ≥2 weeks daily use
- [ ] All §2.2 conditions exercised with a pass/fail record per device
- [ ] Recovery drill 12/12 on every device
- [ ] ≥5 real users, ≥80% approval, findings closed or owner-accepted
- [ ] G1 exit documented → G2 (Play closed testing) started
- [ ] 14-day closed testing with ≥12 active testers, ≥99.5% crash-free
- [ ] Tester cohort signs off → production access requested
