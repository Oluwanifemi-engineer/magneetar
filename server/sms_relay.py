"""
Magneetar Offline Command Relay (SMS)

The core of the "no internet" story: when a device is offline (no data), the
dashboard can still reach it over the cellular SMS channel — every phone
receives SMS even with zero data plan. This module:

  1. Builds the wire-format command SMS (MAGNET ...) that the Android app's
     SmsCommandReceiver parses and executes locally.
  2. Sends it through the SAME Twilio (preferred) / Termii (fallback)
     pipeline as the alert engine, so the relay requires zero new
     infrastructure and inherits the existing E.164 normalization.
  3. Parses the phone's best-effort SMS reply ("MT-ACK #<id> <status>") for
     the /api/sms/inbound Twilio webhook — the instant return channel when
     the device can send SMS (the network outbox is the reliable default).

Security model:
  - The SMS carries the device's pairing code (first 8 hex chars of
    SHA-256(device_key)) as its auth token. The app holds the raw device_key
    and derives the same code locally (PairingCode.kt), so verification
    needs no shared secret distribution and no server round-trip.
  - A random SMS to the victim's number can therefore NOT trigger commands
    without the 32-bit pairing code. Brute force is impractical: each guess
    must be delivered as a real SMS (carrier-gated, visible to the owner),
    and the app rate-limits bad codes.
  - Defense in depth (sender allowlist): the app only accepts commands from
    the server's relay number (TWILIO_SMS_FROM, exposed via /api/config) or
    the Termii alphanumeric "Magneetar" sender — so a leaked/intercepted
    pairing code can't be replayed from a random number.
  - Commands are only relayed when the OWNER enabled SMS commands for the
    device AND the device is offline (the poll channel is preferred whenever
    it works — SMS costs money), and each device is capped at 5 relays/min
    server-side (cost/abuse control).
  - The return channel is Twilio-signature-verified (only genuine Twilio
    traffic can drive acks) and sender-matched to the device's sms_phone, so
    a stranger can never ack (or forge) another device's commands.
"""

import logging
import re

from alerts import normalize_phone_to_e164
from config import settings

logger = logging.getLogger(__name__)

# Wire format: MAGNET <pairing-code> CMD <command_id> <command> [params]
# The Android SmsCommandReceiver parses exactly this (see SmsCommand.kt) —
# keep both sides in sync. Tokens are space-separated and ASCII-only so any
# carrier/encoding survives the trip.
PREFIX = "MAGNET"
CODE_LEN = 8

# The Termii fallback sender is the alphanumeric "Magneetar" (alphanumeric
# senders can't be spoofed by another app the way numbers can be re-used);
# the Android app allowlists it alongside the Twilio number.
TERMII_ALPHANUMERIC_SENDER = "Magneetar"


def command_sms_body(device_key_hash: str, command_id: int, command: str, params: str = "") -> str:
    """Build the wire-format command SMS for one command.

    The pairing code is the first 8 hex chars of the stored SHA-256 device
    key hash — exactly what the app derives locally via PairingCode.of().
    """
    code = (device_key_hash or "")[:CODE_LEN]
    tokens = [PREFIX, code, "CMD", str(command_id), command]
    if params:
        tokens.append(params)
    return " ".join(tokens)


def _twilio_send(to: str, body: str) -> bool:
    """Send via Twilio Messages API (the same credentials alerts.py uses)."""
    import httpx

    if not (settings.TWILIO_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_SMS_FROM):
        return False
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
                auth=(settings.TWILIO_SID, settings.TWILIO_AUTH_TOKEN),
                data={
                    "To": to,
                    "From": settings.TWILIO_SMS_FROM,
                    "Body": body,
                },
            )
            if resp.status_code in (200, 201):
                return True
            logger.warning(f"SMS relay: Twilio returned {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        logger.warning(f"SMS relay: Twilio send failed: {e}")
    return False


def _termii_send(to: str, body: str) -> bool:
    """Send via Termii (Nigerian provider) as fallback."""
    import httpx

    if not settings.TERMII_API_KEY:
        return False
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://api.termii.com/api/sms/send",
                json={
                    "to": to,
                    "from": "Magneetar",
                    "sms": body,
                    "type": "plain",
                    "api_key": settings.TERMII_API_KEY,
                },
            )
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"SMS relay: Termii send failed: {e}")
    return False


def parse_ack_sms(body: str):
    """Parse the phone's SMS reply "MT-ACK #<id> <status>" → (id, status).

    Returns (command_id, "executed"|"failed") or None when the body is not a
    valid ack (e.g. a stray message to the relay number). Case-insensitive on
    the status; the Android app emits exactly this format (see
    TrackingService.replyViaSms).
    """
    if not body:
        return None
    m = re.match(r"^MT-ACK\s+#(\d+)\s+(executed|failed)$", body.strip(), re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), m.group(2).lower()


def send_command_sms(to: str, body: str) -> bool:
    """Deliver a command SMS to a phone number. Returns True on success.

    Prefers Twilio, falls back to Termii — identical ordering to the alert
    engine. Returns False (never raises) when no provider is configured or
    both providers reject, so the caller degrades gracefully.
    """
    to = normalize_phone_to_e164(to, settings.PHONE_COUNTRY_CODE)
    if _twilio_send(to, body):
        return True
    return _termii_send(to, body)
