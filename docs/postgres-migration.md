# Magneetar — PostgreSQL Migration Runbook

Honest assessment of moving the live data plane from SQLite to PostgreSQL,
with measured evidence, the current gap, and a phased execution plan. This
document does NOT claim the switch is ready — it is the plan + evidence so
the switch can be scheduled deliberately.

Status date: **2026-08-07** · Production data plane: **SQLite** (unchanged).

---

## 1. Why migrate (measured, this session)

| Measurement | SQLite (current) | Postgres (scratch, PG16) |
|---|---|---|
| Raw insert throughput, commit-per-row | ~1,900/s | — |
| Raw insert throughput, batched commits | ~705,000/s (WAL, commit/1000) | **bench below** |
| Full `/api/device/location` handler (4 workers, sync) | ~370–400 req/s, p50 3s at 2,000 devices | — |
| Full handler + `MT_WRITE_BATCH_MS=250` (deployed) | ~400 req/s ceiling; p99 91→50ms at 100 req/s | — |
| Single-writer serialization | **YES — the hard ceiling** | **NO** (multi-writer, MVCC) |

The measured bottleneck is NOT the disk: it is SQLite's **single-writer lock**
(per-commit path) and, above ~400 req/s, the **per-ping CPU work** (sentinel
scoring + ~6 SQLite ops + JSON + Redis publish). Postgres removes the
single-writer ceiling entirely; the CPU ceiling then scales with more
workers/cores. **Decision rule:** stay on SQLite while fleet ≤ ~2,000–3,000
devices (batched writes keep latency flat); migrate before crossing that line
or when you need HA/failover/multi-instance.

## 2. The honest gap: the current adapter is NOT a usable data plane

`server/database_postgres.py` (333 lines, asyncpg pool) — schema parity audit:

| Table | In SQLite | In pg adapter | Notes |
|---|---|---|---|
| `users` | ✅ | ❌ **MISSING** | the app cannot boot against pg without this |
| `fcm_tokens` | ✅ | ❌ MISSING | push delivery broken |
| `error_log` | ✅ | ❌ MISSING | error tracking broken |
| `email_verify_tokens` | ✅ | ❌ MISSING | account verification broken |
| `password_reset_tokens` | ✅ | ❌ MISSING | password reset broken |
| `cell_location_cache` | ✅ | ❌ MISSING | offline-SMS coarse-locate cache |
| 14 other tables | ✅ | ✅ | alerts, audit_log, commands, devices, evidence_cases, geofences, guardian_profiles, heartbeats, locations, media, rate_limits, recovery_requests, recovery_sightings, revoked_tokens |

Additionally, **`database.py` (the live data plane) is SQLite-only** — every
route uses `get_db()`/`get_db_context()` returning `sqlite3.Connection`.
`main.py` explicitly warns that the pg adapter is experimental and NOT wired
into application routes. Enabling `MT_DATABASE_URL` today would break
registration immediately (`users` missing). **Flipping the env var is NOT a
migration — the storage interface itself must be converted.**

## 3. Migration drill — proven this session (lossless)

On a scratch Postgres 16 container, a drill copied the **production** DB
(read-only copy of `/app/data/magneetar.db`):

```
20 tables migrated; parity failures: 0
users=14 devices=1 locations=1794 heartbeats=154 audit_log=897 error_log=88
```

Type mapping used (drill): `INTEGER→BIGINT`, `REAL→DOUBLE PRECISION`,
`TEXT→TEXT`; primary keys preserved (ids keep values → references intact).
Foreign keys are NOT recreated by the drill — they must be rebuilt in the
real migration (see §5). The drill script pattern is reusable:
`scripts/`-candidate `pg_migrate.py` (SQLite→pg copy + parity check).

## 4. Phased plan (each phase lands green independently)

**Phase 1 — Schema parity (1–2 days).** Add the 6 missing tables +
constraints to `database_postgres.py` matching `database.py`'s DDL exactly
(column names/types/defaults, indexes, FKs, the `location_encrypted` /
`sms_phone` / `alert_settings` columns added in v1.4). Add a schema-drift
test: `database.py` schema vs `database_postgres.py` schema must match
table-for-table, column-for-column.

**Phase 2 — Storage interface (the real work, 3–5 days).** Introduce a thin
storage layer the routes already depend on (`get_db`/`get_db_context`) that
returns a SQLite connection by default and a pg-backed adapter when
`MT_DATABASE_URL` is set. This means converting `database.py`'s helpers and
the route modules' `?`/`%s` params to asyncpg parameter style — the single
biggest chunk. Recommend: keep SQLite as the default forever (`MT_DATABASE_URL`
empty), so risk is opt-in.

**Phase 3 — Cutover drill (1 day).** From the proven §3 script:
1. `scripts/backup-db.sh` (pre-migration checkpoint).
2. Run the real migration (schema + data + indexes + FKs) into a scratch pg.
3. Boot a staging server with `MT_DATABASE_URL` → run the full test suite +
   the fleet load test against it.
4. Verify counts/`integrity_check` equivalents; keep SQLite untouched.

**Phase 4 — Production switch (maintenance window, 30–60 min).** Deploy
server with `MT_DATABASE_URL` set + `MT_DB_PATH` left (fallback), health-gate
with `deploy.sh`, watch: registration, heartbeats, WS, alerts. Rollback =
unset `MT_DATABASE_URL` (SQLite still has the full history up to the switch;
dual-write during a transition week is the safer variant).

## 5. Open items to settle before Phase 1

- **Timestamp comparison**: SQLite's `datetime()` string normalization is
  used in several queries; pg uses proper `timestamptz`. The migration must
  store timestamps as `timestamptz` and the query layer must stop relying on
  string comparison (the `datetime(expires_at)` patterns).
- **FK rebuild**: `devices` FK references from locations/media/commands/etc.
  must be created in dependency order and validated (`pg_restore`-style
  `--disable-triggers` or explicit ordering).
- **Per-user device-limit + unowned-cap queries**: straight-forward port, but
  include them in the schema-drift test.
- **Encryption at rest**: SQLite uses the filesystem; pg should get
  `pgcrypto`/TDE considerations documented before the switch (not required to
  start).
- **Hosting**: a production pg instance (managed: Neon/Supabase/RDS, or a
  second container on this VPS) — decide the ops owner before Phase 3.

## 6. Decision gate (do not skip)

- [ ] Phase 1 landed: schema-drift test green (tables/columns identical)
- [ ] Phase 2 landed: full suite green with `MT_DATABASE_URL` set
- [ ] Phase 3 drill: 20/20 tables parity + load test p95 < 100ms at 2,000 devices
- [ ] Off-site backups configured first (Postgres needs its own backup story —
      `pg_dump` + the same rclone remote, so a migration can never be the
      only copy of the data)
- [ ] Maintenance window scheduled + rollback rehearsed (unset env, restart)
