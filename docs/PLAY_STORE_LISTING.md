# Magneetar — Play Console Listing (copy-paste ready)

**Date:** 2026-08-14 · **Build to upload:** v1.4.2 AAB (versionCode 8)
**Assets:** `docs/play-assets/feature-graphic-1024x500.png`,
`docs/play-assets/icon-512.png`

Everything below is ready to paste into the Play Console. The declaration
answers match what the app actually does (verified against
`docs/play-store-checklist.md` and the play-flavor manifest).

---

## 1. Store listing

**App name:** Magneetar

**Short description** (≤80 chars):
> Anti-theft tracking: SIM-change alerts, remote lock & wipe, evidence capture

**Full description:**

```
Magneetar turns your Android phone into a self-protecting anti-theft device.

WHAT IT DOES
• Real-time location tracking with theft-pattern detection (Sentinel AI)
• SIM-change alerts — the instant a different SIM is inserted, you're notified
• Remote lock, alarm, and data wipe from the web dashboard
• Evidence capture (front camera + microphone) during an armed theft response,
  with a SHA-256 chain of custody for law enforcement
• Offline resilience — telemetry queues and syncs when the connection returns
• Guardian Network — trusted contacts help locate a stolen device
• Geofencing safe zones with exit alerts
• Background persistence designed to survive app-kill attempts

PRIVACY FIRST
• Location and evidence go ONLY to your own Magneetar account
• Protected in transit with TLS; account secrets hashed and encrypted
• Two-factor authentication (TOTP) for sensitive operations
• No ads, no tracking, no data selling
• Full export and permanent deletion from the dashboard

HOW TO START
1. Install on your phone and create your free Magneetar account
2. Open the dashboard (app or magneetar.me) and link the device
3. Grant location access for theft protection (one-time, explained in-app)

Works on Android 7.0 (API 24) and up.
```

---

## 2. App content → Data safety (each answer)

| Field | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| **Location** — Approximate / Precise | **Yes** — collected (device telemetry). Used for: App functionality. Shared: **No one** |
| **Personal info** — Email address | **Yes** — collected (account). App functionality. Not shared |
| **Personal info** — Name | **Yes** — display name (account profile). Not shared |
| **Personal info** — Phone number | **Yes** — ONLY if the user sets an alert phone for SMS/WhatsApp alerts. Not shared |
| **Photos** | **Yes** — captured ONLY during an active theft response for the owner's evidence case (App functionality). Not shared |
| **Audio** | **Yes** — captured ONLY during an active theft response (App functionality). Not shared |
| **Device or other IDs** | **Yes** — Firebase instance ID (push delivery). Not shared |
| **App activity** — app interactions / in-app search history | **No** |
| **App info and performance** — crash logs / diagnostics | **No** (Sentry optional, off by default) |
| **Security practices** | Data **encrypted in transit** (TLS); account secrets **hashed** (bcrypt) and **encrypted** (AES-256-GCM); **TOTP 2FA** available; **data deletion** supported (device + account, from the dashboard); deleted rows purged by the 90-day retention sweep |
| Data can be deleted on request | **Yes** — `Delete Device` and `Delete Account` are in the dashboard (two-step confirm); documented at `/privacy` |
| Does the app allow data export? | **Yes** — evidence/recovery PDF generation + read API access |

---

## 3. App content → Permissions declaration

Declare each with its feature rationale (paste these verbatim):

1. **`ACCESS_BACKGROUND_LOCATION`** — *Theft detection must keep working when
   the app is closed. The phone reports location to the owner's own account in
   the background while tracking is armed. The user grants this via a
   prominent in-app disclosure explaining the purpose, the data destination,
   and how to revoke it (Settings). Tracking is disabled immediately when
   permission is revoked.*
2. **`BIND_DEVICE_ADMIN`** — *Thief-resistant uninstall protection and remote
   lock/wipe during an armed theft response. Activated ONLY with explicit
   in-app user consent at onboarding; no policies run unless the owner arms
   theft response.*
3. **`SCHEDULE_EXACT_ALARM`** — *Health-check/watchdog alarms that keep the
   tracking service alive so theft detection survives app-kill attempts. The
   app requests it via system settings and silently degrades to inexact
   alarms when not granted.*
4. **`SYSTEM_ALERT_WINDOW`** — *The theft-deterrent full-screen overlay
   (alarm + lock notice) shown during an armed theft response. The app shows
   an on-device rationale and links to Settings for the grant.*

> **Do NOT tick the "App content → Device management" declaration** — it is
> for enterprise/MDM apps, triggers a rigorous manual review, and
> misdeclaring a consumer app risks account termination. `BIND_DEVICE_ADMIN`
> belongs in the **Permissions declaration** above (Cerberus-class precedent
> ships Device Admin with honest disclosure).

---

## 4. App content → IARC / audience

- **Rating:** complete the questionnaire honestly → expect **18+** (the
  "location sharing" and "surveillance/tracking" flags answered Yes, plus
  remote wipe). Violence: none.
- **Target audience:** Adults (18+). Parental controls: not applicable.
- **Ads:** No. **In-app purchases:** No (free tier; self-hosted server).

---

## 5. App content → Account deletion

- **In-app:** Dashboard → Settings → Danger Zone → **Delete Account**
  (two-step confirm). Also **Delete Device** per device.
- **Web API:** `DELETE /api/auth/user/account` (cascade-deletes all owned
  devices, media, evidence, alerts) and `DELETE /api/dashboard/devices/{id}`.
- **Privacy policy:** https://magneetar.me/privacy (live, HTTP 200).

---

## 6. Production release

1. Upload `android-app/app/build/outputs/bundle/playRelease/app-play-release.aab`
   (freshly built 2026-08-14, `versionName 1.4.2`, `versionCode 8`, signed
   with the release keystore — SHA-256 `02:4C:BB:34…0A:7F`, play flavor =
   **zero** SMS/phone-state perms; also staged at
   `server/static/apk/magneetar-v1.4.2-play.aab`).
2. **Release notes:** "Session tokens encrypted at rest, SIM-change
   detection, remote lock/wipe, evidence capture with SHA-256 chain of
   custody, Guardian recovery network, geofencing, background theft
   detection."
3. **Rollout:** start at 10% staged rollout; watch for policy questions.
4. Expect a **manual review** (device admin + background location). Have
   `docs/PLAY_READINESS_VERDICT.md` + `docs/security.md` ready to paste into
   review-question responses.

---

## 7. Screenshots (still need a phone)

The 6–8 phone screenshots must come from the real app. Recommended set:
1. Login page (on-brand dark/aqua)
2. Dashboard device map (live location + accuracy)
3. Device panel with commands (Lock / Alarm / Capture / Wipe)
4. Sentinel threat score + theft alert
5. Evidence gallery (case timeline)
6. **Permissions disclosure dialog** (mandatory — background location)
7. Geofence safe-zone editor
8. Guardian Network setup

Add the disclosure dialog screenshot to the store listing AND keep it for the
review; it is the strongest evidence that background location is disclosed
prominently.
