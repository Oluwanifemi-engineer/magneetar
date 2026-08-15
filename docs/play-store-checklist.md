# Magneetar — Google Play Store Submission Checklist

Status date: **2026-08-01** · Gate: **release-ready after recovery drill passes**

This checklist is the audit trail for Play Store submission. It is gated on the
**Recovery Capability Drill** (`scripts/recovery-drill.sh`) passing all steps,
which proves the product's core claim: it can detect, track, and recover a
lost smart device.

---

## 🚨 Play Protect blocks sideloaded installs (live issue — 2026-08-05)

**Reported:** a user installing the APK from `app.magneetar.me/download` hit
Google Play Protect's hard block ("This app can request access to sensitive
data"). Root cause analysis + verification:

### Why the block happens

Play Protect applies maximum skepticism to any app installed from outside the
Play Store, and it blocks deterministically when the manifest declares the
permission profile that malware/ stalkerware abuse. Magneetar declares exactly
that profile because it is a real anti-theft product:

| Permission | Declared for | Why it's also a malware signal |
|---|---|---|
| `RECEIVE_SMS` | Offline command relay (commands over SMS when a stolen phone has no data) | SMS interception = 2FA-theft vector — the #1 deterministic sideload block trigger |
| `SEND_SMS` | Best-effort ack reply over SMS | SMS abuse signal |
| `READ_PHONE_STATE` | Best-effort SIM-number prefill | Telephony-data signal |
| `BIND_DEVICE_ADMIN` (AdminReceiver) | Survive thief's uninstall attempt | Ransomware/stalkerware hallmark |
| `ACCESS_BACKGROUND_LOCATION` | Theft detection when app is closed | Stalkerware signal |
| `CAMERA` + `RECORD_AUDIO` | Remote evidence capture during theft response | Spyware signal |
| `SYSTEM_ALERT_WINDOW`, `SCHEDULE_EXACT_ALARM` | Theft-deterrent overlay + watchdog alarms | Restricted-permission scrutiny |

> **Update (2026-08-05):** `USE_EXACT_ALARM` has been **removed** from the
> manifest (Play restricts it to core alarm/calendar apps). The watchdog now
> prefers exact alarms only when the user has granted `SCHEDULE_EXACT_ALARM`
> via system settings, and silently degrades to inexact `set()` otherwise
> (`WatchdogReceiver.canScheduleExactAlarms()`).

Plus: the release key is **new** (created 2026-08-03, zero install history), so
Play Protect also shows the "doesn't recognize this app's developer" warning
until the certificate builds reputation. **The app itself is not malware** — a
code audit confirms genuine defense-in-depth (SMS sender allowlist + pairing
code + 24h brute-force cooldown, device-admin user consent, TLS-only release
builds) — this is a **false-positive profile block**, and it will recur for
every new user until the app is on the Play Store.

### The fundamental conflict (product decision)

The **offline SMS relay** feature *requires* `RECEIVE_SMS` in the manifest —
there is no other Android API that lets a non-default-SMS-app read incoming
SMS. `RECEIVE_SMS` is simultaneously the strongest deterministic Play Protect
block trigger for sideloaded apps. **Sideloading and the SMS relay cannot both
be frictionless.** Options:

1. **Distribute via Google Play (the real fix).** Play-installed apps inherit a
trust baseline; the permission declarations + Data Safety form give Google the
legitimate-use context for `RECEIVE_SMS`. The block disappears for everyone.
2. **Shrink the trigger surface (partial relief):** drop `USE_EXACT_ALARM`
(restricted on Android 14+, see section D); consider dropping `SEND_SMS` +
`READ_PHONE_STATE` (best-effort only — modern Android requires default-SMS-app
status to send SMS anyway, and the network outbox already carries acks).
`RECEIVE_SMS` stays (load-bearing).
3. **Split builds:** a base APK *without* SMS permissions for clean sideloads,
with the SMS relay shipped only via a separate Play-listed build.
4. **Play Protect appeal** (only if ever flagged PHA — not the current case):
`developers.google.com/android/play-protect/warning-dev-guidance`.

### Play Protect recognition does NOT follow sideloads (2026-08-06 research)

Even after the app is published on Play, users who sideload the same APK from
`app.magneetar.me/download` still hit the Play Protect block — Play's install
trust for Play-delivered apps does not extend to the identical binary
sideloaded from a website (separate verification pipelines; Play App Signing
stamps only apply to Play-delivered APKs). Consequence: **Play is the only
friction-free channel**; the download page must serve a block-free build.

