"""
Tests for USSD, WhatsApp bot, and BLE mesh routes.
"""

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ─── USSD Tests ──────────────────────────────────────────────────────────────


class TestUSSD:
    """Test the USSD menu system."""

    def test_main_menu_returns_options(self):
        """USSD with empty text shows main menu."""
        resp = client.post(
            "/ussd/callback",
            data={"sessionId": "test-1", "phoneNumber": "2348012345678", "text": ""},
        )
        assert resp.status_code == 200
        assert "Check device" in resp.text
        assert "Lock my phone" in resp.text

    def test_main_menu_option_1_shows_check(self):
        """Selecting 1 shows check device prompt."""
        resp = client.post(
            "/ussd/callback",
            data={"sessionId": "test-2", "phoneNumber": "2348012345678", "text": "1"},
        )
        assert resp.status_code == 200
        assert "phone number" in resp.text.lower()

    def test_check_device_no_device_found(self):
        """Checking a phone with no device returns not found (two-step flow)."""
        # Step 1: Select option 1
        resp1 = client.post(
            "/ussd/callback",
            data={"sessionId": "test-3", "phoneNumber": "2348012345678", "text": "1"},
        )
        assert resp1.status_code == 200
        # Step 2: Enter phone number
        resp2 = client.post(
            "/ussd/callback",
            data={
                "sessionId": "test-3",
                "phoneNumber": "2348012345678",
                "text": "1*08099999999",
            },
        )
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text

    def test_lock_no_device_found(self):
        """Locking a phone with no device returns not found (two-step flow)."""
        # Step 1: Select option 2
        resp1 = client.post(
            "/ussd/callback",
            data={"sessionId": "test-4", "phoneNumber": "2348012345678", "text": "2"},
        )
        assert resp1.status_code == 200
        # Step 2: Enter phone number
        resp2 = client.post(
            "/ussd/callback",
            data={
                "sessionId": "test-4",
                "phoneNumber": "2348012345678",
                "text": "2*08099999999",
            },
        )
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text

    def test_siren_no_device_found(self):
        """Triggering siren with no device returns not found (two-step flow)."""
        # Step 1: Select option 3
        resp1 = client.post(
            "/ussd/callback",
            data={"sessionId": "test-5", "phoneNumber": "2348012345678", "text": "3"},
        )
        assert resp1.status_code == 200
        # Step 2: Enter phone number
        resp2 = client.post(
            "/ussd/callback",
            data={
                "sessionId": "test-5",
                "phoneNumber": "2348012345678",
                "text": "3*08099999999",
            },
        )
        assert resp2.status_code == 200
        assert "No Magneetar device found" in resp2.text


# ─── WhatsApp Tests ──────────────────────────────────────────────────────────


class TestWhatsApp:
    """Test the WhatsApp bot."""

    def test_webhook_verification_requires_correct_token(self):
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

    def test_help_command(self):
        """HELP command returns available commands."""
        from routes.whatsapp import _handle_command

        response = _handle_command("HELP", "2348012345678")
        assert "LOCK" in response
        assert "UNLOCK" in response
        assert "SOS" in response
        assert "STATUS" in response

    def test_lock_without_number_returns_usage(self):
        """LOCK without a number returns usage."""
        from routes.whatsapp import _handle_command

        response = _handle_command("LOCK", "2348012345678")
        assert "Usage" in response

    def test_unknown_command_returns_help_hint(self):
        """Unknown command returns help hint."""
        from routes.whatsapp import _handle_command

        response = _handle_command("BLARGH", "2348012345678")
        assert "didn't understand" in response.lower() or "HELP" in response

    def test_status_no_device(self):
        """STATUS for unregistered number returns not found."""
        from routes.whatsapp import _handle_command

        response = _handle_command("STATUS 08099999999", "2348012345678")
        assert "No Magneetar device found" in response

    def test_lock_no_device(self):
        """LOCK for unregistered number returns not found."""
        from routes.whatsapp import _handle_command

        response = _handle_command("LOCK 08099999999", "2348012345678")
        assert "No Magneetar device found" in response

    def test_sos_no_device(self):
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
        import secrets

        email = f"guardian-{secrets.token_hex(4)}@example.com"
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass1", "display_name": "Guardian Tester"},
        )
        assert resp.status_code == 200, resp.text
        token = resp.json()["token"]

        profile = client.get("/api/guardian/profile", headers={"Authorization": f"Bearer {token}"})
        assert profile.status_code == 200, profile.text
        body = profile.json()
        assert body["opted_in"] is False
        assert body["handle"] is None
        assert body["radius_km"] is None
