# Magneetar — Secret Rotation Runbook

Operational guide for rotating the core security secrets without bricking
deployed devices or losing data. Follow the **impact table** first — each
secret has a different blast radius.

---

## 1. The secrets and their roles

Since **v1.4.0 (2026-08-06)** the shared key is SPLIT into two tiers so the
public APK can never carry admin power:

| Secret | Env var | Min length | Used for | Ships in APK? |
|---|---|---|---|---|
| **Master key** | `MT_API_KEY` | 32 chars | Dashboard `/api/auth/login` + admin step-up ONLY | ❌ server-side only |
| **Device key** | `MT_DEVICE_KEY` | 32 chars | Device-scope auth (`x-api-key`): register, location, media, fcm, command poll | ✅ embedded in every APK (`BuildConfig.DEVICE_KEY`) |
| **Legacy device key** | `MT_LEGACY_DEVICE_KEY` | 32 chars | ~~Pre-split master key accepted for device-scope auth during rotation~~ **RETIRED 2026-08-10 — removed from code/config; old APKs must upgrade** | ❌ |
| JWT secret | `MT_JWT_SECRET` | 64 chars | Signing every access/refresh/device/dashboard token | ❌ |
| Encryption key | `MT_ENCRYPTION_KEY` | 64 hex (32 bytes) | AES-256-GCM at rest for account secrets (TOTP) AND location telemetry (per-device HKDF keys, v1.5+) | ❌ |

