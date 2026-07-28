"""
Magneetar Alert System
Multi-channel alerts: Email (SendGrid), SMS (Termii), WhatsApp (Twilio), Push (FCM).
"""
import os
import asyncio
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional
from database import get_db_context, log_audit
from config import settings

logger = logging.getLogger(__name__)


class AlertEngine:
    """Send alerts via multiple channels with graceful degradation."""

    ALERT_TEMPLATES = {
        "theft_detected": {
            "subject": "🚨 MAGNEETAR ALERT: Device theft detected",
            "email": "Your device may have been stolen. Open the dashboard to track it in real-time.\n\nLocation: {location}\nTime: {time}\nThreat Score: {score}/100",
            "sms": "MAGNEETAR: Your phone may be stolen. Track it at magneetar.me/dashboard. Location: {location}",
            "push_title": "🚨 Theft Detected",
            "push_body": "Your device is moving suspiciously. Tap to track.",
        },
        "sim_changed": {
            "subject": "⚠️ MAGNEETAR: SIM card changed",
            "email": "A different SIM card was detected in your device.\n\nNew SIM detected at: {location}\nTime: {time}",
            "sms": "MAGNEETAR: SIM changed on your device at {location}.",
            "push_title": "⚠️ SIM Changed",
            "push_body": "A new SIM card was inserted in your device.",
        },
        "battery_low": {
            "subject": "🔋 MAGNEETAR: Device battery critical",
            "email": "Your device battery is at {battery}%.\n\nLast known location: {location}",
            "sms": "MAGNEETAR: Device at {battery}% battery. Last location: {location}",
            "push_title": "🔋 Battery Critical",
            "push_body": "Device battery at {battery}%. Location saved.",
        },
        "device_offline": {
            "subject": "📡 MAGNEETAR: Device went offline",
            "email": "Your device has been offline since {time}.\n\nLast known location: {location}",
            "sms": "MAGNEETAR: Device offline since {time}. Last: {location}",
            "push_title": "📡 Device Offline",
            "push_body": "Your device went offline at {time}.",
        },
        "device_recovered": {
            "subject": "✅ MAGNEETAR: Device appears recovered",
            "email": "Your device is back at a known location.\n\nLocation: {location}\nTime: {time}",
            "sms": "MAGNEETAR: Device back at known location. Check dashboard.",
            "push_title": "✅ Device Recovered",
            "push_body": "Your device appears to be back in a safe location.",
        },
        "factory_reset": {
            "subject": "🚨 MAGNEETAR CRITICAL: Factory reset attempted",
            "email": "A factory reset was attempted on your device.\n\nLocation: {location}\nTime: {time}\nEvidence has been captured.",
            "sms": "MAGNEETAR CRITICAL: Factory reset attempted at {location}. Evidence captured.",
            "push_title": "🚨 Factory Reset",
            "push_body": "Factory reset attempted. Evidence captured.",
        },
        "geofence_exit": {
            "subject": "📍 MAGNEETAR: Device left safe zone",
            "email": "Your device left the safe zone '{zone_name}'.\n\nLocation: {location}\nTime: {time}",
            "sms": "MAGNEETAR: Device left safe zone '{zone_name}' at {location}.",
            "push_title": "📍 Left Safe Zone",
            "push_body": "Device left '{zone_name}'.",
        },
    }

    async def send_email(self, to: str, template: str, data: dict) -> bool:
        """Send email via SendGrid API."""
        if not settings.SENDGRID_API_KEY:
            return False

        tmpl = self.ALERT_TEMPLATES.get(template, {})
        subject = tmpl.get("subject", f"MAGNEETAR Alert: {template}")
        body = tmpl.get("email", "").format(**data)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": to}]}],
                        "from": {"email": "alerts@magneetar.me", "name": "Magneetar"},
                        "subject": subject,
                        "content": [{"type": "text/plain", "value": body}],
                    },
                    timeout=10,
                )
                return response.status_code in (200, 202)
        except Exception as e:
            logger.warning(f"Email send failed: {e}")
            return False

    async def send_sms(self, to: str, template: str, data: dict) -> bool:
        """Send SMS via Termii API (Nigerian provider)."""
        if not settings.TERMII_API_KEY:
            return False

        tmpl = self.ALERT_TEMPLATES.get(template, {})
        message = tmpl.get("sms", "").format(**data)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.termii.com/api/sms/send",
                    json={
                        "to": to,
                        "from": "Magneetar",
                        "sms": message,
                        "type": "plain",
                        "api_key": settings.TERMII_API_KEY,
                    },
                    timeout=10,
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"SMS send failed: {e}")
            return False

    async def send_push(self, device_token: str, template: str, data: dict) -> bool:
        """Send push notification via Firebase Cloud Messaging (FCM v1).
        Uses asyncio.to_thread() to avoid blocking the event loop with Firebase's synchronous SDK.
        """
        if not settings.FIREBASE_CREDENTIALS:
            return False

        tmpl = self.ALERT_TEMPLATES.get(template, {})
        title = tmpl.get("push_title", "Magneetar Alert")
        body = tmpl.get("push_body", "").format(**data)

        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            # Initialize Firebase app if not already initialized
            try:
                firebase_admin.get_app()
            except ValueError:
                # Parse credentials — supports both file path and JSON string
                cred_path = settings.FIREBASE_CREDENTIALS
                if cred_path.startswith("{"):
                    import json as _json
                    cred = credentials.Certificate(_json.loads(cred_path))
                else:
                    cred = credentials.Certificate(cred_path)
                # Initialize in a thread to avoid blocking on file I/O
                await asyncio.to_thread(firebase_admin.initialize_app, cred)

            # Build the FCM message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=device_token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        sound="default",
                        priority="high",
                        channel_id="mt_alerts",
                        click_action="FLUTTER_NOTIFICATION_CLICK",
                    ),
                ),
                data={
                    "type": template,
                    "title": title,
                    "body": body,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **{k: str(v) for k, v in data.items()},
                },
            )

            # Send in thread to avoid blocking the async event loop
            response = await asyncio.to_thread(messaging.send, message)
            logger.info(f"Push notification sent: {response}")
            return True

        except ImportError:
            logger.warning("firebase-admin not installed. Run: pip install firebase-admin")
            return False
        except Exception as e:
            logger.error(f"Push notification failed: {e}")
            return False

    async def send_whatsapp(self, to: str, template: str, data: dict) -> bool:
        """Send WhatsApp message via Twilio."""
        if not settings.TWILIO_SID or not settings.TWILIO_AUTH_TOKEN:
            return False

        tmpl = self.ALERT_TEMPLATES.get(template, {})
        message = tmpl.get("sms", "").format(**data)  # Reuse SMS template

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
                    auth=(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN),
                    data={
                        "To": f"whatsapp:{to}",
                        "From": "whatsapp:+14155238886",
                        "Body": message,
                    },
                    timeout=10,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"WhatsApp send failed: {e}")
            return False

    async def send_all(
        self,
        device_id: str,
        alert_type: str,
        data: dict,
        channels: list[str] = None
    ) -> dict[str, bool]:
        """
        Send alert via all configured channels.
        Returns dict of channel -> success status.
        """
        if channels is None:
            channels = ["email", "sms", "push"]

        results = {}

        # Get alert recipients from device settings
        email_to = data.get("email") or os.environ.get("MT_ALERT_EMAIL")
        phone_to = data.get("phone") or os.environ.get("MT_ALERT_PHONE")

        # Look up stored FCM tokens from the database
        push_tokens: list[str] = []
        if data.get("push_token"):
            push_tokens = [data["push_token"]]
        else:
            try:
                with get_db_context() as conn:
                    # First, try to get tokens registered by this specific device
                    rows = conn.execute(
                        "SELECT DISTINCT fcm_token FROM fcm_tokens WHERE device_id=? ORDER BY updated_at DESC",
                        (device_id,)
                    ).fetchall()
                    push_tokens = [r["fcm_token"] for r in rows]

                    # If no device-specific tokens found, broadcast to ALL registered tokens.
                    # This handles:
                    #   - Old tokens stored under "api_key_user" (backward compat)
                    #   - Tokens registered without device_id ("broadcast")
                    #   - Tokens from other devices the user may have
                    if not push_tokens:
                        rows = conn.execute(
                            "SELECT DISTINCT fcm_token FROM fcm_tokens ORDER BY updated_at DESC"
                        ).fetchall()
                        push_tokens = [r["fcm_token"] for r in rows]
            except Exception:
                pass

        for channel in channels:
            success = False
            if channel == "email" and email_to:
                success = await self.send_email(email_to, alert_type, data)
            elif channel == "sms" and phone_to:
                success = await self.send_sms(phone_to, alert_type, data)
            elif channel == "push":
                # Send push to all registered FCM tokens
                if push_tokens:
                    for token in push_tokens:
                        token_success = await self.send_push(token, alert_type, data)
                        if token_success:
                            success = True  # At least one succeeded
            elif channel == "whatsapp" and phone_to:
                success = await self.send_whatsapp(phone_to, alert_type, data)

            results[channel] = success

            # Log alert to database
            recipient = email_to if channel == "email" else (phone_to if channel in ("sms", "whatsapp") else "fcm")
            with get_db_context() as conn:
                conn.execute(
                    """INSERT INTO alerts (device_id, alert_type, channel, recipient, message, delivered)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        device_id,
                        alert_type,
                        channel,
                        recipient,
                        self.ALERT_TEMPLATES.get(alert_type, {}).get("sms", "").format(**data),
                        success,
                    )
                )
                conn.commit()

        return results


# Singleton
alert_engine = AlertEngine()
