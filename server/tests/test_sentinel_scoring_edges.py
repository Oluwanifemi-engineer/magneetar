"""
Magneetar Sentinel Scoring Edge-Case Tests

Pins the scoring engine's boundaries that unit tests tend to skip because
they are awkward to construct exactly:

  * the 100-point hard cap (raw sums can reach ~135) and that anomalies stay
    complete after the cap is applied;
  * the exact level thresholds (29/30 ELEVATED, 59/60 HIGH, 79/80 CRITICAL)
    and the false-positive cap value (CAP_AFTER_CONFIRMATION = 79);
  * the velocity bands after the 45 km/h vehicle fix: running = 15-45 km/h
    (a human can't run faster), vehicle = >45 km/h (car/okada flight);
  * signal boundaries: battery at 5% vs 6%, queue at 9 vs 11 minutes;
  * the 2am-5am unusual-time window on BOTH sides of every boundary (tests
    run at any wall-clock hour, so sentinel.datetime is stubbed — the only
    wall-clock dependency in the engine);
  * the false-positive confirmation gate: single spike vs sustained, exact
    streak length, decay (old high scores fall out of the 3-ping window),
    and the documented no-history contract (a first ping has no history to
    confirm against, so the gate cannot apply).

These tests import only config/models/sentinel (pure scoring — no DB, no
app), mirroring test_sentinel.py, so they are immune to the module-eviction
ordering hazards that integration suites in this repo must defend against.
"""

import os
from datetime import datetime, timedelta

import pytest

# Set test environment BEFORE imports (same pattern as test_sentinel.py)
os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64  # fixed: cross-generation decryption (see conftest.py)
os.environ["MT_DB_PATH"] = ":memory:"

import sentinel as sentinel_module  # noqa: E402
from config import settings  # noqa: E402
from models import TelemetryPing  # noqa: E402 (env set above)
from sentinel import CAP_AFTER_CONFIRMATION, CAP_SCORE, SentinelEngine  # noqa: E402

# ─── Fixtures & helpers ──────────────────────────────────────────────────────


@pytest.fixture
def engine():
    return SentinelEngine()


@pytest.fixture
def noon(monkeypatch):
    """Stub the engine's wall clock at 10:00 UTC — OUTSIDE the 2-5am
    unusual-time window, so scores below are deterministic at any hour the
    suite runs."""
    return _freeze_clock(monkeypatch, "2026-08-15T10:00:00+00:00")


class _FixedClock:
    """Replaces sentinel.datetime so unusual_time / queue-age math is
    deterministic regardless of when the tests run. Keeps fromisoformat
    (used by the queue-age and time-diff paths) pointing at the REAL
    datetime class, which lives in this module's namespace untouched."""

    def __init__(self, dt):
        self.dt = dt

    def now(self, tz=None):
        return self.dt if tz is None else self.dt.astimezone(tz)

    @classmethod
    def fromisoformat(cls, s):
        return datetime.fromisoformat(s)


def _freeze_clock(monkeypatch, iso: str) -> _FixedClock:
    clock = _FixedClock(datetime.fromisoformat(iso))
    monkeypatch.setattr(sentinel_module, "datetime", clock)
    return clock


def make_ping(**overrides) -> TelemetryPing:
    """A SAFE baseline ping; overrides add signals. Speed defaults to a slow
    walk (0.5 m/s) so velocity never contributes unless asked."""
    base = dict(
        device_id="edge-device",
        lat=9.0820,
        lng=8.6753,
        accuracy_horizontal=10.0,
        speed=0.5,
        battery_percent=90,
        is_charging=False,
        provider="gps",
        confidence_level="HIGH",
        is_location_enabled=True,
        is_airplane_mode=False,
        sim_changed=False,
        device_timestamp="2026-08-15T10:00:00+00:00",
    )
    base.update(overrides)
    return TelemetryPing(**base)


def queued_ping(clock: _FixedClock, minutes_ago: int, **overrides) -> TelemetryPing:
    """A ping that sat in the offline queue `minutes_ago` minutes."""
    queued_at = (clock.dt - timedelta(minutes=minutes_ago)).isoformat()
    return make_ping(was_queued=True, queued_at=queued_at, **overrides)


