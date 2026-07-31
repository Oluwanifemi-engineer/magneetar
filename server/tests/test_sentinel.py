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
