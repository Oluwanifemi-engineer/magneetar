"""
Magneetar Database Migration System
Manages schema changes safely with version tracking.

Features:
- Version-controlled migrations
- Automatic migration on startup
- Rollback support
- Migration history tracking
- Idempotent migrations
"""

import logging
import os
import sqlite3
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# Current schema version
CURRENT_VERSION = 15  # Increment when adding migrations


class Migration:
    """A single database migration."""

    def __init__(self, version: int, name: str, up_fn: Callable, down_fn: Optional[Callable] = None):
        self.version = version
        self.name = name
        self.up_fn = up_fn
        self.down_fn = down_fn

    def up(self, conn: sqlite3.Connection):
        """Apply migration."""
        logger.info(f"Applying migration {self.version}: {self.name}")
        self.up_fn(conn)

    def down(self, conn: sqlite3.Connection):
        """Rollback migration."""
        if self.down_fn:
            logger.info(f"Rolling back migration {self.version}: {self.name}")
            self.down_fn(conn)
        else:
            logger.warning(f"No rollback defined for migration {self.version}: {self.name}")


# Migration registry
_migrations: List[Migration] = []


def register_migration(version: int, name: str, down_fn: Optional[Callable] = None):
    """Decorator to register a migration."""

    def decorator(fn: Callable):
        migration = Migration(version, name, fn, down_fn)
        _migrations.append(migration)
        _migrations.sort(key=lambda m: m.version)
        return fn

    return decorator


def _ensure_migration_table(conn: sqlite3.Connection):
    """Create migration tracking table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            checksum TEXT
        )
    """
    )
    conn.commit()


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    _ensure_migration_table(conn)
    row = conn.execute("SELECT MAX(version) as version FROM schema_migrations").fetchone()
    return row["version"] if row and row["version"] else 0


def get_applied_migrations(conn: sqlite3.Connection) -> List[int]:
    """Get list of applied migration versions."""
    _ensure_migration_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [row["version"] for row in rows]


def apply_migrations(conn: sqlite3.Connection, target_version: Optional[int] = None):
    """Apply all pending migrations up to target version."""
    _ensure_migration_table(conn)
    current = get_current_version(conn)

    if target_version is None:
        target_version = CURRENT_VERSION

    pending = [m for m in _migrations if m.version > current and m.version <= target_version]

    if not pending:
        logger.info(f"Database is up to date (version {current})")
        return

    logger.info(f"Applying {len(pending)} migration(s) from version {current} to {target_version}")

    for migration in pending:
        try:
            migration.up(conn)
            # Record migration
            import hashlib

            checksum = hashlib.sha256(f"{migration.version}:{migration.name}".encode()).hexdigest()
            conn.execute(
                "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, checksum),
            )
            conn.commit()
            logger.info(f"Migration {migration.version} applied successfully")
        except Exception as e:
            logger.error(f"Migration {migration.version} failed: {e}")
            conn.rollback()
            raise


def rollback_migration(conn: sqlite3.Connection, target_version: int):
    """Rollback to a specific version."""
    applied = get_applied_migrations(conn)
    to_rollback = [v for v in applied if v > target_version]

    for version in reversed(to_rollback):
        migration = next((m for m in _migrations if m.version == version), None)
        if migration and migration.down_fn:
            try:
                migration.down(conn)
                conn.execute("DELETE FROM schema_migrations WHERE version=?", (version,))
                conn.commit()
                logger.info(f"Migration {version} rolled back")
            except Exception as e:
                logger.error(f"Rollback of migration {version} failed: {e}")
                conn.rollback()
                raise


def get_migration_status() -> dict:
    """Get migration status."""
    try:
        from database import get_db_context

        with get_db_context() as conn:
            current = get_current_version(conn)
            applied = get_applied_migrations(conn)
            pending = [m.version for m in _migrations if m.version > current]

            return {
                "current_version": current,
                "target_version": CURRENT_VERSION,
                "applied_count": len(applied),
                "pending_count": len(pending),
                "applied": applied,
                "pending": pending,
                "migrations": [{"version": m.version, "name": m.name} for m in _migrations],
            }
    except Exception as e:
        return {"error": str(e)}


# ─── Define Migrations ─────────────────────────────────────────────────────
# Each migration is a function that modifies the schema.


@register_migration(1, "Initial schema")
def migration_001_initial(conn: sqlite3.Connection):
    """Create initial schema."""
    # This is handled by database.py init_db()
    pass


@register_migration(2, "Add device_key_hash")
def migration_002_device_key_hash(conn: sqlite3.Connection):
    """Add device_key_hash column to devices."""
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN device_key_hash TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists


@register_migration(3, "Add alert preferences")
def migration_003_alert_preferences(conn: sqlite3.Connection):
    """Add alert preference columns."""
    for col in ("alert_channels", "enabled_types"):
        try:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    for col in ("quiet_hours_start", "quiet_hours_end"):
        try:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {col} INTEGER")
        except sqlite3.OperationalError:
            pass


@register_migration(4, "Add capture_armed")
def migration_004_capture_armed(conn: sqlite3.Connection):
    """Add capture_armed column."""
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN capture_armed BOOLEAN")
    except sqlite3.OperationalError:
        pass


@register_migration(5, "Add failure_reason to commands")
def migration_005_command_failure_reason(conn: sqlite3.Connection):
    """Add failure_reason column to commands."""
    try:
        conn.execute("ALTER TABLE commands ADD COLUMN failure_reason TEXT")
    except sqlite3.OperationalError:
        pass


@register_migration(6, "Add archived_at")
def migration_006_archived_at(conn: sqlite3.Connection):
    """Add archived_at column to devices."""
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN archived_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass


@register_migration(7, "Add SMS relay columns")
def migration_007_sms_relay(conn: sqlite3.Connection):
    """Add SMS relay columns."""
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN sms_phone TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN sms_commands_enabled BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass


@register_migration(8, "Add delivery_channel to commands")
def migration_008_delivery_channel(conn: sqlite3.Connection):
    """Add delivery_channel column."""
    try:
        conn.execute("ALTER TABLE commands ADD COLUMN delivery_channel TEXT")
    except sqlite3.OperationalError:
        pass


@register_migration(9, "Add media file columns")
def migration_009_media_files(conn: sqlite3.Connection):
    """Add file_path and file_size to media."""
    try:
        conn.execute("ALTER TABLE media ADD COLUMN file_path TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE media ADD COLUMN file_size INTEGER")
    except sqlite3.OperationalError:
        pass


@register_migration(10, "Add 2FA columns")
def migration_010_2fa(conn: sqlite3.Connection):
    """Add 2FA columns to users."""
    for col in ("totp_secret_enc",):
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    for col in ("totp_enabled", "totp_last_period"):
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass


@register_migration(11, "Create token tables")
def migration_011_token_tables(conn: sqlite3.Connection):
    """Create password reset and email verify token tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id)")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verify_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_verify_user ON email_verify_tokens(user_id)")


@register_migration(12, "Create cell location cache")
def migration_012_cell_cache(conn: sqlite3.Connection):
    """Create cell location cache table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cell_location_cache (
            fingerprint TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            accuracy_meters REAL,
            provider TEXT,
            resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )


@register_migration(13, "Create error log")
def migration_013_error_log(conn: sqlite3.Connection):
    """Create error log table."""
    conn.execute(
        """
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
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_error_log_timestamp ON error_log(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_error_log_resolved ON error_log(resolved)")


@register_migration(14, "Create guardian tables")
def migration_014_guardian(conn: sqlite3.Connection):
    """Create guardian network tables."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS guardian_profiles (
            user_id TEXT PRIMARY KEY,
            opted_in BOOLEAN DEFAULT TRUE,
            radius_km INTEGER DEFAULT 20,
            handle TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
    """
    )

    conn.execute(
        """
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
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_requests_status ON recovery_requests(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_requests_owner ON recovery_requests(owner_id)")

    conn.execute(
        """
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
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_sightings_request ON recovery_sightings(request_id)")


@register_migration(15, "Add location_mode to devices")
def migration_015_location_mode(conn: sqlite3.Connection):
    """Add location_mode column (G1-17: system location MODE reported on the
    heartbeat so a Battery-saving/GPS-only device is visible server-side)."""
    try:
        conn.execute("ALTER TABLE devices ADD COLUMN location_mode TEXT")
    except sqlite3.OperationalError:
        pass


def init_migrations():
    """Initialize migration system."""
    from database import get_db_context

    with get_db_context() as conn:
        _ensure_migration_table(conn)
        current = get_current_version(conn)

        if current < CURRENT_VERSION:
            logger.info(f"Database needs migration from version {current} to {CURRENT_VERSION}")
            apply_migrations(conn)
        else:
            logger.info(f"Database is up to date (version {current})")


# Run on import to check status
try:
    from database import DB_PATH

    if DB_PATH != ":memory:" and os.path.exists(DB_PATH):
        init_migrations()
except Exception:
    pass  # Don't fail on import
