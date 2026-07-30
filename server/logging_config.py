"""
Magneetar Logging Configuration
Structured JSON logging for production observability.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

# ─── Log Levels ──────────────────────────────────────────────────────────────

LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


# ─── Structured JSON Formatter ───────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for machine parsing and structured analysis."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        # Include extra fields
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry["extra"] = record.extra_data

        return json.dumps(log_entry, default=str)


# ─── Logger Factory ──────────────────────────────────────────────────────────


def get_logger(name: str, level: str = "info") -> logging.Logger:
    """Get a structured JSON logger."""
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVELS.get(level, logging.INFO))

    # Avoid adding handlers multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    return logger


# ─── Audit Logger ────────────────────────────────────────────────────────────


class AuditLogger:
    """Structured audit logging for security-relevant events."""

    def __init__(self):
        self.logger = get_logger("magneetar.audit")

    def log(
        self,
        action: str,
        actor: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[dict] = None,
        outcome: str = "success",
    ):
        """Log an audit event."""
        entry = {
            "audit": True,
            "action": action,
            "actor": actor or "system",
            "resource": resource or "unknown",
            "outcome": outcome,
            "details": details or {},
        }
        self.logger.info(json.dumps(entry, default=str))

    def security_event(
        self,
        event_type: str,
        severity: str,
        actor: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        """Log a security event with severity level."""
        entry = {
            "audit": True,
            "security": True,
            "event_type": event_type,
            "severity": severity,
            "actor": actor or "system",
            "details": details or {},
        }

        log_level = {
            "critical": self.logger.critical,
            "high": self.logger.error,
            "medium": self.logger.warning,
            "low": self.logger.info,
        }.get(severity, self.logger.info)

        log_level(json.dumps(entry, default=str))


# ─── Singleton ───────────────────────────────────────────────────────────────

audit_logger = AuditLogger()