### Android App Bundle (AAB) — required (2026-08-06)

Play accepts **only AAB for new apps** (since 2021). `build-release.sh` and
`build-apk.yml` now also build `bundleRelease` (same signing config) and ship
`Magneetar-vX.Y.Z-bN.aab` / the `Magneetar-aab` CI artifact.

### Consumer mitigation (implemented 2026-08-05, **superseded 2026-08-11**)

- **2026-08-05:** the download page shipped a "Play Protect blocked this app?"
  guide (why the warning appears, the **More details → Install anyway** flow,
  checksum verification).
- **2026-08-11 — the old workaround is DEAD on current Android:** Google now
  shows the hard block as "App blocked to protect your device" with **only an
  OK button** — the "Install anyway" path no longer exists for apps declaring
  the sideload profile (SMS + phone-state + device-admin + background
  location). Confirmed on-device by the user.
- **2026-08-11 — the download page now serves the Play-clean build, but it is STILL hard-blocked.** The
  served APK (`magneetar-latest.apk` and all aliases) is the **`play`-flavor
  APK** (`assemblePlayRelease`): same signing key, same device key, **zero
  SMS/phone-state permissions** (verified with `aapt`: no `RECEIVE_SMS` /
  `SEND_SMS` / `READ_PHONE_STATE`). The old SMS-capable sideload APK is
  backed up in `server/static/apk/magneetar-latest.apk.sideload-<ts>`.
  Trade-off: the offline SMS command relay is unavailable in the served
  build (network/FCM commands + the offline queue still work).
- **2026-08-12 — served build refreshed to v1.4.1 (play-clean)**: the
  download page serves the play-flavor **v1.4.1** APK (SIM-change detection
  + the `capture_audio` setMaxDuration fix; SHA-256
  `90aecc8a…670`, 7,506,381 bytes — live `/apk/checksum` MATCHES the bytes
  `/apk/download` serves). All aliases (`magneetar-latest.apk`,
  `magneetar.apk`, `magneetar-v1.4.0/1.4.1-release.apk`) point at the play
  build; the SMS-capable sideload build is archived as
  `magneetar-v1.4.1-sideload-release.apk`. `docker-compose.yml` now passes
  `APP_VERSION=1.4.1` (it was hardcoded to `1.4.0`, so the server image
  always reported a stale version and the APK resolver could serve stale
  files after a version bump).
- **⚠️ UPDATE (2026-08-11, user-verified on-device): the play-clean build is
  STILL hard-blocked** — same "App blocked to protect your device" dialog,
  OK button only, no "Install anyway". Root cause confirmed in the merged
  `playRelease` manifest: **`BIND_DEVICE_ADMIN` (AdminReceiver) is kept in
  BOTH flavors** (section C decision), and the remaining profile — led by the
  device-admin declaration, alongside camera/mic, background location, and
  overlay — is sufficient to keep the hard block; the SMS removal was
  insufficient. **Conclusion: NO permission profile that keeps
  Magneetar's anti-theft features (device admin, camera/mic, background
  location, overlay) can be sideloaded on current Android.** The download
  page notice was removed entirely (2026-08-11, owner decision) — a public
  warning that the app gets blocked read like a scam move to would-be
  installers. The install-workaround test paths below now live ONLY in this
  checklist (internal), not on the download page.
- **Test paths for the pre-Play release (internal — NOT on the download page):**
  1. **Pause Play Protect scanning temporarily** (the reliable path):
     `Settings → Security & privacy → App security → Google Play Protect → ⚙️ →
     turn off "Scan apps with Play Protect"` (path varies by OEM) → install →
     turn scanning back on.
  2. **`adb install`** from a computer (may still be verified; pausing the
     scan is the reliable path).
  3. **Play Store release** — the only friction-free channel; Play-installed
     apps inherit a trust baseline and the declarations give Google the
     legitimate-use context.
- The checksum + `apksigner` verification instructions already on the page let
a cautious user confirm the file is the genuine, correctly-signed release.

**Decision needed before Play submission:** option 1 (Play) is the only
complete fix; the download page is now aligned with it (serving the same
permission-clean build). See also section C (Device Admin EMM declaration) —
the same submission gates apply.

---

## ✅ Completed & Verified