def history(*scores) -> list[dict]:
    """History rows (newest first) from raw sentinel_score values."""
    return [{"sentinel_score": s} for s in scores]


# Theft-level ping: 35+20+15+25+20 = 115 raw -> capped. Used by gate tests.
def theft_ping() -> TelemetryPing:
    return make_ping(
        sim_changed=True,  # 35
        is_location_enabled=False,  # 20
        is_airplane_mode=True,  # 15
        speed=45.0,  # 162 km/h -> vehicle 25
        battery_percent=3,  # 10
    )


def _check(ping, hx):
    engine = SentinelEngine()
    return engine.compute_score(ping, hx)


# ─── Score cap ───────────────────────────────────────────────────────────────


class TestScoreCap:
    def test_all_signals_cap_at_exactly_100(self, noon):
        """Every scorable signal at once sums to ~135 raw; the engine must
        return exactly 100 — never more — and still report every anomaly."""
        ping = make_ping(
            sim_changed=True,  # 35
            failed_unlock_count=settings.FAILED_UNLOCK_THRESHOLD,  # 20
            is_location_enabled=False,  # 20
            is_airplane_mode=True,  # 15
            battery_percent=1,  # 10
            speed=45.0,  # 162 km/h -> vehicle 25
            was_queued=True,
            queued_at=(noon.dt - timedelta(minutes=30)).isoformat(),  # 10
        )
        score, level, anomalies = _check(ping, history(79, 79, 0))
        assert score == CAP_SCORE == 100
        assert level == "CRITICAL"
        # 7 triggered signals; cap must not swallow any anomaly description
        assert len(anomalies) == 7

    def test_cap_still_holds_inside_unusual_time_window(self, monkeypatch):
        """Same full-signal ping at 3am adds unusual_time (+10) — the cap
        must still bind at exactly 100."""
        clock = _freeze_clock(monkeypatch, "2026-08-15T03:00:00+00:00")
        ping = make_ping(
            sim_changed=True,
            failed_unlock_count=settings.FAILED_UNLOCK_THRESHOLD,
            is_location_enabled=False,
            is_airplane_mode=True,
            battery_percent=1,
            speed=45.0,
            was_queued=True,
            queued_at=(clock.dt - timedelta(minutes=30)).isoformat(),
        )
        score, level, anomalies = _check(ping, history(79, 79, 0))
        assert score == 100
        assert len(anomalies) == 8  # + unusual_time
        assert any("unusual" in a.lower() for a in anomalies)

    def test_gate_cap_is_below_theft_threshold(self, noon):
        """A single theft spike over clean history must come back capped at
        CAP_AFTER_CONFIRMATION (79) — strictly below the 80 activation bar,
        so the location path can never auto-activate stolen mode on it."""
        score, level, _ = _check(theft_ping(), history(0, 0, 0))
        assert score == CAP_AFTER_CONFIRMATION == 79
        assert score < settings.THEFT_SCORE_THRESHOLD
        assert level == "HIGH"


# ─── Exact level thresholds ──────────────────────────────────────────────────


class TestLevelThresholdBoundaries:
    def test_score_20_is_safe(self, noon):
        ping = queued_ping(noon, 30, battery_percent=5)  # queued 10 + battery 10
        score, level, anomalies = _check(ping, [])
        assert score == 20
        assert level == "SAFE"
        assert len(anomalies) == 2

    def test_exactly_30_is_elevated(self, noon):
        """10 (queued) + 10 (battery) + 10 (running at 20 km/h) = 30 -> the
        ELEVATED bar, not HIGH."""
        ping = queued_ping(noon, 30, battery_percent=4, speed=5.56)  # 20 km/h -> running
        score, level, anomalies = _check(ping, [])
        assert score == 30
        assert level == "ELEVATED"
        assert not any("vehicle" in a.lower() for a in anomalies)

    def test_exactly_60_is_high(self, noon):
        """35 (SIM) + 15 (airplane) + 10 (battery) = 60 -> the HIGH bar."""
        ping = make_ping(sim_changed=True, is_airplane_mode=True, battery_percent=5)
        score, level, _ = _check(ping, [])
        assert score == 60
        assert level == "HIGH"

    def test_exactly_80_with_confirmation_is_critical(self, noon):
        """35 + 15 + 10 + 10 (queued) + 10 (running) = 80 raw, backed by two
        recent high pings -> the gate passes and CRITICAL fires at the theft
        threshold exactly."""
        ping = queued_ping(noon, 30, sim_changed=True, is_airplane_mode=True, battery_percent=5, speed=5.56)
        score, level, _ = _check(ping, history(79, 79))
        assert score == settings.THEFT_SCORE_THRESHOLD == 80
        assert level == "CRITICAL"


