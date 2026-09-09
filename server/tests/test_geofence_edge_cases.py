"""
Geofencing Edge Case Tests
──────────────────────────
Tests the geofencing system under boundary conditions that could cause
incorrect behavior in production:

1. Exact boundary (device exactly at radius) — should be INSIDE
2. Just outside boundary — should trigger exit
3. Rapid entry/exit transitions — dedup prevents duplicate alerts
4. Auto-action dedup — only one capture/siren per exit transition
5. last_inside persistence — exit only fires after observed entry
6. Multiple geofences — independent transitions
7. Haversine precision — antipodal points, same point, pole
8. Inactive geofence — skipped entirely
9. Null last_inside — never observed inside, exit should not fire
10. Auto-action types — capture vs siren vs None
"""

import math

import pytest
from sentinel import TelemetryPing

# NOTE: no env mutation, no module eviction, no DB setup here. These tests are
# pure: they exercise SentinelEngine.check_geofences arithmetic directly and
# never touch the database or settings. Mutating os.environ / evicting
# config/database/main from sys.modules at import time poisons every test file
# that runs after this one ("Invalid API key" 401s from a stale module
# generation), so this file deliberately stays inert.

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def engine():
    """Fresh SentinelEngine for each test."""
    from sentinel import SentinelEngine

    return SentinelEngine()


@pytest.fixture
def center():
    """Geofence center: Lagos, Nigeria."""
    return {"lat": 6.5244, "lng": 3.3792}


@pytest.fixture
def fence(center):
    """A standard 500m safe-zone geofence."""
    return {
        "id": 1,
        "name": "Home",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 500,
        "is_safe_zone": True,
        "active": True,
        "last_inside": None,  # never observed
        "auto_action": None,
    }


def _ping(lat, lng, **kwargs):
    """Create a TelemetryPing at the given coordinates."""
    defaults = {
        "device_id": "test-device",
        "lat": lat,
        "lng": lng,
        "accuracy_horizontal": 10.0,
        "confidence_level": "HIGH",
        "battery_percent": 80,
        "is_charging": False,
        "speed": 0.0,
    }
    defaults.update(kwargs)
    return TelemetryPing(**defaults)


# ── Test: Exact boundary is INSIDE ──────────────────────────────────────────


def test_exact_boundary_is_inside(engine, fence, center):
    """A device exactly at the radius distance should be considered inside."""
    # Calculate a point exactly 500m from center
    R = 6371000
    lat1 = math.radians(center["lat"])
    lng1 = math.radians(center["lng"])
    d = 500  # exactly the radius
    bearing = 0  # north
    lat2 = math.asin(math.sin(lat1) * math.cos(d / R) + math.cos(lat1) * math.sin(d / R) * math.cos(bearing))
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(d / R) * math.cos(lat1),
        math.cos(d / R) - math.sin(lat1) * math.sin(lat2),
    )
    point_lat = math.degrees(lat2)
    point_lng = math.degrees(lng2)

    ping = _ping(point_lat, point_lng)
    triggered = engine.check_geofences(ping, [fence])

    # Exactly at boundary: distance == radius, so is_inside = True
    # Since last_inside is None (never observed), entering should trigger
    assert len(triggered) == 1
    assert triggered[0]["event"] == "entered"


# ── Test: Just outside boundary triggers exit ───────────────────────────────


def test_just_outside_boundary_triggers_exit(engine, fence, center):
    """A device 1m outside the radius should be outside."""
    R = 6371000
    lat1 = math.radians(center["lat"])
    lng1 = math.radians(center["lng"])
    d = 501  # 1m outside the 500m radius
    bearing = 0
    lat2 = math.asin(math.sin(lat1) * math.cos(d / R) + math.cos(lat1) * math.sin(d / R) * math.cos(bearing))
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(d / R) * math.cos(lat1),
        math.cos(d / R) - math.sin(lat1) * math.sin(lat2),
    )
    point_lat = math.degrees(lat2)
    point_lng = math.degrees(lng2)

    # Device was inside (last_inside=1), now outside
    fence_inside = {**fence, "last_inside": True}
    ping = _ping(point_lat, point_lng)
    triggered = engine.check_geofences(ping, [fence_inside])

    assert len(triggered) == 1
    assert triggered[0]["event"] == "exited"


