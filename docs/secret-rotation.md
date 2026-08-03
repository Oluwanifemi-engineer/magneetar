# Magneetar — Secret Rotation Runbook

Operational guide for rotating the three core security secrets without
bricking deployed devices or losing data. Follow the **impact table** first —
each secret has a different blast radius, and one of them (MT_API_KEY) is
baked into every installed APK, so rotating it blindly **will** take
deployed devices offline.

---

## 1. The secrets and their roles

| Secret | Env var | Minimum length | Used for |
|---|---|---|---|
| API key | `MT_API_KEY` | 32 chars | Device registration bootstrap (`x-api-key`), dashboard `/api/auth/login` |
| JWT secret | `MT_JWT_SECRET` | 64 chars | Signing every access/refresh/device/dashboard token |
| Encryption key | `MT_ENCRYPTION_KEY` | 64 hex (32 bytes) | AES-256-GCM field encryption, HKDF per-device key derivation |

## 2. Impact table (read this first)

| Rotating | Devices affected | Dashboards affected | Data risk | Notes |
|---|---|---|---|---|
| `MT_API_KEY` | **YES — all deployed APKs** | YES (login requires the key) | None | The key is compiled into every sideloaded APK (`BuildConfig.API_KEY`). Old APKs cannot re-register until a new APK ships with the new key. |
| `MT_JWT_SECRET` | YES — all active tokens invalid | YES — all sessions invalid | None | Tokens are short-lived; devices auto re-register (`TrackingService` auth-death loop) and users re-login. |
| `MT_ENCRYPTION_KEY` | N/A (device-side never holds it) | N/A | **YES** | Old ciphertext becomes undecryptable. **Verify encryption is actually in use before rotating.** |

## 3. The APK-baked-key hazard (MT_API_KEY)

`MT_API_KEY` is embedded in every APK at build time via `-PAPI_KEY`. An APK
installed from `v1.x.y` will always present the key it was built with. The
server compares against `settings.API_KEY` loaded at startup.

**Consequence:** rotating `MT_API_KEY` on the server immediately breaks
`/api/device/register` and `/api/auth/login` for every phone running an APK
that still carries the old key. Devices already registered keep working
(their per-device JWT + `x-device-key` remain valid — see §4), but any
re-registration (auth-death recovery, reinstall, new phone) fails.

### Safe rotation procedure for MT_API_KEY

1. **Ship the new key first.** Generate a new key:
   ```bash
   openssl rand -hex 32   # 64 hex chars — or use python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. Build a new release APK with `-PAPI_KEY=<new key>` (CI does this via the
   `API_KEY` secret — update that secret, then trigger the workflow).
3. Update `server/.env` with the new `MT_API_KEY` **in the same release
   window** as the APK rollout, then `bash scripts/deploy.sh`.
4. Optionally keep a **grace window** by NOT revoking the old key elsewhere
   — the server only holds one `MT_API_KEY`, so this rotation is
   all-or-nothing. Plan the APK + server deploy to land together.
5. Old APKs in the wild will fail to re-register. That is expected; prompt
   users to update via the in-app update notice / `/download` page.

> **Long-term fix:** per-device keys (`x-device-key`) already exist and are
> preferred by current APKs for device auth. Deprecating the shared-key
> registration path entirely (Tier-2) removes this hazard.

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

## 8. Incident trigger — when to rotate

- `MT_JWT_SECRET`: any suspicion that a token was forged or a signing key
  leaked (repo history, CI logs, container image).
- `MT_API_KEY`: key extracted from an APK and abused (it already ships in
  APKs — so only rotate when a *different* key than the shipped one leaked,
  or as part of a scheduled key lifecycle).
- `MT_ENCRYPTION_KEY`: team-member departure with DB access, or key shown
  in logs/screenshots.
