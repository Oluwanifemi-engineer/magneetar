"""
Telemetry Pipeline Domain

Owns: Location ingestion, location storage, GPS fix processing,
      telemetry write batching, data retention purging, historical queries.

Data tables: locations (partitioned monthly on Postgres)
Extracted from: routes/devices.py (location upload portions), write_queue.py

CQRS Notes:
  - Write path: high-throughput location ingestion (3s intervals per device)
  - Read path: dashboard queries for device trails, location history
  - Partitioning: monthly partitions on locations.timestamp (Postgres)

Domain Events Published:
  - location_received      {device_id, lat, lon, accuracy, timestamp}
  - location_outside_geofence {device_id, geofence_id, lat, lon}
  - data_purged            {table, records_deleted, cutoff_date}
"""

from __future__ import annotations

import json
import sqlite3
from functools import partial
from typing import Optional

from encryption import decrypt_location_row, encrypt_location_for_store
from logging_config import get_logger
from models import TelemetryPing
from websocket_manager import broadcast_to_dashboards
from write_queue import enqueue_write, write_queue_enabled

logger = get_logger("magneetar.telemetry")

# ─── At-most-once guard ─────────────────────────────────────────────────────────


def location_row_exists(
    conn: sqlite3.Connection,
    device_id: str,
    report: TelemetryPing,
) -> bool:
    """True when this exact ping (device + seq + device-clock timestamp)
    was already persisted.

    OkHttp's default retryOnConnectionFailure re-sends the same body when
    the connection dies after the server processed it (seen live: a
    captive-portal reconnect inserted every ping twice — the server got the
    request, the response was lost, the client re-POSTed the identical body
    ~45s later). This guard prevents duplicate rows.
    """
    if not report.ping_sequence:
        return False
    row = conn.execute(
        """SELECT 1 FROM locations
           WHERE device_id=? AND ping_sequence=?
             AND device_timestamp=? LIMIT 1""",
        (device_id, report.ping_sequence, report.device_timestamp),
    ).fetchone()
    return row is not None


# ─── Persistence ───────────────────────────────────────────────────────────────


