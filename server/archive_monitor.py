"""
Magneetar Stale-Device Archive Monitor

Background task that soft-archives devices that have been silent beyond the
archive threshold (MT_ARCHIVE_AFTER_DAYS, default 30). Design goals:

- **Soft flag, never delete**: archived_at is set on the device row but the
  row and its full history are kept. The permanent-deletion path stays the
  explicit, password-gated dashboard action (a soft archive must never
  destroy data automatically).
- **Any telemetry un-archives**: the location, heartbeat, offline-queue and
  register handlers clear archived_at on every fresh report, so a device
  that comes back online (battery died, phone in a drawer, SIM swap) is
  immediately restored to the active list — no manual step.
- **Idempotent and restart-safe**: the sweep only touches devices whose
  last_seen is older than the threshold and that are not already archived,
  so re-runs (including after a server restart) change nothing.
- **Stolen/alerted devices are still archived**: offline alerting (who to
  notify) and archiving (list hygiene) are separate concerns — an archived
  device that has an owner still gets its offline alert.

The sweep runs from the FastAPI lifespan (see main.py) every 6 hours.
"""

import asyncio

from logging_config import get_logger

logger = get_logger("magneetar")

# Hard floor so a misconfigured MT_ARCHIVE_AFTER_DAYS can never archive
# healthy devices.
_MIN_FLOOR_DAYS = 7


def archive_stale_devices(days: int = None) -> int:
    """Soft-archive devices silent for more than `days` days.

    Returns how many devices were newly archived. Safe to call repeatedly.
    """
    # Import INSIDE the function (codebase convention, see main.py): test_e2e
    # evicts the database/config modules from sys.modules mid-suite, and a
    # stale import-time binding would read a DB path from a dead instance.
    from config import settings
    from database import get_db_context

    threshold = max(days if days is not None else settings.ARCHIVE_AFTER_DAYS, _MIN_FLOOR_DAYS)

    with get_db_context() as conn:
        # datetime() normalizes both the ISO-8601 and SQLite-space timestamp
        # formats the DB has accumulated (same pattern as offline_monitor and
        # purge_old_data).
        rows = conn.execute(
            """UPDATE devices
               SET archived_at = datetime('now')
               WHERE last_seen IS NOT NULL
                 AND archived_at IS NULL
                 AND datetime(last_seen) < datetime('now', ?)""",
            (f"-{threshold} days",),
        )
        conn.commit()
        return rows.rowcount if rows else 0


async def archive_stale_devices_loop(interval_seconds: int = 6 * 3600):
    """Periodic sweep that soft-archives stale devices."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            archived = archive_stale_devices()
            if archived:
                logger.info(f"Archive sweep: {archived} device(s) archived")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Archive sweep failed: {e}")


def unarchive_device(db, device_id: str) -> None:
    """Clear the archived flag when a device reports fresh activity.

    Called by the telemetry/heartbeat/offline-queue/register handlers so a
    device that comes back online is restored to the active list. Cheap and
    idempotent (no-op when the flag is already NULL).
    """
    db.execute(
        "UPDATE devices SET archived_at = NULL WHERE id = ? AND archived_at IS NOT NULL",
        (device_id,),
    )
