"""
Magneetar Encryption
AES-256-GCM field-level encryption for sensitive location data.
Each location's lat/lng encrypted individually with per-device derived keys.
"""

import base64
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

    def encrypt_location(self, lat: float, lng: float, device_id: str) -> dict:
        return {
            "location_encrypted": False,
            "lat": lat,
            "lng": lng,
        }

    def decrypt_location(self, encrypted_data: str, device_id: str) -> tuple[float, float]:
        raise NotImplementedError("Encryption not configured")
