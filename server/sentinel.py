"""
Magneetar Sentinel Engine
Server-side theft detection system with anomaly scoring.
"""

import math
from datetime import datetime, timezone
from typing import Optional

from config import settings
from database import get_db_context, log_audit
from models import TelemetryPing

# ─── Threat-level boundaries (shared) ─────────────────────────────────────────
# Single source of truth so compute_score()'s level thresholds and the
# false-positive confirmation gate can never drift apart.
ELEVATED_BAR = 30  # score >= 30 -> ELEVATED
HIGH_BAR = 60  # score >= 60 -> HIGH (also the confirmation gate's bar)
CAP_SCORE = 100  # hard ceiling for a single ping's score
CAP_AFTER_CONFIRMATION = 79  # score stored while the gate is still holding


class SentinelEngine:
    """
    Computes threat score from telemetry data.
    Uses weighted signals with false-positive prevention.
    """

    THEFT_SIGNALS = {
        "sim_changed": {"weight": 35, "description": "SIM card changed"},
        "admin_disabled": {"weight": 40, "description": "Device admin deactivated"},
        "factory_reset_attempted": {
            "weight": 50,
            "description": "Factory reset initiated",
        },
        "location_disabled": {
            "weight": 20,
            "description": "Location services disabled",
        },
        "airplane_mode_on": {"weight": 15, "description": "Airplane mode activated"},
        "velocity_vehicle": {"weight": 25, "description": "Moving at vehicle speed"},
        "velocity_running": {"weight": 10, "description": "Moving at running speed"},
        "battery_critical": {"weight": 10, "description": "Battery below 5%"},
        "unknown_network": {
            "weight": 10,
            "description": "Connected to unknown network",
        },
        "was_queued_long": {"weight": 10, "description": "Data queued >10 minutes"},
        "failed_unlocks": {
            "weight": 20,
            "description": "Multiple failed unlock attempts",
        },
        "new_google_account": {"weight": 15, "description": "New Google account added"},
        "outside_known_locations": {
            "weight": 15,
            "description": "Outside all known locations",
        },
        "unusual_time": {"weight": 10, "description": "Activity at unusual hour"},
    }

    def __init__(self):
        self.confirmation_count = settings.ANOMALY_CONFIRMATION_COUNT
        self.theft_threshold = settings.THEFT_SCORE_THRESHOLD
        # Confirmation bar: capped scores are persisted as CAP_AFTER_CONFIRMATION
        # (79), so requiring the full theft threshold (80) made the gate
        # unreachable — a device with any history could never be confirmed
        # stolen (score pinned at 79). The HIGH-level boundary (HIGH_BAR) lets
        # capped-but-elevated pings count toward the streak so a sustained
        # theft pattern unlocks CRITICAL.
        self.confirmation_bar = HIGH_BAR

    def compute_score(self, ping: TelemetryPing, history: list[dict]) -> tuple[int, str, list[str]]:
        """
        Compute threat score from current ping and recent history.

        Args:
            ping: Current telemetry ping
            history: List of recent location records (newest first)

        Returns:
            (score 0-100, threat_level, list of anomaly descriptions)
        """
        anomalies = []
        total_score = 0

        # ── SIM Change Detection ──────────────────────────────────────────
        if ping.sim_changed:
            sig = self.THEFT_SIGNALS["sim_changed"]
            anomalies.append(sig["description"])
            total_score += sig["weight"]

        # ── Failed-Unlock "Theftie" Detection ──────────────────────────────
        # Multiple failed unlock attempts strongly suggest a stranger in
        # possession (weight 20 — the same signal the telemetry path reacts
        # to by queuing an evidence capture). The Android app reports the
        # count since the last successful unlock on every ping/heartbeat.
        if ping.failed_unlock_count is not None and ping.failed_unlock_count >= settings.FAILED_UNLOCK_THRESHOLD:
            sig = self.THEFT_SIGNALS["failed_unlocks"]
            anomalies.append(f"{sig['description']}: {ping.failed_unlock_count} attempts")
            total_score += sig["weight"]

        # ── Device State Checks ───────────────────────────────────────────
        if ping.is_location_enabled is False:
            sig = self.THEFT_SIGNALS["location_disabled"]
            anomalies.append(sig["description"])
            total_score += sig["weight"]

        if ping.is_airplane_mode:
            sig = self.THEFT_SIGNALS["airplane_mode_on"]
            anomalies.append(sig["description"])
            total_score += sig["weight"]

        if ping.battery_percent is not None and ping.battery_percent <= 5:
            sig = self.THEFT_SIGNALS["battery_critical"]
            anomalies.append(sig["description"])
            total_score += sig["weight"]

        # ── Velocity Analysis ─────────────────────────────────────────────
        if ping.speed is not None:
            speed_kmh = ping.speed * 3.6  # m/s to km/h
            if speed_kmh > 120:
                sig = self.THEFT_SIGNALS["velocity_vehicle"]
                anomalies.append(f"{sig['description']}: {speed_kmh:.0f} km/h")
                total_score += sig["weight"]
            elif speed_kmh > 15:
                sig = self.THEFT_SIGNALS["velocity_running"]
                anomalies.append(f"{sig['description']}: {speed_kmh:.0f} km/h")
                total_score += sig["weight"]

        # ── Offline Queue Analysis ────────────────────────────────────────
        if ping.was_queued and ping.queued_at:
            try:
                queued_time = datetime.fromisoformat(ping.queued_at.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                minutes_queued = (now - queued_time).total_seconds() / 60
                if minutes_queued > 10:
                    sig = self.THEFT_SIGNALS["was_queued_long"]
                    anomalies.append(f"{sig['description']}: {minutes_queued:.0f} min")
                    total_score += sig["weight"]
            except (ValueError, TypeError):
                pass

        # ── Location History Analysis ─────────────────────────────────────
        if history and len(history) >= 1:
            # Check for impossible jumps (teleportation). History is ordered
            # newest-first, so the immediately-previous fix is history[0] —
            # using history[1] compared against a fix 2 pings old and inflated
            # the distance for every moving device.
            prev = history[0]  # Previous location (newest stored fix)
            prev_lat = prev.get("lat")
            prev_lng = prev.get("lng")
            if prev_lat and prev_lng:
                # _haversine returns METERS (it is also used that way by the
                # geofence radius check below). This block wants km — without
                # the /1000, an ordinary 118m walk reads as "119km" and every
                # moving device gets a false "Impossible jump" teleport alert.
                distance_km = self._haversine(prev_lat, prev_lng, ping.lat, ping.lng) / 1000.0
                time_diff = self._time_diff_seconds(prev.get("server_timestamp"), ping.device_timestamp)
                if time_diff > 0:
                    implied_speed_kmh = (distance_km / time_diff) * 3600
                    # If implied speed > 500 km/h, likely GPS spoofing or teleport
                    if implied_speed_kmh > 500:
                        total_score += 15
                        anomalies.append(f"Impossible jump: {distance_km:.0f}km in {time_diff:.0f}s")

        # ── Unusual Time Detection ────────────────────────────────────────
        # Only flag late-night activity as suspicious when there is actual
        # context: the device is moving (not parked at home), or other
        # anomalies are already present. An idle device at 3am is normal.
        hour = datetime.now(timezone.utc).hour
        # Threshold must stay above walking pace (~1.5 m/s): test_low_speed_safe
        # uses 2.0 m/s and asserts a SAFE score, so 3.0 keeps idle devices
        # unflagged at night while still catching slow moving vehicles.
        is_moving = ping.speed is not None and ping.speed > 3.0  # > ~11 km/h
        if 2 <= hour <= 5 and (is_moving or total_score > 0):  # 2am-5am
            sig = self.THEFT_SIGNALS["unusual_time"]
            anomalies.append(sig["description"])
            total_score += sig["weight"]

        # ── Cap Score ─────────────────────────────────────────────────────
        total_score = min(total_score, CAP_SCORE)

        # ── Determine Threat Level ────────────────────────────────────────
        if total_score >= self.theft_threshold:
            threat_level = "CRITICAL"
        elif total_score >= HIGH_BAR:
            threat_level = "HIGH"
        elif total_score >= ELEVATED_BAR:
            threat_level = "ELEVATED"
        else:
            threat_level = "SAFE"

        # ── False Positive Prevention ─────────────────────────────────────
        # Require consecutive anomalies to escalate to CRITICAL. Compare recent
        # scores against HIGH_BAR (60, HIGH level) rather than the full theft
        # threshold: capped scores are stored as CAP_AFTER_CONFIRMATION (79), so
        # a >=80 check could never be satisfied once any cap had applied — theft
        # mode was unreachable for devices with history (observed live: stuck at
        # 79). Capped-but-elevated pings count toward the streak, so a sustained
        # theft pattern unlocks CRITICAL.
        if threat_level == "CRITICAL" and history:
            recent_scores = [loc.get("sentinel_score", 0) for loc in history[: self.confirmation_count]]
            high_count = sum(1 for s in recent_scores if s >= self.confirmation_bar)
            if high_count < self.confirmation_count - 1:
                threat_level = "HIGH"
                total_score = min(total_score, CAP_AFTER_CONFIRMATION)

        return total_score, threat_level, anomalies

    def auto_activate_theft_mode(self, device_id: str, score: int):
        """
        When score >= threshold:
        1. Set device operating_mode = 'stolen'
        2. Queue capture commands
        3. Create evidence case
        4. Log to audit

        Calls below settings.THEFT_SCORE_THRESHOLD are no-ops: escalating to
        stolen mode is reserved for the location path, which only invokes this
        after its false-positive confirmation gate has unlocked a CRITICAL
        score. Sub-threshold signals (e.g. a heartbeat's admin-disabled score
        of 40) must never flip a device to stolen on their own.
        """
        if score < settings.THEFT_SCORE_THRESHOLD:
            return

        with get_db_context() as conn:
            # Check if already in theft mode
            device = conn.execute("SELECT operating_mode FROM devices WHERE id=?", (device_id,)).fetchone()

            if device and device["operating_mode"] == "stolen":
                return  # Already activated

            # Update device status
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """UPDATE devices
                   SET is_stolen=1, theft_confirmed_at=?,
                       operating_mode='stolen', sentinel_score=?
                   WHERE id=?""",
                (now, score, device_id),
            )

            # Create evidence case
            case_id = self._generate_case_id()
            conn.execute(
                """INSERT INTO evidence_cases (id, device_id, theft_time, status)
                   VALUES (?, ?, ?, 'active')""",
                (case_id, device_id, now),
            )

            # Queue high-priority evidence commands
            priority_commands = [
                ("capture_photo_front", 1),
                ("capture_audio", 1),
                ("location_burst", 2),
            ]
            for cmd, priority in priority_commands:
                conn.execute(
                    """INSERT INTO commands (device_id, command, status, priority, issued_at)
                       VALUES (?, ?, 'pending', ?, ?)""",
                    (device_id, cmd, priority, now),
                )

            conn.commit()

            # Log the theft activation
            log_audit(
                action="theft_mode_activated",
                actor=device_id,
                details=f"Score: {score}, Case: {case_id}",
            )

    def check_geofences(self, ping: TelemetryPing, geofences: list[dict]) -> list[dict]:
        """
        Check if device entered/left any geofence.
        Returns list of triggered geofences.
        """
        triggered = []

        for fence in geofences:
            if not fence.get("active", True):
                continue

            distance = self._haversine(ping.lat, ping.lng, fence["center_lat"], fence["center_lng"])

            is_inside = distance <= fence["radius_meters"]

            # Check if this is a new entry or exit. The live database rows
            # carry the PERSISTED state in last_inside (v1.5 — the device
            # route writes it after every observed transition); the unit-test
            # dicts use was_inside. Prefer last_inside, fall back to was_inside
            # so both callers agree on the transition semantics. NULL (never
            # observed inside) counts as outside: an 'exited' event can only
            # fire after an observed 'entered' event has set last_inside=1.
            was_inside = fence.get("last_inside", fence.get("was_inside", False))

            if is_inside and not was_inside:
                triggered.append(
                    {
                        "geofence_id": fence["id"],
                        "name": fence.get("name", "Unknown"),
                        "event": "entered",
                        "is_safe_zone": fence.get("is_safe_zone", True),
                        "distance_meters": distance,
                        "auto_action": fence.get("auto_action"),
                    }
                )
            elif not is_inside and was_inside:
                triggered.append(
                    {
                        "geofence_id": fence["id"],
                        "name": fence.get("name", "Unknown"),
                        "event": "exited",
                        "is_safe_zone": fence.get("is_safe_zone", True),
                        "distance_meters": distance,
                        "auto_action": fence.get("auto_action"),
                    }
                )

        return triggered

    def validate_report(self, ping: TelemetryPing, previous: Optional[dict] = None) -> tuple[bool, Optional[str]]:
        """
        Anti-spoofing validation.
        Returns (is_valid, reason_if_invalid).
        """
        # Check timestamp is within 5 minutes of server time
        if ping.device_timestamp:
            try:
                device_time = datetime.fromisoformat(ping.device_timestamp.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                diff = abs((now - device_time).total_seconds())
                if diff > 300:  # 5 minutes
                    return False, "Timestamp too far from server time"
            except (ValueError, TypeError):
                return False, "Invalid timestamp format"

        # Check speed plausibility (< 300 km/h = ~83 m/s)
        if ping.speed is not None:
            if ping.speed > 83:  # 83 m/s ≈ 300 km/h
                speed_kmh = ping.speed * 3.6
                return False, f"Impossible speed: {speed_kmh:.0f} km/h"

        # Check battery plausibility
        if previous and ping.battery_percent is not None:
            prev_battery = previous.get("battery_percent")
            if prev_battery is not None and not ping.is_charging:
                # Battery shouldn't increase without charging
                if ping.battery_percent > prev_battery + 2:
                    return False, "Battery increased without charging"

        # Check GPS jitter patterns (real GPS has variance > 0)
        if ping.accuracy_horizontal is not None:
            if ping.accuracy_horizontal <= 0:
                return False, "Invalid accuracy value"

        return True, None

    def _haversine(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Calculate distance between two points in meters."""
        R = 6371000  # Earth's radius in meters

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def _time_diff_seconds(self, time1: Optional[str], time2: Optional[str]) -> float:
        """Calculate time difference in seconds between two ISO timestamps."""
        if not time1 or not time2:
            return 0
        try:
            t1 = datetime.fromisoformat(time1.replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(time2.replace("Z", "+00:00"))
            return abs((t2 - t1).total_seconds())
        except (ValueError, TypeError):
            return 0

    def _generate_case_id(self) -> str:
        """Generate case ID: MGT-2026-XXXXX"""
        import secrets
        import string

        year = datetime.now(timezone.utc).year
        chars = string.ascii_uppercase + string.digits
        suffix = "".join(secrets.choice(chars) for _ in range(5))
        return f"MGT-{year}-{suffix}"


# Singleton
sentinel = SentinelEngine()
