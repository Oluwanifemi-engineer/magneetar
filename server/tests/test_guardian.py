"""
Magneetar Guardian Network Tests
Community recovery: guardian opt-in, recovery request launch/close,
blurred nearby listing for guardians, and rate-limited sightings.
"""

import os
import secrets
import sqlite3
import tempfile

import pytest
from fastapi.testclient import TestClient

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "guardian-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "guardian-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY
TEST_USER_PASSWORD = "StrongPass1"


def register_user(email: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_USER_PASSWORD,
            "display_name": "Test User",
        },
    )
    assert resp.status_code == 200, f"register_user failed: {resp.text}"
    return resp.json()


def user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def api_key_headers() -> dict:
    return {"x-api-key": TEST_API_KEY}


def register_device(device_id: str, user_token: str = None) -> dict:
    headers = api_key_headers()
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"fp-{device_id}",
            "model": "Guardian Test Phone",
            "os_version": "Android 14",
            "app_version": "1.1.0",
            "device_key": f"devicekey-{device_id}",
        },
        headers=headers,
    )
    assert resp.status_code == 200, f"register_device failed: {resp.text}"
    return resp.json()


def set_device_stolen(device_id: str):
    """Flip a device into stolen mode directly (as Sentinel would)."""
    with database.get_db_context() as conn:
        conn.execute(
            "UPDATE devices SET is_stolen=1, operating_mode='stolen', sentinel_score=90 WHERE id=?",
            (device_id,),
        )
        conn.execute(
            "INSERT INTO evidence_cases (id, device_id, theft_time, status) VALUES (?, ?, datetime('now'), 'active')",
            (f"case-{device_id}", device_id),
        )
        conn.execute(
            "INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES (?, ?, ?, datetime('now'))",
            (device_id, 9.0820, 8.6753),
        )
        conn.commit()


