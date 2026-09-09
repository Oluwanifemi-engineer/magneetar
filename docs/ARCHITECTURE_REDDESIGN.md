# Magneetar Architecture Redesign

**Status:** Proposal
**Date:** 2026-09-02
**Deciders:** Oluwanifemi Tinubu
**Supersedes:** ADR-0001 through ADR-0005 (SQLite/Postgres decisions are absorbed)

---

## 1. Problem Statement

The current architecture is a **monolith with organic growth**. Features were added incrementally without domain boundaries, resulting in:

- `main.py` (1,412 lines) handling APK downloads, WebSocket, SMS webhooks, health checks, and app initialization
- `routes/dashboard.py` (1,935 lines) mixing device CRUD, evidence, geofences, stats, admin, and payments
- `routes/devices.py` (1,391 lines) mixing registration, telemetry ingestion, heartbeat, commands, and FCM
- `models.py` (642 lines) as a flat dump of every Pydantic schema
- SQLite ↔ PostgreSQL dual-path with incomplete migration
- No event system — features are silos that don't coordinate
- No background job system — `asyncio.create_task()` with no retry, no visibility
- No separation between write-heavy (telemetry) and read-heavy (dashboard) paths

**This won't scale to a team of 5, let alone a fleet of 1M devices.**

---

## 2. Target Architecture: Domain-Driven Monolith

