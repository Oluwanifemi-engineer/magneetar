"""
Magneetar Database Layer
SQLite implementation with full schema. PostgreSQL-compatible syntax.

Performance optimizations:
- Connection pooling (db_pool.py) for reduced connection overhead
- In-memory caching (cache.py) for frequently accessed data
- WAL mode for concurrent reads
- Write batching for high-throughput telemetry
"""

import os
import sqlite3
from contextlib import contextmanager

from config import settings

DB_PATH = settings.DB_PATH

# Import caching layer
try:
    from cache import (
        cache_device_info,
        cache_device_owner,
        get_cached_device_info,
        get_cached_device_owner,
        invalidate_device_cache,
        invalidate_device_owner,
    )

    CACHE_ENABLED = True
except ImportError:
    CACHE_ENABLED = False


def _connect() -> sqlite3.Connection:
    """Create a new database connection with correct settings."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s if DB is locked
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster than FULL, still safe with WAL
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _connect_store():
    """Return the storage connection for the configured backend.

    MT_DATABASE_URL set -> PgStore (sync facade over asyncpg, storage.py);
    otherwise -> the unchanged sqlite3.Connection. Both expose the same
    route-facing contract (execute/fetchone/fetchall/rowcount/lastrowid/
    commit/close), so no route code changes for the switch itself
    (ADR-0005 Phase 2a).
    """
    if settings.DATABASE_URL:
        from storage import PgStore

        return PgStore()
    return _connect()


def get_db():
    """FastAPI dependency - yields a database connection.
    Connection failures propagate to the caller for fast failure detection.
    SQLite contention is handled by busy_timeout=5000 in _connect().
    """
    conn = _connect_store()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_context():
    """Context manager for non-FastAPI usage."""
    conn = _connect_store()
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: str = None):
    """Initialize database schema with all required tables."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.executescript(
        """
        -- ─── Users ────────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            tier TEXT DEFAULT 'free',
            is_active BOOLEAN DEFAULT TRUE,
            email_verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

        -- ─── Devices ────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            alias TEXT,
            owner_id TEXT,
            device_fingerprint TEXT,
            platform TEXT DEFAULT 'android',
            app_version TEXT,
            os_version TEXT,
            model TEXT,
            imei_hash TEXT,
            sim_serial_hash TEXT,
            device_key_hash TEXT,
            last_seen TIMESTAMP,
            registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_stolen BOOLEAN DEFAULT FALSE,
            theft_confirmed_at TIMESTAMP,
            operating_mode TEXT DEFAULT 'normal',
            sentinel_score INTEGER DEFAULT 0,
            capture_armed BOOLEAN,
            alert_phone TEXT,
            alert_email TEXT,
            -- Per-device alert preferences (NULL = global defaults)
            -- alert_channels: JSON array e.g. ["whatsapp","sms","push"]
            -- enabled_types:  JSON array e.g. ["theft","sim_change","offline"]
            alert_channels TEXT,
            enabled_types TEXT,
            quiet_hours_start INTEGER,
            quiet_hours_end INTEGER,
            -- Set when a device has been silent beyond the archive threshold
            -- (MT_ARCHIVE_AFTER_DAYS, default 30). Soft flag only: the row and
            -- its history are kept so an archived device can come back. Any
            -- fresh telemetry/heartbeat clears it automatically.
            archived_at TIMESTAMP,
            -- Offline Command Relay (SMS): the phone's SIM number to which the
            -- server SMSes commands when the device is offline, plus the opt-in
            -- toggle (owner must enable + confirm the number before any SMS is
            -- sent — Twilio costs real money and an SMS command is a security
            -- surface). The Android app reports its SIM number best-effort and
            -- the server prefills sms_phone only when it is still NULL.
            sms_phone TEXT,
            sms_commands_enabled BOOLEAN DEFAULT 0
        );

        -- ─── Cell Location Cache (offline command relay) ───────────────────
        -- Maps a cell-tower fingerprint (MCC/MNC/TAC/CID list, as reported by
        -- an offline device) to approximate coordinates, resolved lazily by a
        -- pluggable provider (Unwired Labs etc.) and cached so a fingerprint is
        -- never looked up twice. Graceful degradation: an unconfigured
        -- provider simply means "unresolved" — the raw fingerprint is still
        -- stored on the location row for a future lookup.
        CREATE TABLE IF NOT EXISTS cell_location_cache (
            fingerprint TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            accuracy_meters REAL,
            provider TEXT,
            resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    )
    # NOTE: idx_devices_key_hash is created AFTER the column migrations below —
    # on an existing DB whose devices table predates device_key_hash, creating
    # the index here would crash with "no such column" before the ALTER TABLE
    # migration runs.

    # ─── Safe Schema Migrations ───────────────────────────────────────────────
    # Add device_key_hash to existing databases (column may already exist on fresh DBs)
    try:
        c.execute("ALTER TABLE devices ADD COLUMN device_key_hash TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists — fresh DB or already migrated

    # Per-device alert recipients (override the global MT_ALERT_PHONE/EMAIL)
    for col in ("alert_phone", "alert_email"):
        try:
            c.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Per-device alert preferences (channels, enabled types, quiet hours)
    for col in ("alert_channels", "enabled_types"):
        try:
            c.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Quiet hours are hours 0-23 — INTEGER affinity so existing DBs (migrated
    # via ALTER) store real ints, matching the CREATE TABLE declaration on
    # fresh DBs (TEXT affinity would store 22 as the string '22').
    for col in ("quiet_hours_start", "quiet_hours_end"):
        try:
            c.execute(f"ALTER TABLE devices ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Armed Watch state — True while the device's camera|mic FGS is armed
    # (remote capture possible). Reported via telemetry/heartbeat; NULL until
    # the first report from an updated app (dashboard shows "Unknown").
    try:
        c.execute("ALTER TABLE devices ADD COLUMN capture_armed BOOLEAN")
    except sqlite3.OperationalError:
        pass  # Column already exists — fresh DB or already migrated

    # Failure reason for a failed command ack — the Android app sends WHY a
    # capture failed (muted mic / blocked camera) so the dashboard isn't a
    # bare red FAILED. Migrated for existing DBs.
    try:
        c.execute("ALTER TABLE commands ADD COLUMN failure_reason TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists — fresh DB or already migrated

    # Stale-device archive flag — set by the archive sweep when a device is
    # silent beyond MT_ARCHIVE_AFTER_DAYS; cleared by any fresh telemetry.
    try:
        c.execute("ALTER TABLE devices ADD COLUMN archived_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass  # Column already exists — fresh DB or already migrated

    # Offline Command Relay (SMS): phone number + opt-in toggle. Migrated for
    # existing DBs — an ALTERed column defaults to NULL/0 (not enabled), so a
    # pre-existing deployment is never auto-enrolled for paid SMS commands.
    try:
        c.execute("ALTER TABLE devices ADD COLUMN sms_phone TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        c.execute("ALTER TABLE devices ADD COLUMN sms_commands_enabled BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Delivery channel for a command: NULL/'poll' (the normal device poll) or
    # 'sms' (delivered to the phone over the cellular SMS channel because the
    # device was offline). Surfaced in command history so the dashboard can
    # show how a command was routed.
    try:
        c.execute("ALTER TABLE commands ADD COLUMN delivery_channel TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Geofence auto-actions + persisted transition state (v1.5). auto_action
    # is NULL (no reaction beyond the alert) until an owner sets a policy;
    # last_inside is NULL until the device is first observed inside the zone.
    try:
        c.execute("ALTER TABLE geofences ADD COLUMN auto_action TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        c.execute("ALTER TABLE geofences ADD COLUMN last_inside BOOLEAN")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Find Network: opaque per-request beacon token broadcast over BLE by the
    # stolen device. Migrated for existing DBs — a pre-beacon request stays
    # NULL and simply can't be beaconed until a new request is launched.
    try:
        c.execute("ALTER TABLE recovery_requests ADD COLUMN beacon_token TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Location at-rest encryption (v1.5): ciphertext column for encrypted
    # telemetry rows (see the locations CREATE TABLE comment). Existing rows
    # stay plaintext (flag 0) — dual-mode readers handle both.
    try:
        c.execute("ALTER TABLE locations ADD COLUMN location_data TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Media storage refactor (v1.4): evidence bytes moved from the data_b64
    # blob to files on disk. New columns are NULL for legacy rows (they keep
    # their base64) and populated for new rows (data_b64 written as '').
    try:
        c.execute("ALTER TABLE media ADD COLUMN file_path TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        c.execute("ALTER TABLE media ADD COLUMN file_size INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Developer API keys v1.1 (2026-08-14): readonly key type + usage
    # metering. Existing rows default to 'live' (current behavior) and a
    # request count of 0.
    try:
        c.execute("ALTER TABLE api_keys ADD COLUMN key_type TEXT NOT NULL DEFAULT 'live'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        c.execute("ALTER TABLE api_keys ADD COLUMN request_count INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # ─── Account security (v1.4) ────────────────────────────────────────────
    # TOTP 2FA: the secret is AES-256-GCM encrypted at rest (user_security.py)
    # and only enabled after the user proves a valid code; totp_last_period
    # stores the time-step of the last accepted code for replay protection.
    for col in ("totp_secret_enc",):
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
    for col in ("totp_enabled", "totp_last_period"):
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # Column already exists

    c.executescript(
        """
        -- Password reset + email verification tokens (single-use, hashed,
        -- expiring). token_hash stores SHA-256(token) — the raw token is
        -- only ever sent to the user's inbox.
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id);

        CREATE TABLE IF NOT EXISTS email_verify_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verify_tokens(user_id);
        """
    )

    c.executescript(
        """

        -- ─── Locations (TelemetryPing) ─────────────────────────────────────
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            altitude REAL,
            accuracy_horizontal REAL,
            accuracy_vertical REAL,
            confidence_level TEXT DEFAULT 'UNKNOWN',
            speed REAL,
            bearing REAL,
            activity_type TEXT,
            step_count INTEGER,
            provider TEXT,
            gps_satellite_count INTEGER,
            wifi_bssids TEXT,
            cell_tower_ids TEXT,
            ble_devices_nearby INTEGER,
            battery_percent INTEGER,
            is_charging BOOLEAN,
            network_type TEXT,
            signal_strength_dbm INTEGER,
            is_location_enabled BOOLEAN,
            is_airplane_mode BOOLEAN,
            sim_changed BOOLEAN DEFAULT FALSE,
            sim_serial_hash TEXT,
            sentinel_score INTEGER DEFAULT 0,
            threat_level TEXT DEFAULT 'SAFE',
            anomalies TEXT,
            device_timestamp TIMESTAMP,
            server_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            was_queued BOOLEAN DEFAULT FALSE,
            queued_at TIMESTAMP,
            queue_position INTEGER,
            ping_sequence INTEGER,
            location_encrypted BOOLEAN DEFAULT FALSE,
            -- At-rest encryption (v1.5): when MT_ENCRYPTION_KEY is set, lat/lng
            -- hold 0.0 placeholders (NOT NULL constraint) and the base64
            -- AES-256-GCM ciphertext (per-device HKDF key) lives here with
            -- location_encrypted=1. ALL readers must go through
            -- encryption.decrypt_location_row() — legacy plaintext rows keep
            -- real coords in lat/lng with the flag 0 (dual-mode reads).
            location_data TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Media ──────────────────────────────────────────────────────────
        -- file_path/file_size: since the v1.4 media refactor, evidence bytes
        -- live on DISK (media_store.py) and the row keeps metadata only.
        -- data_b64 stays NOT NULL for legacy rows (pre-refactor); new rows
        -- store '' and carry file_path. Consumers use media_store's
        -- media_bytes_for_row() which prefers disk and falls back to b64.
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            type TEXT NOT NULL,
            data_b64 TEXT NOT NULL,
            lat REAL,
            lng REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            evidence_case_id TEXT,
            sha256_hash TEXT,
            file_path TEXT,
            file_size INTEGER,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Commands ───────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            command TEXT NOT NULL,
            params TEXT,
            status TEXT DEFAULT 'pending',
            priority INTEGER DEFAULT 5,
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            executed_at TIMESTAMP,
            expires_at TIMESTAMP,
            failure_reason TEXT,
            -- Delivery channel: NULL/'poll' (normal device poll) or 'sms'
            -- (offline command relay — delivered over the cellular SMS
            -- channel because the device had no data). SMS-delivered commands
            -- are excluded from the device poll so an offline phone that
            -- executes from SMS then comes online does not double-run them.
            delivery_channel TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Evidence Cases ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS evidence_cases (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            theft_time TIMESTAMP,
            status TEXT DEFAULT 'active',
            location_count INTEGER DEFAULT 0,
            photo_count INTEGER DEFAULT 0,
            audio_count INTEGER DEFAULT 0,
            sha256_chain TEXT,
            pdf_generated BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Alerts ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            recipient TEXT,
            message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Heartbeats ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            battery_percent INTEGER,
            is_charging BOOLEAN,
            network_type TEXT,
            device_admin_active BOOLEAN,
            sim_hash TEXT,
            app_version TEXT,
            pending_evidence_count INTEGER DEFAULT 0,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Geofences ──────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS geofences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            name TEXT,
            center_lat REAL NOT NULL,
            center_lng REAL NOT NULL,
            radius_meters REAL NOT NULL,
            is_safe_zone BOOLEAN DEFAULT TRUE,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            -- Per-zone automated action fired on an EXIT transition (once, at
            -- the entry→exit boundary): 'capture' queues a front-camera photo
            -- + audio capture, 'siren' queues the max-volume alarm, 'alert'
            -- fires the geofence_exit alert only. NULL = alert only.
            -- (v1.5 auto-actions — P0 gap-closer #1 from COMPETITOR_AUDIT.md)
            auto_action TEXT,
            -- Persisted inside/outside state so a transition is reported
            -- EXACTLY ONCE. NULL = unknown (device never observed inside);
            -- an exit can only fire after an observed entry. The old code
            -- never persisted this, so check_geofences always saw
            -- was_inside=False and 'exited' events (and the exit alert) could
            -- never fire — dead code in production. (v1.5 fix)
            last_inside BOOLEAN,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Device Sharing (Milestone 2 P1) ───────────────────────────────
        -- Grant another account (family member, partner) access to a device.
        -- role: device_only (status glance) / viewer (read) / admin (control);
        -- only the device owner can grant/revoke (enforced in routes).
        -- UNIQUE(device_id, grantee) makes an invite idempotent — re-inviting
        -- the same account upgrades/downgrades the role in place.
        CREATE TABLE IF NOT EXISTS device_shares (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            grantee_user_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (device_id, grantee_user_id),
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        CREATE INDEX IF NOT EXISTS idx_device_shares_device ON device_shares(device_id);
        CREATE INDEX IF NOT EXISTS idx_device_shares_grantee ON device_shares(grantee_user_id);

        -- ─── Developer API Keys (docs/developer-api.md) ───────────────────
        -- Per-account, scoped, revocable keys for third-party integrations
        -- (resellers, alerting scripts, custom dashboards). The full key is
        -- shown EXACTLY once at creation and never stored: only its SHA-256
        -- hash + a 12-char prefix (indexed lookup) live here. scopes is a
        -- comma-separated subset of {devices:read, devices:write,
        -- alerts:read, media:read}; a key is always intersected with the
        -- owning account's own RBAC rights (viewer-shared devices stay
        -- read-only through the key too). revoked_at is a soft-revoke
        -- (checked on every request); expires_at NULL = never.
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            key_prefix TEXT NOT NULL UNIQUE,
            key_hash TEXT NOT NULL,
            scopes TEXT NOT NULL DEFAULT 'devices:read',
            -- 'live' (default) or 'readonly' — readonly keys structurally
            -- cannot carry devices:write (enforced at creation AND auth
            -- time), so a leaked readonly key can never issue a wipe/lock.
            key_type TEXT NOT NULL DEFAULT 'live',
            -- Usage metering: incremented on every key-authenticated request
            -- (best-effort, alongside last_used_at).
            request_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP,
            expires_at TIMESTAMP,
            revoked_at TIMESTAMP
            -- NOTE: no FOREIGN KEY on user_id (same precedent as
            -- guardian_profiles) — the shared-DB test fixtures wipe the users
            -- table without an ordering dependency, and a key whose account
            -- was deleted is already rejected at auth time (the account must
            -- exist and be active). Account deletion removes keys explicitly
            -- (data_export.delete_user_data).
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);

        -- ─── Guardian Network (community recovery) ─────────────────────────
        -- Users who opted in to help recover other people's stolen devices.
        CREATE TABLE IF NOT EXISTS guardian_profiles (
            user_id TEXT PRIMARY KEY,
            opted_in BOOLEAN DEFAULT TRUE,
            radius_km INTEGER DEFAULT 20,
            handle TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        );

        -- Recovery campaigns: an owner launches one for a stolen device.
        CREATE TABLE IF NOT EXISTS recovery_requests (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            description TEXT,
            last_lat REAL,
            last_lng REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP,
            closed_reason TEXT,
            -- Find Network: opaque per-request token broadcast by the stolen
            -- device over BLE. Guardians report the token (never the request
            -- id) so the request id itself never goes on the air; the server
            -- resolves token -> request. NULL for pre-beacon requests.
            beacon_token TEXT,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        CREATE INDEX IF NOT EXISTS idx_recovery_requests_status ON recovery_requests(status);
        CREATE INDEX IF NOT EXISTS idx_recovery_requests_owner ON recovery_requests(owner_id);

        -- Guardian-reported sightings on an active recovery request.
        CREATE TABLE IF NOT EXISTS recovery_sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            guardian_id TEXT NOT NULL,
            guardian_handle TEXT,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES recovery_requests(id)
        );

        CREATE INDEX IF NOT EXISTS idx_recovery_sightings_request ON recovery_sightings(request_id);

        -- ─── Audit Log (never deleted) ──────────────────────────────────────
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            actor TEXT,
            ip_address TEXT,
            details TEXT
        );

        -- ─── FCM Push Tokens ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS fcm_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            fcm_token TEXT NOT NULL,
            platform TEXT DEFAULT 'android',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(device_id, fcm_token),
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        CREATE INDEX IF NOT EXISTS idx_fcm_tokens_device ON fcm_tokens(device_id);

        -- ─── Rate Limiting ──────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- ─── Token Revocation ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti TEXT PRIMARY KEY,
            revoked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        );

        -- ─── Indexes ────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_devices_key_hash ON devices(device_key_hash);
        CREATE INDEX IF NOT EXISTS idx_locations_device ON locations(device_id);
        CREATE INDEX IF NOT EXISTS idx_locations_timestamp ON locations(server_timestamp);
        -- At-most-once dedup lookups (device + ping_sequence + device_timestamp
        -- uniqueness is enforced by the application layer in
        -- routes/devices.py::location_row_exists, NOT by a UNIQUE index — the
        -- prod DB already contains historical duplicates, so a UNIQUE index
        -- migration would fail; the index keeps the guard cheap instead).
        CREATE INDEX IF NOT EXISTS idx_locations_dedup ON
            locations(device_id, ping_sequence, device_timestamp);
        CREATE INDEX IF NOT EXISTS idx_media_device ON media(device_id);
        CREATE INDEX IF NOT EXISTS idx_commands_device ON commands(device_id);
        CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
        CREATE INDEX IF NOT EXISTS idx_heartbeats_device ON heartbeats(device_id);
        CREATE INDEX IF NOT EXISTS idx_geofences_device ON geofences(device_id);
        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier ON rate_limits(identifier, action);

        -- ─── Token Revocation Indexes ──────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_revoked_tokens_jti ON revoked_tokens(jti);

        -- ─── Error Log ───────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL DEFAULT 'ERROR',
            source TEXT,
            message TEXT NOT NULL,
            traceback TEXT,
            request_method TEXT,
            request_path TEXT,
            request_ip TEXT,
            user_agent TEXT,
            device_id TEXT,
            resolved BOOLEAN DEFAULT FALSE,
            resolved_at TIMESTAMP,
            resolved_by TEXT,
            notes TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_error_log_timestamp ON error_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_error_log_resolved ON error_log(resolved);
    """
    )
    conn.commit()
    conn.close()


def delete_device_cascade(conn, device_id: str):
    """Permanently delete a device and ALL of its related data.

    Deletes child rows first to satisfy FK constraints (guardian sightings and
    recovery requests reference devices; locations/media/commands/evidence/
    alerts/heartbeats/geofences/fcm_tokens all reference devices). This is the
    "permanent deletion" path promised in the privacy policy.
    """
    # Guardian sightings reference recovery_requests, which reference devices.
    conn.execute(
        "DELETE FROM recovery_sightings WHERE request_id IN (SELECT id FROM recovery_requests WHERE device_id=?)",
        (device_id,),
    )
    conn.execute("DELETE FROM recovery_requests WHERE device_id=?", (device_id,))

    # Media files on disk must be removed when the device row goes away —
    # the DB rows are deleted below, so resolve the file paths FIRST.
    try:
        from media_store import delete_media_file

        media_rows = conn.execute("SELECT file_path FROM media WHERE device_id=?", (device_id,)).fetchall()
        for row in media_rows:
            delete_media_file(row["file_path"])
    except Exception:
        pass  # never block deletion on a disk glitch

    # Everything else references the device row directly. device_shares rows
    # must go with the device (a deleted device must not leave dangling grants
    # that the grantee's device list would try to join).
    for table in (
        "locations",
        "media",
        "commands",
        "evidence_cases",
        "alerts",
        "heartbeats",
        "geofences",
        "device_shares",
        "fcm_tokens",
        "error_log",
    ):
        conn.execute(f"DELETE FROM {table} WHERE device_id=?", (device_id,))

    conn.execute("DELETE FROM devices WHERE id=?", (device_id,))


def log_audit(action: str, actor: str = None, ip_address: str = None, details: str = None):
    """Log an action to the audit trail."""
    with get_db_context() as conn:
        conn.execute(
            "INSERT INTO audit_log (action, actor, ip_address, details) VALUES (?,?,?,?)",
            (action, actor, ip_address, details),
        )
        conn.commit()


def log_error(
    level: str,
    message: str,
    source: str = None,
    traceback: str = None,
    request_method: str = None,
    request_path: str = None,
    request_ip: str = None,
    user_agent: str = None,
    device_id: str = None,
):
    """Log an error to the error_log table for dashboard viewing."""
    try:
        with get_db_context() as conn:
            conn.execute(
                """INSERT INTO error_log (level, message, source, traceback,
                   request_method, request_path, request_ip, user_agent, device_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    level,
                    message,
                    source,
                    traceback,
                    request_method,
                    request_path,
                    request_ip,
                    user_agent,
                    device_id,
                ),
            )
            conn.commit()
    except Exception:
        pass  # Don't crash if error logging itself fails


