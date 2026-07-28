"""
Magneetar Evidence System
Evidence package builder with chain of custody and PDF generation.
"""
import hashlib
import json
import secrets
import string
from datetime import datetime, timezone
from typing import Optional
from database import get_db_context, log_audit


class EvidenceBuilder:
    """Build and manage evidence packages for theft cases."""

    def create_case(self, device_id: str) -> str:
        """
        Create a new evidence case.
        Returns case ID in format: MGT-2026-XXXXX
        """
        case_id = self.generate_case_id()

        with get_db_context() as conn:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """INSERT INTO evidence_cases (id, device_id, theft_time, status)
                   VALUES (?, ?, ?, 'active')""",
                (case_id, device_id, now)
            )
            conn.commit()

            log_audit(
                action="evidence_case_created",
                actor=device_id,
                details=f"Case: {case_id}"
            )

        return case_id

    def generate_case_id(self) -> str:
        """Generate case ID: MGT-{YEAR}-{5 random uppercase alphanumeric}"""
        year = datetime.now().year
        chars = string.ascii_uppercase + string.digits
        suffix = ''.join(secrets.choice(chars) for _ in range(5))
        return f"MGT-{year}-{suffix}"

    def update_chain(self, case_id: str, item_hash: str) -> str:
        """
        Update SHA-256 chain of custody.
        chain = SHA256(previous_chain + item_hash + timestamp)
        Returns new chain hash.
        """
        with get_db_context() as conn:
            case = conn.execute(
                "SELECT sha256_chain FROM evidence_cases WHERE id=?",
                (case_id,)
            ).fetchone()

            previous_chain = case["sha256_chain"] if case and case["sha256_chain"] else ""
            timestamp = datetime.now(timezone.utc).isoformat()

            # Compute new chain hash
            chain_input = f"{previous_chain}{item_hash}{timestamp}"
            new_chain = hashlib.sha256(chain_input.encode()).hexdigest()

            # Update case
            conn.execute(
                "UPDATE evidence_cases SET sha256_chain=? WHERE id=?",
                (new_chain, case_id)
            )
            conn.commit()

        return new_chain

    def compute_item_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of evidence item."""
        return hashlib.sha256(data).hexdigest()

    def add_location_to_case(self, case_id: str) -> None:
        """Increment location count for a case."""
        with get_db_context() as conn:
            conn.execute(
                """UPDATE evidence_cases 
                   SET location_count = location_count + 1 
                   WHERE id=?""",
                (case_id,)
            )
            conn.commit()

    def add_media_to_case(self, case_id: str, media_type: str, data_b64: str) -> str:
        """
        Add media item to evidence case.
        Computes hash and updates chain of custody.
        Returns the item hash.
        """
        import base64

        data = base64.b64decode(data_b64)
        item_hash = self.compute_item_hash(data)

        # Update chain
        self.update_chain(case_id, item_hash)

        # Update case counters
        with get_db_context() as conn:
            if media_type == "photo":
                conn.execute(
                    "UPDATE evidence_cases SET photo_count = photo_count + 1 WHERE id=?",
                    (case_id,)
                )
            elif media_type == "audio":
                conn.execute(
                    "UPDATE evidence_cases SET audio_count = audio_count + 1 WHERE id=?",
                    (case_id,)
                )
            conn.commit()

        return item_hash

    def get_case_summary(self, case_id: str) -> Optional[dict]:
        """Get evidence case summary."""
        with get_db_context() as conn:
            case = conn.execute(
                "SELECT * FROM evidence_cases WHERE id=?",
                (case_id,)
            ).fetchone()

            if not case:
                return None

            # Get media items
            media = conn.execute(
                "SELECT id, type, timestamp, sha256_hash FROM media WHERE evidence_case_id=?",
                (case_id,)
            ).fetchall()

            return {
                "case_id": case["id"],
                "device_id": case["device_id"],
                "created_at": case["created_at"],
                "theft_time": case["theft_time"],
                "status": case["status"],
                "item_counts": {
                    "locations": case["location_count"],
                    "photos": case["photo_count"],
                    "audio": case["audio_count"],
                },
                "sha256_chain": case["sha256_chain"],
                "media_items": [dict(m) for m in media],
            }

    def compile_pdf_data(self, case_id: str) -> Optional[dict]:
        """
        Compile evidence data for PDF generation.
        Returns structured data that can be used to generate a PDF.
        """
        summary = self.get_case_summary(case_id)
        if not summary:
            return None

        with get_db_context() as conn:
            # Get device info
            device = conn.execute(
                "SELECT * FROM devices WHERE id=?",
                (summary["device_id"],)
            ).fetchone()

            # Get location trail
            locations = conn.execute(
                """SELECT lat, lng, accuracy, provider, timestamp, speed, bearing,
                          battery_percent, network_type, sentinel_score, threat_level
                   FROM locations 
                   WHERE device_id=? 
                   ORDER BY server_timestamp ASC""",
                (summary["device_id"],)
            ).fetchall()

            # Get media metadata
            media = conn.execute(
                "SELECT id, type, lat, lng, timestamp, sha256_hash FROM media WHERE evidence_case_id=?",
                (case_id,)
            ).fetchall()

            # Get alerts
            alerts = conn.execute(
                """SELECT alert_type, channel, message, sent_at 
                   FROM alerts 
                   WHERE device_id=? 
                   ORDER BY sent_at ASC""",
                (summary["device_id"],)
            ).fetchall()

            return {
                "case": summary,
                "device": {
                    "id": device["id"] if device else "Unknown",
                    "model": device["model"] if device else "Unknown",
                    "os_version": device["os_version"] if device else "Unknown",
                    "imei_hash": device["imei_hash"] if device else None,
                },
                "locations": [dict(loc) for loc in locations],
                "media": [dict(m) for m in media],
                "alerts": [dict(a) for a in alerts],
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "chain_of_custody": summary["sha256_chain"],
            }


# Singleton
evidence_builder = EvidenceBuilder()