We don't need microservices. We need **clear domain boundaries inside a single deployable**. Microservices at this stage would add operational complexity without benefit. The goal is a monolith that can be decomposed later if needed.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API Gateway Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Device API   │  │ Dashboard API│  │ Public API               │  │
│  │ (high-thrpt) │  │ (rich queries│  │ (config, health, APK)    │  │
│  │ /api/device/* │  │ /api/dash/*  │  │ /api/*, /health, /apk/* │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                 │                      │                  │
│  ───────┴─────────────────┴──────────────────────┴───────────────  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Domain Layer                               │  │
│  │                                                               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │  │
│  │  │  Identity    │ │  Device     │ │ Telemetry   │            │  │
│  │  │  & Access    │ │  Lifecycle  │ │ Pipeline    │            │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘            │  │
│  │                                                               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │  │
│  │  │  Command &   │ │  Security   │ │  Evidence   │            │  │
│  │  │  Control     │ │  & Sentinel │ │  & Forensics│            │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘            │  │
│  │                                                               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │  │
│  │  │  Geospatial  │ │  Notif.     │ │  Sharing &  │            │  │
│  │  │              │ │  Router     │ │  Circles    │            │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘            │  │
│  │                                                               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │  │
│  │  │  Business &  │ │  Privacy &  │ │ Observability│           │  │
│  │  │  Payments    │ │  Compliance │ │             │            │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘            │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                 Infrastructure Layer                          │  │
│  │                                                               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐│  │
│  │  │ Event Bus│ │ Job      │ │ Storage  │ │ Observability    ││  │
│  │  │ (Redis   │ │ Queue    │ │ Facade   │ │ (Sentry, Prometheus│
│  │  │ Streams) │ │ (ARQ)    │ │ (Pg+Obj) │ │  Grafana)        ││  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘│  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Domain Definitions

### 3.1 Identity & Access (`domains/identity/`)

**Owns:** User accounts, authentication, authorization, API keys, sessions.

| Table | Owner |
|-------|-------|
| `users` | Identity |
| `password_reset_tokens` | Identity |
| `email_verify_tokens` | Identity |
| `api_keys` | Identity |
| `revoked_tokens` | Identity |
| `rate_limits` | Identity |

**Responsibilities:**
- User registration, login, password reset, email verification
- JWT token lifecycle (access + refresh)
- TOTP 2FA enrollment and verification
- API key management (device keys + dashboard keys)
- Step-up authentication for destructive operations
- Rate limiting per identity

**Boundaries:**
- Does NOT know about devices, commands, or geofences
- Emits: `user.registered`, `user.authenticated`, `user.deleted`
- Consumes: nothing (leaf domain)

**Current files absorbed:** `user_auth.py`, `user_security.py`, `auth.py` (token functions only)

---

### 3.2 Device Lifecycle (`domains/device/`)

**Owns:** Device registration, device state, device configuration, device metadata.

| Table | Owner |
|-------|-------|
| `devices` | Device |
| `fcm_tokens` | Device |

**Responsibilities:**
- Device registration and pairing (key generation, hashing)
- Device claim/ownership transfer
- Device alias, model, OS version tracking
- Device online/offline state
- Device archive/unarchive
- FCM token registration for push notifications
- Device Admin status tracking

**Boundaries:**
- Does NOT store location data (that's Telemetry)
- Does NOT execute commands (that's Command & Control)
- Emits: `device.registered`, `device.claimed`, `device.offline`, `device.archived`
- Consumes: `user.registered` (to link ownership)

**Current files absorbed:** Device registration logic from `routes/devices.py`, device query logic from `routes/dashboard.py`

---

### 3.3 Telemetry Pipeline (`domains/telemetry/`)

**Owns:** Location pings, heartbeats, device state snapshots, telemetry batching.

| Table | Owner |
|-------|-------|
| `locations` | Telemetry |
| `heartbeats` | Telemetry |
| `cell_location_cache` | Telemetry |

**Responsibilities:**
- Ingest location pings (3-second intervals from fleet)
- Ingest heartbeat packets (60-second intervals)
- Validate coordinates (reject 0,0, reject stale timestamps)
- Batch writes for throughput (write queue)
- Deduplicate pings (session_id + ping_sequence)
- Maintain "latest location" materialized view per device
- Feed telemetry into Sentinel for scoring

**Boundaries:**
- This is the **hottest write path** — must be optimized independently
- Does NOT decide what to do with threat data (that's Security)
- Does NOT send alerts (that's Notification)
- Emits: `telemetry.location_received`, `telemetry.heartbeat_received`, `telemetry.sim_changed`
- Consumes: `device.registered` (to validate device exists)

**Design decisions:**
- Partitioned by time (monthly) for automatic old-data purging
- Write path: FastAPI endpoint → validation → write queue → batch INSERT
- Read path: Latest location per device is a materialized view or Redis cache
- Historical queries hit the partitioned table directly

**Current files absorbed:** `write_queue.py`, location/heartbeat handlers from `routes/devices.py`, `offline_monitor.py`

---

### 3.4 Command & Control (`domains/command/`)

**Owns:** Command lifecycle, multi-channel delivery, command acknowledgment.

| Table | Owner |
|-------|-------|
| `commands` | Command |

**Responsibilities:**
- Issue remote commands (lock, alarm, wipe, capture_photo, etc.)
- Multi-channel delivery: FCM push → SMS fallback → poll fallback
- Command priority and deduplication
- Command acknowledgment (device → server)
- SMS inbound webhook (Twilio signature verification)
- Step-up password requirement for destructive commands (wipe)

**Boundaries:**
- Does NOT decide WHEN to send a command (that's Security or User)
- Does NOT track device state after command execution
- Emits: `command.issued`, `command.delivered`, `command.executed`, `command.failed`
- Consumes: `device.registered`, `telemetry.heartbeat_received` (for delivery channel selection)

**Current files absorbed:** Command logic from `routes/devices.py`, `sms_relay.py`, `fcm_command.py`

---

### 3.5 Security & Threat Detection (`domains/security/`)

**Owns:** Sentinel scoring, threat assessment, automated responses, theft state.

| Table | Owner |
|-------|-------|
| `audit_log` | Security |

**Responsibilities:**
- Sentinel engine: score suspicious activity (SIM change, failed unlocks, device admin disabled, location anomalies)
- Theft state machine: `normal` → `suspect` → `stolen` → `recovered`
- Automated response triggers: when Sentinel score crosses threshold → queue evidence capture + alert owner
- Anomaly classification and pattern detection
- Device attestation verification

**Boundaries:**
- Does NOT store telemetry (that's Telemetry)
- Does NOT send alerts directly (emits events, Notification handles delivery)
- Emits: `security.theft_detected`, `security.score_changed`, `security.recovered`
- Consumes: `telemetry.location_received`, `telemetry.heartbeat_received`, `telemetry.sim_changed`

**Current files absorbed:** `sentinel.py` (Sentinel scoring), theft detection logic from device routes

---

### 3.6 Evidence & Forensics (`domains/evidence/`)

**Owns:** Evidence capture, storage, integrity chains, police report generation.

| Table | Owner |
|-------|-------|
| `media` | Evidence |
| `evidence_cases` | Evidence |

**Responsibilities:**
- Capture photos, audio, video from device
- Store media with SHA-256 integrity chain
- Group evidence into cases (per theft incident)
- Generate police reports (PDF)
- Evidence retention and cleanup
- Media deduplication

**Boundaries:**
- Does NOT trigger captures (that's Security or User)
- Does NOT command the device (that's Command & Control)
- Emits: `evidence.captured`, `evidence.case_created`, `evidence.package_ready`
- Consumes: `security.theft_detected` (to auto-create cases), `command.executed` (capture commands)

**Current files absorbed:** `evidence.py`, `evidence_pdf.py`, media handlers from device routes

---

### 3.7 Geospatial (`domains/geospatial/`)

**Owns:** Geofences, location history queries, spatial queries, CSV export.

| Table | Owner |
|-------|-------|
| `geofences` | Geospatial |

**Responsibilities:**
- Geofence CRUD (create, update, delete safe/danger zones)
- Geofence evaluation: detect entry/exit transitions
- Location history queries (time-range, device-filtered)
- CSV export of location history
- Spatial queries (nearest device, distance calculations)
- Geofence auto-actions (on exit: capture, siren, alert)

**Boundaries:**
- Does NOT store raw telemetry (reads from Telemetry)
- Does NOT send alerts (emits geofence_exit events)
- Emits: `geospatial.geofence_exit`, `geospatial.geofence_enter`
- Consumes: `telemetry.location_received` (to evaluate geofences)

**Current files absorbed:** Geofence logic from `routes/dashboard.py`

---

### 3.8 Notification Router (`domains/notification/`)

**Owns:** Alert delivery, channel routing, quiet hours, notification preferences.

| Table | Owner |
|-------|-------|
| `alerts` | Notification |
| `fcm_tokens` (read-only) | Device (shared) |

**Responsibilities:**
- Route alerts to correct channel: push (FCM), SMS (Twilio), email, WhatsApp, USSD
- Quiet hours enforcement
- Alert deduplication (don't spam the same theft alert)
- User notification preferences
- Health webhook delivery (Slack/Discord)
- WhatsApp bot responses

**Boundaries:**
- Does NOT decide WHAT to alert about (that's Security, Geospatial, Device)
- Does NOT store device state
- Emits: `notification.sent`, `notification.delivered`, `notification.failed`
- Consumes: ALL security/device/geospatial events (fan-in pattern)

**Current files absorbed:** `alerts.py`, `health_webhook.py`, `routes/whatsapp.py`, `routes/ussd.py`

---

### 3.9 Sharing & Circles (`domains/sharing/`)

**Owns:** Device sharing, family circles, access control.

| Table | Owner |
|-------|-------|
| `device_shares` | Sharing |
| `circles` | Sharing |
| `circle_members` | Sharing |
| `circle_devices` | Sharing |
| `family_circles` | Sharing |
| `family_members` | Sharing |

**Responsibilities:**
- Device sharing with role-based access (viewer, admin, device_only)
- Family circle creation and management
- Circle member invitation and removal
- Access control evaluation: "can user X do Y on device Z?"
- Share revocation

**Boundaries:**
- Does NOT know about commands or telemetry
- Pure ACL layer — other domains query it for authorization
- Emits: `sharing.granted`, `sharing.revoked`, `sharing.role_changed`
- Consumes: `device.registered`, `user.registered`

**Current files absorbed:** `routes/circles.py`, sharing logic from `routes/dashboard.py`

---

### 3.10 Business & Payments (`domains/business/`)

**Owns:** Subscriptions, payments, plan enforcement, usage limits.

| Table | Owner |
|-------|-------|
| `payments` | Business |

**Responsibilities:**
- Subscription plan management (free, personal, guardian, enterprise)
- Payment processing (Paystack integration)
- Usage limit enforcement (device count, storage, features)
- Plan upgrade/downgrade
- Invoice generation

**Boundaries:**
- Does NOT manage devices or users
- Emits: `business.plan_changed`, `business.payment_received`
- Consumes: `user.registered`

**Current files absorbed:** `routes/payments.py`

---

### 3.11 Privacy & Compliance (`domains/privacy/`)

**Owns:** Consent management, data export, data deletion, abuse prevention.

| Table | Owner |
|-------|-------|
| `tracking_consents` | Privacy |
| `privacy_consents` | Privacy |
| `abuse_reports` | Privacy |
| `data_export_requests` | Privacy |
| `data_retention` | Privacy |

**Responsibilities:**
- GDPR data export requests
- Right to deletion (account + all data)
- Tracking consent management
- Abuse report processing
- Data retention policy enforcement (auto-purge after N days)
- Privacy consent audit trail

**Boundaries:**
- Cross-cutting concern — other domains must query it
- Emits: `privacy.deletion_requested`, `privacy.export_completed`
- Consumes: `user.registered`

**Current files absorbed:** `routes/consent.py`, `data_retention.py`, `abuse_prevention.py`

---

### 3.12 Observability (`domains/observability/`)

**Owns:** Metrics, logging, tracing, error tracking, analytics.

| Table | Owner |
|-------|-------|
| `error_log` | Observability |
| `analytics_events` | Observability |
| `schema_migrations` | Observability |

**Responsibilities:**
- Structured logging (all domains emit structured events)
- Prometheus metrics exposition
- Sentry error tracking integration
- Analytics event collection (AB tests, feature usage)
- Health check aggregation
- Schema migration tracking

**Boundaries:**
- Pure infrastructure — consumed by all domains
- Emits: nothing (it IS the emission target)
- Consumes: all domain events

**Current files absorbed:** `analytics.py`, `logging_config.py`, `metrics.py` (collection parts)

---

## 4. Event Bus Architecture

### 4.1 Why Events

The current codebase has **zero coordination between domains**. When Sentinel detects theft:

1. Security scores the threat → needs to trigger evidence capture
2. Evidence capture needs to issue a command → needs Command & Control
3. Command delivery needs a notification → needs Notification Router
4. Dashboard needs real-time update → needs WebSocket broadcast

Today this is all **hardcoded in route handlers**. One route does everything. Events decouple this.

### 4.2 Implementation: Redis Streams

Redis Streams is chosen over a full message broker (RabbitMQ, Kafka) because:
- Redis is already in the stack (caching, pub/sub)
- Streams provide persistence, consumer groups, and acknowledgment
- At Magneetar's scale (< 10K events/sec), Streams are sufficient
- No new infrastructure to operate

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ Telemetry│────▶│ magneetar:   │────▶│ Security     │
│ Ingest   │     │ events       │     │ (Sentinel)   │
└──────────┘     │              │     └──────┬───────┘
                 │  Stream:     │            │
┌──────────┐     │  - telemetry │     ┌──────▼───────┐
│ Security │────▶│  - security  │────▶│ Evidence     │
│ (Score)  │     │  - command   │     │ (Capture)    │
└──────────┘     │  - geospatial│     └──────┬───────┘
                 │  - notification           │
┌──────────┐     │  - sharing   │     ┌──────▼───────┐
│ Geospatial│───▶│              │────▶│ Notification │
│ (Exit)   │     └──────────────┘     │ (Router)     │
└──────────┘                          └──────┬───────┘
                                             │
                                        ┌────▼─────┐
                                        │ WebSocket│
                                        │ Broadcast│
                                        └──────────┘
```

### 4.3 Event Contracts

Every event follows a standard envelope:

```python
@dataclass
class DomainEvent:
    event_type: str          # e.g. "security.theft_detected"
    aggregate_id: str        # e.g. device_id
    timestamp: str           # ISO 8601 UTC
    payload: dict            # Domain-specific data
    metadata: dict           # Correlation ID, source domain, etc.
```

**Event catalog:**

| Event Type | Producer | Consumers | Payload |
|------------|----------|-----------|---------|
| `telemetry.location_received` | Telemetry | Security, Geospatial | `{device_id, lat, lng, score, anomalies}` |
| `telemetry.heartbeat_received` | Telemetry | Security, Device | `{device_id, battery, sim_hash, admin_active}` |
| `telemetry.sim_changed` | Telemetry | Security, Notification | `{device_id, old_sim, new_sim}` |
| `security.theft_detected` | Security | Evidence, Command, Notification, WebSocket | `{device_id, score, threat_level, anomalies}` |
| `security.score_changed` | Security | WebSocket | `{device_id, old_score, new_score, threat_level}` |
| `security.recovered` | Security | Command, Notification, WebSocket | `{device_id}` |
| `command.issued` | Command | Notification | `{device_id, command_id, command_type, channel}` |
| `command.delivered` | Command | WebSocket | `{device_id, command_id, channel}` |
| `command.executed` | Command | Evidence, WebSocket | `{device_id, command_id, status}` |
| `command.failed` | Command | Notification, WebSocket | `{device_id, command_id, reason}` |
| `evidence.captured` | Evidence | WebSocket | `{device_id, case_id, media_type, media_id}` |
| `geospatial.geofence_exit` | Geospatial | Command, Notification, WebSocket | `{device_id, geofence_id, auto_action}` |
| `notification.sent` | Notification | Observability | `{channel, recipient, alert_type}` |
| `sharing.granted` | Sharing | WebSocket | `{device_id, grantee_id, role}` |
| `business.plan_changed` | Business | WebSocket | `{user_id, old_plan, new_plan}` |

### 4.4 Event Bus Interface

```python
# domains/events/bus.py

class EventBus:
    """Redis Streams-backed domain event bus."""

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to the appropriate stream."""

    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer: str,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> None:
        """Subscribe to a stream with automatic acknowledgment."""

    async def replay(
        self,
        stream: str,
        start: str = "0",
        end: str = "+",
    ) -> List[DomainEvent]:
        """Replay events from a stream (for debugging/recovery)."""
```

---

## 5. CQRS: Separating Writes from Reads

### 5.1 The Problem

Telemetry ingestion is **write-heavy** (thousands of location pings/sec). Dashboard queries are **read-heavy** (complex joins, aggregations, time-range queries). They compete for database resources.

### 5.2 The Solution

```
Device Fleet                    Dashboard Users
     │                               │
     ▼                               ▼
┌─────────┐                    ┌──────────┐
│ Write   │    ┌──────────┐   │ Read     │
│ Model   │───▶│ Postgres │◀──│ Model    │
│ ( append │    │          │   │ ( complex │
│   only)  │    │ locations│   │   queries)│
└─────────┘    │ (partitioned) │ └──────────┘
               └──────────┘
                     │
              ┌──────▼──────┐
              │ Materialized │
              │ View / Cache │
              │ (latest loc) │
              └─────────────┘
```

**Write model:**
- Optimized for append-only inserts
- Partitioned by time (monthly partitions for `locations`)
- Batch writes via write queue
- Minimal indexes (only what write path needs)

**Read model:**
- Pre-computed aggregations (device stats, daily summaries)
- Redis cache for "latest location per device"
- Denormalized views for dashboard queries
- Updated via event consumers (eventual consistency is acceptable for dashboard)

---

## 6. Background Job System

### 6.1 Problem

Current approach: `asyncio.create_task()` with no retry, no dead-letter queue, no visibility. If a task fails silently, nobody knows.

### 6.2 Solution: ARQ (Async Redis Queue)

ARQ is chosen because:
- Native async (matches FastAPI)
- Redis-backed (already in stack)
- Job retry, scheduling, and result storage
- Worker health monitoring

**Job categories:**

| Job | Schedule | Retry | Description |
|-----|----------|-------|-------------|
| `evaluate_geofences` | On location event | 3 | Check geofence transitions |
| `process_sentinel` | On heartbeat event | 3 | Score threat, trigger responses |
| `capture_evidence` | On theft_detected event | 5 | Queue photo + audio capture |
| `send_alert` | On security/geospatial event | 5 | Multi-channel alert delivery |
| `purge_old_data` | Daily at 03:00 UTC | 1 | Data retention cleanup |
| `archive_stale_devices` | Every 6 hours | 1 | Soft-archive silent devices |
| `cleanup_rate_limits` | Every 6 hours | 1 | Purge stale rate limit entries |
| `generate_evidence_pdf` | On case closure | 3 | Build police report PDF |
| `process_data_export` | On user request | 3 | Package user data for GDPR |
| `sync_device_state` | Every 30 seconds | 1 | Update online/offline status |

---

## 7. API Surface Separation

### 7.1 Three API Surfaces

| Surface | Audience | Protocol | Latency Budget | Throughput |
|---------|----------|----------|---------------|------------|
| **Device API** | Android app | HTTP/REST | < 500ms | High (1K+ req/s) |
| **Dashboard API** | Web dashboard | HTTP/REST + WebSocket | < 2s | Medium (100 req/s) |
| **Public API** | Config, health, APK | HTTP/REST | < 1s | Low (10 req/s) |

### 7.2 Device API (`/api/device/*`)

Optimized for high-throughput, low-latency device communication:

```
POST /api/device/register          → Device Lifecycle
POST /api/device/location          → Telemetry Pipeline
POST /api/device/heartbeat         → Telemetry Pipeline
POST /api/device/media             → Evidence
GET  /api/device/commands/{id}     → Command & Control
POST /api/device/commands/{id}/ack → Command & Control
POST /api/device/fcm-token         → Device Lifecycle
```

**Design principles:**
- Stateless (JWT validated per request)
- Minimal response bodies (devices don't need rich payloads)
- Write batching for location pings
- No complex queries — devices write, they don't read dashboards

### 7.3 Dashboard API (`/api/dashboard/*`)

Optimized for rich queries and real-time updates:

```
GET  /api/dashboard/devices                    → Device (with latest location)
GET  /api/dashboard/devices/{id}/locations     → Telemetry (time-range query)
POST /api/dashboard/command                    → Command & Control
GET  /api/dashboard/evidence/{id}              → Evidence
POST /api/dashboard/geofence                   → Geospatial
GET  /api/dashboard/alerts                     → Notification
POST /api/dashboard/share                      → Sharing
GET  /api/dashboard/stats                      → Observability (aggregated)
```

**Design principles:**
- Rich query support (filters, pagination, sorting)
- WebSocket for real-time updates (device location changes, alerts)
- Complex joins acceptable (read-optimized)
- Rate limited per user

### 7.4 WebSocket Protocol

```
Client → Server:
  {"type": "ping"} / {"type": "pong"}

Server → Client:
  {"type": "device_location", "device_id": "...", "lat": ..., "lng": ...}
  {"type": "alert", "device_id": "...", "alert_type": "theft", ...}
  {"type": "command_status", "device_id": "...", "command_id": ..., "status": "..."}
  {"type": "device_online", "device_id": "..."}
  {"type": "device_offline", "device_id": "..."}
  {"type": "theft_detected", "device_id": "...", "score": ..., "threat_level": "..."}
  {"type": "shutdown", "message": "...", "reconnect": true}
```

---

## 8. Storage Architecture

### 8.1 PostgreSQL (Primary)

**Why PostgreSQL over SQLite (final decision):**

| Requirement | SQLite | PostgreSQL |
|-------------|--------|------------|
| Concurrent writes | ❌ Single-writer | ✅ True concurrency |
| Horizontal scaling | ❌ File-based | ✅ Read replicas |
| Geospatial queries | ❌ Limited | ✅ PostGIS |
| Point-in-time recovery | ❌ Manual backup | ✅ WAL archiving |
| Connection pooling | ❌ N/A | ✅ PgBouncer / asyncpg |
| Time-series partitioning | ❌ N/A | ✅ Native partitioning |

**Schema design principles:**
- One domain = one schema file (or migration set)
- Foreign keys enforced at DB level
- UUID primary keys for user-facing entities
- Auto-increment for internal entities (locations, heartbeats)
- Timestamps in UTC, stored as `timestamptz`
- Soft deletes for user data (GDPR compliance)
- No ORM — raw SQL with parameterized queries (existing convention)

**Partitioning strategy for `locations`:**

```sql
CREATE TABLE locations (
    id BIGSERIAL,
    device_id TEXT NOT NULL,
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    provider TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    -- ... other columns
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Monthly partitions
CREATE TABLE locations_2026_09 PARTITION OF locations
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE locations_2026_10 PARTITION OF locations
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
```

### 8.2 Redis (Cache + Real-time)

| Use Case | Key Pattern | TTL |
|----------|-------------|-----|
| Latest device location | `device:{id}:location` | 5 min |
| Device online status | `device:{id}:online` | 2 min |
| Dashboard WebSocket connections | `ws:connections:{user_id}` | Session |
| Rate limiting | `ratelimit:{identity}:{endpoint}` | Sliding window |
| Session cache | `session:{token_hash}` | 15 min |
| Event bus streams | `magnetar:events:{domain}` | Persistent |

### 8.3 Object Storage (Media)

Evidence media (photos, audio, video) should be stored in object storage, not the database:

- **Development:** Local filesystem (`server/media/`)
- **Production:** S3-compatible (Cloudflare R2, AWS S3, or Neon Object Storage)
- Media metadata in PostgreSQL, binary content in object storage
- Signed URLs for dashboard access (time-limited, no direct DB access)

---

## 9. File Structure (Target)

```
server/
├── main.py                          # App init, middleware, route registration (< 200 lines)
├── config.py                        # Environment configuration
├── models.py                        # Shared Pydantic schemas (thin, per-domain below)
│
├── domains/
│   ├── __init__.py
│   │
│   ├── identity/
│   │   ├── __init__.py
│   │   ├── routes.py                # Auth endpoints (register, login, 2FA, etc.)
│   │   ├── service.py               # Business logic
│   │   ├── repository.py            # Database queries
│   │   └── models.py                # Domain-specific Pydantic schemas
│   │
│   ├── device/
│   │   ├── __init__.py
│   │   ├── routes.py                # Device registration, claim, config
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── telemetry/
│   │   ├── __init__.py
│   │   ├── routes.py                # Location, heartbeat endpoints
│   │   ├── service.py               # Validation, batching, dedup
│   │   ├── repository.py
│   │   ├── models.py
│   │   └── write_queue.py           # Batched write pipeline
│   │
│   ├── command/
│   │   ├── __init__.py
│   │   ├── routes.py                # Issue command, ack
│   │   ├── service.py               # Multi-channel delivery
│   │   ├── repository.py
│   │   ├── models.py
│   │   ├── fcm_delivery.py          # Push notification delivery
│   │   └── sms_delivery.py          # SMS fallback delivery
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── routes.py                # Security score queries
│   │   ├── service.py               # Sentinel engine
│   │   ├── repository.py
│   │   ├── models.py
│   │   └── sentinel.py              # Scoring algorithms
│   │
│   ├── evidence/
│   │   ├── __init__.py
│   │   ├── routes.py                # Evidence cases, media access
│   │   ├── service.py               # Capture orchestration
│   │   ├── repository.py
│   │   ├── models.py
│   │   └── pdf_generator.py         # Police report PDF
│   │
│   ├── geospatial/
│   │   ├── __init__.py
│   │   ├── routes.py                # Geofence CRUD, location history
│   │   ├── service.py               # Geofence evaluation
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── notification/
│   │   ├── __init__.py
│   │   ├── routes.py                # Alert history, preferences
│   │   ├── service.py               # Channel routing
│   │   ├── repository.py
│   │   ├── models.py
│   │   ├── push.py                  # FCM delivery
│   │   ├── sms.py                   # Twilio delivery
│   │   ├── email.py                 # Email delivery
│   │   ├── whatsapp.py              # WhatsApp bot
│   │   └── ussd.py                  # USSD menu
│   │
│   ├── sharing/
│   │   ├── __init__.py
│   │   ├── routes.py                # Share, circle management
│   │   ├── service.py
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── business/
│   │   ├── __init__.py
│   │   ├── routes.py                # Payment endpoints
│   │   ├── service.py               # Plan enforcement
│   │   ├── repository.py
│   │   └── models.py
│   │
│   ├── privacy/
│   │   ├── __init__.py
│   │   ├── routes.py                # Consent, data export
│   │   ├── service.py               # GDPR operations
│   │   ├── repository.py
│   │   └── models.py
│   │
│   └── observability/
│       ├── __init__.py
│       ├── routes.py                # Metrics, health
│       ├── service.py
│       └── models.py
│
├── infrastructure/
│   ├── __init__.py
│   ├── database.py                  # Connection pool, session management
│   ├── migrations/                  # Alembic migrations (one per domain)
│   ├── events/
│   │   ├── bus.py                   # Redis Streams event bus
│   │   ├── types.py                 # DomainEvent dataclass
│   │   └── handlers.py             # Event → job dispatch
│   ├── jobs/
│   │   ├── worker.py               # ARQ worker setup
│   │   └── tasks.py                # Background job definitions
│   ├── cache.py                     # Redis cache interface
│   ├── storage.py                   # Object storage (S3/R2)
│   └── middleware.py                # CORS, rate limiting, logging, etc.
│
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/                        # Domain unit tests
│   ├── integration/                 # Cross-domain integration tests
│   └── e2e/                         # End-to-end API tests
│
├── migrations/                      # Alembic migration files
├── static/                          # APK files, static assets
└── requirements.txt
```

---

## 10. Migration Path

We don't rewrite from scratch. We **incrementally extract domains** from the monolith.

### Phase 0: Foundation (Week 1-2)

1. **Finish PostgreSQL migration** — complete the SQL portability pass (ADR-0005 Phase 2b)
2. **Set up Alembic** — replace manual `migrations.py` with proper migration tooling
3. **Establish domain directory structure** — create `domains/` and `infrastructure/` directories
4. **Extract event bus** — implement Redis Streams bus in `infrastructure/events/`
5. **Extract middleware** — move all middleware from `main.py` to `infrastructure/middleware.py`

**main.py target:** < 200 lines (app init, middleware registration, route inclusion)

### Phase 1: Extract Identity Domain (Week 3-4)

1. Move `user_auth.py`, `user_security.py` → `domains/identity/`
2. Move auth functions from `auth.py` → `domains/identity/` (keep token utilities in infrastructure)
3. Write domain-specific Pydantic models
4. Add unit tests for identity domain
5. Wire event bus: `user.registered`, `user.authenticated`

### Phase 2: Extract Device + Telemetry (Week 5-8)

1. Extract device registration → `domains/device/`
2. Extract telemetry ingestion → `domains/telemetry/`
3. Extract write queue → `domains/telemetry/write_queue.py`
4. Implement CQRS read model for dashboard queries
5. Add location table partitioning
6. Wire events: `telemetry.location_received`, `telemetry.heartbeat_received`
7. This is the **highest-risk phase** — the write path is performance-critical

### Phase 3: Extract Command + Security (Week 9-12)

1. Extract command lifecycle → `domains/command/`
2. Extract Sentinel engine → `domains/security/`
3. Wire event-driven theft detection: `security.theft_detected` → auto-capture + alert
4. Extract FCM/SMS delivery → `domains/command/fcm_delivery.py`, `domains/command/sms_delivery.py`
5. Wire events: `command.issued`, `command.executed`, `security.theft_detected`

### Phase 4: Extract Supporting Domains (Week 13-16)

1. Extract evidence → `domains/evidence/`
2. Extract geospatial → `domains/geospatial/`
3. Extract notifications → `domains/notification/`
4. Extract sharing → `domains/sharing/`
5. Extract business → `domains/business/`
6. Extract privacy → `domains/privacy/`
7. Wire remaining events

### Phase 5: Infrastructure Hardening (Week 17-20)

1. Set up ARQ workers for background jobs
2. Add Redis cache layer for device state
3. Set up object storage for media (S3/R2)
4. Add Prometheus metrics per domain
5. Add Grafana dashboards per domain
6. Performance testing and optimization

---

## 11. Migration Rules

During extraction, these rules prevent regressions:

1. **No behavioral changes.** Extract first, refactor second. The API contract must not change.
2. **Tests must pass at every step.** Each extraction commit must leave the test suite green.
3. **Events are additive.** Publishing events doesn't change existing behavior — it's a new output.
4. **Feature flags for new paths.** If a new event-driven path replaces an old direct call, use a feature flag to toggle.
5. **No big-bang rewrites.** Every phase is independently deployable.

---

## 12. What This Unblocks

| Current Limitation | After Redesign |
|-------------------|----------------|
| `dashboard.py` at 1,935 lines | Each domain < 400 lines |
| SQLite single-writer bottleneck | PostgreSQL concurrent writes |
| No background job visibility | ARQ dashboard + retry + dead-letter |
| Features are silos | Event-driven coordination |
| Can't add a team member without merge conflicts | Clear domain ownership |
| No way to test domains independently | Domain-level unit tests |
| Telemetry write path bottlenecks dashboard reads | CQRS separation |
| No media object storage | S3/R2 with signed URLs |
| No time-series optimization | Partitioned location tables |
| Manual migrations | Alembic with rollback support |

---

## 13. Decisions NOT Made Here

These are deferred to domain-specific ADRs:

- **ORM vs raw SQL:** The codebase convention is raw SQL. This stays unless a domain specifically benefits from SQLAlchemy (likely Evidence and Sharing).
- **GraphQL vs REST:** REST stays. The current API surface is clean enough.
- **Microservices decomposition:** Explicitly rejected. Domain-driven monolith is the target.
- **Event sourcing:** Too complex for current scale. Standard CRUD with event notifications is sufficient.
- **Kubernetes vs single-server:** Infrastructure choice is orthogonal to domain architecture.

---

*This document replaces ADR-0001 through ADR-0005 in scope. Those ADRs remain for historical context but their decisions are superseded by the PostgreSQL-first, domain-driven approach defined here.*