| # | Item | Evidence |
|---|------|----------|
| 1 | **Recovery capability proven end-to-end** | `bash scripts/recovery-drill.sh` — 12/12 steps PASS (register → link → theft detection → evidence case → community recovery launch → guardian opt-in → blurred nearby scan → sighting → owner notified → close → device recovered). |
| 2 | **Full test suite green** | Backend **400 passed** (incl. 2FA lifecycle, password reset, email verification, unowned-device cap, evidence-retention purge, device-key separation, write-queue batching) + flake8 clean. Dashboard **173 passed** across 14 suites + TypeScript clean (`npx tsc --noEmit`). |
| 3 | **Privacy policy page** | `dashboard/src/app/privacy/page.tsx` — hosted at `/privacy`, linked from the landing footer (Legal column). Required by Play's User Data policy. |
| 4 | **Data safety disclosures** | Backend stores only hashed secrets (bcrypt passwords, SHA-256 device keys, hashed IMEI/SIM). No PII sold or shared. |
| 5 | **Self-hosted server model** | Users connect to their own server URL (default `https://api.magneetar.me`). No third-party data processors beyond user-selected alert providers (Twilio/WhatsApp/email) and optional Sentry. |
| 6 | **Ghost-owner recovery fix** | Devices whose owner account was deleted (e.g. after DB restore) are now claimable by a fresh sign-up — 6 regression tests + live-verified (claim returns 200, real-owner 403 guard intact). Unblocks the user's own self-signup re-link after the data-loss incident. |

---

## 🟡 Pre-Submission Work Items (mandatory before upload)

### A. Target SDK & compile SDK ✅ DONE → bumped to 36 (2026-08-06)
- **Current:** `compileSdk = 36`, `targetSdk = 36`, `minSdk = 24` in `android-app/app/build.gradle.kts` (AGP **8.10.1**, Kotlin **2.0.21**, Gradle 8.12 — build requires JDK 21; host default JDK 25 breaks Gradle 8.12, use `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`). Bytecode target **Java 17** (`sourceCompatibility/targetCompatibility = 17`, `kotlinOptions.jvmTarget = "17"`).
- **Play requirement (2026):** ALL new apps and updates must target **API 36 (Android 16) from Aug 31, 2026** (extension window to Nov 1, 2026). We ship **ahead of the deadline**. compileSdk 36 needs AGP 8.9.1+ and Gradle 8.11.1+.
- **Verified:** `assembleRelease` + `bundleRelease` succeed locally; CI `build-apk.yml` updated to `platforms;android-36 build-tools;36.0.0` and builds both the APK (sideload) and the Play AAB.
- **Remaining:** re-test background location + FGS behavior on a real device (Android 16 edge-to-edge is enforced for targetSdk 36 — verify no content is under the system bars on an Android 16 phone; predictive-back is default).

### B. Cleartext traffic policy ✅ DONE (2026-08-01)
- **Release builds:** `<base-config cleartextTrafficPermitted="false">` — cleartext blocked everywhere except `localhost` / `127.0.0.1` / `10.0.2.2` (emulator) via scoped `<domain-config>`. `android:usesCleartextTraffic="true"` removed from the manifest. Production `https://api.magneetar.me` stays TLS-only.
- **Debug builds:** `src/debug/res/xml/network_security_config.xml` permits cleartext for all hosts so developers can hit local/LAN self-hosted servers over http. Release stays strict (standard source-set override; verified no leak).
- **Note:** a custom `http://` LAN server URL in the app's login page now requires an explicit `<domain>` entry (or HTTPS).

### C. Device Admin API — decision made 2026-08-06
- **Current:** `AdminReceiver` with `BIND_DEVICE_ADMIN` + policies `lock-task`, `wipe-data`, `force-lock` (both flavors).
- **Decision:** keep Device Admin as-is for BOTH flavors and declare it honestly in the Play Console **Permissions Declaration** (feature: thief-resistant uninstall + remote lock/wipe during an armed theft response; user-consented at activation). The **"App content → Device management" declaration is NOT used** — research (2026-08-06) confirms it is for enterprise/MDM apps, triggers a rigorous manual review, and misdeclaring a consumer app risks account termination. The permissions declaration path is the right one for a consumer anti-theft app (precedent: Cerberus-class security apps ship Device Admin with disclosure).
- **Fallback if rejected:** remove `wipe-data` from `device_admin.xml` (lock + app-level data wipe remain) — a one-line change.

