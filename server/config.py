"""
Magneetar Server Configuration
All configuration from environment variables - NEVER hardcode secrets.
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if it exists
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings:
    """Central configuration - reads from environment variables."""

    # ── Core Security ──────────────────────────────────────────────────────
    API_KEY: str = os.environ.get("MT_API_KEY", "")
    JWT_SECRET: str = os.environ.get("MT_JWT_SECRET", "")
    ENCRYPTION_KEY: str = os.environ.get("MT_ENCRYPTION_KEY", "")

    # ── Database ───────────────────────────────────────────────────────────
    DB_PATH: str = os.environ.get("MT_DB_PATH", "magneetar.db")
    DATABASE_URL: str = os.environ.get("MT_DATABASE_URL", "")

    # ── Alert Services ─────────────────────────────────────────────────────
    SENDGRID_API_KEY: str = os.environ.get("MT_SENDGRID_KEY", "")
    TERMII_API_KEY: str = os.environ.get("MT_TERMII_KEY", "")
    TWILIO_SID: str = os.environ.get("MT_TWILIO_SID", "")
    TWILIO_AUTH_TOKEN: str = os.environ.get("MT_TWILIO_AUTH_TOKEN", "")
    # Twilio number used as the SMS sender (e.g. "+15551234567", SMS-capable).
    # On a trial account, use the Twilio-assigned trial number and verify
    # the recipient in the console before sending.
    TWILIO_SMS_FROM: str = os.environ.get("MT_TWILIO_SMS_FROM", "")
    # WhatsApp sender. Defaults to Twilio's shared sandbox number; replace with
    # your approved WhatsApp Business sender after sandbox onboarding.
    TWILIO_WHATSAPP_FROM: str = os.environ.get(
        "MT_TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"
    )
    FIREBASE_CREDENTIALS: str = os.environ.get("MT_FIREBASE_KEY", "")

    # ── Monitoring ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = os.environ.get("MT_SENTRY_DSN", "")

    # ── Environment ────────────────────────────────────────────────────────
    ENVIRONMENT: str = os.environ.get("MT_ENVIRONMENT", "development")

    # ── Limits ─────────────────────────────────────────────────────────────
    MAX_DEVICES_PER_USER: int = int(os.environ.get("MT_MAX_DEVICES", "5"))
    DATA_RETENTION_DAYS: int = int(os.environ.get("MT_RETENTION_DAYS", "90"))

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LOCATION_INTERVAL_MS: int = 2000  # 2 seconds between location reports
    RATE_LOGIN_ATTEMPTS: int = 5
    RATE_LOGIN_WINDOW_MINUTES: int = 10
    RATE_COMMAND_PER_MINUTE: int = 20  # Max commands per minute per dashboard user
    RATE_MEDIA_PER_MINUTE: int = 10  # Max media uploads per minute per device
    RATE_HEARTBEAT_PER_MINUTE: int = 10  # Max heartbeats per minute per device
    RATE_COMMAND_POLL_PER_MINUTE: int = 30  # Max command polls per minute per device

    # ── JWT Settings ───────────────────────────────────────────────────────
    JWT_ACCESS_EXPIRY_HOURS: int = 24
    JWT_REFRESH_EXPIRY_DAYS: int = 90

    # ── Sentinel Thresholds ────────────────────────────────────────────────
    THEFT_SCORE_THRESHOLD: int = 80  # Auto-activate theft mode
    ANOMALY_CONFIRMATION_COUNT: int = 3  # Consecutive anomalies to escalate

    # ── Server ─────────────────────────────────────────────────────────────
    HOST: str = os.environ.get("MT_HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("MT_PORT", "8000"))
    LOG_LEVEL: str = os.environ.get("MT_LOG_LEVEL", "info")

    # ── Reliability ────────────────────────────────────────────────────────
    REQUEST_TIMEOUT_SECONDS: int = int(os.environ.get("MT_REQUEST_TIMEOUT", "30"))

    def validate(self) -> list[str]:
        """Validate required settings. Returns list of errors (empty if valid)."""
        errors = []

        if not self.API_KEY or len(self.API_KEY) < 32:
            errors.append("MT_API_KEY must be at least 32 characters")

        if not self.JWT_SECRET or len(self.JWT_SECRET) < 64:
            errors.append("MT_JWT_SECRET must be at least 64 characters")

        if not self.ENCRYPTION_KEY:
            errors.append("MT_ENCRYPTION_KEY is required (32 bytes hex)")
        else:
            try:
                key_bytes = bytes.fromhex(self.ENCRYPTION_KEY)
                if len(key_bytes) != 32:
                    errors.append("MT_ENCRYPTION_KEY must be exactly 32 bytes (64 hex chars)")
            except ValueError:
                errors.append("MT_ENCRYPTION_KEY must be valid hex")

        return errors

    def validate_optional(self) -> list[str]:
        """Validate OPTIONAL integrations. Returns warnings (non-fatal).

        A misconfigured optional service (e.g. a Twilio SID typo) should NOT
        prevent the server from starting — tracking, the dashboard, and other
        channels must keep working. The alert circuit breaker degrades
        gracefully instead.
        """
        warnings = []

        # Twilio Account SIDs always start with "AC" (e.g. ACxxxxxxxx...). A
        # wrong prefix (like a pasted User SID starting with "US") causes every
        # WhatsApp/SMS send to fail with HTTP 401 — warn here instead.
        if self.TWILIO_SID and not (len(self.TWILIO_SID) == 34 and self.TWILIO_SID.startswith("AC")):
            warnings.append(
                "MT_TWILIO_SID looks invalid: Twilio Account SIDs are 34 chars "
                "and start with 'AC' (current value starts with "
                f"'{self.TWILIO_SID[:2]}'). Check the Twilio Console > Account Info."
            )

        if self.TWILIO_SMS_FROM and not self.TWILIO_SMS_FROM.startswith("+"):
            warnings.append(
                "MT_TWILIO_SMS_FROM must be in E.164 format starting with '+', "
                f"e.g. +15551234567 (got: {self.TWILIO_SMS_FROM!r})"
            )

        # Twilio configured but no SMS sender → SMS silently no-ops (falls to
        # Termii, also usually unconfigured). Flag it so partial setup is obvious.
        if self.TWILIO_SID and self.TWILIO_AUTH_TOKEN and not self.TWILIO_SMS_FROM:
            warnings.append(
                "Twilio is configured but MT_TWILIO_SMS_FROM is empty — SMS via "
                "Twilio will not send. Set it to an SMS-capable Twilio number "
                "(e.g. +15551234567) to enable SMS alerts."
            )

        # Twilio Auth Tokens are 32 chars; a wrong-length token causes the same
        # silent 401s as a bad SID, so flag it for parity.
        if self.TWILIO_AUTH_TOKEN and len(self.TWILIO_AUTH_TOKEN) != 32:
            warnings.append(
                "MT_TWILIO_AUTH_TOKEN looks invalid: Twilio Auth Tokens are 32 "
                f"characters (current value is {len(self.TWILIO_AUTH_TOKEN)} chars). "
                "Check the Twilio Console > Account Info."
            )

        return warnings

    def generate_secrets(self) -> dict:
        """Generate secure random secrets for initial setup."""
        return {
            "MT_API_KEY": secrets.token_hex(32),
            "MT_JWT_SECRET": secrets.token_hex(64),
            "MT_ENCRYPTION_KEY": secrets.token_hex(32),
        }


def get_settings() -> Settings:
    """Get validated settings instance."""
    return Settings()


settings = get_settings()
