"""
Magneetar Data Export Service
GDPR-compliant data export and deletion functionality.

Features:
- Export all user data as JSON/ZIP
- Export device data with location history
- Export evidence packages
- Right to erasure (account deletion)
- Data portability
"""

import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional

from config import settings
from database import get_db_context
from encryption import decrypt_location_row

logger = logging.getLogger(__name__)


class DataExportService:
    """GDPR-compliant data export service."""

    def __init__(self):
        self._export_dir = os.path.join(settings.MEDIA_DIR, "exports")
        os.makedirs(self._export_dir, exist_ok=True)

    def export_user_data(self, user_id: str, format: str = "json") -> dict:
        """Export all data for a user."""
        with get_db_context() as conn:
            # Get user info
            user = conn.execute(
                "SELECT id, email, display_name, tier, created_at, last_login FROM users WHERE id=?",
                (user_id,),
            ).fetchone()

            if not user:
                return {"error": "User not found"}

            # Get all devices
            devices = conn.execute(
                "SELECT * FROM devices WHERE owner_id=?",
                (user_id,),
            ).fetchall()

            export_data = {
                "export_date": datetime.now(timezone.utc).isoformat(),
                "user": dict(user),
                "devices": [],
            }

            for device in devices:
                device_data = dict(device)

                # Get location history (at-rest encryption: decrypt each ping
                # so the GDPR export carries real coordinates, never 0.0
                # placeholders or ciphertext).
                locations = conn.execute(
                    "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC LIMIT 10000",
                    (device["id"],),
                ).fetchall()
                exported_locations = []
                for loc in locations:
                    loc_dict = dict(loc)
                    loc_dict["lat"], loc_dict["lng"] = decrypt_location_row(loc_dict)
                    # location_data is the raw ciphertext — never export it.
                    loc_dict.pop("location_data", None)
                    exported_locations.append(loc_dict)
                device_data["locations"] = exported_locations

                # Get commands
                commands = conn.execute(
                    "SELECT * FROM commands WHERE device_id=? ORDER BY issued_at DESC",
                    (device["id"],),
                ).fetchall()
                device_data["commands"] = [dict(cmd) for cmd in commands]

                # Get alerts
                alerts = conn.execute(
                    "SELECT * FROM alerts WHERE device_id=? ORDER BY sent_at DESC",
                    (device["id"],),
                ).fetchall()
                device_data["alerts"] = [dict(alert) for alert in alerts]

                # Get evidence cases
                evidence = conn.execute(
                    "SELECT * FROM evidence_cases WHERE device_id=?",
                    (device["id"],),
                ).fetchall()
                device_data["evidence_cases"] = [dict(ev) for ev in evidence]

                # Get media
                media = conn.execute(
                    "SELECT id, device_id, type, timestamp, evidence_case_id, file_size FROM media WHERE device_id=?",
                    (device["id"],),
                ).fetchall()
                device_data["media"] = [dict(m) for m in media]

                # Get heartbeats
                heartbeats = conn.execute(
                    "SELECT * FROM heartbeats WHERE device_id=? ORDER BY timestamp DESC LIMIT 1000",
                    (device["id"],),
                ).fetchall()
                device_data["heartbeats"] = [dict(hb) for hb in heartbeats]

                # Get geofences
                geofences = conn.execute(
                    "SELECT * FROM geofences WHERE device_id=?",
                    (device["id"],),
                ).fetchall()
                device_data["geofences"] = [dict(gf) for gf in geofences]

                export_data["devices"].append(device_data)

            # Get guardian profile
            guardian = conn.execute(
                "SELECT * FROM guardian_profiles WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if guardian:
                export_data["guardian_profile"] = dict(guardian)

            # Get recovery requests
            recovery = conn.execute(
                "SELECT * FROM recovery_requests WHERE owner_id=?",
                (user_id,),
            ).fetchall()
            export_data["recovery_requests"] = [dict(r) for r in recovery]

        return export_data

    def export_device_data(self, device_id: str, owner_id: Optional[str] = None) -> dict:
        """Export data for a specific device."""
        with get_db_context() as conn:
            # Verify ownership if owner_id provided
            if owner_id:
                device = conn.execute(
                    "SELECT * FROM devices WHERE id=? AND owner_id=?",
                    (device_id, owner_id),
                ).fetchone()
            else:
                device = conn.execute(
                    "SELECT * FROM devices WHERE id=?",
                    (device_id,),
                ).fetchone()

            if not device:
                return {"error": "Device not found or access denied"}

            device_data = dict(device)

            # Get all related data
            exported_locations = []
            for loc in conn.execute(
                "SELECT * FROM locations WHERE device_id=? ORDER BY server_timestamp DESC",
                (device_id,),
            ).fetchall():
                loc_dict = dict(loc)
                loc_dict["lat"], loc_dict["lng"] = decrypt_location_row(loc_dict)
                # location_data is the raw ciphertext — never export it.
                loc_dict.pop("location_data", None)
                exported_locations.append(loc_dict)
            device_data["locations"] = exported_locations

            device_data["commands"] = [
                dict(cmd)
                for cmd in conn.execute(
                    "SELECT * FROM commands WHERE device_id=? ORDER BY issued_at DESC",
                    (device_id,),
                ).fetchall()
            ]

            device_data["media"] = [
                dict(m)
                for m in conn.execute(
                    "SELECT id, type, timestamp, file_size FROM media WHERE device_id=?",
                    (device_id,),
                ).fetchall()
            ]

            device_data["evidence_cases"] = [
                dict(ev)
                for ev in conn.execute(
                    "SELECT * FROM evidence_cases WHERE device_id=?",
                    (device_id,),
                ).fetchall()
            ]

        return device_data

    def create_zip_export(self, user_id: str) -> Optional[str]:
        """Create a ZIP file with all user data."""
        try:
            export_data = self.export_user_data(user_id)

            if "error" in export_data:
                return None

            # Create ZIP file
            zip_path = os.path.join(
                self._export_dir, f"export_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            )

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                # Add main export data
                zipf.writestr("export.json", json.dumps(export_data, indent=2, default=str))

                # Add individual device files
                for device in export_data.get("devices", []):
                    device_id = device["id"]

                    # Location history
                    if device.get("locations"):
                        zipf.writestr(
                            f"devices/{device_id}/locations.json",
                            json.dumps(device["locations"], indent=2, default=str),
                        )

                    # Commands
                    if device.get("commands"):
                        zipf.writestr(
                            f"devices/{device_id}/commands.json", json.dumps(device["commands"], indent=2, default=str)
                        )

                    # Alerts
                    if device.get("alerts"):
                        zipf.writestr(
                            f"devices/{device_id}/alerts.json", json.dumps(device["alerts"], indent=2, default=str)
                        )

                # Add metadata
                zipf.writestr(
                    "metadata.json",
                    json.dumps(
                        {
                            "export_version": "1.0",
                            "export_date": datetime.now(timezone.utc).isoformat(),
                            "user_id": user_id,
                            "format": "GDPR Data Export",
                        },
                        indent=2,
                    ),
                )

            logger.info(f"Data export created for user {user_id}: {zip_path}")
            return zip_path

        except Exception as e:
            logger.error(f"Failed to create export for user {user_id}: {e}")
            return None

    def delete_user_data(self, user_id: str, confirm: bool = False) -> dict:
        """Delete all user data (right to erasure)."""
        if not confirm:
            return {"error": "Must confirm deletion", "requires_confirmation": True}

        with get_db_context() as conn:
            # Get all user devices
            devices = conn.execute(
                "SELECT id FROM devices WHERE owner_id=?",
                (user_id,),
            ).fetchall()

            deleted_counts = {
                "devices": 0,
                "locations": 0,
                "commands": 0,
                "media": 0,
                "alerts": 0,
                "evidence": 0,
            }

            for device in devices:
                device_id = device["id"]

                # Delete related data
                for table in ["locations", "commands", "alerts", "evidence_cases", "heartbeats", "geofences"]:
                    result = conn.execute(f"DELETE FROM {table} WHERE device_id=?", (device_id,))
                    deleted_counts[table] = deleted_counts.get(table, 0) + result.rowcount

                # Delete media files from disk
                media_rows = conn.execute(
                    "SELECT file_path FROM media WHERE device_id=?",
                    (device_id,),
                ).fetchall()

                try:
                    from media_store import delete_media_file

                    for row in media_rows:
                        if row["file_path"]:
                            delete_media_file(row["file_path"])
                except Exception:
                    pass

                conn.execute("DELETE FROM media WHERE device_id=?", (device_id,))
                deleted_counts["media"] += len(media_rows)

                # Delete device
                conn.execute("DELETE FROM devices WHERE id=?", (device_id,))
                deleted_counts["devices"] += 1

            # Delete user data
            conn.execute("DELETE FROM guardian_profiles WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM recovery_requests WHERE owner_id=?", (user_id,))
            conn.execute(
                "DELETE FROM fcm_tokens WHERE device_id IN (SELECT id FROM devices WHERE owner_id=?)", (user_id,)
            )
            conn.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM email_verify_tokens WHERE user_id=?", (user_id,))

            # Delete user account
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))

            conn.commit()

        logger.info(f"User data deleted: {user_id}")
        return {
            "status": "deleted",
            "user_id": user_id,
            "deleted": deleted_counts,
        }

    def get_export_status(self, user_id: str) -> dict:
        """Get export status for a user."""
        # Check for existing exports
        exports = []
        for filename in os.listdir(self._export_dir):
            if filename.startswith(f"export_{user_id}_") and filename.endswith(".zip"):
                filepath = os.path.join(self._export_dir, filename)
                stat = os.stat(filepath)
                exports.append(
                    {
                        "filename": filename,
                        "size_bytes": stat.st_size,
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    }
                )

        return {
            "user_id": user_id,
            "export_count": len(exports),
            "exports": exports,
        }


# Singleton
data_export_service = DataExportService()
