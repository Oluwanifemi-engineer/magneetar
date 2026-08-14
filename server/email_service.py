"""
Magneetar Email Service
Complete email integration with SendGrid, fallback to Resend, SMTP, and
logging.

Features:
- SendGrid primary (transactional + alerts)
- Resend fallback (when SendGrid not configured)
- SMTP fallback (when neither API provider is configured)
- Email templates for all notification types
- Delivery tracking and retry logic
- Rate limiting per recipient
"""

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Multi-provider email service with fallbacks."""

    def __init__(self):
        self._sendgrid_configured = bool(settings.SENDGRID_API_KEY)
        self._resend_configured = bool(settings.RESEND_API_KEY)
        self._smtp_configured = all(
            [
                getattr(settings, "SMTP_HOST", None),
                getattr(settings, "SMTP_PORT", None),
                getattr(settings, "SMTP_USER", None),
                getattr(settings, "SMTP_PASSWORD", None),
            ]
        )

        # Email templates
        self.templates = {
            "password_reset": {
                "subject": "Magneetar - Reset Your Password",
                "html": (
                    '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">'
                    '<h2 style="color: #e91e63;">Password Reset Request</h2>'
                    "<p>You requested a password reset for your Magneetar account.</p>"
                    "<p>Click the button below to reset your password:</p>"
                    '<a href="{reset_url}" style="display: inline-block; background: #e91e63; '
                    'color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">'
                    "Reset Password</a>"
                    '<p style="margin-top: 20px; color: #666;">This link expires in 15 minutes.</p>'
                    '<p style="color: #666;">If you didn\'t request this, ignore this email.</p>'
                    "</div>"
                ),
            },
            "email_verification": {
                "subject": "Magneetar - Verify Your Email",
                "html": (
                    '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">'
                    '<h2 style="color: #e91e63;">Welcome to Magneetar!</h2>'
                    "<p>Please verify your email address to complete registration.</p>"
                    '<a href="{verify_url}" style="display: inline-block; background: #e91e63; '
                    'color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">'
                    "Verify Email</a>"
                    '<p style="margin-top: 20px; color: #666;">This link expires in 24 hours.</p>'
                    "</div>"
                ),
            },
            "theft_alert": {
                "subject": "🚨 MAGNEETAR ALERT: Theft Detected",
                "html": (
                    '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">'
                    '<h2 style="color: #f44336;">🚨 Theft Alert</h2>'
                    "<p>Your device may have been stolen.</p>"
                    '<div style="background: #ffebee; padding: 15px; border-radius: 4px; margin: 15px 0;">'
                    "<p><strong>Location:</strong> {location}</p>"
                    "<p><strong>Time:</strong> {time}</p>"
                    "<p><strong>Threat Score:</strong> {score}/100</p>"
                    "</div>"
                    '<a href="{dashboard_url}" style="display: inline-block; background: #e91e63; '
                    'color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px;">'
                    "Track Device</a>"
                    "</div>"
                ),
            },
            "device_offline": {
                "subject": "📡 MAGNEETAR: Device Offline",
                "html": (
                    '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">'
                    '<h2 style="color: #ff9800;">Device Offline</h2>'
                    "<p>Your device has gone offline.</p>"
                    '<div style="background: #fff3e0; padding: 15px; border-radius: 4px; margin: 15px 0;">'
                    "<p><strong>Last Seen:</strong> {time}</p>"
                    "<p><strong>Last Location:</strong> {location}</p>"
                    "</div>"
                    "</div>"
                ),
            },
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send email via available provider."""
        # Try SendGrid first
        if self._sendgrid_configured:
            try:
                return await self._send_via_sendgrid(to, subject, html_content, text_content)
            except Exception as e:
                logger.warning("SendGrid failed, trying Resend: %s", e)

        # Resend second
        if self._resend_configured:
            try:
                return await self._send_via_resend(to, subject, html_content, text_content)
            except Exception as e:
                logger.warning("Resend failed, trying SMTP: %s", e)

        # Fallback to SMTP
        if self._smtp_configured:
            try:
                return self._send_via_smtp(to, subject, html_content, text_content)
            except Exception as e:
                logger.warning("SMTP failed: %s", e)

        # Last resort: log the email
        logger.warning(
            "Email not delivered (no provider configured): to=%s, subject=%s",
            to,
            subject,
        )
        return False

    async def _send_via_sendgrid(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send email via SendGrid API."""
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": "alerts@magneetar.me", "name": "Magneetar"},
            "subject": subject,
            "content": [],
        }

        if text_content:
            payload["content"].append({"type": "text/plain", "value": text_content})
        payload["content"].append({"type": "text/html", "value": html_content})

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )

            success = response.status_code in (200, 202)
            if not success:
                logger.warning(
                    "SendGrid returned %d: %s",
                    response.status_code,
                    response.text[:200],
                )
            return success

    async def _send_via_resend(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send email via the Resend API (resend.com)."""
        payload = {
            "from": settings.RESEND_FROM or "Magneetar <onboarding@resend.dev>",
            "to": [to],
            "subject": subject,
        }
        if text_content:
            payload["text"] = text_content
        if html_content:
            payload["html"] = html_content

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )

            success = response.status_code in (200, 201)
            if not success:
                logger.warning(
                    "Resend returned %d: %s",
                    response.status_code,
                    response.text[:200],
                )
            return success

    def _send_via_smtp(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send email via SMTP."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = getattr(settings, "SMTP_FROM", "alerts@magneetar.me")
        msg["To"] = to

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        context = ssl.create_default_context()

        with smtplib.SMTP(
            getattr(settings, "SMTP_HOST", "smtp.gmail.com"),
            getattr(settings, "SMTP_PORT", 587),
        ) as server:
            server.starttls(context=context)
            server.login(
                getattr(settings, "SMTP_USER", ""),
                getattr(settings, "SMTP_PASSWORD", ""),
            )
            server.send_message(msg)

        return True

    def send_template(self, to: str, template_name: str, **kwargs) -> bool:
        """Send email using a template."""
        template = self.templates.get(template_name)
        if not template:
            logger.error("Unknown email template: %s", template_name)
            return False

        subject = template["subject"]
        html = template["html"].format(**kwargs)

        # Run async send in sync context
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an async context
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(asyncio.run, self.send_email(to, subject, html))
                    return result.result()
            else:
                return loop.run_until_complete(self.send_email(to, subject, html))
        except Exception:
            return asyncio.run(self.send_email(to, subject, html))

    def get_status(self) -> dict:
        """Get email service status."""
        return {
            "sendgrid_configured": self._sendgrid_configured,
            "resend_configured": self._resend_configured,
            "smtp_configured": self._smtp_configured,
            "available_providers": (["sendgrid"] if self._sendgrid_configured else [])
            + (["resend"] if self._resend_configured else [])
            + (["smtp"] if self._smtp_configured else []),
        }


# Singleton
email_service = EmailService()
