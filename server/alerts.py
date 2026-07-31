"""
Magneetar Alert System
Multi-channel alerts: Email (SendGrid), SMS (Termii), WhatsApp (Twilio), Push (FCM).
"""

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone

import httpx
from config import settings
from database import get_db_context

logger = logging.getLogger(__name__)

# Default mapping from template placeholders ({{1}}, {{2}}, ...) to alert data
# keys. Used when MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES is unset — keep in sync
# with the template created in the Twilio Console.
DEFAULT_WHATSAPP_TEMPLATE_VARIABLES = {
    "1": "location",
    "2": "time",
    "3": "score",
}


def normalize_phone_to_e164(phone: str, default_country_code: str = "234") -> str:
    """Convert a phone number to E.164 format for Twilio.

    Twilio requires recipient numbers in E.164 (e.g. +2348081234567).
    Users commonly enter local formats, so normalize only the UNAMBIGUOUS
    cases (never guess on bare digits, which could be a number already
    carrying a country code or an unrelated ID):
      - "+2348081234567"            → unchanged (already E.164)
      - "08081234567" (national)    → +2348081234567
      - "002348081234567" (dialing) → +2348081234567
      - "2348081234567" (CC, no +)  → +2348081234567
      - "+1 (555) 123-4567"         → +15551234567 (formatting stripped)
    Everything else is returned unchanged.
    """
    if not phone:
        return phone
    cleaned = re.sub(r"[\s\-().]", "", phone.strip())
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("00"):
        return "+" + cleaned[2:]
    if cleaned.startswith("0") and len(cleaned) >= 10:
        # National number, e.g. Nigerian 0808... → +234808...
        return "+" + default_country_code + cleaned[1:]
    if cleaned.isdigit() and cleaned.startswith(default_country_code):
        # International number typed without the '+' prefix
        return "+" + cleaned
    return phone


