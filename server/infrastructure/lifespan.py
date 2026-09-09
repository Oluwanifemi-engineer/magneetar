"""
Magneetar Lifespan Handler (extracted from main.py — Phase 0).

Manages server startup and shutdown:
- Database initialization (SQLite or PostgreSQL)
- Configuration validation
- Background task scheduling (heartbeat, offline monitor, archive, rate limit cleanup)
- Graceful shutdown (cancel tasks, notify websockets, close connections)

This module is imported by main.py and registered as FastAPI's lifespan handler.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from config import settings
from database import DB_PATH, ensure_initialized
from fastapi import FastAPI
from logging_config import get_logger
from write_queue import start_write_queue, stop_write_queue, write_queue_enabled

logger = get_logger("magneetar")


def create_lifespan(app_version: str):
    """Create a lifespan handler closure capturing the app version.

    Returns an async context manager suitable for FastAPI(lifespan=...).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """FastAPI lifespan handler for startup/shutdown."""
        # ── Initialize database (safe, idempotent) ───────────────────────
        ensure_initialized()

        # ── Batched telemetry writes (opt-in, MT_WRITE_BATCH_MS) ──────────
        if write_queue_enabled() and not settings.DATABASE_URL:
            await start_write_queue(DB_PATH)

        # ── Validate configuration on startup ──────────────────────────────
        config_errors = settings.validate()
        if config_errors:
            logger.error("FATAL: Configuration errors detected:")
            for err in config_errors:
                logger.error(f"  ❌ {err}")
            logger.error("")
            logger.error("Fix: Run './scripts/generate-env.sh' to generate secure secrets,")
            logger.error("     then edit server/.env with your alert service credentials.")
            raise RuntimeError(f"Server cannot start: {len(config_errors)} configuration errors")

        for warn in settings.validate_optional():
            logger.warning(f"⚠️  Optional configuration: {warn}")

        logger.info(
            "Magneetar server starting",
            extra={
                "extra_data": {
                    "version": app_version,
                    "environment": settings.ENVIRONMENT,
                    "host": settings.HOST,
                    "port": settings.PORT,
                    "database": "PostgreSQL" if settings.DATABASE_URL else "SQLite",
                    "retention_days": settings.DATA_RETENTION_DAYS,
                    "max_devices": settings.MAX_DEVICES_PER_USER,
                }
            },
        )

        # ── PostgreSQL Setup (optional, storage facade — ADR-0005 Phase 2a) ──
        pg_connected = False
        if settings.DATABASE_URL:
            try:
                from storage import init_pg_store

                try:
                    if init_pg_store():
                        pg_connected = True
                except Exception as schema_err:
                    if "duplicate key" in str(schema_err) and "pg_type" in str(schema_err):
                        from storage import _get_pg_db

                        _get_pg_db(settings.DATABASE_URL)
                        pg_connected = True
                        logger.info("PostgreSQL schema already exists (concurrent init)")
                    else:
                        raise

                if pg_connected:
                    logger.info(
                        "PostgreSQL wired via the storage facade " "(ADR-0005 Phase 2a): routes read/write Postgres."
                    )
            except Exception as e:
                logger.warning(f"PostgreSQL setup failed, falling back to SQLite: {e}")

        if not pg_connected:
            logger.info(f"Using SQLite database: {settings.DB_PATH}")

        # ── Data Retention Cleanup (non-blocking) ──────────────────────────
        async def run_cleanup():
            try:
                if pg_connected:
                    from database_postgres import get_postgres_db

                    pg = await get_postgres_db()
                    result = await pg.purge_old_data(settings.DATA_RETENTION_DAYS)
                    logger.info(f"Data retention cleanup: {result}")
                else:
                    from database import purge_old_data

                    result = await asyncio.to_thread(purge_old_data, settings.DATA_RETENTION_DAYS)
                    if result:
                        total_purged = sum(result.values())
                        logger.info(
                            f"Data retention cleanup: {total_purged} records purged",
                            extra={"extra_data": result},
                        )
            except Exception as e:
                logger.warning(f"Data retention cleanup skipped: {e}")

        asyncio.create_task(run_cleanup())

        # ── WebSocket Connection Heartbeat (every 30s) ───────────────────
        from websocket_manager import start_connection_heartbeat

        heartbeat_task = asyncio.create_task(start_connection_heartbeat(interval=30))

        # ── Multi-worker broadcast listener (Redis pub/sub) ─────────────────
        from websocket_manager import redis_broadcast_listener

        redis_task = asyncio.create_task(redis_broadcast_listener())
        if settings.REDIS_URL:
            logger.info(
                "Realtime broadcast: Redis pub/sub enabled",
                extra={"extra_data": {"channel": "magneetar:ws"}},
            )
            try:
                from cache_redis import init_redis_cache

                init_redis_cache(settings.REDIS_URL)
                logger.info("Shared device cache: Redis-backed (cross-worker consistent)")
            except Exception as e:
                logger.warning(f"Redis cache init failed — using per-worker in-memory cache: {e}")
        else:
            logger.info("Realtime broadcast: local (single-worker mode)")

        # ── Offline Monitor (every 60s) ──────────────────────────────────
        from offline_monitor import check_offline_devices_loop

        offline_task = asyncio.create_task(check_offline_devices_loop(interval_seconds=60))

        # ── Stale-Device Archive (every 6h) ───────────────────────────────
        from archive_monitor import archive_stale_devices_loop

        archive_task = asyncio.create_task(archive_stale_devices_loop(interval_seconds=6 * 3600))

        # ── Scheduled Rate Limit Cleanup (every 6 hours) ────────────────────
        from leader_lock import acquire_task_lock, release_task_lock

        async def periodic_rate_limit_cleanup():
            while True:
                try:
                    await asyncio.sleep(6 * 3600)
                    won, token = await acquire_task_lock("rate_limit_cleanup", ttl=6 * 3600 + 60)
                    if not won:
                        continue
                    try:
                        use_pg = False
                        try:
                            from database_postgres import (
                                get_postgres_db,
                                is_postgres_configured,
                            )

                            if is_postgres_configured():
                                pg = await get_postgres_db()
                                if pg.is_connected:
                                    use_pg = True
                        except Exception:
                            pass

                        if use_pg:
                            await pg.execute("DELETE FROM rate_limits " "WHERE timestamp < NOW() - interval '7 days'")
                            logger.info("Rate limit cleanup (PostgreSQL): " "purged entries older than 7 days")
                        else:
                            from database import get_db_context

                            with get_db_context() as conn:
                                conn.execute("DELETE FROM rate_limits " "WHERE timestamp < datetime('now', '-7 days')")
                                conn.commit()
                            logger.info("Rate limit cleanup (SQLite): " "purged entries older than 7 days")

                        from memory_rate_limit import sweep

                        swept = sweep()
                        if swept:
                            logger.info(f"Rate limit cleanup (in-memory): " f"swept {swept} idle device keys")
                    finally:
                        await release_task_lock("rate_limit_cleanup", token)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.warning(f"Rate limit cleanup failed: {e}")

        cleanup_task = asyncio.create_task(periodic_rate_limit_cleanup())

        # ── Yield to application ────────────────────────────────────────────
        yield

        # ── Shutdown ────────────────────────────────────────────────────────
        cleanup_task.cancel()
        heartbeat_task.cancel()
        redis_task.cancel()
        offline_task.cancel()
        archive_task.cancel()

        logger.info("Magneetar server shutting down")

        if write_queue_enabled():
            await stop_write_queue()

        try:
            from database_postgres import close_postgres_db

            await close_postgres_db()
        except Exception:
            pass

        from websocket_manager import (
            active_dashboard_connections,
            broadcast_to_dashboards,
        )

        if active_dashboard_connections:
            logger.info(f"Notifying {len(active_dashboard_connections)} " f"dashboard client(s) of shutdown...")
            try:
                await asyncio.wait_for(
                    broadcast_to_dashboards(
                        {
                            "type": "shutdown",
                            "message": "Server is shutting down",
                            "reconnect": True,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                    timeout=0.5,
                )
            except (asyncio.TimeoutError, Exception):
                logger.warning("Shutdown notification timed out or failed")

        active_dashboard_connections.clear()

        if settings.DATABASE_URL:
            try:
                from storage import close_pg_store

                close_pg_store()
            except Exception:
                logger.warning("PostgreSQL pool close failed (process exit continues)")

    return lifespan
