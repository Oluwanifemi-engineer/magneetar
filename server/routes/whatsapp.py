"""
Magneetar WhatsApp Bot — Minimal.

WhatsApp is how Nigerians communicate. This bot lets owners control their
devices by sending simple text commands.

Commands:
  LOCK <phone>   — Lock a device (Lost Mode)
  UNLOCK         — not supported: the device has no unlock command
  SOS <phone>    — Trigger alarm + capture evidence
  STATUS <phone> — Check device status
  HELP           — Show commands

Integration: WhatsApp Business API (Meta Cloud API) webhook.

Security (fixed 2026-09-17/18):
- The POST webhook VERIFIES Meta's `X-Hub-Signature-256` (HMAC-SHA256 of the
  raw body, keyed with the app secret). It previously processed whatever was
  POSTed: `settings.WHATSAPP_APP_SECRET` existed but was referenced nowhere, so
  anyone who could reach the endpoint could queue lock/alarm/photo/audio on any
  device by knowing its phone number.
- The GET verification handshake now actually binds Meta's DOTTED query keys
  (`hub.mode`, `hub.verify_token`, `hub.challenge`). Plain `hub_mode: str`
  parameters never matched what Meta sends, so real verification attempts
  could not succeed.
- Commands are only accepted from the device's registered OWNER phone
  (`devices.alert_phone`), not from any number that knows the target.
- Commands are validated against models.VALID_COMMANDS. The old path built raw
  INSERTs and accepted an "unlock" command that exists nowhere else.
- Both hooks fail CLOSED when their secrets are unset.
"""

import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from alerts import normalize_phone_to_e164
from config import settings
from database import check_rate_limit, get_db_context
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from models import VALID_COMMANDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Inbound messages allowed per sender per minute.
RATE_INBOUND_PER_MINUTE = 10


# ─── WhatsApp Webhook Verification (Meta's GET handshake) ────────────────────


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Meta calls this to verify the webhook endpoint.

    Fails closed: with MT_WHATSAPP_VERIFY_TOKEN unset there is nothing to
    compare against, so the handshake is refused instead of matching a
    hardcoded default the previous config shipped.

    Meta's handshake sends DOTTED query keys (`hub.mode=subscribe&...`).
    Declaring plain `hub_mode: str` parameters never binds them — the
    endpoint 403'd every real verification attempt until this switched to
    reading the query string directly. Both spellings are accepted because
    some proxies mangle dots into underscores.
    """
    qp = request.query_params
    hub_mode = qp.get("hub.mode", qp.get("hub_mode", ""))
    hub_verify_token = qp.get("hub.verify_token", qp.get("hub_verify_token", ""))
    hub_challenge = qp.get("hub.challenge", qp.get("hub_challenge", ""))
    if not settings.WHATSAPP_VERIFY_TOKEN:
        logger.error("WhatsApp webhook verification attempted but MT_WHATSAPP_VERIFY_TOKEN is unset")
        raise HTTPException(status_code=503, detail="WhatsApp webhook not configured")

    if hub_mode == "subscribe" and hmac.compare_digest(hub_verify_token, settings.WHATSAPP_VERIFY_TOKEN):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ─── WhatsApp Webhook Receiver ──────────────────────────────────────────────


def _verify_meta_signature(raw_body: bytes, header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 over the RAW request body."""
    secret = settings.WHATSAPP_APP_SECRET
    if not secret:
        return False
    if not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256=") :])