# ─── Velocity bands (vehicle above 45 km/h) ─────────────────────────────────


class TestVelocityBands:
    def test_below_running_threshold_is_clean(self, noon):
        """14.4 km/h (4 m/s) — a brisk run — must not score at all."""
        score, level, anomalies = _check(make_ping(speed=4.0), [])
        assert score == 0
        assert level == "SAFE"
        assert len(anomalies) == 0

    def test_just_over_running_threshold_scores_running(self, noon):
        """16.2 km/h (4.5 m/s) is the bottom of the running band."""
        score, level, anomalies = _check(make_ping(speed=4.5), [])
        assert score == 10
        assert any("running" in a.lower() for a in anomalies)

    def test_exactly_45_kmh_is_still_running(self, noon):
        """45.0 km/h exactly (12.5 m/s) stays in the running band (the vehicle
        bar is strictly >45)."""
        score, level, anomalies = _check(make_ping(speed=12.5), [])
        assert score == 10
        assert any("running" in a.lower() for a in anomalies)

    def test_just_over_45_kmh_is_vehicle(self, noon):
        """46.8 km/h (13 m/s) — an okada/moped getaway — is vehicle +25."""
        score, level, anomalies = _check(make_ping(speed=13.0), [])
        assert score == 25
        assert any("vehicle" in a.lower() for a in anomalies)

    def test_100_kmh_is_vehicle_not_running(self, noon):
        """The bug this band change fixes: a phone fleeing at 100 km/h (27.8
        m/s) is motorized flight and must read 'vehicle', never 'running'."""
        score, level, anomalies = _check(make_ping(speed=27.8), [])
        assert score == 25
        assert any("vehicle" in a.lower() for a in anomalies)
        assert not any("running" in a.lower() for a in anomalies)

    def test_highway_speed_is_vehicle(self, noon):
        score, level, anomalies = _check(make_ping(speed=40.0), [])  # 144 km/h
        assert score == 25
        assert any("vehicle" in a.lower() for a in anomalies)


# ─── Signal boundaries ───────────────────────────────────────────────────────


class TestSignalBoundaries:
    def test_battery_5_percent_scores(self, noon):
        score, level, anomalies = _check(make_ping(battery_percent=5), [])
        assert score == 10
        assert any("battery" in a.lower() for a in anomalies)

    def test_battery_6_percent_is_clean(self, noon):
        score, level, anomalies = _check(make_ping(battery_percent=6), [])
        assert score == 0
        assert len(anomalies) == 0

    def test_queued_9_minutes_is_clean(self, noon):
        score, level, anomalies = _check(queued_ping(noon, 9), [])
        assert score == 0
        assert len(anomalies) == 0

    def test_queued_11_minutes_scores(self, noon):
        score, level, anomalies = _check(queued_ping(noon, 11), [])
        assert score == 10
        assert any("queued" in a.lower() for a in anomalies)


# ─── Unusual-time window (2am-5am UTC) ──────────────────────────────────────