@pytest.fixture(autouse=True)
def reset_db_state():
    """Reset the shared test DB between tests."""
    with database.get_db_context() as conn:
        for table in (
            "recovery_sightings",
            "recovery_requests",
            "guardian_profiles",
            "locations",
            "media",
            "commands",
            "evidence_cases",
            "alerts",
            "heartbeats",
            "geofences",
            "fcm_tokens",
            "devices",
            "users",
            "audit_log",
            "rate_limits",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()

    import websocket_manager

    websocket_manager._device_owners.clear()
    websocket_manager._connection_owners.clear()
    yield


def teardown_module(module):
    try:
        os.remove(test_db_path)
    except OSError:
        pass


# ─── Schema migration (existing DBs must gain new tables) ────────────────────


class TestSchemaMigration:
    def test_ensure_initialized_migrates_existing_db(self, monkeypatch):
        """An existing database (created before the Guardian tables) must be
        migrated forward by ensure_initialized() on server startup."""
        fd, old_db_path = tempfile.mkstemp(suffix="-old.db")
        os.close(fd)

        # Simulate a DB created by an older release: devices table only.
        conn = sqlite3.connect(old_db_path)
        conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        # Point the database module at the old file and run the startup check.
        monkeypatch.setattr(database, "DB_PATH", old_db_path)
        assert database.ensure_initialized() is True

        conn = sqlite3.connect(old_db_path)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()

        assert "guardian_profiles" in tables
        assert "recovery_requests" in tables
        assert "recovery_sightings" in tables
        assert "devices" in tables
        os.remove(old_db_path)

    def test_ensure_initialized_noop_when_current(self, monkeypatch):
        """A fully-migrated DB should not be rewritten on every startup."""
        fd, fresh_db_path = tempfile.mkstemp(suffix="-fresh.db")
        os.close(fd)
        monkeypatch.setattr(database, "DB_PATH", fresh_db_path)

        assert database.ensure_initialized() is True  # created it
        assert database.ensure_initialized() is False  # no-op on second call
        os.remove(fresh_db_path)


# ─── Guardian opt-in ─────────────────────────────────────────────────────────


class TestGuardianOptIn:
    def test_opt_in_creates_profile(self):
        user = register_user("guardian@example.com")
        resp = client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 30, "handle": "NightWatch"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["opted_in"] is True
        assert resp.json()["handle"] == "NightWatch"
        assert resp.json()["radius_km"] == 30

    def test_opt_out(self):
        user = register_user("optout@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 10, "handle": "Ghost"},
            headers=user_headers(user["token"]),
        )
        resp = client.post(
            "/api/guardian/opt-in",
            json={"opted_in": False},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["opted_in"] is False

    def test_profile_defaults_opted_out(self):
        user = register_user("fresh@example.com")
        resp = client.get("/api/guardian/profile", headers=user_headers(user["token"]))
        assert resp.status_code == 200
        assert resp.json()["opted_in"] is False

    def test_opt_in_requires_real_user(self):
        resp = client.post("/api/guardian/opt-in", json={"opted_in": True}, headers=api_key_headers())
        assert resp.status_code == 401

    def test_profile_requires_auth(self):
        resp = client.get("/api/guardian/profile")
        assert resp.status_code == 401


# ─── Recovery request launch / list / close ──────────────────────────────────


class TestRecoveryRequests:
    def _setup_stolen_device(self, email="owner@example.com"):
        user = register_user(email)
        device = register_device("stolen-phone", user_token=user["token"])
        set_device_stolen("stolen-phone")
        return user, device

    def test_launch_requires_stolen_device(self):
        user = register_user("normal@example.com")
        register_device("normal-phone", user_token=user["token"])
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "normal-phone", "description": "Not stolen"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 400

    def test_launch_success(self):
        user, _ = self._setup_stolen_device()
        resp = client.post(
            "/api/recovery/requests",
            json={
                "device_id": "stolen-phone",
                "description": "Grey Pixel 8, lost near the mall",
            },
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "active"
        assert body["device_id"] == "stolen-phone"
        assert body["id"].startswith("rec-")
        assert body["sighting_count"] == 0

    def test_launch_non_owner_403(self):
        owner = register_user("owner-a@example.com")
        intruder = register_user("owner-b@example.com")
        register_device("stolen-phone", user_token=owner["token"])
        set_device_stolen("stolen-phone")
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(intruder["token"]),
        )
        assert resp.status_code == 403

    def test_launch_duplicate_409(self):
        user, _ = self._setup_stolen_device()
        client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "First"},
            headers=user_headers(user["token"]),
        )
        resp = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Second"},
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 409

    def test_list_only_own_requests(self):
        user_a, _ = self._setup_stolen_device(email="owner-a@example.com")
        user_b = register_user("owner-b@example.com")
        client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(user_a["token"]),
        )
        resp_b = client.get("/api/recovery/requests", headers=user_headers(user_b["token"]))
        assert resp_b.status_code == 200
        assert resp_b.json()["requests"] == []

        resp_a = client.get("/api/recovery/requests", headers=user_headers(user_a["token"]))
        assert len(resp_a.json()["requests"]) == 1

    def test_close_marks_device_recovered(self):
        user, _ = self._setup_stolen_device()
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Help find it"},
            headers=user_headers(user["token"]),
        ).json()

        resp = client.post(
            f"/api/recovery/requests/{req['id']}/close",
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert "recovered" in resp.json()["message"]

        with database.get_db_context() as conn:
            device = conn.execute("SELECT is_stolen, operating_mode FROM devices WHERE id='stolen-phone'").fetchone()
            assert device["is_stolen"] == 0
            assert device["operating_mode"] == "normal"

        # Closing a closed request → 400
        resp = client.post(
            f"/api/recovery/requests/{req['id']}/close",
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 400

    def test_close_non_owner_403(self):
        user, _ = self._setup_stolen_device()
        other = register_user("other@example.com")
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone"},
            headers=user_headers(user["token"]),
        ).json()
        resp = client.post(
            f"/api/recovery/requests/{req['id']}/close",
            headers=user_headers(other["token"]),
        )
        assert resp.status_code == 403

    def test_close_unknown_404(self):
        user = register_user("close404@example.com")
        resp = client.post(
            "/api/recovery/requests/rec-nonexistent/close",
            headers=user_headers(user["token"]),
        )
        assert resp.status_code == 404


# ─── Guardian nearby view & sightings ────────────────────────────────────────


class TestNearbyAndSightings:
    def _setup(self):
        """Owner with a stolen device + an active request; a guardian nearby."""
        owner = register_user("owner@example.com")
        register_device("stolen-phone", user_token=owner["token"])
        set_device_stolen("stolen-phone")
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": "stolen-phone", "description": "Find this Pixel"},
            headers=user_headers(owner["token"]),
        ).json()

        guardian = register_user("guardian@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "EagleEye"},
            headers=user_headers(guardian["token"]),
        )
        return owner, guardian, req

    def test_nearby_requires_opt_in(self):
        owner, _g, req = self._setup()
        stranger = register_user("stranger@example.com")
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(stranger["token"]),
        )
        assert resp.status_code == 403

    def test_nearby_shows_blurred_request(self):
        _o, guardian, _req = self._setup()
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200
        requests = resp.json()["requests"]
        assert len(requests) == 1
        r = requests[0]
        assert r["device_model"] == "Guardian Test Phone"
        assert r["distance_km"] <= 1.0
        # Location is blurred — must not be the exact device coordinate
        assert r["blurred_lat"] != 9.0820 or r["blurred_lng"] != 8.6753
        assert isinstance(r["blurred_lat"], float)

    def test_nearby_filters_by_distance(self):
        _o, guardian, _req = self._setup()
        # Far away (device at 9.08, 8.67 — asking from London)
        resp = client.get(
            "/api/recovery/nearby?lat=51.5074&lng=-0.1278&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200
        assert resp.json()["requests"] == []

    def test_report_sighting_requires_opt_in(self):
        owner, _g, req = self._setup()
        stranger = register_user("sight-stranger@example.com")
        resp = client.post(
            "/api/recovery/sightings",
            json={
                "request_id": req["id"],
                "lat": 9.083,
                "lng": 8.676,
                "note": "Saw it!",
            },
            headers=user_headers(stranger["token"]),
        )
        assert resp.status_code == 403

    def test_report_sighting_success_and_owner_sees_it(self):
        owner, guardian, req = self._setup()
        resp = client.post(
            "/api/recovery/sightings",
            json={
                "request_id": req["id"],
                "lat": 9.083,
                "lng": 8.676,
                "note": "Saw it near the bus stop",
            },
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["guardian_handle"] == "EagleEye"

        # Owner's request detail now includes the sighting
        resp = client.get("/api/recovery/requests", headers=user_headers(owner["token"]))
        requests = resp.json()["requests"]
        assert len(requests) == 1
        assert requests[0]["sighting_count"] == 1
        assert requests[0]["sightings"][0]["guardian_handle"] == "EagleEye"
        assert requests[0]["sightings"][0]["note"] == "Saw it near the bus stop"

    def test_sighting_persists_relay_metadata(self):
        """Offline Device Network (§3.3): a relayed sighting carries
        hop_count + relayed; a plain Phase-1 sighting defaults to 0/false."""
        owner, guardian, req = self._setup()
        headers = user_headers(guardian["token"])

        # Direct sighting (Phase-1 client, no metadata) → defaults
        resp = client.post(
            "/api/recovery/sightings",
            json={"request_id": req["id"], "lat": 9.08, "lng": 8.67},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        # Relayed sighting through 2 guardian hops
        resp = client.post(
            "/api/recovery/sightings",
            json={
                "request_id": req["id"],
                "lat": 9.09,
                "lng": 8.68,
                "hop_count": 2,
                "relayed": True,
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

        resp = client.get("/api/recovery/requests", headers=user_headers(owner["token"]))
        sightings = resp.json()["requests"][0]["sightings"]
        direct = next(s for s in sightings if s["hop_count"] == 0)
        relayed = next(s for s in sightings if s["hop_count"] == 2)
        assert direct["relayed"] is False
        assert relayed["relayed"] is True
        assert relayed["guardian_handle"] == "EagleEye"

    def test_sighting_on_closed_request_400(self):
        owner, guardian, req = self._setup()
        client.post(
            f"/api/recovery/requests/{req['id']}/close",
            headers=user_headers(owner["token"]),
        )
        resp = client.post(
            "/api/recovery/sightings",
            json={
                "request_id": req["id"],
                "lat": 9.083,
                "lng": 8.676,
                "note": "Too late",
            },
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 400

    def test_sighting_rate_limited(self, monkeypatch):
        _o, guardian, req = self._setup()
        # Shrink the limit to make the test fast and deterministic.
        #
        # SIGHTING_RATE_MAX is a module global of the routes.guardian module
        # the app ACTUALLY holds. test_e2e / test_sim_change evict
        # routes.guardian from sys.modules at collection and re-import it with
        # THEIR env, so a fresh `import routes.guardian` here can resolve to a
        # DIFFERENT module object than the one the app's handlers call — and a
        # monkeypatch there would be invisible to the app (the full-suite CI
        # order hazard). The app wraps each router in _IncludedRouter, so walk
        # the original routers to the live POST sighting handler and patch its
        # globals — the limit the app actually enforces is the one we shrink.
        sighting_globals = None
        for route in client.app.routes:
            # Flat APIRoute shape (plain include_router)…
            if getattr(route, "path", None) == "/api/recovery/sightings" and "POST" in (
                getattr(route, "methods", None) or ()
            ):
                sighting_globals = route.endpoint.__globals__
                break
            # …or the app's current _IncludedRouter wrapping.
            original_router = getattr(route, "original_router", None)
            if original_router is None:
                continue
            for sub in original_router.routes:
                if getattr(sub, "path", None) == "/api/recovery/sightings" and "POST" in (
                    getattr(sub, "methods", None) or ()
                ):
                    sighting_globals = sub.endpoint.__globals__
                    break
            if sighting_globals is not None:
                break
        assert sighting_globals is not None, "POST /api/recovery/sightings route not registered"
        monkeypatch.setitem(sighting_globals, "SIGHTING_RATE_MAX", 3)

        for i in range(3):
            resp = client.post(
                "/api/recovery/sightings",
                json={
                    "request_id": req["id"],
                    "lat": 9.083,
                    "lng": 8.676,
                    "note": f"Sighting {i}",
                },
                headers=user_headers(guardian["token"]),
            )
            assert resp.status_code == 200

        resp = client.post(
            "/api/recovery/sightings",
            json={
                "request_id": req["id"],
                "lat": 9.083,
                "lng": 8.676,
                "note": "Fourth",
            },
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 429

    def test_guardian_cannot_see_owner_identity(self):
        _o, guardian, _req = self._setup()
        resp = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(guardian["token"]),
        )
        body = resp.json()
        payload = str(body)
        assert "owner" not in payload.lower() or "owner_id" not in payload
        assert "owner_id" not in payload


# ─── Find Network — BLE beacon protocol (COMPETITOR_AUDIT P1 #6, Phase 1) ────
# The stolen device broadcasts an opaque per-request beacon_token over BLE;
# guardians in range report the token back (never the request id) and the
# server resolves token -> request. Tests lock the whole lifecycle:
# launch mints a token, the device can fetch ONLY its own active token, the
# token never leaks through owner/guardian request views, and a sighting
# reported by beacon_token lands on the right request.


class TestFindNetworkBeacon:
    def _launch(self, device_id="stolen-phone", email="beacon-owner@example.com"):
        """Owner + stolen device + active recovery request; returns (owner, req)."""
        user = register_user(email)
        register_device(device_id, user_token=user["token"])
        set_device_stolen(device_id)
        req = client.post(
            "/api/recovery/requests",
            json={"device_id": device_id, "description": "Find this Pixel"},
            headers=user_headers(user["token"]),
        ).json()
        return user, req

    def _device_headers(self, device_id="stolen-phone"):
        # Device auth via the device JWT minted at registration (auth method
        # 1 — pure token decode, no DB lookup). The x-device-key path does a
        # per-request DB lookup via a function-local import that resolves a
        # DIFFERENT database module after test_e2e's sys.modules eviction
        # (the full-suite order hazard this file documents elsewhere), so the
        # suite convention for device-authenticated tests is the JWT.
        resp = client.post(
            "/api/device/register",
            json={
                "device_id": device_id,
                "fingerprint": f"fp-{device_id}",
                "model": "Guardian Test Phone",
                "os_version": "Android 14",
                "app_version": "1.1.0",
                "device_key": f"devicekey-{device_id}",
            },
            headers=api_key_headers(),
        )
        assert resp.status_code == 200, f"device re-register failed: {resp.text}"
        return {"Authorization": f"Bearer {resp.json()['token']}"}

    def test_launch_mints_beacon_token(self):
        _user, req = self._launch()
        # The launch response itself must NOT carry the token — only the
        # device endpoint hands it out, and only to the device.
        assert "beacon_token" not in req
        with database.get_db_context() as conn:
            row = conn.execute("SELECT beacon_token FROM recovery_requests WHERE id=?", (req["id"],)).fetchone()
        assert row and row["beacon_token"]
        assert len(row["beacon_token"]) >= 16  # token_hex(8) -> 16 chars

    def test_device_fetches_own_beacon_token(self):
        _user, _req = self._launch()
        resp = client.get("/api/device/recovery/beacon", headers=self._device_headers())
        assert resp.status_code == 200, resp.text
        token = resp.json()["beacon_token"]
        assert token, "device must get its active beacon token"
        assert len(token) == 16

    def test_device_beacon_null_when_no_active_request(self):
        user = register_user("beacon-none@example.com")
        register_device("stolen-phone", user_token=user["token"])
        # Device exists but no recovery request.
        resp = client.get("/api/device/recovery/beacon", headers=self._device_headers())
        assert resp.status_code == 200
        assert resp.json()["beacon_token"] is None

    def test_device_beacon_null_after_request_closed(self):
        user, req = self._launch()
        client.post(f"/api/recovery/requests/{req['id']}/close", headers=user_headers(user["token"]))
        resp = client.get("/api/device/recovery/beacon", headers=self._device_headers())
        assert resp.status_code == 200
        assert resp.json()["beacon_token"] is None

    def test_device_beacon_requires_device_auth(self):
        self._launch()
        # The shared API key is NOT a specific device — it must be rejected.
        resp = client.get("/api/device/recovery/beacon", headers=api_key_headers())
        assert resp.status_code == 401

    def test_other_device_cannot_fetch_this_beacon(self):
        self._launch()
        # A DIFFERENT device (registered, but with no request of its own)
        # must get null — never someone else's token.
        register_device("other-phone")
        resp = client.get("/api/device/recovery/beacon", headers=self._device_headers("other-phone"))
        assert resp.status_code == 200
        assert resp.json()["beacon_token"] is None

    def test_shared_api_key_cannot_mint_device_beacon(self):
        """The shared x-api-key identity ('api_key_user') is device-scope only
        but is NOT a specific device — the beacon endpoint must reject it so
        anyone holding the public APK key can't probe other devices' tokens."""
        self._launch()
        resp = client.get("/api/device/recovery/beacon", headers={"x-api-key": TEST_API_KEY})
        assert resp.status_code == 401

    def test_token_never_leaks_to_owner_or_guardian_views(self):
        owner, req = self._launch()
        guardian = register_user("beacon-guardian@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "Scanner"},
            headers=user_headers(guardian["token"]),
        )

        # Owner's request list must not contain the token.
        owner_list = client.get("/api/recovery/requests", headers=user_headers(owner["token"])).json()
        assert "beacon_token" not in str(owner_list)

        # Guardian's nearby view must not contain it either.
        nearby = client.get(
            "/api/recovery/nearby?lat=9.0820&lng=8.6753&radius_km=50",
            headers=user_headers(guardian["token"]),
        ).json()
        assert "beacon_token" not in str(nearby)

    def test_sighting_by_beacon_token_resolves_to_request(self):
        owner, req = self._launch()
        guardian = register_user("beacon-g@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "Scanner"},
            headers=user_headers(guardian["token"]),
        )

        # Guardian got the token off the air — they report it, not the id.
        with database.get_db_context() as conn:
            token = conn.execute("SELECT beacon_token FROM recovery_requests WHERE id=?", (req["id"],)).fetchone()[
                "beacon_token"
            ]

        resp = client.post(
            "/api/recovery/sightings",
            json={"beacon_token": token, "lat": 9.083, "lng": 8.676, "note": "Picked up the beacon"},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["request_id"] == req["id"]

        # The sighting lands on the owner's request.
        owner_list = client.get("/api/recovery/requests", headers=user_headers(owner["token"])).json()
        assert owner_list["requests"][0]["sighting_count"] == 1
        assert owner_list["requests"][0]["sightings"][0]["note"] == "Picked up the beacon"

    def test_sighting_unknown_beacon_token_404(self):
        self._launch()
        guardian = register_user("beacon-404@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "Noob"},
            headers=user_headers(guardian["token"]),
        )
        resp = client.post(
            "/api/recovery/sightings",
            json={"beacon_token": "deadbeefdeadbeef", "lat": 9.0, "lng": 8.6},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 404

    def test_sighting_requires_request_id_or_beacon_token(self):
        self._launch()
        guardian = register_user("beacon-422@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "Oblivious"},
            headers=user_headers(guardian["token"]),
        )
        resp = client.post(
            "/api/recovery/sightings",
            json={"lat": 9.0, "lng": 8.6},
            headers=user_headers(guardian["token"]),
        )
        assert resp.status_code == 422

    def test_sighting_by_token_on_closed_request_400(self):
        owner, req = self._launch()
        guardian = register_user("beacon-late@example.com")
        client.post(
            "/api/guardian/opt-in",
            json={"opted_in": True, "radius_km": 50, "handle": "Late"},
            headers=user_headers(guardian["token"]),
        )
        client.post(f"/api/recovery/requests/{req['id']}/close", headers=user_headers(owner["token"]))
        with database.get_db_context() as conn:
            token = conn.execute("SELECT beacon_token FROM recovery_requests WHERE id=?", (req["id"],)).fetchone()[
                "beacon_token"
            ]
        resp = client.post(
            "/api/recovery/sightings",
            json={"beacon_token": token, "lat": 9.0, "lng": 8.6},
            headers=user_headers(guardian["token"]),
        )
        # Status is no longer active -> the request_id flow 400s; the beacon
        # flow must behave identically (a stale beacon is worthless).
        assert resp.status_code == 400

    def test_migrated_db_gains_beacon_token_column(self, monkeypatch):
        """An existing DB created before beacon_token must gain the column via
        ensure_initialized() — the same migration the server runs at startup
        (the device_shares no-op bug class)."""
        fd, old_db_path = tempfile.mkstemp(suffix="-beacon-old.db")
        os.close(fd)
        conn = sqlite3.connect(old_db_path)
        # A realistic pre-beacon recovery_requests table — every column that
        # shipped before v1.6, minus beacon_token. (init_db() skips the
        # CREATE TABLE IF NOT EXISTS for an existing table, then the guarded
        # ALTER adds the new column; a minimal table would break the index
        # creation instead, which is NOT how a real old DB looks.)
        conn.execute(
            """CREATE TABLE recovery_requests (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                description TEXT,
                last_lat REAL,
                last_lng REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                closed_reason TEXT
            )"""
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(database, "DB_PATH", old_db_path)
        assert database.ensure_initialized() is True

        conn = sqlite3.connect(old_db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(recovery_requests)")}
        conn.close()
        assert "beacon_token" in cols
        os.remove(old_db_path)
