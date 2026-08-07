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
| **Legacy device key** | `MT_LEGACY_DEVICE_KEY` | 32 chars | Pre-split master key accepted for **device-scope** auth only (rotation grace for installed APKs) | ❌ (it IS the old master, so old APKs present it) |
| JWT secret | `MT_JWT_SECRET` | 64 chars | Signing every access/refresh/device/dashboard token | ❌ |
| Encryption key | `MT_ENCRYPTION_KEY` | 64 hex (32 bytes) | AES-256-GCM field encryption, HKDF per-device key derivation | ❌ |

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
| `MT_API_KEY` (master) | ❌ (device auth accepts device/legacy keys) | YES — users re-login | None | Rotation is now **zero-downtime for devices**: installed APKs keep working via `MT_LEGACY_DEVICE_KEY` (or the device key) until you also rotate it. |
| `MT_DEVICE_KEY` | **YES — APKs that embed it** | ❌ | None | Ship a new APK embedding the new device key, and keep the old one as `MT_LEGACY_DEVICE_KEY` during rollout so in-the-wild APKs keep registering. |
| `MT_LEGACY_DEVICE_KEY` | YES — pre-split APKs can't re-register | ❌ | None | Clear it only after the installed fleet has upgraded to an APK embedding the device key. |
| `MT_JWT_SECRET` | YES — all active tokens invalid | YES — all sessions invalid | None | Tokens are short-lived; devices auto re-register (`TrackingService` auth-death loop) and users re-login. |
| `MT_ENCRYPTION_KEY` | N/A (device-side never holds it) | N/A | **YES** | Old ciphertext becomes undecryptable. **Verify encryption is actually in use before rotating.** |

## 3. Rotating the master key (MT_API_KEY) — now safe anytime

Because device auth accepts the device/legacy keys, `MT_API_KEY` is **no
longer baked into APKs** and can be rotated without touching devices:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # new master
```

1. Update `MT_API_KEY` in `server/.env` (keep `MT_DEVICE_KEY` and
   `MT_LEGACY_DEVICE_KEY` unchanged), then `bash scripts/deploy.sh`.
2. Dashboard sessions using the old key are rejected at login — log in with
   the new master key. Device traffic is unaffected.
3. Verify: `POST /api/auth/login` with the new key → 200; with the old key
   → 401; a device registration with `x-api-key` = old key → still 200
   (legacy device scope) if `MT_LEGACY_DEVICE_KEY` still holds it.

### Rotating the device key (MT_DEVICE_KEY)

1. Generate a new device key; put it in `server/.env` as `MT_DEVICE_KEY`
   AND move the current one to `MT_LEGACY_DEVICE_KEY` (grace).
2. Update `DEVICE_KEY` in `android-app/local.properties` and the GitHub
   secret `DEVICE_KEY`, then rebuild + ship the APK.
3. Deploy the server and roll the APK out; once the fleet has upgraded,
   drop the old key from `MT_LEGACY_DEVICE_KEY` and redeploy.

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

`MT_ENCRYPTION_KEY` derives a per-device AES-256-GCM key via HKDF
(`salt=b"magneetar-v1"`, `info=device:<id>`). Existing ciphertext cannot be
decrypted with a new master key.

### First: is encryption actually enabled?

As of v1.3.x, **`post_location` does NOT call `encrypt_field`** — the
`FieldEncryption` helper exists and the `location_encrypted` column is
present, but the write path stores plaintext lat/lng. **If the flag column
shows all zeros and no ciphertext exists in `locations.lat/lng`, rotating
the key is a no-op data-wise.**

Verify before rotating:

```sql
SELECT COUNT(*) FROM locations WHERE location_encrypted = 1;
```

### If encryption is NOT in use

Safe to rotate anytime:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Update `server/.env`, deploy. Done.

### If encryption IS in use (future)

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

## 11. Executable checklist — retiring MT_LEGACY_DEVICE_KEY

The legacy key exists ONLY as a grace credential for APKs installed before
the master/device-key split (v1.4.0). Every day it stays, the old master
(a key proven extractable from the public APK by `strings`) is a live
device-scope credential. Retire it as soon as the fleet runs the new APK.

> **Where the value lives**: `docker-compose.yml` carries it inline as
> `MT_LEGACY_DEVICE_KEY` (server env block) — it is NOT only in `server/.env`.
> Remove it from BOTH places.

### Pre-flight gate (all must pass before touching the env)

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
- `MT_LEGACY_DEVICE_KEY`: the old master key is in this chat log / every
  old APK — keep it only for the installed-fleet grace period, then clear.
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
  rebuild + ship a release APK embedding `BuildConfig.DEVICE_KEY`; once the
  fleet has upgraded, remove `MT_LEGACY_DEVICE_KEY` from `server/.env`.