class TestUnusualTimeWindow:
    # 3.5 m/s = 12.6 km/h: fast enough to count as "moving" for the unusual-
    # time rule (>3.0) but below the 15 km/h running band, so the ONLY signal
    # that can fire is unusual_time itself — clean isolation of the window.
    _moving = dict(speed=3.5)

    def test_0159_utc_not_suspicious(self, monkeypatch):
        _freeze_clock(monkeypatch, "2026-08-15T01:59:00+00:00")
        score, level, anomalies = _check(make_ping(**self._moving), [])
        assert score == 0
        assert len(anomalies) == 0

    def test_0200_utc_suspicious(self, monkeypatch):
        _freeze_clock(monkeypatch, "2026-08-15T02:00:00+00:00")
        score, level, anomalies = _check(make_ping(**self._moving), [])
        assert score == 10
        assert any("unusual" in a.lower() for a in anomalies)

    def test_0559_utc_suspicious(self, monkeypatch):
        _freeze_clock(monkeypatch, "2026-08-15T05:59:00+00:00")
        score, level, anomalies = _check(make_ping(**self._moving), [])
        assert score == 10
        assert any("unusual" in a.lower() for a in anomalies)

    def test_0600_utc_not_suspicious(self, monkeypatch):
        _freeze_clock(monkeypatch, "2026-08-15T06:00:00+00:00")
        score, level, anomalies = _check(make_ping(**self._moving), [])
        assert score == 0
        assert len(anomalies) == 0

    def test_idle_device_at_3am_is_normal(self, monkeypatch):
        """A parked phone at 3am with no other signal must NOT be flagged —
        the guard exists so night-time inactivity is not suspicious."""
        _freeze_clock(monkeypatch, "2026-08-15T03:00:00+00:00")
        score, level, anomalies = _check(make_ping(speed=0.5), [])
        assert score == 0
        assert len(anomalies) == 0

    def test_idle_device_with_anomaly_at_3am_gets_unusual_time(self, monkeypatch):
        """Idle + an existing anomaly at 3am DOES stack unusual_time."""
        _freeze_clock(monkeypatch, "2026-08-15T03:00:00+00:00")
        score, level, anomalies = _check(make_ping(speed=0.5, battery_percent=3), [])
        assert score == 20  # battery 10 + unusual 10
        assert any("unusual" in a.lower() for a in anomalies)


# ─── False-positive confirmation gate & decay ───────────────────────────────


class TestConfirmationGate:
    def test_first_ping_with_no_history_is_ungated(self, noon):
        """Documented contract: the gate compares against history rows, so a
        device's very first ping has nothing to confirm against and a big
        signal burst reaches CRITICAL immediately. Whether first-pings should
        require a baseline is a product decision — this pins today's behavior
        so a future change to it is deliberate."""
        score, level, _ = _check(theft_ping(), [])
        assert score >= settings.THEFT_SCORE_THRESHOLD
        assert level == "CRITICAL"

    def test_single_spike_over_clean_history_stays_capped(self, noon):
        score, level, _ = _check(theft_ping(), history(0, 0, 0))
        assert level == "HIGH"
        assert score == CAP_AFTER_CONFIRMATION
        assert score < settings.THEFT_SCORE_THRESHOLD

    def test_one_recent_high_ping_is_not_enough(self, noon):
        """Only 1 of the last 3 pings was high -> the streak is too thin."""
        score, level, _ = _check(theft_ping(), history(79, 0, 0))
        assert level == "HIGH"
        assert score == CAP_AFTER_CONFIRMATION

    def test_two_recent_high_pings_unlock(self, noon):
        """2 of the last 3 high (the confirmation_count-1 requirement) plus
        the current ping -> CRITICAL at full score."""
        score, level, _ = _check(theft_ping(), history(79, 79, 0))
        assert level == "CRITICAL"
        assert score >= settings.THEFT_SCORE_THRESHOLD

    def test_old_high_scores_decay_out_of_window(self, noon):
        """A device that HAD a sustained high burst five pings ago but has
        been clean since must NOT confirm a fresh spike — recent scores are
        all 0, so the gate holds. This is the 'score decay' guarantee: only
        RECENT history can unlock theft mode."""
        old_burst = history(0, 0, 0, 79, 79, 79, 79, 79)  # newest first
        score, level, _ = _check(theft_ping(), old_burst)
        assert level == "HIGH"
        assert score == CAP_AFTER_CONFIRMATION

    def test_gate_only_demotes_never_promotes(self, noon):
        """A HIGH-level ping (60, below threshold) over confirming history
        must stay HIGH — the gate caps CRITICAL scores, it never escalates
        sub-threshold ones."""
        ping = make_ping(sim_changed=True, is_airplane_mode=True, battery_percent=5)  # 35+15+10=60
        score, level, _ = _check(ping, history(79, 79, 79))
        assert score == 60
        assert level == "HIGH"

    def test_short_history_still_gates(self, noon):
        """Even one prior SAFE ping engages the gate (1 high of 1 < 2)."""
        score, level, _ = _check(theft_ping(), history(0))
        assert level == "HIGH"
        assert score == CAP_AFTER_CONFIRMATION
