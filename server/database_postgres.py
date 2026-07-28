"""
Magneetar PostgreSQL Database Adapter
Production-grade PostgreSQL backend with connection pooling.
Falls back to SQLite when PostgreSQL is not configured.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator, AsyncContextManager
from contextlib import asynccontextmanager

from config import settings


# ─── PostgreSQL Adapter ──────────────────────────────────────────────────────

class PostgresDatabase:
    """Async PostgreSQL database operations using asyncpg."""

    def __init__(self):
        self._pool = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self, database_url: Optional[str] = None):
        """Create connection pool."""
        if self._connected:
            return

        url = database_url or settings.DATABASE_URL
        if not url:
            raise ValueError("DATABASE_URL not configured")

        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                url,
                min_size=2,
                max_size=10,
                command_timeout=30,
            )
            self._connected = True
        except ImportError:
            raise RuntimeError("asyncpg not installed. Run: pip install asyncpg")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to PostgreSQL: {e}")

    async def disconnect(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._connected = False

    async def init_schema(self):
        """Create all tables if they don't exist."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
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
                        last_seen TIMESTAMPTZ,
                        registered TIMESTAMPTZ DEFAULT NOW(),
                        is_stolen BOOLEAN DEFAULT FALSE,
                        theft_confirmed_at TIMESTAMPTZ,
                        operating_mode TEXT DEFAULT 'normal',
                        sentinel_score INTEGER DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS locations (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        lat DOUBLE PRECISION NOT NULL,
                        lng DOUBLE PRECISION NOT NULL,
                        altitude DOUBLE PRECISION,
                        accuracy_horizontal DOUBLE PRECISION,
                        accuracy_vertical DOUBLE PRECISION,
                        confidence_level TEXT DEFAULT 'UNKNOWN',
                        speed DOUBLE PRECISION,
                        bearing DOUBLE PRECISION,
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
                        device_timestamp TIMESTAMPTZ,
                        server_timestamp TIMESTAMPTZ DEFAULT NOW(),
                        was_queued BOOLEAN DEFAULT FALSE,
                        queued_at TIMESTAMPTZ,
                        queue_position INTEGER,
                        ping_sequence INTEGER,
                        location_encrypted BOOLEAN DEFAULT FALSE
                    );

                    CREATE TABLE IF NOT EXISTS media (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        type TEXT NOT NULL,
                        data_b64 TEXT NOT NULL,
                        lat DOUBLE PRECISION,
                        lng DOUBLE PRECISION,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        evidence_case_id TEXT,
                        sha256_hash TEXT
                    );

                    CREATE TABLE IF NOT EXISTS commands (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        command TEXT NOT NULL,
                        params TEXT,
                        status TEXT DEFAULT 'pending',
                        priority INTEGER DEFAULT 5,
                        issued_at TIMESTAMPTZ DEFAULT NOW(),
                        executed_at TIMESTAMPTZ,
                        expires_at TIMESTAMPTZ
                    );

                    CREATE TABLE IF NOT EXISTS evidence_cases (
                        id TEXT PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        theft_time TIMESTAMPTZ,
                        status TEXT DEFAULT 'active',
                        location_count INTEGER DEFAULT 0,
                        photo_count INTEGER DEFAULT 0,
                        audio_count INTEGER DEFAULT 0,
                        sha256_chain TEXT,
                        pdf_generated BOOLEAN DEFAULT FALSE
                    );

                    CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        alert_type TEXT NOT NULL,
                        channel TEXT NOT NULL,
                        recipient TEXT,
                        message TEXT,
                        sent_at TIMESTAMPTZ DEFAULT NOW(),
                        delivered BOOLEAN DEFAULT FALSE
                    );

                    CREATE TABLE IF NOT EXISTS heartbeats (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        battery_percent INTEGER,
                        is_charging BOOLEAN,
                        network_type TEXT,
                        device_admin_active BOOLEAN,
                        sim_hash TEXT,
                        app_version TEXT,
                        pending_evidence_count INTEGER DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS geofences (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL REFERENCES devices(id),
                        name TEXT,
                        center_lat DOUBLE PRECISION NOT NULL,
                        center_lng DOUBLE PRECISION NOT NULL,
                        radius_meters DOUBLE PRECISION NOT NULL,
                        is_safe_zone BOOLEAN DEFAULT TRUE,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        timestamp TIMESTAMPTZ DEFAULT NOW(),
                        action TEXT NOT NULL,
                        actor TEXT,
                        ip_address TEXT,
                        details TEXT
                    );

                    CREATE TABLE IF NOT EXISTS rate_limits (
                        id BIGSERIAL PRIMARY KEY,
                        identifier TEXT NOT NULL,
                        action TEXT NOT NULL,
                        timestamp TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS revoked_tokens (
                        jti TEXT PRIMARY KEY,
                        revoked_at TIMESTAMPTZ DEFAULT NOW(),
                        reason TEXT
                    );
                """)

                # Create indexes
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_locations_device ON locations(device_id);
                    CREATE INDEX IF NOT EXISTS idx_locations_timestamp ON locations(server_timestamp);
                    CREATE INDEX IF NOT EXISTS idx_media_device ON media(device_id);
                    CREATE INDEX IF NOT EXISTS idx_commands_device ON commands(device_id);
                    CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
                    CREATE INDEX IF NOT EXISTS idx_heartbeats_device ON heartbeats(device_id);
                    CREATE INDEX IF NOT EXISTS idx_geofences_device ON geofences(device_id);
                    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_rate_limits_identifier ON rate_limits(identifier, action);
                """)

    async def purge_old_data(self, retention_days: int = 90):
        """Purge data older than retention_days (in days)."""
        async with self._pool.acquire() as conn:
            results = {}
            for table, col, days in [
                ("locations", "server_timestamp", retention_days),
                ("heartbeats", "timestamp", retention_days),
                ("media", "timestamp", retention_days),
                ("audit_log", "timestamp", retention_days * 2),
            ]:
                result = await conn.execute(
                    f"DELETE FROM {table} WHERE {col} < NOW() - interval '{days} days'"
                )
                results[table] = int(result.split()[-1]) if result else 0

            await conn.execute(
                "DELETE FROM rate_limits WHERE timestamp < NOW() - interval '7 days'"
            )

            return results

    # ── Query Methods ─────────────────────────────────────────────────────

    async def fetch_all(self, query: str, *args):
        """Fetch multiple rows."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]

    async def fetch_one(self, query: str, *args):
        """Fetch single row."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def execute(self, query: str, *args):
        """Execute a query."""
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)


# ─── Database Factory ────────────────────────────────────────────────────────

_db_instance = None


async def get_postgres_db() -> PostgresDatabase:
    """Get or create the PostgreSQL database singleton."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PostgresDatabase()
        await _db_instance.connect()
        await _db_instance.init_schema()
    return _db_instance


def is_postgres_configured() -> bool:
    """Check if PostgreSQL is configured for use."""
    return bool(settings.DATABASE_URL)


async def close_postgres_db():
    """Close the PostgreSQL connection pool."""
    global _db_instance
    if _db_instance:
        await _db_instance.disconnect()
        _db_instance = None
