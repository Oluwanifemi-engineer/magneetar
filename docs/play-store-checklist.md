# Magneetar — Google Play Store Submission Checklist

Status date: **2026-08-01** · Gate: **release-ready after recovery drill passes**

This checklist is the audit trail for Play Store submission. It is gated on the
**Recovery Capability Drill** (`scripts/recovery-drill.sh`) passing all steps,
which proves the product's core claim: it can detect, track, and recover a
lost smart device.

---

## ✅ Completed & Verified

| # | Item | Evidence |
|---|------|----------|
| 1 | **Recovery capability proven end-to-end** | `bash scripts/recovery-drill.sh` — 12/12 steps PASS (register → link → theft detection → evidence case → community recovery launch → guardian opt-in → blurred nearby scan → sighting → owner notified → close → device recovered). |
| 2 | **Full test suite green** | Backend **193 passed** (`server/tests/`: 69 reliability, 36 multi-user, 23 guardian, 22 api, 17 sentinel, 15 auth, 11 e2e). Dashboard **74 passed** (jest, 11 suites) + TypeScript clean (`npx tsc --noEmit`). |
| 3 | **Privacy policy page** | `dashboard/src/app/privacy/page.tsx` — hosted at `/privacy`, linked from the landing footer (Legal column). Required by Play's User Data policy. |
| 4 | **Data safety disclosures** | Backend stores only hashed secrets (bcrypt passwords, SHA-256 device keys, hashed IMEI/SIM). No PII sold or shared. |
| 5 | **Self-hosted server model** | Users connect to their own server URL (default `https://api.magneetar.me`). No third-party data processors beyond user-selected alert providers (Twilio/WhatsApp/email) and optional Sentry. |
| 6 | **Ghost-owner recovery fix** | Devices whose owner account was deleted (e.g. after DB restore) are now claimable by a fresh sign-up — 6 regression tests + live-verified (claim returns 200, real-owner 403 guard intact). Unblocks the user's own self-signup re-link after the data-loss incident. |

---

## 🟡 Pre-Submission Work Items (mandatory before upload)

### A. Target SDK & compile SDK ✅ DONE (2026-08-01)
- **Current:** `compileSdk = 35`, `targetSdk = 35`, `minSdk = 24` in `android-app/app/build.gradle.kts` (AGP 8.7.3, Gradle 8.12 — build requires JDK 21; host default JDK 25 breaks Gradle 8.12, use `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`).
- **Play requirement (2026):** new apps must target **API 35 (Android 15)**; API 36 (Android 16) becomes mandatory **Aug 31, 2026** — bump to 36 then (AGP 8.9.1+ + Gradle 8.11.1+).
- **Verified:** `./gradlew assembleRelease` succeeds; `aapt` reports `targetSdkVersion:'35'`, `compileSdkVersion:'35'`; release APK live at `/apk/download` (byte-identical). Both CI workflows (`ci.yml`, `build-apk.yml`) now install `platforms;android-35 build-tools;35.0.0`.
- **Remaining:** re-test background location + FGS behavior on a real device (Android 15 FGS time limits) once the phone is plugged in.

### B. Cleartext traffic policy ✅ DONE (2026-08-01)
- **Release builds:** `<base-config cleartextTrafficPermitted="false">` — cleartext blocked everywhere except `localhost` / `127.0.0.1` / `10.0.2.2` (emulator) via scoped `<domain-config>`. `android:usesCleartextTraffic="true"` removed from the manifest. Production `https://api.magneetar.me` stays TLS-only.
- **Debug builds:** `src/debug/res/xml/network_security_config.xml` permits cleartext for all hosts so developers can hit local/LAN self-hosted servers over http. Release stays strict (standard source-set override; verified no leak).
- **Note:** a custom `http://` LAN server URL in the app's login page now requires an explicit `<domain>` entry (or HTTPS).

### C. Device Admin API — Google deprecation (REVIEW REQUIRED)
- **Current:** `AdminReceiver` with `BIND_DEVICE_ADMIN` + policies `lock-task`, `wipe-data`, `force-lock`.
- **Policy:** Google restricts **Device Admin apps to enterprise/EMM use cases**; consumer anti-theft
  apps using Device Admin (esp. `wipe-data`) need an **Enterprise Mobility Management (EMM)** or
  **BYOD** declaration, or the feature must be dropped for the consumer listing.
