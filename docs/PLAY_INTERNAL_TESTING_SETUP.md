# Play Internal Testing Track — Setup Guide (ADR-0007, 2026-08-15)

**Goal:** get Magneetar installed on real testers' phones without the
sideload hard-block that modern Android applies to apps with Magneetar's
permission profile (see `PLAY_POLICY_ANALYSIS.md`). The **internal testing
track** is private — only invited emails can install, the app never appears
in search, and there is no public listing. This is NOT a production
submission; production still waits for G1 + G2 (ADR-0006).

## Artifact

- `server/static/apk/magneetar-v1.4.4-play.aab`
- SHA-256: `c958dcfd6b089cbeebb84558365c266cc297f4adec1c37c62484435420db25ae`
- versionCode 10 / versionName 1.4.4, not debuggable, zero SMS
  permissions, zero accessibility service (verified 2026-08-15)

## Steps (one-time, ~45 min)

### 1. Play Console prerequisites (already ~90% done per play-store-checklist.md)
- Google Play Developer account (one-time $25 registration, if not done).
- App created in Play Console: name Magneetar, free, no ads.
- **Privacy policy URL** live at `https://magneetar.me/privacy` (200, verified).
- **Data safety form** answered per checklist section F.
- **Permissions declaration** added: `ACCESS_BACKGROUND_LOCATION`,
  `SCHEDULE_EXACT_ALARM`, `SYSTEM_ALERT_WINDOW`, `BIND_DEVICE_ADMIN`
  (wording ready in `docs/PLAY_STORE_LISTING.md`).
- **IARC content rating** completed (18+, honest surveillance/location flags).
- **App content** → Target audience (18+), account deletion answered
  (in-app Settings → Danger Zone + `DELETE /api/auth/user/account`).

### 2. Create the internal testing track
1. Play Console → **Testing → Internal testing** (left menu).
2. **Create a new version** (or reuse an existing track).
3. Upload `server/static/apk/magneetar-v1.4.4-play.aab`.
4. **Release notes** — keep minimal and honest:
   > Private beta — anti-theft tracking. v1.4.4: device-admin uninstall
   > protection, background theft detection, recovery beacon, evidence
   > capture, offline command relay (network/FCM). Please report any
   > issue from Settings → Report.
5. Save → Review (internal testing has **no review delay** — the build
   becomes available to testers almost immediately).
6. **Testers** → Add email addresses of the G1 fleet (use a Google
   account per tester; `+` aliases do not work for invites). Roll out to
   100% of testers.

### 3. Give testers the link
- Play Console shows the **opt-in link** (e.g.
  `https://play.google.com/apps/testing/com.magneetar.app`).
- Testers open it on their phone → tap **Become a tester** → **Install
  from Play Store**. No "Install unknown apps", no Play Protect block.
- **Auto-updates:** every future AAB uploaded to the internal track
  updates testers automatically (no manual sideload, no in-app updater
  dependency).

### 4. Wire the link into the download page
- After the track exists, put the opt-in link in
  `dashboard/src/app/download/page.tsx` (the "Google Play install
  (recommended)" banner) so the site drives testers to the Play path.

### 5. G2 transition (after G1 passes)
- Promote the same validated build to **Testing → Closed testing** (up to
  2,000 testers, light review) — testers keep their installs; only the
  serving track changes. Then, after G2, promote to production.

## Ops notes
- The AAB must be rebuilt + re-uploaded for every release (versionCode
  must strictly increase). Build: `cd android-app && JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 ./gradlew bundlePlayRelease`.
- Keep the sideload APK on the download page as the documented fallback —
  it still works on older Android / via adb for devices that can't use Play.
- Sentry is live (EU) — crashes from testers land in the project; watch
  Issues during G1.
