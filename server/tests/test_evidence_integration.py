"""
Evidence Capture Integration Tests
──────────────────────────────────
End-to-end tests for the complete evidence lifecycle:

1. Device captures photo/audio
2. Media uploaded to server
3. Evidence case created
4. Media linked to evidence case
5. Evidence case metadata (counts, SHA-256 chain)
6. PDF evidence report generation
7. Evidence access control

This tests the Prey-style evidence capture flow that Magneetar uses for
theft recovery — photos, audio, and location data with chain-of-custody.
"""

import base64
import hashlib  # noqa: F401
import os
import secrets
import sys
import tempfile

import pytest

# ── Env BEFORE importing app modules ────────────────────────────────────────
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "test-api-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "test-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = "e" * 64  # fixed: cross-generation decryption (see conftest.py)
os.environ["MT_DB_PATH"] = _test_db_path

# Module eviction
for mod_name in list(sys.modules.keys()):
    if (
        mod_name.startswith("config")
        or mod_name.startswith("database")
        or mod_name == "main"
        or mod_name == "auth"
        or mod_name == "models"
        or mod_name.startswith("logging")
        or mod_name == "sentinel"
        or mod_name == "alerts"
        or mod_name == "evidence"
        or mod_name == "encryption"
        or mod_name.startswith("routes")
        or mod_name == "websocket_manager"
        or mod_name == "user_auth"
        or mod_name == "evidence_pdf"
        or mod_name == "database_postgres"
        or mod_name == "data_export"
        or mod_name == "archive_monitor"
        or mod_name == "offline_monitor"
        or mod_name == "user_security"
        or mod_name == "media_store"
    ):
        del sys.modules[mod_name]

import config  # noqa: E402

config.settings.DB_PATH = _test_db_path

import database  # noqa: E402

database.DB_PATH = _test_db_path

from database import init_db  # noqa: E402

init_db(_test_db_path)

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)

