"""
Magneetar Encryption helpers (AES-256-GCM field-level).

STATUS (2026-08-11): WIRED — location telemetry is now encrypted at rest via
encrypt_location_for_store()/decrypt_location_row() when MT_ENCRYPTION_KEY is
configured (per-device HKDF-derived keys; see routes/devices.py, the dashboard
read paths, guardian, offline_monitor, data_export, evidence). Account secrets
(TOTP 2FA) were already encrypted via user_security.py. Without a configured
key the module degrades to NoOpEncryption and everything stores plaintext, so
local/dev setups keep working unchanged.
"""

import base64
import logging
import os

from config import settings
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


class FieldEncryption:
    """AES-256-GCM encryption for individual fields."""

    def __init__(self, master_key_hex: str = None):
        if master_key_hex is None:
            master_key_hex = settings.ENCRYPTION_KEY

        if not master_key_hex:
            raise ValueError("Encryption key not configured")

        self.master_key = bytes.fromhex(master_key_hex)
        if len(self.master_key) != 32:
            raise ValueError("Master key must be 32 bytes (64 hex chars)")

    def _derive_device_key(self, device_id: str) -> bytes:
        """Derive a unique key for each device using HKDF."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"magneetar-v1",
            info=f"device:{device_id}".encode(),
        )
        return hkdf.derive(self.master_key)

    def encrypt_field(self, plaintext: str, device_id: str) -> str:
        """
        Encrypt a single field value.
        Returns: base64(nonce + ciphertext + tag)
        """
        key = self._derive_device_key(device_id)
        nonce = os.urandom(12)  # 96-bit nonce for AES-GCM

        aesgcm = AESGCM(key)
        # AES-GCM automatically appends 16-byte auth tag
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # Combine: nonce (12) + ciphertext (includes 16-byte tag)
        combined = nonce + ciphertext
        return base64.b64encode(combined).decode("ascii")

    def decrypt_field(self, encrypted_b64: str, device_id: str) -> str:
        """
        Decrypt a single field value.
        Input: base64(nonce + ciphertext + tag)
        """
        key = self._derive_device_key(device_id)
        combined = base64.b64decode(encrypted_b64)

        nonce = combined[:12]
        ciphertext = combined[12:]

        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")

    def encrypt_location(self, lat: float, lng: float, device_id: str) -> dict:
        """
        Encrypt latitude and longitude together.
        Returns dict with encrypted location data.
        """
        location_str = f"{lat},{lng}"
        encrypted = self.encrypt_field(location_str, device_id)
        return {
            "location_encrypted": True,
            "location_data": encrypted,
        }

    def decrypt_location(self, encrypted_data: str, device_id: str) -> tuple[float, float]:
        """
        Decrypt location data.
        Returns (lat, lng) tuple.
        """
        decrypted = self.decrypt_field(encrypted_data, device_id)
        lat_str, lng_str = decrypted.split(",")
        return float(lat_str), float(lng_str)

    def is_enabled(self) -> bool:
        """True when this instance actually encrypts (vs the NoOp fallback)."""
        return True


# Singleton instance
_encryption_instance = None


def get_encryption() -> FieldEncryption:
    """Get or create the encryption singleton."""
    global _encryption_instance
    if _encryption_instance is None:
        try:
            _encryption_instance = FieldEncryption()
        except ValueError:
            # Encryption not configured - return a no-op implementation
            _encryption_instance = NoOpEncryption()
    return _encryption_instance


class NoOpEncryption:
    """Fallback when encryption is not configured - stores plaintext."""

    def is_enabled(self) -> bool:
        return False

    def encrypt_location(self, lat: float, lng: float, device_id: str) -> dict:
        return {
            "location_encrypted": False,
            "lat": lat,
            "lng": lng,
        }

    def decrypt_location(self, encrypted_data: str, device_id: str) -> tuple[float, float]:
        raise NotImplementedError("Encryption not configured")

    def encrypt_field(self, plaintext: str, device_id: str) -> str:
        """NoOp mode stores the field as plaintext (matches encrypt_location)."""
        return plaintext

    def decrypt_field(self, encrypted_b64: str, device_id: str) -> str:
        """NoOp mode reads the field back as plaintext."""
        return encrypted_b64


# ── At-rest store/read helpers (the wired contract) ─────────────────────────


def encrypt_location_for_store(lat, lng, device_id: str) -> tuple:
    """Return (lat, lng, encrypted_flag, location_data) for a locations INSERT.

    When the master encryption key is configured, the coordinates are
    AES-256-GCM encrypted with a per-device HKDF-derived key: the row stores
    0.0 placeholders in the NOT NULL lat/lng columns (plaintext never touches
    the DB), location_encrypted=1, and the base64 ciphertext in
    location_data. Without a key (NoOp mode) the row stores plaintext exactly
    as before.
    """
    enc = get_encryption()
    if enc.is_enabled() and lat is not None and lng is not None:
        result = enc.encrypt_location(lat, lng, device_id)
        return 0.0, 0.0, True, result["location_data"]
    return lat, lng, False, None


def decrypt_location(lat, lng, encrypted, location_data, device_id: str) -> tuple:
    """Return (lat, lng) for one location row's coordinate columns.

    Handles BOTH storage modes: encrypted rows (location_encrypted=1) decrypt
    location_data with the per-device key; legacy plaintext rows pass through
    unchanged. Returns (None, None) when decryption fails so every caller
    degrades gracefully instead of crashing the dashboard/export/PDF.
    """
    if encrypted:
        enc = get_encryption()
        if not enc.is_enabled():
            return None, None
        try:
            return enc.decrypt_location(location_data, device_id)
        except Exception:
            # Ops visibility: rows become (None, None) on the dashboard when
            # MT_ENCRYPTION_KEY is rotated — log it so the silent degradation
            # is distinguishable from an empty history.
            logging.getLogger("magneetar").warning(
                "Location decrypt failed for device %s (MT_ENCRYPTION_KEY rotated?)", device_id
            )
            return None, None
    return lat, lng


def decrypt_location_row(row) -> tuple:
    """(lat, lng) from a locations row (dict or sqlite3.Row) that carries the
    device_id/lat/lng/location_encrypted/location_data keys."""
    if row is None:
        return None, None
    return decrypt_location(
        row["lat"],
        row["lng"],
        bool(row["location_encrypted"]),
        row["location_data"],
        row["device_id"],
    )
