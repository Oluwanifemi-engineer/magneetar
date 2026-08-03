"""
Magneetar Server Configuration
All configuration from environment variables - NEVER hardcode secrets.
"""

import json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv


def _env_json_dict(name: str) -> dict:
    """Parse an env var containing a JSON object; returns {} on unset/invalid."""
    raw = os.environ.get(name, "")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


# Load .env file if it exists
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


# Default paid-tier device allowances. MT_PLAN_LIMITS (env) merges over these
# per-tier, so a partial override never drops a tier's default.
_PLAN_DEFAULTS: dict = {
    "personal": 3,
    "guardian": 10,
    "enterprise": 999,
    "admin": 999,
}


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
    TWILIO_WHATSAPP_FROM: str = os.environ.get("MT_TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    # WhatsApp Content API template (ContentSid, e.g. "HX..."). Business-
    # initiated alerts (theft, sim change...) arrive OUTSIDE the 24h window
    # where free-form Body is rejected — set this to an approved template so
    # alerts keep delivering. When empty, send_whatsapp falls back to Body.
    TWILIO_WHATSAPP_TEMPLATE_SID: str = os.environ.get("MT_TWILIO_WHATSAPP_TEMPLATE_SID", "")
    # JSON mapping of template placeholder ({{1}}, {{2}}...) to alert data keys,
    # e.g. '{"1": "location", "2": "time", "3": "score"}'. Unset/invalid JSON
    # degrades to a sensible default mapping.
    TWILIO_WHATSAPP_TEMPLATE_VARIABLES: dict = _env_json_dict("MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES")
    # Firebase service-account JSON for FCM v1 push alerts. Accepts a path to
    # a downloaded service-account key file OR the JSON contents as a string.
    # NOTE: the legacy FCM "server key" (API key) is deprecated since June
    # 2024 and does NOT work with firebase-admin — see scripts/firebase-setup.sh.
    FIREBASE_CREDENTIALS: str = os.environ.get("MT_FIREBASE_KEY", "")
    # Default country code for normalizing local phone numbers to E.164
    # (e.g. Nigerian "0808..." → "+234808..."). Override per region.
    PHONE_COUNTRY_CODE: str = os.environ.get("MT_COUNTRY_CODE", "234")

    # ── Monitoring ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = os.environ.get("MT_SENTRY_DSN", "")

    # ── Environment ────────────────────────────────────────────────────────
    ENVIRONMENT: str = os.environ.get("MT_ENVIRONMENT", "development")

    # ── Limits ─────────────────────────────────────────────────────────────
    # Free-tier device allowance (default 1 — "free for one device").
    MAX_DEVICES_PER_USER: int = int(os.environ.get("MT_MAX_DEVICES", "1"))
    # Device allowance per PAID tier. Overridable as a JSON object via
    # MT_PLAN_LIMITS, e.g. '{"personal": 3, "guardian": 10, "enterprise": 999}'.
    # A partial override MERGES over the defaults (never replaces them), so
    # omitting a tier keeps its default instead of silently granting unlimited.
    # plan_device_limit() resolves a user's allowance from their tier.
    PLAN_DEVICE_LIMITS: dict = {
        **_PLAN_DEFAULTS,
        **_env_json_dict("MT_PLAN_LIMITS"),
    }
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

    # ── Offline Monitor ────────────────────────────────────────────────────
    # A device is considered offline (and its owner alerted) after this many
    # minutes without any heartbeat/location. Floor of 10 minutes is enforced
    # in the monitor so a bad config can never spam alerts.
    OFFLINE_ALERT_MINUTES: int = int(os.environ.get("MT_OFFLINE_ALERT_MINUTES", "30"))

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

        # WhatsApp Content template SIDs always start with "HX".
        if self.TWILIO_WHATSAPP_TEMPLATE_SID and not self.TWILIO_WHATSAPP_TEMPLATE_SID.startswith("HX"):
            warnings.append(
                "MT_TWILIO_WHATSAPP_TEMPLATE_SID looks invalid: Twilio Content "
                "template SIDs start with 'HX' (current value starts with "
                f"'{self.TWILIO_WHATSAPP_TEMPLATE_SID[:2]}'). Find it in the "
                "Twilio Console > Content > Templates."
            )

        # Firebase: flag legacy API keys ("AIza...") which were deprecated by
        # Google in June 2024 and silently fail with firebase-admin. MT_FIREBASE_KEY
        # must be a service-account JSON path or JSON string instead.
        fcm = self.FIREBASE_CREDENTIALS.strip()
        if fcm.startswith("AIza"):
            warnings.append(
                "MT_FIREBASE_KEY looks like the legacy FCM server key (starts with "
                "'AIza'). That key type was deprecated by Google in June 2024 and "
                "does NOT work with firebase-admin — set it to a service-account "
                "JSON path or JSON string instead (see scripts/firebase-setup.sh)."
            )
        elif fcm and not fcm.startswith("{") and not os.path.exists(fcm):
            warnings.append(
                f"MT_FIREBASE_KEY points to a file that doesn't exist: {fcm!r}. "
                "Push alerts will be skipped until a valid service-account JSON "
                "path (or JSON string) is configured."
            )

        # Template variables JSON must be an object if provided.
        raw_vars = os.environ.get("MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES", "")
        if raw_vars.strip():
            try:
                parsed = json.loads(raw_vars)
                if not isinstance(parsed, dict):
                    warnings.append(
                        "MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES must be a JSON object "
                        'like {"1": "location"} (got a non-object). Using defaults.'
                    )
            except (ValueError, TypeError):
                warnings.append("MT_TWILIO_WHATSAPP_TEMPLATE_VARIABLES is not valid JSON — using defaults.")

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


def plan_device_limit(tier: str) -> int:
    """Max devices a user of the given tier may own.

    free (and unknown/blank tiers) use MAX_DEVICES_PER_USER so the free
    allowance stays operator-tunable via MT_MAX_DEVICES (default 1 device);
    paid tiers use PLAN_DEVICE_LIMITS (personal=3, guardian=10, enterprise
    and admin=unlimited). Unrecognised tiers fall back to the free allowance
    — never unlimited — so a typo'd tier can't silently grant everything.
    """
    tier = (tier or "").strip().lower()
    if tier in ("", "free"):
        return settings.MAX_DEVICES_PER_USER
    return settings.PLAN_DEVICE_LIMITS.get(tier, settings.MAX_DEVICES_PER_USER)