def check_rate_limit(identifier: str, action: str, max_requests: int, window_minutes: int) -> bool:
    """
    Check if identifier has exceeded rate limit.
    Returns True if request is allowed, False if rate limited.
    """
    with get_db_context() as conn:
        # Clean old entries
        conn.execute(
            "DELETE FROM rate_limits WHERE timestamp < datetime('now', ?)",
            (f"-{window_minutes} minutes",),
        )

        # Count recent requests
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM rate_limits WHERE identifier=? AND action=?",
            (identifier, action),
        ).fetchone()

        if row and row["cnt"] >= max_requests:
            return False

        # Record this request
        conn.execute(
            "INSERT INTO rate_limits (identifier, action) VALUES (?,?)",
            (identifier, action),
        )
        conn.commit()
        return True


def purge_old_data(retention_days: int = 90):
    """
    Purge data older than retention_days.
    Run as a scheduled task.
    """
    with get_db_context() as conn:
        cutoff = f"-{retention_days} days"

        # datetime(...) normalizes both the ISO-8601 (T+offset) and SQLite-space
        # timestamp formats the DB has accumulated — without it, ISO strings
        # always sort AFTER the space-separated cutoff ('T' > ' ') and the purge
        # silently deletes nothing.
        deleted_locations = conn.execute(
            "DELETE FROM locations WHERE datetime(server_timestamp) < datetime('now', ?)",
            (cutoff,),
        ).rowcount

        deleted_heartbeats = conn.execute(
            "DELETE FROM heartbeats WHERE datetime(timestamp) < datetime('now', ?)",
            (cutoff,),
        ).rowcount

        # Evidence retention (v1.4): media belonging to an ACTIVE evidence
        # case is excluded from the retention purge — a forensic case must
        # never have its photos/audio silently deleted while the case is
        # still open. Closed cases age out normally. Files on disk are
        # removed alongside the DB rows.
        stale_media = conn.execute(
            """SELECT id, file_path FROM media
               WHERE datetime(timestamp) < datetime('now', ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM evidence_cases ec
                     WHERE ec.id = media.evidence_case_id AND ec.status = 'active'
                 )""",
            (cutoff,),
        ).fetchall()
        try:
            from media_store import delete_media_file

            for row in stale_media:
                delete_media_file(row["file_path"])
        except Exception:
            pass  # never let a disk glitch crash the purge
        deleted_media = conn.execute(
            """DELETE FROM media
               WHERE datetime(timestamp) < datetime('now', ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM evidence_cases ec
                     WHERE ec.id = media.evidence_case_id AND ec.status = 'active'
                 )""",
            (cutoff,),
        ).rowcount

        # Keep audit logs longer
        audit_cutoff = f"-{retention_days * 2} days"
        deleted_audit = conn.execute(
            "DELETE FROM audit_log WHERE datetime(timestamp) < datetime('now', ?)",
            (audit_cutoff,),
        ).rowcount

        # Keep rate limits for only 7 days
        conn.execute("DELETE FROM rate_limits WHERE datetime(timestamp) < datetime('now', '-7 days')")

        # Purge resolved errors older than retention_days (unresolved errors kept indefinitely)
        deleted_errors = conn.execute(
            "DELETE FROM error_log WHERE resolved=1 AND datetime(timestamp) < datetime('now', ?)",
            (cutoff,),
        ).rowcount

        conn.commit()

        return {
            "locations_purged": deleted_locations,
            "heartbeats_purged": deleted_heartbeats,
            "media_purged": deleted_media,
            "audit_purged": deleted_audit,
            "errors_purged": deleted_errors,
        }