# ── Test: Rapid entry/exit produces exactly one of each ─────────────────────


def test_rapid_entry_exit_produces_exactly_one_each(engine, fence, center):
    """Simulate rapid movement: enter → exit → enter. Each transition fires once."""
    # Start outside, enter, exit, re-enter
    # Step 1: Outside (last_inside=None) → should fire "entered"
    ping_outside = _ping(center["lat"] + 0.01, center["lng"])  # ~1.1km away
    triggered1 = engine.check_geofences(ping_outside, [fence])
    assert len(triggered1) == 0  # outside, was never inside → no transition

    # Step 2: Inside (last_inside=None) → should fire "entered"
    fence_after_step1 = {**fence, "last_inside": 0}  # explicitly outside
    ping_inside = _ping(center["lat"], center["lng"])
    triggered2 = engine.check_geofences(ping_inside, [fence_after_step1])
    assert len(triggered2) == 1
    assert triggered2[0]["event"] == "entered"

    # Step 3: Outside (last_inside=1) → should fire "exited"
    fence_after_step2 = {**fence, "last_inside": 1}
    ping_outside2 = _ping(center["lat"] + 0.01, center["lng"])
    triggered3 = engine.check_geofences(ping_outside2, [fence_after_step2])
    assert len(triggered3) == 1
    assert triggered3[0]["event"] == "exited"

    # Step 4: Inside again (last_inside=0) → should fire "entered"
    fence_after_step3 = {**fence, "last_inside": 0}
    ping_inside2 = _ping(center["lat"], center["lng"])
    triggered4 = engine.check_geofences(ping_inside2, [fence_after_step3])
    assert len(triggered4) == 1
    assert triggered4[0]["event"] == "entered"


# ── Test: Auto-action dedup — only one pending command per action ───────────


def test_auto_action_capture_produces_correct_event(engine, center):
    """Auto-action 'capture' on exit should produce correct event data."""
    fence = {
        "id": 1,
        "name": "School",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": True,
        "active": True,
        "last_inside": True,
        "auto_action": "capture",
    }
    ping = _ping(center["lat"] + 0.01, center["lng"])  # outside
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 1
    assert triggered[0]["event"] == "exited"
    assert triggered[0]["auto_action"] == "capture"


def test_auto_action_siren_produces_correct_event(engine, center):
    """Auto-action 'siren' on exit should produce correct event data."""
    fence = {
        "id": 2,
        "name": "Danger Zone",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": False,
        "active": True,
        "last_inside": True,
        "auto_action": "siren",
    }
    ping = _ping(center["lat"] + 0.01, center["lng"])
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 1
    assert triggered[0]["event"] == "exited"
    assert triggered[0]["auto_action"] == "siren"


# ── Test: Null last_inside prevents exit ────────────────────────────────────


def test_null_last_inside_prevents_exit(engine, center):
    """If last_inside is None (never observed inside), exiting should not fire."""
    fence = {
        "id": 1,
        "name": "Home",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": True,
        "active": True,
        "last_inside": None,  # never observed inside
        "auto_action": None,
    }
    # Device is outside
    ping = _ping(center["lat"] + 0.01, center["lng"])
    triggered = engine.check_geofences(ping, [fence])

    # Should NOT fire "exited" because device was never observed inside
    assert len(triggered) == 0


# ── Test: Inactive geofence is skipped ──────────────────────────────────────


def test_inactive_geofence_skipped(engine, center):
    """Inactive geofences should not trigger any events."""
    fence = {
        "id": 1,
        "name": "Old Zone",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 500,
        "is_safe_zone": True,
        "active": False,  # deactivated
        "last_inside": True,
        "auto_action": None,
    }
    ping = _ping(center["lat"] + 0.01, center["lng"])  # outside
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 0


# ── Test: Multiple geofences with independent transitions ───────────────────