def persist_location(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    report: TelemetryPing,
    score: int,
    threat_level: str,
    anomalies: list,
    now: str,
    ts: str,
) -> None:
    """Insert one location row + refresh the device row.

    Shared by the synchronous path (runs on the request connection) and the
    batched path (runs on the write queue's dedicated connection). Keeping
    the SQL in one place guarantees the two paths can never drift.

    At-most-once: a retried/duplicate ping is skipped — the device row's
    last_seen still refreshes below, but no second row is inserted.
    """
    if location_row_exists(conn, device_id, report):
        return

    # At-rest encryption (v1.5): when MT_ENCRYPTION_KEY is configured, the
    # coordinates are AES-256-GCM encrypted with the per-device HKDF key —
    # the row stores 0.0 placeholders + ciphertext in location_data. Sentinel
    # and the WebSocket feed already run on the in-memory `report` payload, so
    # encrypting at the DB boundary never affects theft detection.
    lat, lng, loc_enc, loc_data = encrypt_location_for_store(report.lat, report.lng, device_id)

    conn.execute(
        """INSERT INTO locations (device_id, lat, lng, altitude, accuracy_horizontal,
           accuracy_vertical, confidence_level, speed, bearing, activity_type,
           step_count, provider, gps_satellite_count, wifi_bssids, cell_tower_ids,
           ble_devices_nearby, battery_percent, is_charging, network_type,
           signal_strength_dbm, is_location_enabled, is_airplane_mode,
           sim_changed, sim_serial_hash, sentinel_score, threat_level, anomalies,
           device_timestamp, server_timestamp, was_queued, queued_at,
           queue_position, ping_sequence, location_encrypted, location_data)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            device_id,
            lat,
            lng,
            report.altitude,
            report.accuracy_horizontal,
            report.accuracy_vertical,
            report.confidence_level,
            report.speed,
            report.bearing,
            report.activity_type,
            report.step_count,
            report.provider,
            report.gps_satellite_count,
            json.dumps(report.wifi_bssids or []),
            json.dumps(report.cell_tower_ids or []),
            report.ble_devices_nearby,
            report.battery_percent,
            report.is_charging,
            report.network_type,
            report.signal_strength_dbm,
            report.is_location_enabled,
            report.is_airplane_mode,
            report.sim_changed,
            report.sim_serial_hash,
            score,
            threat_level,
            json.dumps(anomalies or []),
            ts,
            now,
            report.was_queued,
            report.queued_at,
            report.queue_position,
            report.ping_sequence,
            loc_enc,
            loc_data,
        ),
    )

    # COALESCE: an old app build that doesn't send capture_armed (None) must
    # not wipe the stored state — the column keeps its last known value.
    conn.execute(
        """UPDATE devices SET last_seen=?, sentinel_score=?,
           capture_armed=COALESCE(?, capture_armed) WHERE id=?""",
        (now, score, report.capture_armed, device_id),
    )


def persist_location_batched(
    device_id: str,
    report: TelemetryPing,
    score: int,
    threat_level: str,
    anomalies: list,
    now: str,
    ts: str,
) -> bool:
    """Attempt to enqueue the location persistence onto the write queue.

    Returns True when enqueued (the write will happen asynchronously on the
    queue's connection). Returns False when the queue is disabled or not yet
    started — the caller must fall back to persist_location() on their own
    connection.
    """
    if not write_queue_enabled():
        return False
    return enqueue_write(
        partial(
            persist_location,
            device_id=device_id,
            report=report,
            score=score,
            threat_level=threat_level,
            anomalies=anomalies,
            now=now,
            ts=ts,
        )
    )


# ─── Unarchive (fresh telemetry un-archives a device) ─────────────────────────


def unarchive_device(conn: sqlite3.Connection, device_id: str) -> None:
    """Clear the archived_at flag on a device that has come back online.

    Any fresh telemetry/heartbeat clears the flag automatically — an archived
    device can come back (e.g. the owner rebooted a stolen phone that is no
    longer stolen, or a device that was silent for 30 days starts reporting
    again). This is a no-op unless the device was archived.
    """
    conn.execute(
        "UPDATE devices SET archived_at=NULL WHERE id=? AND archived_at IS NOT NULL",
        (device_id,),
    )
    conn.commit()


# ─── Live location query ───────────────────────────────────────────────────────


def get_live_location(conn: sqlite3.Connection, device_id: str) -> Optional[dict]:
    """Get the latest location for a device (newest by server_timestamp)."""
    row = conn.execute(
        """SELECT * FROM locations
           WHERE device_id=?
           ORDER BY server_timestamp DESC LIMIT 1""",
        (device_id,),
    ).fetchone()
    if not row:
        return None
    loc = dict(row)
    loc["lat"], loc["lng"] = decrypt_location_row(loc)
    loc.pop("location_data", None)
    return loc


def get_location_history(
    conn: sqlite3.Connection,
    device_id: str,
    limit: int = 200,
    order_desc: bool = True,
) -> list[dict]:
    """Get location history for a device.

    Used by the dashboard's location history endpoint and the replay endpoint.
    """
    direction = "DESC" if order_desc else "ASC"
    rows = conn.execute(
        f"""SELECT * FROM locations
           WHERE device_id=?
           ORDER BY server_timestamp {direction} LIMIT ?""",
        (device_id, limit),
    ).fetchall()
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
        loc.pop("location_data", None)
        locations.append(loc)
    return locations


def get_replay_data(
    conn: sqlite3.Connection,
    device_id: str,
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
) -> list[dict]:
    """Get location data for trail replay (ordered oldest-first)."""
    query = "SELECT * FROM locations WHERE device_id=?"
    params = [device_id]

    if from_time:
        query += " AND server_timestamp >= ?"
        params.append(from_time)
    if to_time:
        query += " AND server_timestamp <= ?"
        params.append(to_time)

    query += " ORDER BY server_timestamp ASC"

    rows = conn.execute(query, params).fetchall()
    locations = []
    for r in rows:
        loc = dict(r)
        loc["lat"], loc["lng"] = decrypt_location_row(loc)
        loc.pop("location_data", None)
        locations.append(loc)
    return locations


# ─── Broadcast ────────────────────────────────────────────────────────────────


async def broadcast_location_update(
    device_id: str,
    report: TelemetryPing,
    score: int,
    threat_level: str,
    now: str,
) -> None:
    """Broadcast a location update to all connected dashboards.

    Accuracy, provider, bearing, and confidence_level are included so the
    real-time feed shows the fused Kalman accuracy ("±12m" vs "±500m") —
    the old broadcast omitted these and always rendered "±?m".
    """
    await broadcast_to_dashboards(
        {
            "type": "location",
            "data": {
                "device_id": device_id,
                "lat": report.lat,
                "lng": report.lng,
                "speed": report.speed,
                "battery": report.battery_percent,
                "sentinel_score": score,
                "threat_level": threat_level,
                "timestamp": now,
                "accuracy_horizontal": report.accuracy_horizontal,
                "provider": report.provider,
                "bearing": report.bearing,
                "confidence_level": report.confidence_level,
            },
        }
    )