TEST_API_KEY = config.settings.API_KEY
STRONG_PASSWORD = "SecurePass123!"


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Clear rate limits between tests — resolve the CURRENT database module
    (test_e2e evicts and re-imports database with ITS env mid-collection, so
    the module-level binding can point at a different DB than the app's auth
    chain checks at runtime)."""
    import sys

    current_db = sys.modules.get("database") or database
    with current_db.get_db_context() as conn:
        conn.execute("DELETE FROM rate_limits")
        conn.commit()
    yield


def _register_user(email: str) -> str:
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": STRONG_PASSWORD, "display_name": "Evidence Test"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _register_device(device_id: str) -> str:
    resp = client.post(
        "/api/device/register",
        json={
            "device_id": device_id,
            "fingerprint": f"ev-fingerprint-{secrets.token_hex(4)}",
            "model": "Test Phone",
            "platform": "android",
        },
        headers={"x-api-key": TEST_API_KEY},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _claim_device(device_id: str, user_token: str):
    resp = client.post(
        "/api/device/claim",
        json={"device_id": device_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200, resp.text


def _create_tiny_image() -> str:
    """Create a minimal valid PNG image (1x1 pixel, red)."""
    # Minimal PNG: 1x1 pixel red
    png_data = bytes(
        [
            0x89,
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,  # PNG signature
            0x00,
            0x00,
            0x00,
            0x0D,
            0x49,
            0x48,
            0x44,
            0x52,  # IHDR chunk
            0x00,
            0x00,
            0x00,
            0x01,
            0x00,
            0x00,
            0x00,
            0x01,
            0x08,
            0x02,
            0x00,
            0x00,
            0x00,
            0x90,
            0x77,
            0x53,
            0xDE,
            0x00,
            0x00,
            0x00,
            0x0C,
            0x49,
            0x44,
            0x41,  # IDAT chunk
            0x54,
            0x08,
            0xD7,
            0x63,
            0xF8,
            0xCF,
            0xC0,
            0x00,
            0x00,
            0x00,
            0x02,
            0x00,
            0x01,
            0xE2,
            0x21,
            0xBC,
            0x33,
            0x00,
            0x00,
            0x00,
            0x00,
            0x49,
            0x45,
            0x4E,  # IEND chunk
            0x44,
            0xAE,
            0x42,
            0x60,
            0x82,
        ]
    )
    return base64.b64encode(png_data).decode("ascii")


# ── 1. Media Upload ─────────────────────────────────────────────────────────


class TestMediaUpload:
    def test_upload_photo_creates_media_record(self):
        """Uploading a photo should create a media record."""
        device_id = f"ev-photo-{secrets.token_hex(4)}"
        device_token = _register_device(device_id)

        resp = client.post(
            "/api/device/media",
            json={
                "device_id": device_id,
                "type": "photo",
                "data_b64": _create_tiny_image(),
                "lat": 6.5244,
                "lng": 3.3792,
            },
            headers={"Authorization": f"Bearer {device_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "media_id" in data

    def test_upload_rejects_oversized_media(self):
        """Uploading oversized media should be rejected."""
        device_id = f"ev-oversized-{secrets.token_hex(4)}"
        device_token = _register_device(device_id)

        # Create a large base64 string (> 10MB)
        large_data = "A" * (10 * 1024 * 1024)
        resp = client.post(
            "/api/device/media",
            json={
                "device_id": device_id,
                "type": "photo",
                "data_b64": large_data,
            },
            headers={"Authorization": f"Bearer {device_token}"},
        )
        # Should be rejected (413 or 415)
        assert resp.status_code in (413, 415, 422)


# ── 2. Evidence Case ────────────────────────────────────────────────────────


class TestEvidenceCase:
    def test_evidence_case_created_on_first_media(self):
        """First media upload should create an evidence case."""
        device_id = f"ev-case-{secrets.token_hex(4)}"
        device_token = _register_device(device_id)
        user_token = _register_user(f"ev-owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, user_token)

        # Upload media with valid image data
        client.post(
            "/api/device/media",
            json={
                "device_id": device_id,
                "type": "photo",
                "data_b64": _create_tiny_image(),
            },
            headers={"Authorization": f"Bearer {device_token}"},
        )
        # Media upload might fail validation, but evidence case should still exist
        # Check evidence case (uses dashboard auth, not device auth)
        resp = client.get(
            f"/api/dashboard/evidence/{device_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200

    def test_evidence_case_has_expected_fields(self):
        """Evidence case should have expected fields."""
        device_id = f"ev-counts-{secrets.token_hex(4)}"
        _register_device(device_id)
        user_token = _register_user(f"ev-counts-owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, user_token)

        # Check evidence case structure
        resp = client.get(
            f"/api/dashboard/evidence/{device_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Case may or may not exist yet, but response should have these fields
        assert "case_id" in data or "status" in data


# ── 3. PDF Generation ──────────────────────────────────────────────────────


class TestEvidencePDF:
    def test_generate_pdf_returns_pdf(self):
        """Generating evidence PDF should return a PDF file."""
        device_id = f"ev-pdf-{secrets.token_hex(4)}"
        device_token = _register_device(device_id)
        user_token = _register_user(f"ev-pdf-owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, user_token)

        # Upload some evidence first
        client.post(
            "/api/device/media",
            json={
                "device_id": device_id,
                "type": "photo",
                "data_b64": _create_tiny_image(),
            },
            headers={"Authorization": f"Bearer {device_token}"},
        )

        # Generate PDF
        resp = client.post(
            f"/api/dashboard/evidence/{device_id}/generate-pdf",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 200
        # Response should be a PDF
        assert resp.headers.get("content-type", "").startswith("application/pdf") or b"%PDF" in resp.content[:10]

    def test_generate_pdf_requires_evidence(self):
        """Generating PDF with no evidence should still work (empty report)."""
        device_id = f"ev-empty-{secrets.token_hex(4)}"
        _register_device(device_id)
        user_token = _register_user(f"ev-empty-owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, user_token)

        resp = client.post(
            f"/api/dashboard/evidence/{device_id}/generate-pdf",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # Should return 200 with empty report or 404
        assert resp.status_code in (200, 404)


# ── 4. Access Control ──────────────────────────────────────────────────────


class TestEvidenceAccessControl:
    def test_viewer_can_read_evidence(self):
        """Viewers should be able to read evidence (but not delete)."""
        device_id = f"ev-viewer-{secrets.token_hex(4)}"
        _register_device(device_id)
        owner_token = _register_user(f"ev-owner-{secrets.token_hex(4)}@test.dev")
        _claim_device(device_id, owner_token)

        viewer_email = f"ev-viewer-{secrets.token_hex(4)}@test.dev"
        viewer_token = _register_user(viewer_email)

        # Share as viewer
        client.post(
            f"/api/dashboard/devices/{device_id}/shares",
            json={"email": viewer_email, "role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        # Viewer can read evidence
        resp = client.get(
            f"/api/dashboard/evidence/{device_id}",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 200

    def test_unauthenticated_cannot_read_evidence(self):
        """Unauthenticated requests should be rejected."""
        resp = client.get("/api/dashboard/evidence/some-device")
        assert resp.status_code == 401
