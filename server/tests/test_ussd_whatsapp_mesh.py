"""
Tests for USSD, WhatsApp bot, and BLE mesh routes.

Both external command channels (USSD callback, WhatsApp webhook) are only
reachable with credentials now, and both bind a command to the device's OWNER
rather than to whoever knows its phone number — so these tests authenticate,
and cover the rejections as first-class behaviour.
"""

import hashlib
import hmac
import json
import secrets
import sys

import database
import pytest
from config import settings
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

USSD_SECRET = "test-ussd-shared-secret"
WHATSAPP_APP_SECRET = "test-whatsapp-app-secret"
WHATSAPP_VERIFY_TOKEN = "test-whatsapp-verify-token"


@pytest.fixture
def ussd_gateway(monkeypatch):
    """Configure the USSD gateway secret for the duration of a test."""
    monkeypatch.setattr(settings, "USSD_WEBHOOK_SECRET", USSD_SECRET)
    return USSD_SECRET


@pytest.fixture
def whatsapp_app(monkeypatch):
    """Configure the Meta app secret + verify token for a test."""
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", WHATSAPP_APP_SECRET)
    monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", WHATSAPP_VERIFY_TOKEN)
    return WHATSAPP_APP_SECRET


def _dial(session_id: str, phone: str, text: str, secret: str = USSD_SECRET):
    return client.post(
        "/ussd/callback",
        data={
            "sessionId": session_id,
            "phoneNumber": phone,
            "text": text,
            "secret": secret,
        },
    )


