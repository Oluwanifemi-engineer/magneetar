# Third-Party Developer API — Scoped API Keys

**Status**: ✅ **implemented (v1.6)** — backend + tests + dashboard UI live
**Owner**: core team
**Depends on**: v1.4.0 key split (master / device), existing RBAC + step-up infra

> Implementation status:
> - Backend: `server/routes/api_keys.py` (management + `/api/v1` data surface),
>   `auth.get_api_key_actor` + `require_api_key_scope`, `api_keys` table in
>   `database.py`/`database_postgres.py`, key cleanup on account deletion.
> - Tests: `server/tests/test_api_keys.py` (28 cases — creation, scope
>   enforcement, RBAC intersection, step-up, rotation, revocation, rate
>   limits, wipe rejection).
> - Dashboard: Settings → Developer API Keys (create / copy-once / rotate /
>   revoke with password step-up).
> - Rollout order §10 items 1-3 are done; item 4 (Android) is intentionally
>   untouched. Remaining future work: per-key usage metering + billing.

---

## 1. Problem

Today the only programmatic credentials are the **device key** (embedded in
every APK, device-scope only) and the **master key** (server-side admin).
Neither is suitable for a third party:

- A reseller / integrator cannot read a customer's device data without the
  customer's password.
- Handing out `MT_API_KEY` grants **full admin** — a non-starter.
- The device key has no owner binding, no scopes, no per-account revocation.

Magneetar has no developer story. This spec adds **per-account, scoped,
revocable API keys** — the Stripe/Supabase/Linear model — so customers can
build integrations (dashboards, alerting scripts, IFTTT-style automations,
reseller tooling) against *their own* data only.

## 2. Goals / non-goals

### Goals
- Per-account API keys with **least privilege** (scopes) and **revocation**.
- The key actor is the owning account — all existing RBAC/share rules apply
  automatically (a viewer-shared device stays read-only for the key too).
- Keys are **auditable** (every request logged), **rate-limited**, and can
  expire.
- Zero impact on the existing device-key / JWT flows.

### Non-goals (v1)
- **OAuth2 / "log in with Magneetar"** for third-party *apps* acting on
  behalf of users — that is a separate authorization-code flow (see §9).
- Webhooks / push-based integrations.
- Billing metering of API usage.

## 3. Key format & storage

```
Format:   mtk_live_<32 random url-safe chars>      # live environment
          mtk_test_<32 random url-safe chars>      # sandbox environment
Example:  mtk_live_7f3KpQ2xLm9zWvR4cTnB8yHd1gJ6sUa
```

- The **full key is displayed exactly once** at creation (server never stores it).
- Stored as **SHA-256 hash** (reuse `auth.hash_device_key` pattern) + a
  short **prefix** for indexed lookup:

```sql
CREATE TABLE IF NOT EXISTS api_keys (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT NOT NULL,                     -- owning account
  name         TEXT NOT NULL,                     -- human label ("Reseller dash")
  key_prefix   TEXT NOT NULL UNIQUE,              -- 'mtk_live_7f3KpQ2x' (first 12)
  key_hash     TEXT NOT NULL,                     -- sha256(full key)
  scopes       TEXT NOT NULL DEFAULT 'devices:read',  -- comma-separated
  created_at   TEXT NOT NULL,
  last_used_at TEXT,
  expires_at   TEXT,                              -- NULL = never
  revoked_at   TEXT                               -- NULL = active
);
CREATE INDEX idx_api_keys_user   ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
```

- Lookup: find candidate row(s) by `key_prefix`, then compare
  `hmac.compare_digest(sha256(presented), key_hash)` — constant time.
- Every write goes through the existing `database.py` context + the column
  detection migration pattern (see `fix(db): migrate existing databases to
  device_shares`).

## 4. Scopes

v1 ships with a small scope set that maps 1:1 onto existing RBAC abilities:

| Scope | Grants |
|---|---|
| `devices:read` | List devices, read location history, device state (default) |
| `devices:write` | Issue remote commands (lock / alarm / lost mode / capture) — still subject to per-device share roles |
| `alerts:read` | Read alert history / incident list for owned+shared devices |
| `media:read` | Read evidence media metadata + download URLs (owner only, not viewers) |

Scopes are **always intersected** with the owner account's own rights: a key
can never exceed what the account could do in the dashboard, and sharing
rules still apply per device.

## 5. Auth flow

```
Integrator:  Authorization: Bearer mtk_live_<32 chars>
                    ↓
get_api_key_actor() → looks up prefix → hash-verify → checks
                      revoked_at / expires_at → returns (user_id, scopes)
                    ↓
Data routes treat the actor as that user, filtered by scopes
```

- New FastAPI dependency `get_api_key_actor` (mirrors `require_dashboard_auth`).
- **Never** accepted on: `/api/auth/*`, `/api/dashboard/errors`, metrics,
  account/key management, or token-minting endpoints. The key is a
  data-plane credential, exactly like the device key's relationship to
  dashboard routes (F-02 guarantee preserved).
- Audit: every key-authenticated request logs `actor="key:<prefix>"` to the
  existing audit/error log.

## 6. Endpoints

All under dashboard JWT auth with **step-up password** (consistent with
sensitive actions like device deletion and 2FA enable):

| Endpoint | Auth | Description |
|---|---|---|
| `POST /api/account/api-keys` | dashboard JWT + step-up | Create key `{name, scopes[], expires_at?}` → returns full key **once** |
| `GET /api/account/api-keys` | dashboard JWT | List own keys (prefix, name, scopes, last_used_at, revoked) |
| `DELETE /api/account/api-keys/{id}` | dashboard JWT + step-up | Revoke immediately (checked per request) |
| `POST /api/account/api-keys/{id}/rotate` | dashboard JWT + step-up | Revoke + mint a new key (old dies instantly) |

Rate limits: separate bucket per key (default 120 req/min), reusing the
existing rate-limiter helpers.

## 7. Dashboard UX

New **API keys** page: create (name + scope checkboxes), list with
last-used + revoke/rotate buttons, and a one-time "copy your key" reveal.
Step-up prompt on create/revoke/rotate. Reuses the existing password gate.

## 8. Test plan

- `tests/test_api_keys.py`, mirroring `test_device_key_separation.py`:
  - key works on data routes with its scopes;
  - key **rejected** on `/api/auth/*`, `/api/dashboard/errors`, metrics,
    key-management endpoints;
  - revoked key → 401 immediately; expired key → 401;
  - viewer-shared device stays read-only through the key (`devices:write` on
    a viewer-shared device → 403);
  - raw `mtk_...` value never appears in logs/DB (only prefix + hash);
  - step-up required for create/revoke (wrong password → 401);
  - rate limit hit → 429.

## 9. Future (v2, out of scope here)

- **OAuth2 authorization-code** for third-party apps ("connect your account").
- Webhooks (theft event → POST to integrator URL).
- Per-key usage metering + billing.

## 10. Rollout order

1. Backend: migration + `auth.get_api_key_actor` + endpoints + tests.
2. Dashboard: API keys page with step-up.
3. Docs: developer quickstart with curl examples (link from README).
4. Android: untouched (device key flow unchanged).