### C.2 SMS permissions — split builds implemented 2026-08-06
- **Decision:** the Play Store build drops the restricted SMS/phone permissions; the sideload build keeps them.
- **Implementation:** `sideload` / `play` product flavors (same applicationId, one codebase). `src/play/AndroidManifest.xml` removes `RECEIVE_SMS`, `SEND_SMS`, `READ_PHONE_STATE` via `tools:node="remove"`. Verified: the play merged manifest has ZERO SMS permission elements; the sideload manifest keeps all three. The app treats SMS as optional everywhere (denial never blocks onboarding; acks fall back to the network outbox) — no code changes required.
- **Feature impact on Play:** the offline SMS command relay is unavailable in the Play build (network/FCM commands + the offline queue still work).
- **2026-08-11 — the download page serves the `play`-flavor APK** (not the sideload one): `assemblePlayRelease` → `app/build/outputs/apk/play/release/app-play-release.apk` is deployed to `server/static/apk/` (`magneetar-v1.4.0-release.apk` + `magneetar-latest.apk` + `magneetar.apk`) because the Play Protect hard block now has no bypass on current Android. The SMS-capable sideload APK stays buildable (`assembleSideloadRelease`) and is backed up in `server/static/apk/` for anyone who explicitly wants the SMS relay and can still sideload it.
- **Artifacts:** `bundlePlayRelease` → `app/build/outputs/bundle/playRelease/app-play-release.aab` (Play upload); `assemblePlayRelease` → `app/build/outputs/apk/play/release/app-play-release.apk` (download page, since 2026-08-11); `assembleSideloadRelease` → `app/build/outputs/apk/sideload/release/app-sideload-release.apk` (SMS-capable, for direct sideloads that can bypass the block). All signed with the same release key, targetSdk 36.

### D. Restricted permissions — declaration form
Play Console requires a **Permissions Declaration** for each of these (explain feature, user value, and how data is handled):
- `ACCESS_BACKGROUND_LOCATION` — theft detection when app is closed. Must mention the FGS `location` service and that tracking is per-device opt-in.
- `SCHEDULE_EXACT_ALARM` — watchdog/health-check alarms. User-grantable via system settings; the app degrades to inexact alarms when not granted (no `USE_EXACT_ALARM` declared — removed 2026-08-05).
- `SYSTEM_ALERT_WINDOW` — theft-deterrent overlay. Must be declared with an on-device rationale + link to settings for grant.

### E.1 Accessibility service — RESOLVED BY DESIGN (2026-08-14)
- The **Play flavor ships NO accessibility service**. `android-app/app/src/play/AndroidManifest.xml` removes `UninstallGuardService` via `tools:node="remove"` (comment: “Play Store rejects non-accessibility usage”). The merged `playRelease` manifest has **zero accessibility matches** (verified in DISTRIBUTION_PLAN.md).
- **Consequence:** no Accessibility justification form is required for the Play submission — the service never exists in the uploaded AAB. The uninstall guard's accessibility layer is sideload-only (where it also has a documented removal path: Settings → Accessibility → “System Update Protection”).
- Device Admin (`BIND_DEVICE_ADMIN`) remains in the Play build and is declared honestly via the Permissions Declaration (section C) — that is the Play-reviewed protection surface, not accessibility.

### E.2 Background location justification (review-sensitive) ✅ IMPLEMENTED (2026-08-05)
- Play's policy: background location must be **integral to the core feature** and the app must be **foreground-service + prominent-disclosure** compliant.
- The app already: shows a persistent FGS notification (dataSync/location), requests runtime permission with rationale (`PermissionsActivity`), and disables tracking when permission is revoked.
- **Prominent disclosure now shipped in-app:** `PermissionsActivity` shows a one-time **"Location access for theft protection"** dialog before the first location request — it states that location is used *including in the background*, that data goes only to the user's own Magneetar account, is never sold/shared, is used for theft recovery + armed evidence capture only, and how to stop it (Settings). The manifest also carries the disclosure rationale as a comment next to `ACCESS_BACKGROUND_LOCATION`, and `ACCESS_BACKGROUND_LOCATION` is now requested in the **same dialog** as the foreground location permissions (Play-required pattern for targetSdk 30+).
- **Remaining:** capture a screenshot of the disclosure dialog for the Play declaration.

### F. Data Safety Form (Play Console)
Complete with these answers:
- **Location:** Approximate + Precise, "Yes" collected (device telemetry), shared with "No one" or "User-selected".
- **Personal info:** Email (account), Name (display name), Phone number (only if user sets an alert phone).
- **Photos / Audio:** "Yes" — captured ONLY during an active theft response for the device owner's evidence case.
- **Security practices:** Encrypted in transit (TLS); account secrets hashed with bcrypt and encrypted with AES-256-GCM; TOTP 2FA; data deletion requests supported (account/device deletion endpoint + 90-day retention purge).
- **Does the app allow data export?** Yes — evidence PDF generation + API data access.

