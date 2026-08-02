"""
Magneetar Database Layer
SQLite implementation with full schema. PostgreSQL-compatible syntax.
"""

import os
import sqlite3
from contextlib import contextmanager

from config import settings

DB_PATH = settings.DB_PATH


def _connect() -> sqlite3.Connection:
    """Create a new database connection with correct settings."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s if DB is locked
    return conn


def get_db():
    """FastAPI dependency - yields a database connection.
    Connection failures propagate to the caller for fast failure detection.
    SQLite contention is handled by busy_timeout=5000 in _connect().
    """
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_context():
    """Context manager for non-FastAPI usage."""
    conn = _connect()
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
            alert_phone TEXT,
            alert_email TEXT,
            -- Per-device alert preferences (NULL = global defaults)
            -- alert_channels: JSON array e.g. ["whatsapp","sms","push"]
            -- enabled_types:  JSON array e.g. ["theft","sim_change","offline"]
            alert_channels TEXT,
            enabled_types TEXT,
            quiet_hours_start INTEGER,
            quiet_hours_end INTEGER
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
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

        -- ─── Media ──────────────────────────────────────────────────────────
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
            FOREIGN KEY (device_id) REFERENCES devices(id)
        );

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

    # Everything else references the device row directly.
    for table in (
        "locations",
        "media",
        "commands",
        "evidence_cases",
        "alerts",
        "heartbeats",
        "geofences",
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
                (level, message, source, traceback, request_method, request_path, request_ip, user_agent, device_id),
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
        conn.execute("DELETE FROM rate_limits WHERE timestamp < datetime('now', ?)", (f"-{window_minutes} minutes",))

        # Count recent requests
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM rate_limits WHERE identifier=? AND action=?", (identifier, action)
        ).fetchone()

        if row and row["cnt"] >= max_requests:
            return False

        # Record this request
        conn.execute("INSERT INTO rate_limits (identifier, action) VALUES (?,?)", (identifier, action))
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
            "DELETE FROM locations WHERE datetime(server_timestamp) < datetime('now', ?)", (cutoff,)
        ).rowcount

        deleted_heartbeats = conn.execute(
            "DELETE FROM heartbeats WHERE datetime(timestamp) < datetime('now', ?)", (cutoff,)
        ).rowcount

        deleted_media = conn.execute(
            "DELETE FROM media WHERE datetime(timestamp) < datetime('now', ?)", (cutoff,)
        ).rowcount

        # Keep audit logs longer
        audit_cutoff = f"-{retention_days * 2} days"
        deleted_audit = conn.execute(
            "DELETE FROM audit_log WHERE datetime(timestamp) < datetime('now', ?)", (audit_cutoff,)
        ).rowcount

        # Keep rate limits for only 7 days
        conn.execute("DELETE FROM rate_limits WHERE datetime(timestamp) < datetime('now', '-7 days')")

        # Purge resolved errors older than retention_days (unresolved errors kept indefinitely)
        deleted_errors = conn.execute(
            "DELETE FROM error_log WHERE resolved=1 AND datetime(timestamp) < datetime('now', ?)", (cutoff,)
        ).rowcount

        conn.commit()

        return {
            "locations_purged": deleted_locations,
            "heartbeats_purged": deleted_heartbeats,
            "media_purged": deleted_media,
            "audit_purged": deleted_audit,
            "errors_purged": deleted_errors,
        }


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
    Returns True if initialization was performed, False if already initialized.
    """
    # In-memory databases always need initialization
    if DB_PATH == ":memory:":
        init_db()
        return True
    # File-based databases: init if file doesn't exist
    if not os.path.exists(DB_PATH):
        init_db()
        return True
    # File exists — verify ALL required tables are present, not just a subset.
    # init_db() is fully idempotent (CREATE TABLE IF NOT EXISTS + guarded
    # ALTER TABLE), so re-running it when anything is missing migrates
    # existing databases forward when a release adds new tables (e.g. the
    # Guardian Network tables).
    # ⚠️ Keep this set in sync with the tables created in init_db().
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
        "guardian_profiles",
        "recovery_requests",
        "recovery_sightings",
        "audit_log",
        "fcm_tokens",
        "rate_limits",
        "revoked_tokens",
        "error_log",
    }
    try:
        with get_db_context() as conn:
            present = {
                row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        if required_tables.issubset(present):
            return False
        init_db()
        return True
    except Exception:
        init_db()
        return True