# ── Cached Helper Functions ───────────────────────────────────────────────
# These functions cache frequently accessed data to reduce database load.


def get_device_info_cached(device_id: str) -> dict:
    """Get device information with caching."""
    if CACHE_ENABLED:
        cached = get_cached_device_info(device_id)
        if cached is not None:
            return cached

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT id, alias, owner_id, model, last_seen, is_stolen, sentinel_score, "
            "alert_phone, alert_email, alert_channels, enabled_types, "
            "quiet_hours_start, quiet_hours_end FROM devices WHERE id=?",
            (device_id,),
        ).fetchone()
        if row:
            info = dict(row)
            if CACHE_ENABLED:
                cache_device_info(device_id, info)
            return info
    return None


def get_device_owner_cached(device_id: str) -> str:
    """Get device owner ID with caching."""
    if CACHE_ENABLED:
        cached = get_cached_device_owner(device_id)
        if cached is not None:
            return cached

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT owner_id FROM devices WHERE id=?",
            (device_id,),
        ).fetchone()
        if row:
            owner_id = row["owner_id"]
            if CACHE_ENABLED:
                cache_device_owner(device_id, owner_id)
            return owner_id
    return None


def invalidate_device_cache_on_write(device_id: str):
    """Invalidate device cache after a write operation."""
    if CACHE_ENABLED:
        invalidate_device_cache(device_id)
        invalidate_device_owner(device_id)


