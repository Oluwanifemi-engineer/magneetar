"""
Magneetar Sentinel Tests
Tests for the theft detection engine.
"""

import os
import secrets

import pytest

# Set test environment
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = ":memory:"

from config import settings  # noqa: E402
from models import TelemetryPing  # noqa: E402 (env set above)
from sentinel import SentinelEngine  # noqa: E402


@pytest.fixture
def engine():
    return SentinelEngine()


@pytest.fixture
def safe_ping():
    """A normal, safe telemetry ping."""
    return TelemetryPing(
        device_id="test-device",
        lat=9.0820,
        lng=8.6753,
        accuracy_horizontal=10.0,
        speed=0.5,
        battery_percent=85,
        is_charging=False,
        provider="gps",
        confidence_level="HIGH",
        is_location_enabled=True,
        is_airplane_mode=False,
        sim_changed=False,
    )


@pytest.fixture
def stolen_ping():
    """A ping indicating potential theft."""
    return TelemetryPing(
        device_id="test-device",
        lat=9.1500,  # Different location
        lng=8.7500,
        accuracy_horizontal=50.0,
        speed=25.0,  # Vehicle speed
        battery_percent=45,
        is_charging=False,
        provider="gps",
        confidence_level="MEDIUM",
        is_location_enabled=True,
        is_airplane_mode=False,
        sim_changed=True,  # SIM changed!
    )


class TestSafeDeviceScore:
    def test_normal_ping_score_zero(self, engine, safe_ping):
        score, level, anomalies = engine.compute_score(safe_ping, [])
        assert score == 0
        assert level == "SAFE"
        assert len(anomalies) == 0

    def test_low_speed_safe(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            speed=2.0,  # Walking speed
            battery_percent=70,
        )
        score, level, _ = engine.compute_score(ping, [])
        assert score == 0
        assert level == "SAFE"


class TestTheftSignals:
    def test_sim_change_raises_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            sim_changed=True,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 35  # SIM change weight
        assert level in ("ELEVATED", "HIGH", "CRITICAL")
        assert any("SIM" in a for a in anomalies)

    def test_failed_unlocks_raise_score(self, engine):
        """The theftie signal (N failed unlocks) must populate the previously
        dead `failed_unlocks` anomaly and add its weight (+20) once the count
        crosses the configured threshold."""
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            failed_unlock_count=settings.FAILED_UNLOCK_THRESHOLD,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 20  # failed_unlocks weight
        assert any("failed unlock" in a.lower() for a in anomalies)

    def test_failed_unlocks_below_threshold_do_not_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            failed_unlock_count=settings.FAILED_UNLOCK_THRESHOLD - 1,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score == 0
        assert len(anomalies) == 0

    def test_failed_unlocks_none_does_not_score(self, engine):
        """Old app builds that never report the field must not be penalized."""
        ping = TelemetryPing(device_id="test", lat=9.0820, lng=8.6753)
        score, level, anomalies = engine.compute_score(ping, [])
        assert score == 0
        assert len(anomalies) == 0

    def test_high_velocity_raises_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            speed=40.0,  # ~144 km/h
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 25  # Vehicle speed weight
        assert any("vehicle" in a.lower() or "km/h" in a for a in anomalies)

    def test_airplane_mode_raises_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            is_airplane_mode=True,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 15
        assert any("airplane" in a.lower() for a in anomalies)

    def test_location_disabled_raises_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            is_location_enabled=False,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 20
        assert any("location" in a.lower() for a in anomalies)

    def test_critical_battery_raises_score(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            battery_percent=3,
        )
        score, level, anomalies = engine.compute_score(ping, [])
        assert score >= 10
        assert any("battery" in a.lower() for a in anomalies)


class TestFalsePositivePrevention:
    def test_single_anomaly_not_critical(self, engine):
        """A single anomaly should not trigger CRITICAL."""
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            sim_changed=True,  # 35 points
        )
        score, level, _ = engine.compute_score(ping, [])
        # Single anomaly should be ELEVATED or HIGH, not CRITICAL
        assert level != "CRITICAL"

    def test_multiple_anomalies_escalate(self, engine):
        """Multiple anomalies should escalate to CRITICAL."""
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            sim_changed=True,  # 35
            is_airplane_mode=True,  # 15
            speed=30.0,  # 25 (vehicle)
            is_location_enabled=False,  # 20
        )
        score, level, anomalies = engine.compute_score(ping, [])
        # Total should be 95, but capped at 100
        assert score >= 80
        assert level == "CRITICAL"