class AlertEngine:
    """Send alerts via multiple channels with graceful degradation.

    Reliability features:
    - Exponential backoff with jitter (1 retry per channel)
    - Per-channel failure tracking (circuit-breaker light)
    - Timeout per HTTP call (10s)
    """

    # ── Retry / Circuit-Breaker ─────────────────────────────────────────
    MAX_CONSECUTIVE_FAILURES = 5
    """If a channel fails this many times consecutively, the circuit opens."""
    CIRCUIT_BREAKER_COOLDOWN = 300
    """Seconds after opening the circuit before allowing a probe attempt (half-open state). Default 5 minutes."""

    def __init__(self):
        """Initialize alert engine with per-instance circuit-breaker state."""
        self._channel_failures: dict[str, int] = {}
        self._channel_disabled_at: dict[str, float] = {}

    def _should_skip_channel(self, channel: str) -> bool:
        """Check if a channel should be skipped (circuit-breaker open).

        Automatically allows a probe attempt after CIRCUIT_BREAKER_COOLDOWN seconds
        (half-open state) so that transient provider outages don't permanently disable alerts.
        """
        failures = self._channel_failures.get(channel, 0)
        if failures < self.MAX_CONSECUTIVE_FAILURES:
            return False

        # Circuit is open — check if cooldown has elapsed (half-open probe)
        disabled_at = self._channel_disabled_at.get(channel, 0.0)
        if time.time() - disabled_at > self.CIRCUIT_BREAKER_COOLDOWN:
            logger.info(f"Channel '{channel}' circuit breaker cooldown elapsed — allowing probe attempt")
            return False

        return True

    def _record_success(self, channel: str):
        self._channel_failures[channel] = 0
        self._channel_disabled_at.pop(channel, None)  # clean up stale timestamp

    def _record_failure(self, channel: str):
        self._channel_failures[channel] = self._channel_failures.get(channel, 0) + 1
        failures = self._channel_failures[channel]
        if failures >= self.MAX_CONSECUTIVE_FAILURES:
            self._channel_disabled_at[channel] = time.time()
            logger.error(
                f"Channel '{channel}' circuit opened after {failures} consecutive failures. "
                f"Will re-try in {self.CIRCUIT_BREAKER_COOLDOWN}s."
            )

    async def _send_with_retry(self, channel: str, send_fn, *args, **kwargs) -> bool:
        """Send with one retry using exponential backoff + jitter."""
        if self._should_skip_channel(channel):
            logger.warning(
                f"Skipping channel '{channel}' — circuit breaker open for {int(time.time() - self._channel_disabled_at.get(channel, 0))}s"
            )
            return False

        for attempt in range(2):  # Attempt 0 and attempt 1
            try:
                success = await send_fn(*args, **kwargs)
                if success:
                    self._record_success(channel)
                    return True
                # send_fn returned False (e.g., API returned non-200)
                if attempt == 0:
                    wait = 1.0 + random.random()  # 1–2s jitter
                    logger.info(f"Retrying {channel} in {wait:.1f}s (attempt {attempt + 1})")
                    await asyncio.sleep(wait)
            except Exception as e:
                logger.warning(f"{channel} attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    wait = 1.0 + random.random()
                    await asyncio.sleep(wait)

        self._record_failure(channel)
        return False

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
        """Send SMS via Twilio (preferred) or Termii (fallback)."""
        to = normalize_phone_to_e164(to, settings.PHONE_COUNTRY_CODE)
        tmpl = self.ALERT_TEMPLATES.get(template, {})
        message = tmpl.get("sms", "").format(**data)

        # ── Preferred: Twilio SMS (same account as WhatsApp) ─────────────
        if settings.TWILIO_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_SMS_FROM:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
                        auth=(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN),
                        data={
                            "To": to,
                            "From": settings.TWILIO_SMS_FROM,
                            "Body": message,
                        },
                        timeout=10,
                    )
                    if response.status_code in (200, 201):
                        return True
                    logger.warning(
                        f"Twilio SMS returned {response.status_code}: {response.text[:300]}"
                    )
            except Exception as e:
                logger.warning(f"Twilio SMS send failed: {e}")
                # fall through to Termii fallback below

        # ── Fallback: Termii API (Nigerian provider) ──────────────────────
        if not settings.TERMII_API_KEY:
            return False

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
        """Send WhatsApp message via Twilio.

        Two modes:
        1. TEMPLATE (recommended for business-initiated alerts like theft):
           When MT_TWILIO_WHATSAPP_TEMPLATE_SID is set, sends ContentSid +
           ContentVariables. Templates work OUTSIDE the 24h window, so real
           theft alerts always deliver. Placeholder variables come from
           MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES (defaults to location/time/score).
        2. FREE-FORM (sandbox / within the 24h window): when no template SID
           is configured, falls back to Body text.

        Recipient must have joined the Twilio sandbox first (send the join
        keyword to the sandbox number) or be approved for the production
        WhatsApp sender. If you see 63010/63017/63018 in the logs, the template
        is missing, unapproved, or the variables don't match the template.
        """
        if not settings.TWILIO_SID or not settings.TWILIO_AUTH_TOKEN:
            return False

        to = normalize_phone_to_e164(to, settings.PHONE_COUNTRY_CODE)
        tmpl = self.ALERT_TEMPLATES.get(template, {})

        # Build the payload: template mode (ContentSid) or free-form (Body)
        payload: dict = {
            "To": f"whatsapp:{to}",
            "From": settings.TWILIO_WHATSAPP_FROM,
        }
        if settings.TWILIO_WHATSAPP_TEMPLATE_SID:
            variables = dict(settings.TWILIO_WHATSAPP_TEMPLATE_VARIABLES) or DEFAULT_WHATSAPP_TEMPLATE_VARIABLES
            content_variables = {k: str(data.get(v, "")) for k, v in variables.items()}
            payload["ContentSid"] = settings.TWILIO_WHATSAPP_TEMPLATE_SID
            payload["ContentVariables"] = json.dumps(content_variables)
        else:
            # Only build the free-form text when actually using Body — avoids
            # dead work and a KeyError risk in template mode when data lacks
            # a key the SMS template references.
            message = tmpl.get("sms", "").format(**data)  # Reuse SMS template
            payload["Body"] = message

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
                    auth=(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN),
                    data=payload,
                    timeout=10,
                )
                if response.status_code in (200, 201):
                    return True
                body = response.text[:300]
                logger.warning(f"Twilio WhatsApp returned {response.status_code}: {body}")
                if any(code in body for code in ("63010", "63016", "63017", "63018")):
                    logger.warning(
                        "WhatsApp message rejected — template problem. Set "
                        "MT_TWILIO_WHATSAPP_TEMPLATE_SID to an approved Content "
                        "template (HX...) and ensure MT_TWILIO_WHATSAPP_TEMPLATE_"
                        "VARIABLES maps placeholders to data keys (location, time, "
                        "score). Within the 24h window free-form Body works without "
                        "a template."
                    )
                return False
        except Exception as e:
            logger.warning(f"WhatsApp send failed: {e}")
            return False

    async def send_all(
        self, device_id: str, alert_type: str, data: dict, channels: list[str] = None
    ) -> dict[str, bool]:
        """
        Send alert via all configured channels.
        Returns dict of channel -> success status.
        """
        if channels is None:
            # Email is optional — included when configured; WhatsApp is a core
            # channel alongside SMS and push (phone number required).
            channels = ["email", "whatsapp", "sms", "push"]

        results = {}

        # Get alert recipients from device settings
        email_to = data.get("email") or os.environ.get("MT_ALERT_EMAIL")
        phone_to = data.get("phone") or os.environ.get("MT_ALERT_PHONE")
        if phone_to:
            phone_to = normalize_phone_to_e164(phone_to, settings.PHONE_COUNTRY_CODE)

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
                        (device_id,),
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
                success = await self._send_with_retry("email", self.send_email, email_to, alert_type, data)
            elif channel == "sms" and phone_to:
                success = await self._send_with_retry("sms", self.send_sms, phone_to, alert_type, data)
            elif channel == "push":
                # Send push to all registered FCM tokens
                if push_tokens:
                    for token in push_tokens:
                        token_success = await self._send_with_retry("push", self.send_push, token, alert_type, data)
                        if token_success:
                            success = True  # At least one succeeded
            elif channel == "whatsapp" and phone_to and settings.TWILIO_SID and settings.TWILIO_AUTH_TOKEN:
                # Skip silently when Twilio isn't fully configured (send_whatsapp
                # requires BOTH SID and Auth Token) — avoids needless retries and
                # circuit-breaker failures for a channel that was never set up
                # (mirrors how email only fires when email_to exists).
                success = await self._send_with_retry("whatsapp", self.send_whatsapp, phone_to, alert_type, data)

            results[channel] = success

            # Log alert to database
            recipient = email_to if channel == "email" else (phone_to if channel in ("sms", "whatsapp") else "fcm")
            # Template mode tolerates missing data keys, so format defensively:
            # missing keys become empty strings instead of raising KeyError.
            safe_data = {k: (v if v is not None else "") for k, v in data.items()}
            message_text = self.ALERT_TEMPLATES.get(alert_type, {}).get("sms", "")
            try:
                log_message = message_text.format(**safe_data)
            except (KeyError, IndexError):
                log_message = message_text  # fall back to raw template
            with get_db_context() as conn:
                conn.execute(
                    """INSERT INTO alerts (device_id, alert_type, channel, recipient, message, delivered)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        device_id,
                        alert_type,
                        channel,
                        recipient,
                        log_message,
                        success,
                    ),
                )
                conn.commit()

        return results


# Singleton
alert_engine = AlertEngine()