def _signed_whatsapp_post(payload: dict, secret: str = WHATSAPP_APP_SECRET, signature: str = None):
    raw = json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Clear rate limits before each test.

    The WhatsApp webhook rate-limits per SENDER phone and the registration
    endpoint per IP; under the full suite other files' requests to those
    endpoints land in whatever DB the CURRENT database module points at, so a
    sender/IP reused here can arrive already rate-limited (429s that only
    appear in full-suite runs).

    Resolve the live module through the REGISTERED route's globals (the
    documented test_e2e eviction hazard): after e2e re-imports routes.*, the
    app's router table still calls functions whose __globals__ reference the
    database module generation the request path actually uses — which can
    differ from sys.modules["database"] once eviction has run. Clearing that
    generation's DB is the only clear guaranteed to reach the live bucket.
    """

    def _registered_endpoint(path: str, method: str):
        for r in app.routes:
            candidates = getattr(r, "_effective_candidates", None)
            if candidates:
                for c in candidates:
                    rt = getattr(c, "original_route", None)
                    if rt is not None and getattr(rt, "path", "") == path and method in getattr(rt, "methods", set()):
                        return rt.endpoint
            elif getattr(r, "path", "") == path and method in getattr(r, "methods", set()):
                return r.endpoint
        return None

    # The register path uses `from database import check_rate_limit, ...`
    # (user_auth.py) — NO `import database` — so its endpoint globals expose
    # only the functions, and after test_e2e's eviction the live generation
    # is reachable ONLY through those functions' defining namespace. The
    # webhook route's generation can differ again. Clear every generation
    # these two credential-gated endpoints can touch — AND rebuild the schema
    # first if a generation's DB file lost it (earlier modules' teardowns
    # delete their temp files; get_db_context then recreates an EMPTY file,
    # so the register call would hit "no such table: rate_limits").
    def _db_namespaces(endpoint):
        """Return the module-namespace dicts of every `database` generation
        reachable from `endpoint`'s globals (module object and/or the defining
        namespace of any function imported from it)."""
        out = []
        g = getattr(endpoint, "__globals__", {}) if endpoint else {}
        if g.get("database") is not None:
            out.append(g["database"].__dict__)
        for v in g.values():
            if callable(v) and getattr(v, "__module__", None) == "database":
                out.append(v.__globals__)
                break
        return out

    namespaces = []
    for path, method in (("/whatsapp/webhook", "POST"), ("/api/auth/register", "POST")):
        namespaces.extend(_db_namespaces(_registered_endpoint(path, method)))
    namespaces.append((sys.modules.get("database") or database).__dict__)

    seen = []
    for ns in namespaces:
        if any(ns is s for s in seen):
            continue
        seen.append(ns)
        try:
            ns["init_db"](ns.get("DB_PATH"))
            with ns["get_db_context"]() as conn:
                conn.execute("DELETE FROM rate_limits")
                conn.commit()
        except Exception:
            pass  # non-sqlite generation — nothing to clear there
    yield


def _incoming_message(sender: str, text: str) -> dict:
    return {"entry": [{"changes": [{"value": {"messages": [{"from": sender, "text": {"body": text}}]}}]}]}


# ─── USSD Tests ──────────────────────────────────────────────────────────────


class TestUSSD:
    """Test the USSD menu system."""

    def test_main_menu_returns_options(self, ussd_gateway):
        """USSD with empty text shows main menu."""
        resp = _dial("test-1", "2348012345678", "")
        assert resp.status_code == 200
        assert "Check device" in resp.text
        assert "Lock my phone" in resp.text

    def test_main_menu_option_1_shows_check(self, ussd_gateway):
        """Selecting 1 shows check device prompt."""
        resp = _dial("test-2", "2348012345678", "1")
        assert resp.status_code == 200
        assert "phone number" in resp.text.lower()

    def test_check_device_no_device_found(self, ussd_gateway):
        """Checking a phone with no device returns not found (two-step flow)."""
        resp1 = _dial("test-3", "2348012345678", "1")
        assert resp1.status_code == 200
        resp2 = _dial("test-3", "2348012345678", "1*08099999999")
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text

    def test_lock_no_device_found(self, ussd_gateway):
        """Locking a phone with no device returns not found (two-step flow)."""
        resp1 = _dial("test-4", "2348012345678", "2")
        assert resp1.status_code == 200
        resp2 = _dial("test-4", "2348012345678", "2*08099999999")
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text

    def test_siren_no_device_found(self, ussd_gateway):
        """Triggering siren with no device returns not found (two-step flow)."""
        resp1 = _dial("test-5", "2348012345678", "3")
        assert resp1.status_code == 200
        resp2 = _dial("test-5", "2348012345678", "3*08099999999")
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text

    def test_callback_requires_gateway_secret(self, monkeypatch):
        """Fails CLOSED when no secret is configured — the endpoint used to
        accept unauthenticated lock/siren commands."""
        monkeypatch.setattr(settings, "USSD_WEBHOOK_SECRET", "")
        resp = _dial("test-nosecret", "2348012345678", "2")
        assert resp.status_code == 503

    def test_callback_rejects_wrong_secret(self, ussd_gateway):
        resp = _dial("test-wrongsecret", "2348012345678", "2", secret="not-the-secret")
        assert resp.status_code == 403

    def test_callback_rejects_missing_secret(self, ussd_gateway):
        resp = client.post(
            "/ussd/callback",
            data={
                "sessionId": "test-missing",
                "phoneNumber": "2348012345678",
                "text": "2",
            },
        )
        assert resp.status_code == 403

    def test_header_secret_is_accepted(self, ussd_gateway):
        """Aggregators that send the secret as a header are also supported."""
        resp = client.post(
            "/ussd/callback",
            data={
                "sessionId": "test-header",
                "phoneNumber": "2348012345678",
                "text": "",
            },
            headers={"X-USSD-Secret": USSD_SECRET},
        )
        assert resp.status_code == 200
        assert "Welcome to Magneetar" in resp.text


class TestChannelOwnership:
    """A command channel must only act on devices owned by the caller/owner."""

    @staticmethod
    def _seed_device(device_id: str, sim_phone: str, owner_phone: str):
        from database import get_db_context

        with get_db_context() as db:
            db.execute("DELETE FROM devices WHERE id=?", (device_id,))
            db.execute("DELETE FROM devices WHERE sms_phone=?", (sim_phone,))
            db.execute(
                "INSERT INTO devices (id, alias, model, sms_phone, alert_phone)" " VALUES (?, ?, ?, ?, ?)",
                (
                    device_id,
                    "ownership-test",
                    "Ownership Test Device",
                    sim_phone,
                    owner_phone,
                ),
            )
            db.commit()

    def test_ussd_lookup_binds_to_owner_phone(self):
        from routes.ussd import _find_owned_device

        suffix = secrets.token_hex(5)
        device_id = f"mt-own-{suffix}"
        self._seed_device(
            device_id,
            sim_phone=f"+234803{suffix}",
            owner_phone=f"+234804{suffix}",
        )

        # The owner's number resolves the device...
        assert _find_owned_device(f"+234803{suffix}", f"+234804{suffix}")["id"] == device_id
        # ...anyone else does not, even knowing the device's own number.
        assert _find_owned_device(f"+234803{suffix}", "+2348039999999") is None
        # A device with no owner phone recorded cannot be commanded at all.
        unowned_suffix = secrets.token_hex(5)
        unowned = f"mt-unowned-{unowned_suffix}"
        self._seed_device(
            unowned,
            sim_phone=f"+234803{unowned_suffix}",
            owner_phone="",
        )
        assert _find_owned_device(f"+234803{unowned_suffix}", f"+234803{unowned_suffix}") is None

    def test_whatsapp_lookup_binds_to_owner_phone(self):
        from routes.whatsapp import _find_owned_device

        suffix = secrets.token_hex(5)
        device_id = f"mt-wa-{suffix}"
        self._seed_device(
            device_id,
            sim_phone=f"+234803{suffix}",
            owner_phone=f"+234804{suffix}",
        )

        assert _find_owned_device(f"+234803{suffix}", f"+234804{suffix}")["id"] == device_id
        assert _find_owned_device(f"+234803{suffix}", "+2348039999999") is None

    def test_only_valid_commands_can_be_queued(self):
        """Neither channel may queue a command outside the canonical set — the
        WhatsApp path used to INSERT an 'unlock' that exists nowhere else."""
        from routes import ussd, whatsapp

        assert ussd._issue_command("mt-does-not-exist", "unlock") is False
        assert whatsapp._issue_command("mt-does-not-exist", "unlock") is False
        assert whatsapp._issue_command("mt-does-not-exist", "phantom_on") is False


# ─── WhatsApp Tests ──────────────────────────────────────────────────────────


class TestWhatsApp:
    """Test the WhatsApp bot."""

    def test_webhook_verification_requires_correct_token(self, whatsapp_app):
        """Invalid verify token fails webhook verification."""
        resp = client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "challenge_string",
            },
        )
        assert resp.status_code == 403

    def test_webhook_verification_accepts_configured_token(self, whatsapp_app):
        resp = client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": WHATSAPP_VERIFY_TOKEN,
                "hub.challenge": "challenge_string",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "challenge_string"

    def test_webhook_verification_fails_closed_without_token(self, monkeypatch):
        monkeypatch.setattr(settings, "WHATSAPP_VERIFY_TOKEN", "")
        resp = client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "",
                "hub.challenge": "x",
            },
        )
        assert resp.status_code == 503

    def test_post_webhook_rejects_unsigned_payload(self, whatsapp_app):
        """The endpoint processed whatever was POSTed before — it must require
        Meta's signature."""
        resp = client.post("/whatsapp/webhook", json=_incoming_message("2348012345678", "HELP"))
        assert resp.status_code == 403

    def test_post_webhook_rejects_tampered_body(self, whatsapp_app):
        payload = _incoming_message("2348012345678", "SOS 08099999999")
        good = (
            "sha256="
            + hmac.new(
                WHATSAPP_APP_SECRET.encode(),
                json.dumps(payload).encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        tampered = json.dumps(_incoming_message("2348012345678", "SOS 08011111111")).encode()
        resp = client.post(
            "/whatsapp/webhook",
            content=tampered,
            headers={"X-Hub-Signature-256": good, "Content-Type": "application/json"},
        )
        assert resp.status_code == 403

    def test_post_webhook_fails_closed_without_app_secret(self, monkeypatch):
        monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "")
        resp = _signed_whatsapp_post(_incoming_message("2348012345678", "HELP"))
        assert resp.status_code == 503

    def test_post_webhook_accepts_valid_signature(self, whatsapp_app, monkeypatch):
        """A properly signed message is processed (no device → no command)."""
        called = {}
        sender = f"234801{secrets.token_hex(3)}"  # unique sender → own rate bucket

        async def _fake_send(to, text):
            called["to"] = to
            called["text"] = text

        # Patch the module dict that owns the REGISTERED endpoint function.
        # test_e2e evicts and re-imports routes.* mid-suite, so the app's
        # router table keeps the FIRST generation's function (whose __globals__
        # belongs to that generation's module) while sys.modules may hold a
        # newer one. Resolving via the registered endpoint's own globals is
        # the only target guaranteed to intercept the live call path (the
        # documented test_e2e eviction hazard). FastAPI 0.140 wraps included
        # routers, so routes may hide behind _effective_candidates.
        def _registered_endpoint(path: str, method: str):
            for r in app.routes:
                candidates = getattr(r, "_effective_candidates", None)
                if candidates:
                    for c in candidates:
                        rt = getattr(c, "original_route", None)
                        if (
                            rt is not None
                            and getattr(rt, "path", "") == path
                            and method in getattr(rt, "methods", set())
                        ):
                            return rt.endpoint
                elif getattr(r, "path", "") == path and method in getattr(r, "methods", set()):
                    return r.endpoint
            return None

        endpoint = _registered_endpoint("/whatsapp/webhook", "POST")
        assert endpoint is not None, "POST /whatsapp/webhook not found in the live route table"
        monkeypatch.setitem(endpoint.__globals__, "_send_whatsapp_message", _fake_send)
        resp = _signed_whatsapp_post(_incoming_message(sender, "HELP"))
        assert resp.status_code == 200
        assert called.get("to") == sender
        assert "LOCK" in called.get("text", "")

    def test_post_webhook_ignores_non_message_events(self, whatsapp_app):
        resp = _signed_whatsapp_post({"entry": [{"changes": [{"value": {"statuses": []}}]}]})
        assert resp.status_code == 200

    def test_help_command(self, whatsapp_app):
        """HELP lists the commands the device can actually execute."""
        from routes.whatsapp import _handle_command

        response = _handle_command("HELP", "2348012345678")
        assert "LOCK" in response
        assert "SOS" in response
        assert "STATUS" in response
        # UNLOCK is not a command the device implements — it must not be
        # advertised, and the bot must not accept it as one.
        assert "UNLOCK" not in response
        unlock_reply = _handle_command("UNLOCK 08099999999", "2348012345678")
        assert "didn't understand" in unlock_reply.lower() or "HELP" in unlock_reply

    def test_lock_without_number_returns_usage(self, whatsapp_app):
        """LOCK without a number returns usage."""
        from routes.whatsapp import _handle_command

        response = _handle_command("LOCK", "2348012345678")
        assert "Usage" in response

    def test_unknown_command_returns_help_hint(self, whatsapp_app):
        """Unknown command returns help hint."""
        from routes.whatsapp import _handle_command

        response = _handle_command("BLARGH", "2348012345678")
        assert "didn't understand" in response.lower() or "HELP" in response

    def test_status_no_device(self, whatsapp_app):
        """STATUS for unregistered number returns not found."""
        from routes.whatsapp import _handle_command

        response = _handle_command("STATUS 08099999999", "2348012345678")
        assert "No Magneetar device found" in response

    def test_lock_no_device(self, whatsapp_app):
        """LOCK for unregistered number returns not found."""
        from routes.whatsapp import _handle_command

        response = _handle_command("LOCK 08099999999", "2348012345678")
        assert "No Magneetar device found" in response

    def test_sos_no_device(self, whatsapp_app):
        """SOS for unregistered number returns not found."""
        from routes.whatsapp import _handle_command

        response = _handle_command("SOS 08099999999", "2348012345678")
        assert "No Magneetar device found" in response


# ─── BLE Mesh Tests ──────────────────────────────────────────────────────────


class TestMesh:
    """Test the BLE mesh endpoints."""

    def test_beacon_register_requires_auth(self):
        """Beacon registration requires device authentication."""
        resp = client.post(
            "/api/mesh/beacon/register",
            json={"device_id": "mt-test123", "beacon_token": "token123"},
        )
        assert resp.status_code in (401, 403, 422)

    def test_beacon_deactivate_requires_auth(self):
        """Beacon deactivation requires device authentication."""
        resp = client.post("/api/mesh/beacon/deactivate")
        assert resp.status_code in (401, 403, 422)

    def test_sighting_requires_auth(self):
        """Sighting report requires device authentication."""
        resp = client.post(
            "/api/mesh/sighting",
            json={
                "beacon_device_id": "mt-stolen",
                "beacon_token": "token",
                "lat": 6.5244,
                "lng": 3.3792,
            },
        )
        assert resp.status_code in (401, 403, 422)

    def test_sightings_query_requires_auth(self):
        """Sighting query requires authentication."""
        resp = client.get("/api/mesh/sightings/mt-test123")
        assert resp.status_code in (401, 403, 422)


class TestGuardianProfile:
    """The guardian opt-in contract the Android GuardianBeaconScanner calls
    (GET /api/guardian/profile) before each scan cycle. No opt-in flow ships
    yet, so every account must truthfully read opted_in=false and the scanner
    stays off."""

    def test_profile_requires_auth(self):
        """Unauthenticated calls are rejected."""
        resp = client.get("/api/guardian/profile")
        assert resp.status_code in (401, 403)

    def test_account_without_profile_is_opted_out(self):
        """A registered account with no guardian profile row must read
        opted_in=false — the scanner gate keeps volunteer scanning off."""
        email = f"guardian-{secrets.token_hex(4)}@example.com"
        resp = client.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": "StrongPass1",
                "display_name": "Guardian Tester",
            },
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["token"]

        profile = client.get("/api/guardian/profile", headers={"Authorization": f"Bearer {token}"})
        assert profile.status_code == 200, profile.text
        body = profile.json()
        assert body["opted_in"] is False
        assert body["handle"] is None
        assert body["radius_km"] is None