class TestConfirmationGate:
    """The false-positive gate must not deadlock (regression for the live-found
    bug where capped scores were stored as 79 but the gate required >= 80,
    making theft mode unreachable for any device with history)."""

    def _theft_ping(self):
        return TelemetryPing(
            device_id="test-device",
            lat=9.0820,
            lng=8.6753,
            sim_changed=True,  # 35
            is_airplane_mode=True,  # 15
            speed=45.0,  # 25 (vehicle)
            is_location_enabled=False,  # 20
        )

    def _history(self, scores):
        """Build history rows (newest first) from a list of scores."""
        return [{"sentinel_score": s} for s in scores]

    def test_sustained_theft_eventually_unlocks(self, engine):
        """Consecutive theft pings must escalate past the cap."""
        history = []
        for _ in range(4):
            score, level, _ = engine.compute_score(self._theft_ping(), history)
            history.insert(0, {"sentinel_score": score})
        # A sustained theft pattern must reach CRITICAL and trip the threshold
        assert score >= engine.theft_threshold
        assert level == "CRITICAL"

    def test_single_spike_with_history_stays_capped(self, engine):
        """One theft ping after normal history should stay capped (no false alarm)."""
        history = self._history([0, 0, 0])  # device was normal
        score, level, _ = engine.compute_score(self._theft_ping(), history)
        assert score < engine.theft_threshold
        assert level == "HIGH"

    def test_capped_scores_count_toward_confirmation(self, engine):
        """Capped 79s must count toward the streak so the gate can unlock."""
        history = self._history([79, 95, 0])  # capped + raw-high recent pings
        score, level, _ = engine.compute_score(self._theft_ping(), history)
        assert score >= engine.theft_threshold
        assert level == "CRITICAL"


class TestLocationValidation:
    def test_valid_location_accepted(self, engine, safe_ping):
        is_valid, reason = engine.validate_report(safe_ping, None)
        assert is_valid is True
        assert reason is None

    def test_impossible_speed_rejected(self, engine):
        ping = TelemetryPing(
            device_id="test",
            lat=9.0820,
            lng=8.6753,
            speed=100.0,  # 360 km/h - impossible
        )
        is_valid, reason = engine.validate_report(ping, None)
        assert is_valid is False
        assert "speed" in reason.lower()

    def test_negative_accuracy_rejected(self, engine):
        # accuracy_horizontal must be >= 0 per Pydantic validation
        # Test that validation rejects negative accuracy at model level
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TelemetryPing(
                device_id="test",
                lat=9.0820,
                lng=8.6753,
                accuracy_horizontal=-5.0,
            )


class TestImpossibleJumpCheck:
    def _history(self, lat, lng, ts="2026-08-15T10:00:00+00:00"):
        """Newest-first history with the previous fix at [0]."""
        return [{"lat": lat, "lng": lng, "server_timestamp": ts}]

    def test_short_walk_not_flagged(self, engine):
        """A ~100m walk between pings must NOT be a teleport (haversine returns
        meters; without the /1000 this read as "119km" and flagged every ping)."""
        ping = TelemetryPing(
            device_id="test",
            lat=9.0829,  # ~100m north of the previous fix
            lng=8.6753,
            device_timestamp="2026-08-15T10:00:10+00:00",
        )
        score, level, anomalies = engine.compute_score(ping, self._history(9.0820, 8.6753))
        assert not any("Impossible jump" in a for a in anomalies)
        assert score == 0
        assert level == "SAFE"

    def test_teleport_flagged(self, engine):
        """A genuine 100km teleport in seconds MUST be flagged."""
        ping = TelemetryPing(
            device_id="test",
            lat=10.0,  # ~100km north of the previous fix
            lng=8.6753,
            device_timestamp="2026-08-15T10:00:10+00:00",
        )
        score, level, anomalies = engine.compute_score(ping, self._history(9.0820, 8.6753))
        jump = [a for a in anomalies if "Impossible jump" in a]
        assert len(jump) == 1
        # Distance must read in km: ~100km, NOT ~100,000km (meters mislabeled).
        assert "100000km" not in jump[0]
        assert score >= 15


class TestGeofenceCheck:
    def test_inside_geofence_no_trigger(self, engine, safe_ping):
        geofences = [
            {
                "id": 1,
                "center_lat": 9.0820,
                "center_lng": 8.6753,
                "radius_meters": 100,
                "is_safe_zone": True,
                "active": True,
                "was_inside": True,  # Was inside before, still inside
            }
        ]
        triggered = engine.check_geofences(safe_ping, geofences)
        # Device is at center, was inside before, still inside - no transition
        assert len(triggered) == 0

    def test_exit_safe_zone_triggers(self, engine):
        # Device was inside, now outside
        geofences = [
            {
                "id": 1,
                "center_lat": 9.0820,
                "center_lng": 8.6753,
                "radius_meters": 100,
                "is_safe_zone": True,
                "active": True,
                "was_inside": True,  # Was previously inside
            }
        ]

        # Now far away
        ping = TelemetryPing(
            device_id="test",
            lat=9.2000,  # ~13km away
            lng=8.8000,
        )

        triggered = engine.check_geofences(ping, geofences)
        assert len(triggered) == 1
        assert triggered[0]["event"] == "exited"
