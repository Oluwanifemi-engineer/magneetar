"""
Security & Sentinel Domain

Owns: Theft detection engine (Sentinel), motion analysis, unauthorized
      movement detection, security alert escalation, threat scoring.

Extracted from: sentinel.py, routes/devices.py (theft detection portions)

Domain Events Published:
  - theft_detected         {device_id, confidence, location, trigger}
  - security_alert_sent    {device_id, alert_type, recipients}
  - motion_anomaly         {device_id, pattern, severity}
  - device_locked          {device_id, source}
  - device_siren_activated {device_id}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from config import settings
from database import log_audit
from logging_config import get_logger
from models import TelemetryPing

# The actual SentinelEngine lives in sentinel.py — import and re-export it
# so domains/security is the canonical import path for theft detection.
from sentinel import (
    SentinelEngine,
    sentinel,
)

logger = get_logger("magneetar.security")

# Re-export for consumers that want the singleton directly.
__all__ = [
    "sentinel",
    "SentinelEngine",
    "auto_activate_theft_mode",
    "compute_and_persist_score",
    "check_geofence_transitions",
]


# ─── Score computation + persistence ──────────────────────────────────────────


def compute_and_persist_score(
    conn: sqlite3.Connection,
    device_id: str,
    report: TelemetryPing,
) -> tuple[int, str, list[str]]:
    """Compute the threat score for a telemetry ping and persist the result.

    Reads the last 10 location rows to build the history context Sentinel needs.
    Decrypts any encrypted history rows before computing the score (encrypted
    rows carry 0.0 placeholders in lat/lng — passing those through would poison
    the movement/velocity signals).

    Returns (score, threat_level, anomalies).
    """
    # History for Sentinel: last 10 location rows, newest first.
    history = conn.execute(
        """SELECT * FROM locations
           WHERE device_id=?
           ORDER BY server_timestamp DESC LIMIT 10""",
        (device_id,),
    ).fetchall()

    history_dicts = []
    for h in history:
        hd = dict(h)
        hd["lat"], hd["lng"] = __import__("encryption").decrypt_location_row(hd)
        history_dicts.append(hd)

    score, threat_level, anomalies = sentinel.compute_score(report, history_dicts)

    # Persist the score + threat level on the location row is already done
    # by the telemetry domain's persist_location() — this function is called
    # BEFORE persist_location, so the score is returned for the caller to
    # store. But we also update the device-level sentinel_score here so the
    # dashboard's device list shows the current score even before the first
    # location row is read back.
    conn.execute(
        "UPDATE devices SET sentinel_score=? WHERE id=?",
        (score, device_id),
    )
    conn.commit()

    return score, threat_level, anomalies


# ─── Theft mode auto-activation ────────────────────────────────────────────────


def auto_activate_theft_mode(
    conn: sqlite3.Connection,
    device_id: str,
    score: int,
) -> Optional[dict]:
    """When score >= threshold, escalate the device to stolen mode.

    1. Set device operating_mode = 'stolen', is_stolen = 1
    2. Record theft_confirmed_at
    3. Create evidence case
    4. Queue priority evidence commands (front photo, audio, location burst)
    5. Log to audit trail

    Calls below settings.THEFT_SCORE_THRESHOLD are no-ops: escalating to
    stolen mode is reserved for the location path, which only invokes this
    after its false-positive confirmation gate has unlocked a CRITICAL score.
    Sub-threshold signals (e.g. a heartbeat's admin-disabled score of 40) must
    never flip a device to stolen on their own.
    """
    if score < settings.THEFT_SCORE_THRESHOLD:
        return None

    # Check if already in theft mode — no-op if so.
    device = conn.execute(
        "SELECT operating_mode FROM devices WHERE id=?",
        (device_id,),
    ).fetchone()
    if device and device["operating_mode"] == "stolen":
        return None

    now = datetime.now(timezone.utc).isoformat()

    # Update device status.
    conn.execute(
        """UPDATE devices
           SET is_stolen=1, theft_confirmed_at=?,
               operating_mode='stolen', sentinel_score=?
           WHERE id=?""",
        (now, score, device_id),
    )

    # Create evidence case.
    from sentinel import SentinelEngine

    case_id = SentinelEngine()._generate_case_id()
    conn.execute(
        """INSERT INTO evidence_cases (id, device_id, theft_time, status)
           VALUES (?, ?, ?, 'active')""",
        (case_id, device_id, now),
    )

    # Queue high-priority evidence commands.
    priority_commands = [
        ("capture_photo_front", 1),
        ("capture_audio", 1),
        ("location_burst", 2),
    ]
    from domains.command import enqueue_command

    for cmd, priority in priority_commands:
        enqueue_command(conn, device_id, cmd, priority=priority)

    conn.commit()

    # Log the theft activation.
    log_audit(
        action="theft_mode_activated",
        actor=device_id,
        details=f"Score: {score}, Case: {case_id}",
    )

    logger.warning(
        "theft_mode_activated",
        extra={
            "extra_data": {
                "device_id": device_id,
                "score": score,
                "case_id": case_id,
            }
        },
    )

    return {
        "case_id": case_id,
        "device_id": device_id,
        "score": score,
        "activated_at": now,
    }


# ─── Geofence transition checking ─────────────────────────────────────────────


def check_geofence_transitions(
    conn: sqlite3.Connection,
    device_id: str,
    report: TelemetryPing,
) -> list[dict]:
    """Check if a device entered/left any geofence and persist the transition.

    Returns a list of triggered events (entered/exited) with the auto_action
    that should fire (if any). The per-zone inside/outside state is persisted
    on the geofence row (last_inside) so the same transition is never
    re-reported on later pings.

    Delegates to sentinel.check_geofences() for the actual distance math.
    """
    from sentinel import sentinel as _sentinel

    geofences = conn.execute(
        "SELECT * FROM geofences WHERE device_id=? AND active=1",
        (device_id,),
    ).fetchall()

    if not geofences:
        return []

    triggered = _sentinel.check_geofences(report, [dict(g) for g in geofences])

    from domains.command import _queue_auto_action

    exits_to_alert = []
    for event in triggered:
        # Persist the per-zone inside/outside state so the same transition
        # is never re-reported on later pings.
        conn.execute(
            "UPDATE geofences SET last_inside=? WHERE id=?",
            (1 if event["event"] == "entered" else 0, event["geofence_id"]),
        )

        if event["event"] != "exited":
            continue

        # Geofence exit alert — fires for SAFE-ZONE exits (the product
        # meaning: "your device left the safe zone"). The old code checked
        # `not is_safe_zone`, which inverted the intent (exiting HOME never
        # alerted while exiting a restricted zone did).
        if event["is_safe_zone"]:
            exits_to_alert.append(event)

        # Per-zone auto-actions (owner-set policy): react on the device
        # itself, regardless of safe/restricted classification.
        action = event.get("auto_action")
        if action == "capture":
            _queue_auto_action(conn, device_id, "capture_photo_front")
            _queue_auto_action(conn, device_id, "capture_audio")
        elif action == "siren":
            _queue_auto_action(conn, device_id, "alarm")

    conn.commit()
    return triggered + exits_to_alert
