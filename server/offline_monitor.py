"""
Magneetar Offline Monitor

Background task that alerts a device owner when their device stops reporting
(heartbeats / locations). Design goals for production:

- **Once per incident, never on every sweep**: the alerts table is used as the
  dedup record — a device is only alerted when NO `device_offline` alert exists
  that was sent AFTER its `last_seen`. When the device comes back online and
  later goes offline again, it alerts once more.
- **Owned devices only**: devices not linked to an account have nobody to
  notify, and `send_all` would otherwise fall back to the GLOBAL alert phone —
  spamming it for every orphan device.
- **Stolen devices are skipped**: theft mode already has its own escalation and
  its own alerts; an offline ping on top is noise.
- **Safe on restarts**: because dedup is persisted in the DB, a server restart
  does not re-alert devices that were already reported offline.

The sweep runs from the FastAPI lifespan (see main.py) every 60 seconds.
"""

import asyncio
from datetime import datetime, timezone

from logging_config import get_logger

logger = get_logger("magneetar")

# Hard floor so a misconfigured MT_OFFLINE_ALERT_MINUTES can never spam alerts.
_MIN_FLOOR_MINUTES = 10

ALERT_TYPE = "device_offline"


def find_offline_devices(minutes: int = None) -> list[dict]:
    """Return owned, non-stolen devices that have been silent for `minutes`
    and have NOT yet been alerted for the current offline incident."""
    # Import INSIDE the function (codebase convention, see main.py): test_e2e
    # evicts the database/config modules from sys.modules mid-suite, and a
    # stale import-time binding would read a DB path from a dead instance.
    from config import settings
    from database import get_db_context

    threshold = max(minutes if minutes is not None else settings.OFFLINE_ALERT_MINUTES, _MIN_FLOOR_MINUTES)

    with get_db_context() as conn:
        rows = conn.execute(
            """SELECT d.id, d.last_seen, d.owner_id,
                      (SELECT lat FROM locations l WHERE l.device_id = d.id
                       ORDER BY server_timestamp DESC LIMIT 1) AS lat,
                      (SELECT lng FROM locations l WHERE l.device_id = d.id
                       ORDER BY server_timestamp DESC LIMIT 1) AS lng
               FROM devices d
               WHERE d.last_seen IS NOT NULL
                 AND d.owner_id IS NOT NULL
                 AND d.is_stolen = 0
                 AND d.operating_mode != 'stolen'
                 -- datetime() normalizes both the ISO-8601 and SQLite-space
                 -- timestamp formats the DB has accumulated (same pattern the
                 -- rest of the codebase uses).
                 AND datetime(d.last_seen) < datetime('now', ?)
                 AND NOT EXISTS (
                     SELECT 1 FROM alerts a
                     WHERE a.device_id = d.id
                       AND a.alert_type = ?
                       AND datetime(a.sent_at) > datetime(d.last_seen)
                 )
               ORDER BY d.last_seen ASC""",
            (f"-{threshold} minutes", ALERT_TYPE),
        ).fetchall()
        return [dict(r) for r in rows]


async def check_offline_devices_loop(interval_seconds: int = 60):
    """Periodic sweep that alerts owners of newly-offline devices."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await run_offline_sweep()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Offline monitor sweep failed: {e}")


async def run_offline_sweep() -> int:
    """Alert every device that just went offline. Returns how many were alerted.

    Extracted from the loop so tests can invoke a single sweep directly.
    """
    from alerts import alert_engine  # see note in find_offline_devices()

    offline = find_offline_devices()
    alerted = 0
    for device in offline:
        try:
            await alert_engine.send_all(
                device["id"],
                ALERT_TYPE,
                {
                    "time": device["last_seen"],
                    "location": (
                        f"{device['lat']},{device['lng']}"
                        if device.get("lat") is not None and device.get("lng") is not None
                        else "unknown"
                    ),
                },
            )
            from database import log_audit  # see note in find_offline_devices()

            log_audit(
                "device_offline_alerted",
                actor=device["id"],
                details=f"last_seen: {device['last_seen']}, owner: {device['owner_id']}",
            )
            alerted += 1
            logger.info(
                "Device offline alert sent",
                extra={"extra_data": {"device_id": device["id"], "last_seen": device["last_seen"]}},
            )
        except Exception as e:
            logger.warning(f"Offline alert failed for {device['id']}: {e}")
    if offline:
        logger.info(f"Offline monitor sweep: {alerted}/{len(offline)} device(s) alerted")
    return alerted


def _utcnow_iso() -> str:
    """Test-friendly helper: current UTC time as ISO-8601."""
    return datetime.now(timezone.utc).isoformat()