@router.post("/webhook")
async def receive_whatsapp_message(request: Request):
    """Receive incoming WhatsApp messages and respond."""
    raw_body = await request.body()

    # Fail closed: an unconfigured app secret means nothing can be verified.
    if not settings.WHATSAPP_APP_SECRET:
        logger.error(
            "WhatsApp webhook received but MT_WHATSAPP_APP_SECRET is unset — "
            "rejecting. Set it to the Meta app secret so payloads can be verified."
        )
        raise HTTPException(status_code=503, detail="WhatsApp webhook not configured")

    if not _verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning("WhatsApp webhook: signature mismatch — rejecting")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        body = json.loads(raw_body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    # Extract message
    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        messages = value.get("messages", [])
        if not messages:
            return {"status": "ok"}
        msg = messages[0]
        phone = msg["from"]
        text = msg["text"]["body"].strip().upper()
    except (KeyError, IndexError, TypeError):
        return {"status": "ok"}

    if not check_rate_limit(f"whatsapp:{phone}", "whatsapp_inbound", RATE_INBOUND_PER_MINUTE, 1):
        logger.warning(f"WhatsApp: rate limited for sender {phone}")
        return {"status": "ok"}

    # Parse and respond
    response = _handle_command(text, phone)
    if response:
        await _send_whatsapp_message(phone, response)

    return {"status": "ok"}


def _handle_command(text: str, phone: str) -> Optional[str]:
    """Parse command and return response text."""
    parts = text.split()
    if not parts:
        return None

    cmd = parts[0]

    if cmd == "HELP":
        return (
            "Magneetar Commands:\n\n"
            "LOCK <number> — Lock a device\n"
            "SOS <number> — Trigger alarm + capture\n"
            "STATUS <number> — Check device status\n"
            "HELP — Show this message\n\n"
            "Commands are accepted only from the phone number registered as the\n"
            "device's owner in your Magneetar dashboard."
        )

    if cmd in ("LOCK", "SOS", "STATUS"):
        if len(parts) < 2:
            return f"Usage: {cmd} <phone number>\nExample: {cmd} 08012345678"
        target_phone = parts[1]
        return _execute_command(cmd.lower(), target_phone, phone)

    return "I didn't understand that. Send HELP to see available commands."


def _execute_command(cmd: str, target_phone: str, sender_phone: str) -> str:
    """Execute a command on a device owned by `sender_phone`."""
    # Normalize phone number
    target_phone = re.sub(r"[^\d+]", "", target_phone)
    if len(re.sub(r"\D", "", target_phone)) < 10:
        return "Invalid phone number. Use format: 08012345678"

    device = _find_owned_device(target_phone, sender_phone)
    if not device:
        return (
            f"No Magneetar device found for {target_phone}.\n"
            "Either the device is not registered, or this WhatsApp number is not\n"
            "the owner number recorded for it in the dashboard."
        )

    if cmd == "status":
        last_seen = device["last_seen"] or "Never"
        score = device["sentinel_score"] or 0
        status = "STOLEN" if score >= 70 else "At risk" if score >= 40 else "Safe"
        return (
            f"Device: {device['model']}\n" f"Status: {status}\n" f"Last seen: {last_seen}\n" f"Theft score: {score}/100"
        )

    # Map the chat verb to the device's real command name.
    command_map = {"lock": "lock", "sos": "alarm"}
    internal_cmd = command_map.get(cmd)
    if not internal_cmd:
        return "Unknown command."

    if not _issue_command(device["id"], internal_cmd):
        return "Could not queue that command. Try again from the dashboard."

    if cmd == "sos":
        # Also capture evidence on SOS.
        _issue_command(device["id"], "capture_photo_front")
        _issue_command(device["id"], "capture_audio")
        return (
            f"EMERGENCY command sent to {device['model']}.\n"
            "Siren triggered + evidence capture activated.\n"
            "The phone will respond on next connection."
        )

    return f"{cmd.upper()} command sent to {device['model']}.\nWill execute on next connection."


def _find_owned_device(target_phone: str, sender_phone: str) -> Optional[dict]:
    """Find a device by phone number ONLY if the sender is its owner.

    `devices.sms_phone` is the phone's own SIM number (where the SMS relay
    sends commands) — not a credential. The owner's identity is
    `devices.alert_phone`, set by an authenticated owner from the dashboard.
    A device with no owner phone recorded therefore cannot be commanded over
    WhatsApp at all.
    """
    with get_db_context() as db:
        rows = db.execute(
            "SELECT id, model, last_seen, sentinel_score, alert_phone" " FROM devices WHERE sms_phone=?",
            (target_phone,),
        ).fetchall()

    if not rows:
        return None

    sender = normalize_phone_to_e164(sender_phone, settings.PHONE_COUNTRY_CODE)
    for row in rows:
        owner_phone = (row["alert_phone"] or "").strip()
        if not owner_phone:
            continue
        if normalize_phone_to_e164(owner_phone, settings.PHONE_COUNTRY_CODE) == sender:
            return dict(row)

    logger.warning(
        "WhatsApp: device found but sender is not its owner — refusing",
        extra={"extra_data": {"target": target_phone}},
    )
    return None


def _issue_command(device_id: str, command: str) -> bool:
    """Queue a command for a device, validated against the canonical set."""
    if command not in VALID_COMMANDS:
        logger.error(f"WhatsApp: refusing to queue unknown command {command!r}")
        return False

    with get_db_context() as db:
        now = datetime.now(timezone.utc).isoformat()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        db.execute(
            "INSERT INTO commands"
            " (device_id, command, params, status, priority,"
            " issued_at, expires_at, delivery_channel)"
            " VALUES (?, ?, '', 'pending', 0, ?, ?, 'poll')",
            (device_id, command, now, expires),
        )
        db.commit()
    return True


async def _send_whatsapp_message(to: str, text: str):
    """Send a WhatsApp message via Meta Cloud API."""
    import httpx

    if not settings.WHATSAPP_ACCESS_TOKEN:
        logger.warning("WhatsApp access token not configured — message not sent")
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
                headers={
                    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text},
                },
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