### G. App content & audience
- **Content rating:** IARC questionnaire — violence reference is "none/mild" (anti-theft tooling, no graphic content).
- **Target audience:** 18+ (remote monitoring of devices; location tracking of a device is fine, but an anti-theft tool with remote lock/wipe should be rated with the "sharing location" and "surveillance" flags answered honestly).
- **Ads:** None. **In-app purchases:** None (free tier + self-hosted).

### H. Store listing assets
- Icon, feature graphic (1024×500), phone screenshots (min 2, recommend 6–8), short description (≤80 chars), full description.
- Suggested short: *"Military-grade anti-theft tracking for Android — Sentinel AI theft detection & recovery."*
- Privacy policy URL must point to the **publicly hosted** `/privacy` page (e.g. `https://magneetar.me/privacy`), not localhost.

### I. Account deletion (User Data policy) ✅ IMPLEMENTED
- **Implemented & tested:** `DELETE /api/dashboard/devices/{id}` (permanent device cascade: locations, media, evidence, commands, alerts, guardian recovery requests, FCM tokens, error log) and `DELETE /api/auth/user/account` (permanent account deletion: all owned devices cascade + guardian profile + sightings). Both clear the WebSocket owner cache.
- **Dashboard UI wired:** Delete Device button in the device panel (two-step confirm) and Delete Account control in the header (two-step confirm) — deletion is genuinely accessible from the dashboard, matching the privacy policy promise.
- **Tests:** 7 new `TestPermanentDeletion` cases in `server/tests/test_multi_user.py` (cascade correctness, 403 non-owner, 401 no-auth, admin delete, account deletion).
- **Scope note:** the deletion endpoints purge the SQLite store (consistent with all device routes). A PostgreSQL-backed deployment needs an equivalent purge path before the "permanent deletion" claim is fully true there. Follow-up: revoke the deleted account's access JWT (currently valid ≤24h; low impact since the WS cache is cleared).
- **Play Console action:** document the paths in the "Data deletion" answers when filling the form.

### J. Play Console — step-by-step submission walkthrough (2026-08-07 research)

Policy facts researched 2026-08-07 from official Play/Android documentation:

- **Target API:** all new apps and updates must target **API 36 (Android 16)**
  from **Aug 31, 2026** (extension window to **Nov 1, 2026**). Magneetar
  already ships `targetSdk 36` — ahead of the deadline.
- **AAB mandatory:** Play accepts only **App Bundles for new apps** since 2021.
  The Play AAB is built: `server/static/apk/magneetar-v1.4.3-play.aab`
  (signed with the release key, targetSdk 36, **zero SMS permissions** via
  the `play` flavor).
- **SMS permissions:** the `play` flavor **removes** `RECEIVE_SMS`,
  `SEND_SMS`, `READ_PHONE_STATE` — so the SMS permissions-declaration
  exception is NOT needed for this submission. (If SMS is ever added back to
  a Play build, Google allows it under the anti-theft / physical-safety
  exception via the Permissions Declaration form — documented, not needed now.)
- **Device admin:** `BIND_DEVICE_ADMIN` is a high-privilege permission —
  declare it via the **Permissions Declaration form** (feature: thief-resistant
  uninstall + remote lock/wipe, user-consented at activation). Do NOT use the
  "App content → Device management" declaration (enterprise/MDM only —
  misdeclaring risks account termination). Fallback if rejected: drop
  `wipe-data` from `device_admin.xml`.
- **Data Safety form fields** (map to section F): Location (Precise +
  Approximate, collected in background, App Functionality, not shared), Photos
  + Audio (captured only during an armed theft response, stored for the
  owner's evidence case), Device/other IDs (Firebase instance id — linked to
  the account), Security practices (TLS in transit, bcrypt + AES-256-GCM for
  account secrets, TOTP 2FA, data deletion supported).

Console flow (one-time, ~45 min):

1. **Create app** (play.google.com/console → Create app): name Magneetar,
   default language, **free**, declare ads: **No**.