**Why the split:** the APK is a public artifact — anyone can sideload it and
`strings`-scan the dex. Before the split the APK carried the SAME key that
mints dashboard-admin JWTs, so an extracted key = full platform control
(every user's locations, WIPE/LOCK on any device, deleting evidence). Now
`/api/auth/login` and admin step-up compare against `MT_API_KEY` **alone**,
so the APK-embedded keys can never mint admin credentials. The device key
is a low-privilege credential that only gates device-scope endpoints
(bounded further by `MAX_UNOWNED_DEVICES`).

## 2. Impact table (read this first)

| Rotating | Devices affected | Dashboards affected | Data risk | Notes |
|---|---|---|---|---|
| `MT_API_KEY` (master) | ❌ (device auth accepts the device key) | YES — users re-login | None | Rotation is **zero-downtime for devices**: installed APKs authenticate with `MT_DEVICE_KEY`, which is unchanged. |
| `MT_DEVICE_KEY` | **YES — APKs that embed it** | ❌ | None | Ship a new APK embedding the new device key FIRST, then deploy the server. Since the legacy grace key was retired (2026-08-10), rotating before the fleet upgrades orphans in-the-wild APKs. |
| `MT_LEGACY_DEVICE_KEY` | **RETIRED (2026-08-10)** — pre-split APKs can no longer authenticate | ❌ | None | Removed from `config.py`/`auth.py`/env templates; an upgraded APK (embedding `MT_DEVICE_KEY`) is now mandatory. |
| `MT_JWT_SECRET` | YES — all active tokens invalid | YES — all sessions invalid | None | Tokens are short-lived; devices auto re-register (`TrackingService` auth-death loop) and users re-login. |
| `MT_ENCRYPTION_KEY` | N/A (device-side never holds it) | N/A | **YES** | Old ciphertext becomes undecryptable. **Verify encryption is actually in use before rotating.** |

## 3. Rotating the master key (MT_API_KEY) — now safe anytime

Because device auth accepts the device/legacy keys, `MT_API_KEY` is **no
longer baked into APKs** and can be rotated without touching devices:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # new master
```

1. Update `MT_API_KEY` in `server/.env` (keep `MT_DEVICE_KEY` unchanged),
   then `bash scripts/deploy.sh`.
2. Dashboard sessions using the old key are rejected at login — log in with
   the new master key. Device traffic is unaffected.
3. Verify: `POST /api/auth/login` with the new key → 200; with the old key
   → 401; a device registration with `x-api-key` = old key → 401 (the
   legacy grace key was retired 2026-08-10 — devices must use
   `MT_DEVICE_KEY`).

### Rotating the device key (MT_DEVICE_KEY)

1. Generate a new device key; put it in `server/.env` as `MT_DEVICE_KEY`.
2. Update `DEVICE_KEY` in `android-app/local.properties` and the GitHub
   secret `DEVICE_KEY`, then rebuild + ship the APK.
3. Deploy the server and roll the APK out. NOTE: since the legacy grace key
   was retired (2026-08-10), rotating `MT_DEVICE_KEY` immediately orphans
   in-the-wild APKs embedding the old device key — coordinate the rollout so
   the fleet upgrades promptly.

## 4. Rotating MT_JWT_SECRET

JWTs are signed with `MT_JWT_SECRET`. Rotation invalidates:

- Device access tokens → `TrackingService` detects 401s, re-registers with
  the API key + device key, and gets fresh tokens automatically.
- Refresh tokens → same recovery path.
- Dashboard/user sessions → users are logged out; they re-login.

### Procedure

1. Generate: `python -c "import secrets; print(secrets.token_hex(48))"` (96 hex chars).
2. Update `server/.env`, run `bash scripts/deploy.sh`.
3. Expect a burst of re-registrations and logins — **do not** trigger this
   during a peak window. Off-peak (e.g. 02:00 WAT) is ideal.
4. Verify (see §6).

No data is at risk: tokens are stateless and short-lived, and the
`revoked_tokens` table (rotated refresh tokens) is unaffected.

## 5. Rotating MT_ENCRYPTION_KEY

`MT_ENCRYPTION_KEY` is used by `user_security.py` to AES-256-GCM-encrypt
account secrets (TOTP). Since v1.5 it ALSO encrypts location telemetry at
rest: every ingest path (`_persist_location`, `/api/device/location/simple`,
offline-queue) derives a per-device AES-256-GCM key via HKDF
(`salt=b"magneetar-v1"`, `info=device:<id>`) and stores the base64 ciphertext
in `locations.location_data` with `location_encrypted=1`. Legacy plaintext
rows (flag 0) remain readable forever (dual-mode reads). **Rotating the key
affects TOTP secrets AND every encrypted location row — old ciphertext
cannot be decrypted with a new master key.**

### First: is encryption actually enabled?

As of v1.5, YES — with `MT_ENCRYPTION_KEY` set, `post_location` encrypts via
`encrypt_location_for_store()` and every reader decrypts via
`decrypt_location_row()` (dashboard map/replay/live, guardian recovery,
offline monitor, GDPR export, evidence PDF). Sentinel runs on the in-memory
payload, so theft detection is unaffected. Verify live rows:

```sql
SELECT COUNT(*) FROM locations WHERE location_encrypted = 1;
```

Sanity check: encrypted rows must NEVER carry plaintext coordinates in
`lat`/`lng` (they hold 0.0 placeholders) and must always have non-NULL
`location_data`:

```sql
SELECT COUNT(*) FROM locations WHERE location_encrypted = 1 AND location_data IS NULL;
```

### If encryption is NOT in use

Safe to rotate anytime:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Update `server/.env`, deploy. Done.

### If encryption IS in use

You MUST re-encrypt or decrypt-then-encrypt all data before rotating,
otherwise every stored location becomes garbage:

1. Write a one-off migration script that, for each location row:
   - decrypts with the old key (`FieldEncryption(old_key).decrypt_field(...)`),
   - re-encrypts with the new key,
   - updates the row.
2. Run it against a **backup first** (`scripts/backup-db.sh`), then against
   live DB during a maintenance window.
3. Only then rotate `server/.env` and deploy.

## 6. Post-rotation verification checklist

```bash
# 1. Health + version
curl -s https://api.magneetar.me/health | jq .status

# 2. New tokens sign with the new secret (login as dashboard)
curl -s -X POST https://api.magneetar.me/api/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"api_key\":\"$NEW_API_KEY\"}" | jq .token_type

# 3. A device re-registers (use the simulator with a fresh device id)
python scripts/device_simulator.py --server https://api.magneetar.me \
  --api-key "$NEW_API_KEY" --device-id "mt-$(openssl rand -hex 4)" --once

# 4. Dashboard sees the device online within the 5-min window

# 5. WebSocket requires a token (anonymous must be rejected)
#    (websocat or a tiny python websockets script — expect close 4408)
```

## 7. Secret storage hygiene

- Never commit secrets: `server/.env` and `android-app/release.keystore`
  are gitignored. Check with `git status` before pushing.
- GitHub secrets for CI: `API_KEY`, `SERVER_URL`, `KEYSTORE_BASE64`,
  `KEYSTORE_PASS`, `KEY_ALIAS`, `KEY_ALIAS_PASS`, `GOOGLE_SERVICES_JSON`.
- If a secret is ever committed (even briefly), **rotate it immediately**
  and scrub history (or use `git filter-repo`).
- Generate secrets with `scripts/generate-env.sh` (uses `secrets.token_*`).

## 9. Executed rotation — 2026-08-03 (MT_API_KEY + signing keystore)

### What happened
- The release keystore password was **lost** (created with a throwaway
  password nobody recorded). With an install base of ~1 device, we generated
  a **new keystore** and rotated `MT_API_KEY` in the same release — the
  cheapest moment to absorb the signature change.
- New keystore: `android-app/release.keystore` (PKCS12), alias `magneetar`,
  dname `CN=Magneetar, OU=Development, O=Magneetar, L=Lagos, ST=Lagos, C=NG`.
- **New signing-cert SHA-256: `024cbb34db441f37ed3de001174bb1832e3d7ce52e73b6eb35920f1dc4b20a7f`**
  (old: `f5202667…`). The `/download` page pins this fingerprint.
- Old keystore preserved at `android-app/release.keystore.old-password-lost`
  (only copy of the old private key — if the password is ever found, old-
  keystore devices could still be updated).
- New `MT_API_KEY` written to `server/.env` + `android-app/local.properties`
  (both gitignored). CI secrets `API_KEY`, `KEYSTORE_BASE64`, `KEYSTORE_PASS`,
  `KEY_ALIAS`, `KEY_ALIAS_PASS` must be updated to match (GitHub → Settings →
  Secrets).

### Migration consequence for installed devices
APKs signed with the **old** key can no longer update in place (Android
rejects signature mismatches). Those devices must **uninstall + reinstall**;
`device_id`/`device_key` live in SharedPreferences and reset on uninstall, so
old devices re-appear as new devices in the dashboard. With ~1 device this
was free; do NOT lose the new keystore password.

### Keystore credential storage (so this never recurs)
- Credentials live in `android-app/local.properties` (gitignored):
  `KEYSTORE_PASS`, `KEY_ALIAS`, `KEY_ALIAS_PASS`, `API_KEY`.
- `build.gradle.kts` and `scripts/build-release.sh` both read from there
  (env/-P flags still take precedence).
- **PKCS12 gotcha (the build failure we hit):** PKCS12 keystores ignore a
  separate `-keypass` — the private-key password IS the store password.
  `KEY_ALIAS_PASS` must equal `KEYSTORE_PASS` or signing fails with
  "Given final block not properly padded".
- **Kotlin DSL gotcha (the other build failure):** in the `signingConfigs`
  block, `keyAlias = keyAlias` self-assigns (the receiver's `keyAlias`
  property shadows the outer `val`). The val names are deliberately distinct
  (`releaseStorePass` / `releaseKeyAlias` / `releaseKeyPass`).
- Back up BOTH `release.keystore` AND `local.properties` together (e.g. to a
  password manager or encrypted vault) — one without the other is useless.

### Rotation verification performed (live)
- Bogus/old API key → `401` on `/api/device/register`.
- New API key → `200` + valid device JWT (throwaway device registered then
  permanently deleted).
- Existing registered device (`mt-14bddfeb`) kept heartbeating (JWT/
  device-key auth unaffected by the rotation).

## 11. Legacy key retirement — EXECUTED 2026-08-10

`MT_LEGACY_DEVICE_KEY` has been **removed from the codebase**: `config.py`,
`auth.py`, `generate-env.sh`, the README, and this runbook no longer
reference it, and `test_device_key_separation.py` now asserts a legacy-style
key is REJECTED for device scope (regression lock).

Operational notes for the installed fleet:
- Any APK still presenting the pre-split master key gets **401** on
  device endpoints — upgrade those devices to an APK embedding
  `BuildConfig.DEVICE_KEY` (`MT_DEVICE_KEY`).
- If a device drops offline after this change, verify it is on the new APK
  before anything else; re-introducing the legacy key is possible but
  recreates the exact credential the retirement removed.

> The step-by-step checklist below is kept for the audit record — it was
> executed as part of the retirement. It is NOT pending work; do not re-run
> it.

### Historical checklist — pre-flight gate (executed)

```bash
# 1. The phone is on the new APK (installed from the download page, Play
#    Protect paused) AND reporting recently:
curl -s https://api.magneetar.me/health | jq .status          # online

# 2. The phone's device row has a REAL device_key_hash (proves it registered
#    with BuildConfig.DEVICE_KEY, not the legacy master). NULL hash = the
#    device never presented a device key → do NOT retire yet.
docker exec magneetar-server python3 - <<'PY'
import sqlite3
c = sqlite3.connect('/app/data/magneetar.db')
for r in c.execute("SELECT id, device_key_hash, last_seen FROM devices WHERE owner_id IS NOT NULL"):
    print(r[0], 'hash=', 'SET' if r[1] else 'NULL', 'last_seen=', r[2])
PY

# 3. That device's last_seen is within the last 5 minutes (heartbeating live
#    on the current APK).

# 4. Fresh backup so the rollback path is painless:
bash scripts/backup-db.sh
```

### Action

```bash
# 5. Remove the variable from docker-compose.yml AND server/.env, then deploy:
#      grep -n MT_LEGACY_DEVICE_KEY docker-compose.yml server/.env
#    (delete the lines; keep MT_API_KEY + MT_DEVICE_KEY)
bash scripts/deploy.sh
```

### Post-verification (prove the retirement took)

```bash
# 6. Server healthy + version unchanged:
curl -s https://api.magneetar.me/health | jq '{status, version}'

# 7. The PHONE still reports (it authenticates with the device key now):
#    dashboard shows it online within 5 min — confirm last_seen advances.

# 8. Negative test — the retired key must now be REJECTED for device scope:
#    (throwaway device, deleted after)
python scripts/device_simulator.py --server https://api.magneetar.me \
  --api-key "$OLD_MASTER_KEY" --device-id "mt-$(openssl rand -hex 4)" --pings 1
#    expect: ❌ Registration failed: 401

# 9. The master key still works for dashboard login (MT_API_KEY unchanged):
curl -s -X POST https://api.magneetar.me/api/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"api_key\":\"$MT_API_KEY\"}" | jq .token_type

# 10. No leftover references in the running config:
docker exec magneetar-server sh -c 'env | grep -c LEGACY_DEVICE_KEY'  # → 0
```

### Rollback (if the phone drops offline after retirement)

```bash
# The phone is still on the OLD APK → restore the grace key immediately:
#   re-add MT_LEGACY_DEVICE_KEY to docker-compose.yml + server/.env with the
#   previous value, then: bash scripts/deploy.sh
# The predeploy image tag also still carries the old env for a fast revert:
#   docker tag magneetar-server:predeploy magneetar-server:latest
#   docker compose up -d --no-deps server
```

## 8. Incident trigger — when to rotate

- `MT_JWT_SECRET`: any suspicion that a token was forged or a signing key
  leaked (repo history, CI logs, container image).
- `MT_API_KEY` (master): key leaked outside the server (CI logs, chat,
  screenshots, a compromised operator machine). Rotating is now safe — no
  APK depends on it.
- `MT_DEVICE_KEY`: key extracted from an APK (it WILL be — treat it as
  public knowledge; rotate only to force the installed fleet onto a new
  key, using the legacy grace path above).
- `MT_LEGACY_DEVICE_KEY`: retired 2026-08-10 — the old master key no longer
  exists in code/config; in-the-wild APKs embedding it must be upgraded.
- `MT_ENCRYPTION_KEY`: team-member departure with DB access, or key shown
  in logs/screenshots.

## 10. Executed rotation — 2026-08-06 (master/device-key split + master rotation)

- **Split implemented**: `MT_DEVICE_KEY` (low-privilege, embeds in APKs as
  `BuildConfig.DEVICE_KEY`) + `MT_LEGACY_DEVICE_KEY` (grace) added to
  `config.py`, `auth.py`, `generate-env.sh`, the Android build, CI
  (`DEVICE_KEY` secret) and this runbook. Dashboard login/step-up remain
  hard-gated to `MT_API_KEY` alone.
- **Master rotated**: new `MT_API_KEY` written to `server/.env`; the OLD
  master (the one embedded in every shipped APK — it was proven extractable
  with a plain `strings` scan) is now `MT_LEGACY_DEVICE_KEY`, so installed
  devices keep registering during the grace window.
- **Regression coverage**: `tests/test_device_key_separation.py` — 14 tests
  proving device/legacy keys pass device endpoints but are rejected by
  dashboard login, and that dashboard.py never references the device key.
  Full suite: **395 passed**.
- **Actions still outstanding**: set the GitHub `DEVICE_KEY` secret (repo
  Settings → Secrets → Actions) to the `MT_DEVICE_KEY` in `server/.env`;
  rebuild + ship a release APK embedding `BuildConfig.DEVICE_KEY`.
- **DONE 2026-08-10 — legacy key retired**: `MT_LEGACY_DEVICE_KEY` removed
  from `config.py`, `auth.py`, `generate-env.sh`, README, and this runbook.
  Installed APKs still presenting the old master key can no longer
  authenticate — the fleet must run the new APK.

## 11. Firebase client API key — restriction + rotation (2026-08-13)

**What happened**: the real `google-services.json` values (project id
`magneetar-ecf5e`, Android API key, app id) were committed to the PUBLIC repo
in v1.0.0 and existed in history until scrubbed to a placeholder in `60e9e31`.
On 2026-08-13 the history was rewritten with `git filter-repo --replace-text`
(all values → placeholders) and force-pushed; local refs, reflogs and stale
worktrees were pruned so no trace remains on disk either.

**Why the key is still sensitive-in-public**: it is a *client* API key — it
ships inside every downloadable APK, so it can never be truly secret. The
control that matters is **restriction**, not secrecy.

### 11a. Restrict the key (do this regardless of rotation)

1. Google Cloud Console → **APIs & Services → Credentials** → the Android API
   key (`AIzaSyDfAXt…` or its replacement).
2. Edit → **Application restrictions → Android apps** → add package
   `com.magneetar.app` and the release signing **SHA-1**:
   ```bash
   keytool -list -v -keystore android-app/release.keystore \
     -alias <KEY_ALIAS> -storepass <KEYSTORE_PASS> | grep SHA1
   ```
   (credentials come from the `MT_KEYSTORE_PASS` / `MT_KEY_ALIAS` env vars
   used by the release build — see `android-app/app/build.gradle.kts`.)
3. **API restrictions**: restrict to the Firebase services actually used
   (FCM, Firebase Installations) — never “don’t restrict key”.

### 11b. Rotate (if you want the old value dead)

1. Firebase Console → **Project settings → Your apps** → the Android app →
   **Rotate key** (or create a new key in Google Cloud and replace it here).
2. Download the refreshed `google-services.json` and update **all** of:
   - `backups/google-services.json.real` (local, gitignored — used for local
     release builds; `cp` it to `android-app/app/google-services.json`),
   - the `GOOGLE_SERVICES_JSON` GitHub Actions secret,
   - rebuild + re-upload the APK (old APKs keep the old key — fine once the
     key is restricted to package+SHA-1).
3. No server change: the server never sees the client key (`MT_FIREBASE_KEY`
   is the separate service-account JSON used for FCM).
