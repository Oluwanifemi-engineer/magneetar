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
    # MASTER key — the operator's credential. Grants dashboard admin login
    # and admin-mode step-up. NEVER embedded in the APK.
    API_KEY: str = os.environ.get("MT_API_KEY", "")
    # DEVICE key — LOW-PRIVILEGE credential embedded in the public APK.
    # Scoped to device endpoints (register, location, media, fcm, commands)
    # ONLY; it must never mint dashboard/admin credentials. Distinct from the
    # master key so extracting it from the APK buys nothing.
    DEVICE_KEY: str = os.environ.get("MT_DEVICE_KEY", "")
    # LEGACY device key — the PRE-split master key, accepted for DEVICE-scope
    # auth only during the rotation grace period so already-installed APKs
    # (which embedded the old master key) keep working until users upgrade.
    # It grants no dashboard/admin access. Clear it once the installed fleet
    # has upgraded.
    LEGACY_DEVICE_KEY: str = os.environ.get("MT_LEGACY_DEVICE_KEY", "")
    JWT_SECRET: str = os.environ.get("MT_JWT_SECRET", "")
    ENCRYPTION_KEY: str = os.environ.get("MT_ENCRYPTION_KEY", "")

    # ── Database ───────────────────────────────────────────────────────────
    DB_PATH: str = os.environ.get("MT_DB_PATH", "magneetar.db")
    DATABASE_URL: str = os.environ.get("MT_DATABASE_URL", "")
    # Media files (evidence photos/audio/video) live on DISK, not in the DB
    # (see media_store.py). Default `media/` relative to the server CWD; set
    # to /app/media on the persisted volume in the Docker stack. media_store
    # resolves this live from the environment so tests can point it at a temp
    # dir without import-order games.
    MEDIA_DIR: str = os.environ.get("MT_MEDIA_DIR", "media")

    # ── Alert Services ─────────────────────────────────────────────────────
    SENDGRID_API_KEY: str = os.environ.get("MT_SENDGRID_KEY", "")
    TERMII_API_KEY: str = os.environ.get("MT_TERMII_KEY", "")
    TWILIO_SID: str = os.environ.get("MT_TWILIO_SID", "")
    TWILIO_AUTH_TOKEN: str = os.environ.get("MT_TWILIO_AUTH_TOKEN", "")
    # Twilio number used as the SMS sender (e.g. "+15551234567", SMS-capable).
    # On a trial account, use the Twilio-assigned trial number and verify
    # the recipient in the console before sending.
    # Optional cell-tower geolocation provider token (Unwired Labs etc.). The
    # offline command relay captures a cell fingerprint on the device and the
    # server resolves it to approximate coordinates. Graceful degradation: no
    # token → the raw fingerprint is still stored, "unresolved" is returned.
    CELL_LOOKUP_API_KEY: str = os.environ.get("MT_CELL_LOOKUP_API_KEY", "")
    # Optional override for the provider endpoint (Unwired Labs default).
    CELL_LOOKUP_URL: str = os.environ.get("MT_CELL_LOOKUP_URL", "https://us1.unwiredlabs.com/v2/process.php")

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
    # Base URL of the dashboard web app — used for links emailed to users
    # (password reset, email verification). Self-hosted deployments must set
    # this to their own dashboard origin.
    DASHBOARD_URL: str = os.environ.get("MT_DASHBOARD_URL", "https://app.magneetar.me")

    # ── Limits ─────────────────────────────────────────────────────────────
    # Free-tier device allowance (default 1 — "free for one device").
    MAX_DEVICES_PER_USER: int = int(os.environ.get("MT_MAX_DEVICES", "1"))
    # Cap on UNOWNED (not linked to any account) devices. The low-privilege
    # device key ships inside every APK, so anyone can register a device; this
    # bounds the storage-pollution surface so an attacker can't flood the
    # devices table
    # (locations/heartbeats/media can only be uploaded to YOUR OWN registered
    # ids, but thousands of junk rows still bloat the DB and dashboards).
    # Default 250: generous enough for a real deployment's transiently-unlinked
    # fleet (phones register with the embedded key, then link to an account on
    # sign-in) while still capping a single attacker's flood.
    MAX_UNOWNED_DEVICES: int = int(os.environ.get("MT_MAX_UNOWNED_DEVICES", "250"))
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
    # Login throttling is per-IP, but many Nigerian ISPs use CGNAT where a
    # whole neighborhood shares one public IP. A tight per-IP limit therefore
    # locks out legitimate users (a typo + a shared office/compound IP = 10
    # minutes of total lockout). 10 attempts / 15 min still stops credential
    # stuffing while tolerating shared addresses; the per-account timing-safe
    # verify is the real brute-force defense.
    RATE_LOGIN_ATTEMPTS: int = int(os.environ.get("MT_RATE_LOGIN_ATTEMPTS", "10"))
    RATE_LOGIN_WINDOW_MINUTES: int = int(os.environ.get("MT_RATE_LOGIN_WINDOW_MINUTES", "15"))
    # Account registration per IP — same CGNAT reasoning: a family/business
    # onboarding several phones behind one address must not be blocked.
    RATE_REGISTER_ATTEMPTS: int = int(os.environ.get("MT_RATE_REGISTER_ATTEMPTS", "10"))
    RATE_REGISTER_WINDOW_MINUTES: int = int(os.environ.get("MT_RATE_REGISTER_WINDOW_MINUTES", "10"))
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

    # Stale-device archive threshold — a device silent longer than this many
    # days is soft-archived (archived_at set). It stays in the DB with its
    # history; any fresh telemetry clears the flag. Default 30 days.
    ARCHIVE_AFTER_DAYS: int = int(os.environ.get("MT_ARCHIVE_AFTER_DAYS", "30"))

    # Fingerprint-dedup adoption window — when a reinstall registers a fresh
    # device_id with a fingerprint that matches an UNOWNED existing row, the
    # server adopts the old row as canonical only if it has been silent this
    # long (a reinstall goes silent the moment the app is removed; a
    # concurrently-reporting emulator/dual-app row reports recently and is
    # never hijacked). Rows owned by the SAME user are adopted regardless of
    # staleness. Default 24 hours.
    DEVICE_ADOPT_AFTER_HOURS: int = int(os.environ.get("MT_DEVICE_ADOPT_AFTER_HOURS", "24"))

    # ── Server ─────────────────────────────────────────────────────────────
    HOST: str = os.environ.get("MT_HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("MT_PORT", "8000"))
    LOG_LEVEL: str = os.environ.get("MT_LOG_LEVEL", "info")

    # ── Realtime Broadcast (multi-worker WebSocket fan-out) ────────────────
    # Redis URL for the pub/sub channel that keeps dashboard WebSockets
    # consistent when uvicorn runs with --workers > 1. Empty (default)
    # disables Redis: broadcasts are delivered locally in-process (single-
    # worker mode). When set, every worker publishes device updates to the
    # channel and a per-worker subscriber forwards them to that worker's
    # dashboard connections — so a location ping handled by worker A still
    # reaches dashboards connected to worker B. Degrades gracefully: a Redis
    # outage falls back to local delivery (dashboards keep polling).
    REDIS_URL: str = os.environ.get("MT_REDIS_URL", "")

    # ── Reliability ────────────────────────────────────────────────────────
    REQUEST_TIMEOUT_SECONDS: int = int(os.environ.get("MT_REQUEST_TIMEOUT", "30"))

    def validate(self) -> list[str]:
        """Validate required settings. Returns list of errors (empty if valid)."""
        errors = []

        if not self.API_KEY or len(self.API_KEY) < 32:
            errors.append("MT_API_KEY must be at least 32 characters")

        # The low-privilege device key is mandatory in production: the master
        # key must never end up embedded in the public APK again.
        if self.ENVIRONMENT == "production":
            if not self.DEVICE_KEY or len(self.DEVICE_KEY) < 32:
                errors.append("MT_DEVICE_KEY must be at least 32 characters (low-privilege device key for the APK)")
            elif self.DEVICE_KEY == self.API_KEY:
                errors.append("MT_DEVICE_KEY must differ from MT_API_KEY — the APK must not carry the master key")

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
            "MT_DEVICE_KEY": secrets.token_hex(32),
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