- **Options (pick one):**
  1. Declare the app as an EMM/BYOD device-management app in Play Console (Play Console → App content → Device management).
  2. Remove `wipe-data` from `device_admin.xml` and rely on lock + app-level data wipe.
  3. Ship consumer build without Device Admin; keep a separate EMM/enterprise build.
- **Action:** confirm the intended Play Console declaration **before** first submission to avoid a rejection.

### D. Restricted permissions — declaration form
Play Console requires a **Permissions Declaration** for each of these (explain feature, user value, and how data is handled):
- `ACCESS_BACKGROUND_LOCATION` — theft detection when app is closed. Must mention the FGS `location` service and that tracking is per-device opt-in.
- `SCHEDULE_EXACT_ALARM` + `USE_EXACT_ALARM` — watchdog/health-check alarms. Prefer `SCHEDULE_EXACT_ALARM` (user-grantable) over `USE_EXACT_ALARM` (restricted); on Android 14+ `USE_EXACT_ALARM` is denied for most apps unless the app is a calendar/alarm app. **Action: drop `USE_EXACT_ALARM`** and request exact-alarm via `canScheduleExactAlarms()` flow.
- `SYSTEM_ALERT_WINDOW` — theft-deterrent overlay. Must be declared with an on-device rationale + link to settings for grant.

### E. Background location justification (review-sensitive)
- Play's policy: background location must be **integral to the core feature** and the app must be **foreground-service + prominent-disclosure** compliant.
- The app already: shows a persistent FGS notification (dataSync/location), requests runtime permission with rationale (`PermissionsActivity`), and disables tracking when permission is revoked.
- **Action:** add an **in-app prominent disclosure** screen (one-time, before enabling background location) that states: *"Magneetar uses background location only while theft protection is armed, to detect when your device leaves a safe zone or changes SIM. Location stops when you disarm or uninstall."* — capture a screenshot for the Play declaration.

### F. Data Safety Form (Play Console)
Complete with these answers:
- **Location:** Approximate + Precise, "Yes" collected (device telemetry), shared with "No one" or "User-selected".
- **Personal info:** Email (account), Name (display name), Phone number (only if user sets an alert phone).
- **Photos / Audio:** "Yes" — captured ONLY during an active theft response for the device owner's evidence case.
- **Security practices:** Encrypted in transit (TLS) and at rest (AES-256), data deletion requests supported (account/device deletion endpoint + 90-day retention purge).
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

---

## 🚀 Release Build Commands

```bash
# 1. Generate env (secrets)
bash scripts/generate-env.sh

# 2. Gate: recovery capability drill (must be 12/12)
bash scripts/recovery-drill.sh --server http://127.0.0.1:8001

# 3. Full test suites
cd server && ./venv/bin/python -m pytest tests/ -q          # 177 pass
cd dashboard && npx tsc --noEmit && npx jest --silent        # tsc clean, 70 pass

# 4. Release APK (Android SDK required)
cd android-app && ./gradlew assembleRelease
#  → app/build/outputs/apk/release/app-release.apk
```

---

## 📋 Final Gate Checklist (before hitting Upload)

- [ ] Recovery drill 12/12 PASS (user-verified)
- [x] Backend 193 tests + Dashboard 74 tests + tsc clean
- [x] compileSdk/targetSdk ≥ 35 (SDK 35, AGP 8.7.3, Gradle 8.12)
- [x] Cleartext restricted to local hosts only (release strict, debug override)
- [ ] Device Admin decision made (EMM declaration OR wipe-data removed)
- [ ] `USE_EXACT_ALARM` removed; exact-alarm runtime flow implemented
- [ ] Prominent disclosure screenshots captured (background location, overlay)
- [ ] Privacy policy live at public URL (not localhost)
- [ ] Data Safety Form + Permissions Declaration + IARC submitted
- [ ] Signing: release keystore backed up off-machine (current fallback password `magneetar123` MUST be rotated)
