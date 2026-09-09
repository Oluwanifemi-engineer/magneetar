"""
Notification Router Domain

Owns: Multi-channel alert delivery (FCM push, SMS, WhatsApp, email),
      notification preferences, delivery tracking, USSD menu responses.

This is the **only** domain that subscribes to events from ALL other domains.
It acts as a router: receives domain events and dispatches to the appropriate
delivery channel based on user preferences and device capabilities.

Channels:
  - FCM (Firebase Cloud Messaging) — primary push for Android
  - SMS (Twilio) — offline fallback, USSD-capable phones
  - WhatsApp (Twilio) — interactive bot commands
  - USSD (*120# menu) — feature phones without internet
  - WebSocket — real-time dashboard updates
  - Webhook — custom integrations

Domain Events Published:
  - notification_sent      {recipient, channel, status, reference_id}
  - notification_failed    {recipient, channel, reason}
  - alert_delivered        {device_id, alert_type, channel, latency_ms}
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from alerts import alert_engine
from config import settings
from logging_config import get_logger

logger = get_logger("magneetar.notification")

# ─── Alert delivery orchestrator ───────────────────────────────────────────────


async def send_alert(
    device_id: str,
    alert_type: str,
    context: dict,
    *,
    dedup_minutes: int = 10,
) -> dict:
    """Send an alert for a device via all configured channels.

    Uses the alert_engine from alerts.py as the backend (it handles FCM, SMS,
    WhatsApp, email dispatch). This domain module wraps it with dedup logic
    and cross-domain event emission.

    Dedup window: an alert of the same type for the same device is suppressed
    if one was sent within `dedup_minutes` (default 10). This absorbs
    queued/offline replays so one incident = one alert.
    """
    # Dedup check: has an alert of this type been sent recently?
    if _alert_recent(device_id, alert_type, dedup_minutes):
        logger.debug(
            "alert_deduped",
            extra={
                "extra_data": {
                    "device_id": device_id,
                    "alert_type": alert_type,
                }
            },
        )
        return {"status": "deduped", "device_id": device_id, "alert_type": alert_type}

    # Send via alert engine.
    try:
        result = await alert_engine.send_all(device_id, alert_type, context)
    except Exception as e:
        logger.error(
            "alert_send_failed",
            extra={
                "extra_data": {
                    "device_id": device_id,
                    "alert_type": alert_type,
                    "error": str(e),
                }
            },
        )
        # Log the failure so it surfaces in the error log.
        from database import log_error

        log_error(
            level="ERROR",
            message=f"Alert send failed: {alert_type} for {device_id}",
            source="notification",
            traceback=None,
            request_path="/api/device/location",
        )
        return {"status": "failed", "device_id": device_id, "alert_type": alert_type}

    # Record the alert in the alerts table (for history + dedup).
    now = datetime.now(timezone.utc).isoformat()
    from database import get_db_context

    with get_db_context() as conn:
        conn.execute(
            """INSERT INTO alerts (device_id, alert_type, channel, recipient,
               message, sent_at, delivered)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                device_id,
                alert_type,
                result.get("channel", "unknown"),
                result.get("recipient", ""),
                json.dumps(context),
                now,
            ),
        )
        conn.commit()

    logger.info(
        "alert_sent",
        extra={
            "extra_data": {
                "device_id": device_id,
                "alert_type": alert_type,
                "channel": result.get("channel", "unknown"),
            }
        },
    )

    return {
        "status": "sent",
        "device_id": device_id,
        "alert_type": alert_type,
        "channel": result.get("channel", "unknown"),
        "timestamp": now,
    }


def _alert_recent(device_id: str, alert_type: str, minutes: int = 10) -> bool:
    """True when an alert of the given type was already logged for this device
    in the last `minutes` minutes.

    Shared across the location and heartbeat paths so one incident (including
    queued/offline replays of the same flag) = one always-deliver alert.

    Reads through the CURRENT database module (resolved at call time) rather
    than the request connection: alert_engine.send_all resolves
    `from database import get_db_context` at call time too, so under full-suite
    test eviction it writes rows to a DIFFERENT module than the one the
    request's `db` came from. Reading the same module send_all writes keeps
    the dedup truthful.
    """
    import database as _current_db

    with _current_db.get_db_context() as conn:
        recent = conn.execute(
            """SELECT 1 FROM alerts
               WHERE device_id=? AND alert_type=?
                 AND datetime(sent_at) > datetime('now', ?)
               LIMIT 1""",
            (device_id, alert_type, f"-{minutes} minutes"),
        ).fetchone()
    return recent is not None


# ─── Channel preference resolution ─────────────────────────────────────────────


def resolve_channels(
    conn: sqlite3.Connection,
    device_id: str,
) -> list[str]:
    """Resolve which alert channels to use for a device.

    Priority:
    1. Per-device alert_channels (JSON array, e.g. ["whatsapp","sms","push"])
    2. Global defaults (push + email if configured)

    Returns a list of channel names.
    """
    row = conn.execute(
        "SELECT alert_channels FROM devices WHERE id=?",
        (device_id,),
    ).fetchone()

    if row and row["alert_channels"]:
        try:
            channels = json.loads(row["alert_channels"])
            if isinstance(channels, list):
                return channels
        except (json.JSONDecodeError, TypeError):
            pass

    # Default: push + email
    channels = ["push"]
    if settings.RESEND_API_KEY or settings.SENDGRID_API_KEY:
        channels.append("email")
    return channels


# ─── USSD menu (feature phone fallback) ────────────────────────────────────────


def ussd_menu_response(user_input: str, state: Optional[dict] = None) -> dict:
    """Generate a USSD menu response for feature-phone users.

    state tracks the current menu depth (for multi-level menus).
    """
    if not state:
        state = {"depth": 0, "selection": ""}

    if user_input == "*" or user_input == "0":
        return {
            "response": ("Magneetar\n" "1. Check device status\n" "2. Request locate\n" "3. Report theft\n" "0. Back"),
            "state": {"depth": 0, "selection": ""},
            "continue": True,
        }

    if user_input == "1":
        return {
            "response": "Device status lookup — provide device ID",
            "state": {"depth": 1, "selection": "status"},
            "continue": True,
        }
    elif user_input == "2":
        return {
            "response": "Send locate request — provide device ID",
            "state": {"depth": 1, "selection": "locate"},
            "continue": True,
        }
    elif user_input == "3":
        return {
            "response": "Report theft — provide device ID and confirmation",
            "state": {"depth": 1, "selection": "theft"},
            "continue": True,
        }

    return {
        "response": "Invalid option. Press 0 to go back.",
        "state": state,
        "continue": True,
    }