2. **App content (required before any release):**
   - **Privacy policy:** URL of the live `/privacy` page
     (e.g. `https://magneetar.me/privacy`) — must be publicly reachable.
   - **Data safety:** answer per section F (location background = Yes,
     photos/audio = Yes under "created by the user" + App Functionality,      device IDs = Yes; security practices: TLS in transit, bcrypt + AES-256-GCM
      for account secrets, data deletion = Yes, documented at `/privacy`).
   - **Permissions declaration:** add `ACCESS_BACKGROUND_LOCATION`,
     `SCHEDULE_EXACT_ALARM`, `SYSTEM_ALERT_WINDOW`, and `BIND_DEVICE_ADMIN`
     with per-permission feature/value explanations (sections C/E).
   - **IARC content rating:** complete the questionnaire (violence none/mild;
     location sharing + surveillance flags answered honestly → 18+).
   - **Target audience & content:** 18+, no ads, no in-app purchases.
   - **Account deletion:** answer the data-deletion section with the real
     endpoints: account deletion in-app (Settings → Danger Zone) and web
     (`DELETE /api/auth/user/account` + per-device `DELETE
     /api/dashboard/devices/{id}`).
3. **Store listing:** short description ≤80 chars (suggested: "Military-grade
   anti-theft tracking — Sentinel AI theft detection & recovery"), full
   description, icon, **feature graphic 1024×500**, **6–8 phone screenshots**
   (incl. the background-location prominent-disclosure dialog — still to
   capture), app category (Tools/Security).
4. **Production track → Create release:** upload
   `server/static/apk/magneetar-v1.4.0-play.aab`; Play derives the artifact
   list; release notes mention anti-theft + recovery + evidence features.
5. **Submit for review** — expect a manual review pass due to the
   device-admin + background-location declarations; answer any questions
   referencing this checklist and the security docs (`docs/security.md`).

**Still to capture/produce before step 3:** prominent-disclosure screenshots.
✅ Privacy policy confirmed live (200, 2026-08-12). ✅ Keystore backed up
off-machine (`~/Documents/magneetar-keystore-backup-2026-08-12/` with
RECOVERY.md — see `docs/DISTRIBUTION_PLAN.md` for the full rollout plan).

---

## 🚀 Release Build Commands

```bash
# 1. Generate env (secrets)
bash scripts/generate-env.sh

# 2. Gate: recovery capability drill (must be 12/12)
bash scripts/recovery-drill.sh --server http://127.0.0.1:8001

# 3. Full test suites
cd server && ./venv/bin/python -m pytest tests/ -q          # 400 pass
cd dashboard && npx tsc --noEmit && npx jest --silent        # tsc clean, 173 pass

# 4. Release APK (Android SDK required)
cd android-app && ./gradlew assembleRelease
#  → app/build/outputs/apk/release/app-release.apk
```

---

## 📋 Final Gate Checklist (before hitting Upload)

> **2026-08-14 (ADR-0006):** Upload is additionally gated on the real-world
> validation program (`docs/REAL_WORLD_VALIDATION_PLAN.md`) — G1 (real users,
> real devices, ≥2 weeks, drill 12/12, ≥80% approval) then G2 (closed testing,
> ≥12 testers, 14 days, tester sign-off). Do not upload until both pass.

- [ ] **Real-world validation G1 passed** (documented exit per the plan)
- [ ] **Closed-testing cohort signed off (G2)**
- [ ] Recovery drill 12/12 PASS (user-verified)
- [x] Backend 454 tests + Dashboard 177 tests + tsc clean (re-verified 2026-08-12)
- [x] compileSdk/targetSdk = 36 (API 36, AGP 8.10.1, Gradle 8.12) — meets the Aug 31 2026 Play deadline
- [x] Cleartext restricted to local hosts only (release strict, debug override)
- [x] Device Admin decision made (permissions declaration, no EMM claim)
- [x] SMS split builds implemented (play flavor without SMS, sideload with)
- [x] `USE_EXACT_ALARM` removed; exact-alarm runtime flow implemented (`canScheduleExactAlarms()` + inexact fallback)
- [x] In-app prominent disclosure implemented (background location) — screenshots still to capture
- [ ] Prominent disclosure screenshots captured (background location, overlay)
- [x] Privacy policy live at public URL (not localhost) — https://magneetar.me/privacy returns 200 (verified 2026-08-12)
- [ ] Data Safety Form + Permissions Declaration + IARC submitted
- [x] Signing: release keystore backed up off-machine — `~/Documents/magneetar-keystore-backup-2026-08-12/` (keystore + RECOVERY.md, byte-identical hashes; fallback password already rotated to a 64-char value)
- [ ] Move a 2nd keystore copy to a separate physical location (encrypted USB / password-managed vault)
