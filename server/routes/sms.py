"""
Magneetar SMS Inbound Webhook (extracted from main.py — Phase 0).

Handles Twilio inbound-SMS webhook — the SMS reply return channel.
When a device executes a command delivered via SMS, it replies with an
ACK that arrives here.

Separated from main.py to:
- Reduce main.py from 738 lines to < 400
- Make the Twilio signature verification testable independently
"""

import base64
import hashlib
import hmac
import urllib.parse
from datetime import datetime, timezone

from alerts import normalize_phone_to_e164
from config import settings
from database import check_rate_limit, get_db_context
from fastapi import APIRouter, HTTPException, Request
from logging_config import get_logger
from sms_relay import parse_ack_sms

logger = get_logger("magneetar")

router = APIRouter(tags=["SMS"])


@router.post("/api/sms/inbound")
async def sms_inbound_webhook(request: Request):
    """Twilio inbound-SMS webhook — the SMS reply return channel."""
    signature = request.headers.get("X-Twilio-Signature", "")
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not signature or not auth_token:
        raise HTTPException(status_code=403, detail="SMS inbound webhook not configured")

    form = dict(await request.form())
    from_number = (form.get("From") or "").strip()
    body = (form.get("Body") or "").strip()

    canonical_url = str(request.url)
    sorted_params = urllib.parse.urlencode(sorted(form.items()))
    expected = base64.b64encode(
        hmac.new(
            auth_token.encode(),
            f"{canonical_url}{sorted_params}".encode(),
            hashlib.sha1,
        ).digest()
    ).decode()
    if not hmac.compare_digest(expected, signature):
        logger.warning("SMS inbound: Twilio signature mismatch — rejecting")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    parsed = parse_ack_sms(body)
    if not parsed:
        return {"status": "ignored"}
    command_id, ack_status = parsed

    if not check_rate_limit(f"sms_inbound:{from_number}", "sms_inbound", 10, 1):
        logger.warning(f"SMS inbound: rate limited for sender {from_number}")
        raise HTTPException(status_code=429, detail="SMS inbound rate limit exceeded")

    with get_db_context() as conn:
        row = conn.execute(
            "SELECT c.device_id, c.status, d.sms_phone FROM commands c "
            "JOIN devices d ON c.device_id=d.id "
            "WHERE c.id=? AND c.delivery_channel='sms'",
            (command_id,),
        ).fetchone()
        if not row:
            return {"status": "unknown_command"}
        if row["status"] != "pending":
            return {"status": "already_acknowledged"}

        device_phone = (row["sms_phone"] or "").strip()
        if not device_phone:
            return {"status": "no_phone_configured"}
        if normalize_phone_to_e164(from_number, settings.PHONE_COUNTRY_CODE) != normalize_phone_to_e164(
            device_phone, settings.PHONE_COUNTRY_CODE
        ):
            logger.warning(
                f"SMS inbound: ack for command {command_id} from " f"non-owner number {from_number} — rejecting"
            )
            return {"status": "sender_mismatch"}

        conn.execute(
            "UPDATE commands SET status=?, executed_at=? WHERE id=?",
            (ack_status, datetime.now(timezone.utc).isoformat(), command_id),
        )
        conn.commit()

    logger.info(
        "SMS inbound ack applied",
        extra={
            "extra_data": {
                "command_id": command_id,
                "status": ack_status,
                "device_id": row["device_id"],
            }
        },
    )
    return {"status": "acknowledged", "command_id": command_id}
