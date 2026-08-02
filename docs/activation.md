# Magneetar — M1 Live Activation Runbook

Activating the two production monitoring/alerting integrations that are wired
but dormant until credentials are provided: **Firebase Cloud Messaging (FCM)**
for push alerts and **Sentry** for crash/error tracking.

Both integrations are fully coded and tested — they only need real
credentials. The server detects missing credentials and degrades gracefully
(push alerts skip, Sentry stays off), so activation is safe to do at any time.

---

## 1. Firebase Cloud Messaging (push alerts)

> ⚠️ **Important:** The legacy FCM "server key" (an `AIza...` API key from
> `google-services.json`) was **deprecated by Google in June 2024** and does
> NOT work with `firebase-admin`. Magneetar requires a **service-account JSON**.

### 1a. Run the automated setup (recommended)

```bash
npm install firebase-tools --save-dev      # if not already installed
bash scripts/firebase-setup.sh
```

This script:
1. Authenticates with Firebase (browser login or `FIREBASE_TOKEN`).
2. Creates the Firebase project + registers the `com.magneetar.app` Android app.
3. Downloads `android-app/google-services.json` (needed for the Android build).
4. Enables the Cloud Messaging API.
5. Downloads the default Firebase **service-account key**
   (`<project-id>@appspot.gserviceaccount.com`) to
   `server/firebase-service-account.json`.
6. Writes `MT_FIREBASE_KEY` into `server/.env`.

### 1b. Manual fallback (if gcloud is unavailable)

1. Firebase Console → Project settings → **Service accounts**.
2. **Generate new private key** → download the JSON.
3. Save it as `server/firebase-service-account.json`.
4. Add to `server/.env`:

```bash
MT_FIREBASE_KEY=./firebase-service-account.json   # bare metal
# OR, in Docker Compose (file is auto-mounted at this path):
MT_FIREBASE_KEY=/app/firebase-service-account.json
```

### 1c. Verify FCM

```bash
# Server startup validates the credential (wrong type → warning in logs)
cd server && ./venv/bin/python -m pytest tests/ -q -k "reliability or e2e" 2>&1 | tail -3

# Live check — the health endpoint reports config state
curl -s http://localhost:8000/health
```

A push is attempted on every theft/geofence alert. With a valid service account
and a device FCM token registered (`/api/device/fcm-token`), the device
receives the notification via `MagneetarMessagingService`.

**Android side:** FCM is already wired end-to-end (`MagneetarMessagingService`,
manifest receiver, `POST_NOTIFICATIONS` runtime request on Android 13+).
Rebuild the APK after `google-services.json` becomes real:

```bash
bash scripts/build-release.sh
```

---

## 2. Sentry (crash & error tracking)

### 2a. Create a Sentry project

1. Sign up at [sentry.io](https://sentry.io) and create a project for
   **"Magneetar Server"** (Python/FastAPI).
2. Copy the DSN (`https://<key>@o<org>.ingest.sentry.io/<project>`).

### 2b. Server

Add to `server/.env`:

```bash
MT_SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

The server initializes Sentry at startup when the DSN is present (FastAPI +
logging integrations, release-tagged, `send_default_pii=False`). Verify in the
startup log:

```bash
grep -i sentry /tmp/magneetar-server.log   # "Sentry initialized for error tracking"
```

### 2c. Android

The Android app reads the DSN from a Gradle property / env at build time:

```bash
# Either pass at build time…
bash scripts/build-release.sh   # with SENTRY_DSN provided via -P or MT_SENTRY_DSN

# …or set it in the environment / gradle.properties:
#   SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
#   MT_SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
```

`MainActivity.initSentrySafe()` initializes the SDK only when the DSN is
non-empty, so builds without a DSN are unaffected. Release builds can enable
ProGuard mapping upload via the `sentry { autoUploadProguardMapping = true }`
block in `android-app/app/build.gradle.kts`.

### 2d. Verify Sentry

Trigger a test crash/error and confirm it appears in the Sentry dashboard:

- Server: raise an unhandled exception (e.g. hit an endpoint with bad input in
  a test run) and watch the Sentry issues stream.
- Android: `throw RuntimeException("test")` in a debug build.

---

## 3. Post-activation checklist

| Item | Where | Status |
|---|---|---|
| Service-account JSON downloaded | `server/firebase-service-account.json` | ☐ |
| `MT_FIREBASE_KEY` set (path or JSON) | `server/.env` | ☐ |
| `google-services.json` real (not placeholder) | `android-app/google-services.json` | ☐ |
| `MT_SENTRY_DSN` set (backend) | `server/.env` | ☐ |
| `SENTRY_DSN`/`MT_SENTRY_DSN` set (Android build) | env / gradle.properties | ☐ |
| Server restarted + health OK | `curl /health` | ☐ |
| Test theft alert delivers a real push | device + dashboard | ☐ |
| Crash appears in Sentry | sentry.io project | ☐ |
| Docker: `MT_FIREBASE_KEY=/app/firebase-service-account.json` | `server/.env` (Docker only) | ☐ |

---

## 4. Troubleshooting

- **`MT_FIREBASE_KEY looks like the legacy FCM server key (starts with 'AIza')`**
  — the server detects the deprecated key type at startup and logs a warning.
  Replace it with the service-account JSON path.
- **`MT_FIREBASE_KEY points to a file that doesn't exist`** — the path is
  relative to the server CWD. In Docker, use the mounted
  `/app/firebase-service-account.json`.
- **Push silently skipped** — check the server logs for
  `Push notification failed:`; the alert circuit breaker opens after 5
  consecutive failures and re-probes after 5 minutes.
- **Docker: file becomes a directory** — Docker bind-mounts create a
  *directory* at a host path that doesn't exist yet. Create
  `server/firebase-service-account.json` (even an empty `{}` placeholder)
  BEFORE `docker compose up` so the mount is a file, not a directory.
  The server treats an unreadable credential as "push disabled" and keeps
  running.