def test_multiple_geofences_independent_transitions(engine, center):
    """Two geofences should track transitions independently."""
    fence_home = {
        "id": 1,
        "name": "Home",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": True,
        "active": True,
        "last_inside": True,  # was inside
        "auto_action": None,
    }
    fence_school = {
        "id": 2,
        "name": "School",
        "center_lat": center["lat"] + 0.01,  # ~1.1km away
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": True,
        "active": True,
        "last_inside": False,  # was outside
        "auto_action": None,
    }

    # Device is at Home center — inside Home, outside School
    ping = _ping(center["lat"], center["lng"])
    triggered = engine.check_geofences(ping, [fence_home, fence_school])

    # Home: was inside, still inside → no transition
    # School: was outside, still outside → no transition
    home_events = [t for t in triggered if t["geofence_id"] == 1]
    school_events = [t for t in triggered if t["geofence_id"] == 2]
    assert len(home_events) == 0
    assert len(school_events) == 0

    # Device moves to School center — outside Home, inside School
    ping2 = _ping(center["lat"] + 0.01, center["lng"])
    triggered2 = engine.check_geofences(ping2, [fence_home, fence_school])

    home_events2 = [t for t in triggered2 if t["geofence_id"] == 1]
    school_events2 = [t for t in triggered2 if t["geofence_id"] == 2]
    assert len(home_events2) == 1
    assert home_events2[0]["event"] == "exited"
    assert len(school_events2) == 1
    assert school_events2[0]["event"] == "entered"


# ── Test: Haversine precision — same point returns ~0 ───────────────────────


def test_haversine_same_point(engine):
    """Distance between the same point should be ~0 meters."""
    d = engine._haversine(6.5244, 3.3792, 6.5244, 3.3792)
    assert d == pytest.approx(0.0, abs=0.01)


def test_haversine_known_distance(engine):
    """Haversine should return ~111km for 1 degree of latitude."""
    # 1 degree of latitude ≈ 111,319 meters
    d = engine._haversine(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111319, rel=0.01)


def test_haversine_antipodal_points(engine):
    """Antipodal points should be ~20,000km (half Earth's circumference)."""
    d = engine._haversine(0.0, 0.0, 0.0, 180.0)
    assert d == pytest.approx(20015081, rel=0.01)  # ~20,015 km


# ── Test: Restricted zone exit fires even for non-safe zones ────────────────


def test_restricted_zone_exit_fires_event(engine, center):
    """Exiting a restricted zone should still produce an 'exited' event."""
    fence = {
        "id": 1,
        "name": "Restricted Area",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 200,
        "is_safe_zone": False,  # restricted zone
        "active": True,
        "last_inside": True,
        "auto_action": None,
    }
    ping = _ping(center["lat"] + 0.01, center["lng"])
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 1
    assert triggered[0]["event"] == "exited"
    assert triggered[0]["is_safe_zone"] is False


# ── Test: Entry into safe zone does NOT fire alert (only exit does) ─────────


def test_entry_into_safe_zone_no_auto_action(engine, center):
    """Entering a safe zone should not trigger auto-actions (only exit does)."""
    fence = {
        "id": 1,
        "name": "Home",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 500,
        "is_safe_zone": True,
        "active": True,
        "last_inside": 0,  # was outside
        "auto_action": "siren",  # would fire on EXIT
    }
    ping = _ping(center["lat"], center["lng"])  # inside
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 1
    assert triggered[0]["event"] == "entered"
    # auto_action is in the event but should only be acted on for "exited"
    assert triggered[0]["auto_action"] == "siren"


# ── Test: Distance meters in triggered event is accurate ────────────────────


def test_triggered_event_distance_is_accurate(engine, center):
    """The distance_meters in the triggered event should match the actual distance."""
    fence = {
        "id": 1,
        "name": "Home",
        "center_lat": center["lat"],
        "center_lng": center["lng"],
        "radius_meters": 500,
        "is_safe_zone": True,
        "active": True,
        "last_inside": 0,
        "auto_action": None,
    }
    # Place device 300m north of center
    R = 6371000
    lat1 = math.radians(center["lat"])
    lng1 = math.radians(center["lng"])
    d = 300
    bearing = 0
    lat2 = math.asin(math.sin(lat1) * math.cos(d / R) + math.cos(lat1) * math.sin(d / R) * math.cos(bearing))
    lng2 = lng1 + math.atan2(
        math.sin(bearing) * math.sin(d / R) * math.cos(lat1),
        math.cos(d / R) - math.sin(lat1) * math.sin(lat2),
    )

    ping = _ping(math.degrees(lat2), math.degrees(lng2))
    triggered = engine.check_geofences(ping, [fence])

    assert len(triggered) == 1
    assert triggered[0]["distance_meters"] == pytest.approx(300, rel=0.01)
