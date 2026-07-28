"""
Magneetar Server Configuration
All configuration from environment variables - NEVER hardcode secrets.
"""
import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
env_path = Path(__file__).parent / '.env'
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
    RATE_MEDIA_PER_MINUTE: int = 10   # Max media uploads per minute per device
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