# ── Safe Initialization ───────────────────────────────────────────────────
# init_db() is called explicitly by the application lifespan handler in main.py.
# It is NOT called on import to avoid side effects during testing and import.
#
# To initialize manually:
#   from database import init_db
#   init_db()


def ensure_initialized() -> bool:
    """
    Ensure the database is initialized with the complete, current schema.
    Called once during server startup from the lifespan handler.
    Returns True if initialization was performed, False if already current.

    Migration detection must compare COLUMNS, not just tables. The old
    short-circuit skipped init_db whenever every TABLE existed — so a DB
    created before a release kept its old columns and new features 500'd
    with "no such column" on production (capture_armed, alert_channels,
    enabled_types, quiet_hours_* were all silently missing). init_db() is
    fully idempotent (CREATE TABLE IF NOT EXISTS + guarded ALTER TABLE), so
    running it when anything is stale migrates forward safely.

    PostgreSQL mode (MT_DATABASE_URL set) skips SQLite migration entirely —
    the schema lives in database_postgres.init_schema() (parity-enforced by
    tests/test_postgres_adapter_parity.py) and is applied by
    storage.init_pg_store() at startup.
    """
    if settings.DATABASE_URL:
        return False
    if DB_PATH == ":memory:":
        init_db()
        return True
    if not os.path.exists(DB_PATH):
        init_db()
        return True
    # Existing DB — verify the full table list AND the devices columns are
    # current before taking the no-op fast path.
    required_tables = {
        "users",
        "devices",
        "locations",
        "media",
        "commands",
        "evidence_cases",
        "alerts",
        "heartbeats",
        "geofences",
        "device_shares",  # Milestone 2 P1 — family sharing
        "api_keys",  # Developer API keys (docs/developer-api.md)
        "guardian_profiles",
        "recovery_requests",
        "recovery_sightings",
        "audit_log",
        "fcm_tokens",
        "rate_limits",
        "revoked_tokens",
        "error_log",
        "cell_location_cache",
        "password_reset_tokens",
        "email_verify_tokens",
    }
    # ⚠️ Keep in sync with the CREATE TABLE devices columns in init_db() +
    # the guarded ALTER TABLE migrations below it. A stale list here makes
    # the server no-op on a DB that is actually missing columns.
    expected_devices_columns = {
        "id",
        "alias",
        "owner_id",
        "device_fingerprint",
        "platform",
        "app_version",
        "os_version",
        "model",
        "imei_hash",
        "sim_serial_hash",
        "device_key_hash",
        "last_seen",
        "registered",
        "is_stolen",
        "theft_confirmed_at",
        "operating_mode",
        "sentinel_score",
        "capture_armed",
        "alert_phone",
        "alert_email",
        "alert_channels",
        "enabled_types",
        "quiet_hours_start",
        "quiet_hours_end",
        "archived_at",
        "sms_phone",
        "sms_commands_enabled",
    }
    # ⚠️ Keep in sync with the CREATE TABLE commands columns in init_db() +
    # the guarded ALTER TABLE migrations below it. A stale list here makes
    # the server no-op on a DB that is actually missing columns — and every
    # subsequent ack (which now writes failure_reason) 500s with
    # "no such column" in production. This exact bug shipped once: the
    # live DB was missing failure_reason while the running code already
    # wrote it, because the check only validated devices columns.
    expected_commands_columns = {
        "id",
        "device_id",
        "command",
        "params",
        "status",
        "priority",
        "issued_at",
        "executed_at",
        "expires_at",
        "failure_reason",
        "delivery_channel",
    }
    # Geofence columns — a DB that predates auto_action/last_inside must not
    # take the no-op fast path or the ALTER migrations never run (same
    # no-such-column 500 class documented above for devices/commands).
    expected_geofences_columns = {
        "id",
        "device_id",
        "name",
        "center_lat",
        "center_lng",
        "radius_meters",
        "is_safe_zone",
        "active",
        "created_at",
        "auto_action",
        "last_inside",
    }
    # Media refactor columns — a DB that predates them stores base64 blobs
    # only; new rows carry file_path/file_size (see media_store.py).
    expected_media_columns = {
        "id",
        "device_id",
        "type",
        "data_b64",
        "timestamp",
        "evidence_case_id",
        "sha256_hash",
        "file_path",
        "file_size",
    }
    # Account-security columns — 2FA state (secret encrypted, replay period).
    expected_users_columns = {
        "id",
        "email",
        "password_hash",
        "display_name",
        "tier",
        "is_active",
        "email_verified",
        "created_at",
        "last_login",
        "totp_secret_enc",
        "totp_enabled",
        "totp_last_period",
    }
    # Developer API key columns — key_type (readonly enforcement) +
    # request_count (usage metering, v1.7). A DB that predates them must not
    # take the no-op fast path or the guarded ALTER migrations never run —
    # this exact drift just shipped: the prod DB had api_keys (v1.6) and the
    # staleness check never compared its columns, so the new columns were
    # silently missing until an authenticated key lookup 500'd.
    expected_api_keys_columns = {
        "id",
        "user_id",
        "name",
        "key_prefix",
        "key_hash",
        "scopes",
        "key_type",
        "request_count",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    }
    # At-rest encryption columns — location_data must exist before the write
    # path can store ciphertext on a production DB (same no-such-column 500
    # class that bit devices/commands/media historically).
    expected_locations_columns = {
        "id",
        "device_id",
        "lat",
        "lng",
        "altitude",
        "accuracy_horizontal",
        "accuracy_vertical",
        "confidence_level",
        "speed",
        "bearing",
        "activity_type",
        "step_count",
        "provider",
        "gps_satellite_count",
        "wifi_bssids",
        "cell_tower_ids",
        "ble_devices_nearby",
        "battery_percent",
        "is_charging",
        "network_type",
        "signal_strength_dbm",
        "is_location_enabled",
        "is_airplane_mode",
        "sim_changed",
        "sim_serial_hash",
        "sentinel_score",
        "threat_level",
        "anomalies",
        "device_timestamp",
        "server_timestamp",
        "was_queued",
        "queued_at",
        "queue_position",
        "ping_sequence",
        "location_encrypted",
        "location_data",
    }
    try:
        with get_db_context() as conn:
            present_tables = {
                row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            devices_columns = {row["name"] for row in conn.execute("PRAGMA table_info(devices)").fetchall()}
            commands_columns = {row["name"] for row in conn.execute("PRAGMA table_info(commands)").fetchall()}
            media_columns = {row["name"] for row in conn.execute("PRAGMA table_info(media)").fetchall()}
            users_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            locations_columns = {row["name"] for row in conn.execute("PRAGMA table_info(locations)").fetchall()}
            geofences_columns = {row["name"] for row in conn.execute("PRAGMA table_info(geofences)").fetchall()}
            # Find Network beacon token (v1.6) — an existing DB whose
            # recovery_requests table predates the column would take the
            # no-op path below and never migrate (the device_shares bug class).
            recovery_columns = {row["name"] for row in conn.execute("PRAGMA table_info(recovery_requests)").fetchall()}
            api_keys_columns = {row["name"] for row in conn.execute("PRAGMA table_info(api_keys)").fetchall()}
        if (
            required_tables.issubset(present_tables)
            and expected_devices_columns.issubset(devices_columns)
            and expected_commands_columns.issubset(commands_columns)
            and expected_media_columns.issubset(media_columns)
            and expected_users_columns.issubset(users_columns)
            and expected_locations_columns.issubset(locations_columns)
            and expected_geofences_columns.issubset(geofences_columns)
            and {"beacon_token"}.issubset(recovery_columns)
            and expected_api_keys_columns.issubset(api_keys_columns)
        ):
            return False
        init_db()
        return True
    except Exception:
        init_db()
        return True
