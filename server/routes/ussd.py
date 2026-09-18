"""
Magneetar USSD — Minimal menu for feature phones.

Reaches the 60% of Nigerians who use feature phones.
Works on 2G/3G, no internet required.

Menu:
  *123# → Main Menu
    1 → Check device status (enter phone number)
    2 → Lock my phone
    3 → Trigger siren
    0 → Back

Security (fixed 2026-09-17):
- The callback is authenticated with a shared secret the aggregator sends
  (MT_USSD_WEBHOOK_SECRET, via the X-USSD-Secret header or a `secret` field).
  It previously had NO authentication of any kind: anyone who could POST to
  /ussd/callback could queue `lock` or `alarm` on any registered device by
  supplying its phone number, and read back its model + theft score. A USSD
  gateway cannot present a user credential, so the secret is the only thing
  standing in front of command issuance — with it unset, the endpoint now
  rejects everything instead of accepting everything.
- Commands are only accepted for devices OWNED by the caller. The calling
  number (`phoneNumber`, supplied by the telco — not by the user) must match
  the device's registered owner phone (`devices.alert_phone`).
- Sessions are shared via Redis when MT_REDIS_URL is set, so a multi-step menu
  survives across uvicorn workers; the in-process fallback is now bounded and
  TTL-expired instead of growing forever.
"""

import hmac
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from alerts import normalize_phone_to_e164
from cache_redis import get_redis_cache
from config import settings
from database import get_db_context
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse
from models import VALID_COMMANDS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ussd", tags=["ussd"])

# A USSD session is short-lived by nature; expire aggressively.
SESSION_TTL_SECONDS = 300
# Bound the in-process fallback (one entry per live session).
_SESSION_MAX_ENTRIES = 5000

# session_id -> (expires_at_epoch, session_dict)
_sessions: dict = {}


# ── Authentication ──────────────────────────────────────────────────────────


def _authenticate(request: Request, secret: str) -> None:
    """Require the aggregator's shared secret. Fails closed."""
    configured = settings.USSD_WEBHOOK_SECRET
    if not configured:
        logger.error(
            "USSD callback received but MT_USSD_WEBHOOK_SECRET is unset — "
            "rejecting. Set it and configure the aggregator to send it."
        )
        raise HTTPException(status_code=503, detail="USSD gateway not configured")

    provided = request.headers.get("X-USSD-Secret", "") or secret
    if not provided or not hmac.compare_digest(provided, configured):
        logger.warning("USSD callback: invalid or missing shared secret — rejecting")
        raise HTTPException(status_code=403, detail="Invalid USSD gateway credentials")


# ── Sessions ────────────────────────────────────────────────────────────────


def _session_key(session_id: str) -> str:
    return f"ussd:{session_id}"


def _get_session(session_id: str, phone: str) -> dict:
    """Load (or create) a session, shared across workers when Redis is up."""
    cache = get_redis_cache()
    if cache is not None:
        data = cache.get(_session_key(session_id))
        if data is None:
            data = {"phone": phone, "state": "main_menu", "data": {}}
        return data

    now = time.time()
    for key in [k for k, (expires, _) in _sessions.items() if expires < now]:
        _sessions.pop(key, None)
    entry = _sessions.get(session_id)
    if entry is None:
        session = {"phone": phone, "state": "main_menu", "data": {}}
    else:
        session = entry[1]
        session["phone"] = phone
    _sessions[session_id] = (now + SESSION_TTL_SECONDS, session)
    return session


def _save_session(session_id: str, session: dict) -> None:
    cache = get_redis_cache()
    if cache is not None:
        cache.set(_session_key(session_id), session, ttl=SESSION_TTL_SECONDS)
        return

    now = time.time()
    if len(_sessions) >= _SESSION_MAX_ENTRIES:
        # Drop the entry closest to expiry to keep the fallback bounded.
        oldest = min(_sessions, key=lambda k: _sessions[k][0])
        _sessions.pop(oldest, None)
    _sessions[session_id] = (now + SESSION_TTL_SECONDS, session)


# ── Device lookup / command queue ───────────────────────────────────────────


def _find_owned_device(target_phone: str, caller_phone: str) -> Optional[dict]:
    """Find a device by phone number ONLY if the caller owns it.

    `devices.sms_phone` is the phone's own SIM number — not a credential. The
    owner's identity is `devices.alert_phone`, set by an authenticated owner
    from the dashboard. A device with no owner phone recorded cannot be
    commanded over USSD.
    """
    with get_db_context() as db:
        rows = db.execute(
            "SELECT id, model, last_seen, sentinel_score, alert_phone FROM devices WHERE sms_phone=?",
            (target_phone,),
        ).fetchall()

    if not rows:
        return None

    caller = normalize_phone_to_e164(caller_phone, settings.PHONE_COUNTRY_CODE)
    for row in rows:
        owner_phone = (row["alert_phone"] or "").strip()
        if not owner_phone:
            continue
        if normalize_phone_to_e164(owner_phone, settings.PHONE_COUNTRY_CODE) == caller:
            return dict(row)

    logger.warning("USSD: device found but caller is not its owner — refusing")
    return None


def _clean_phone(raw: str) -> str:
    return re.sub(r"[^\d+]", "", (raw or "").strip())


def _issue_command(device_id: str, command: str) -> bool:
    """Queue a command for a device, validated against the canonical set."""
    if command not in VALID_COMMANDS:
        logger.error(f"USSD: refusing to queue unknown command {command!r}")
        return False

    with get_db_context() as db:
        now = datetime.now(timezone.utc).isoformat()
        expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        db.execute(
            "INSERT INTO commands"
            " (device_id, command, params, status, priority,"
            " issued_at, expires_at, delivery_channel)"
            " VALUES (?, ?, '', 'pending', 0, ?, ?, 'sms')",
            (device_id, command, now, expires),
        )
        db.commit()
    return True


# ── Callback ────────────────────────────────────────────────────────────────


@router.post("/callback")
async def ussd_callback(
    request: Request,
    sessionId: str = Form(""),
    phoneNumber: str = Form(""),
    text: str = Form(""),
    secret: str = Form(""),
):
    """Handle USSD callback from the telco gateway."""
    _authenticate(request, secret)

    session = _get_session(sessionId, phoneNumber)

    # Parse user input
    parts = text.split("*") if text else []
    choice = parts[-1] if parts else ""

    # Route based on state
    if session["state"] == "main_menu":
        response = _handle_main_menu(session, choice, sessionId)
    elif session["state"] == "check_device":
        response = _handle_check_device(session, choice, sessionId)
    elif session["state"] == "lock_phone":
        response = _handle_lock_phone(session, choice, sessionId)
    elif session["state"] == "trigger_siren":
        response = _handle_trigger_siren(session, choice, sessionId)
    else:
        response = _main_menu(sessionId)

    # Persist the (possibly mutated) session once, after routing — this is what
    # keeps multi-step menus working when the next step lands on another worker.
    _save_session(sessionId, session)
    return response


def _handle_main_menu(session: dict, choice: str, session_id: str) -> PlainTextResponse:
    if choice == "1":
        session["state"] = "check_device"
        return PlainTextResponse("CON Enter YOUR registered phone number:\n" "(e.g. 08012345678)")
    elif choice == "2":
        session["state"] = "lock_phone"
        return PlainTextResponse("CON Enter YOUR registered phone number to lock:\n" "(e.g. 08012345678)")
    elif choice == "3":
        session["state"] = "trigger_siren"
        return PlainTextResponse("CON Enter YOUR registered phone number for siren:\n" "(e.g. 08012345678)")
    return _main_menu(session_id)


def _handle_check_device(session: dict, choice: str, session_id: str) -> PlainTextResponse:
    phone = _clean_phone(choice)
    session["state"] = "main_menu"

    if len(re.sub(r"\D", "", phone)) < 10:
        return PlainTextResponse("END Invalid number. Dial again and enter a valid phone number.")

    device = _find_owned_device(phone, session["phone"])
    if not device:
        return PlainTextResponse("END No Magneetar device found for this number on your account.")

    last_seen = device["last_seen"] or "Never"
    score = device["sentinel_score"] or 0
    status = "STOLEN" if score >= 70 else "At risk" if score >= 40 else "Safe"

    return PlainTextResponse(
        f"END {device['model']}\n" f"Status: {status}\n" f"Last seen: {last_seen}\n" f"Theft score: {score}/100"
    )


def _handle_lock_phone(session: dict, choice: str, session_id: str) -> PlainTextResponse:
    phone = _clean_phone(choice)
    session["state"] = "main_menu"

    if len(re.sub(r"\D", "", phone)) < 10:
        return PlainTextResponse("END Invalid number. Dial again and enter a valid phone number.")

    device = _find_owned_device(phone, session["phone"])
    if not device:
        return PlainTextResponse("END No Magneetar device found for this number on your account.")

    if not _issue_command(device["id"], "lock"):
        return PlainTextResponse("END Could not queue the lock command. Try again.")

    return PlainTextResponse(f"END Lock command sent to {device['model']}.\n" "The phone will lock on next connection.")


def _handle_trigger_siren(session: dict, choice: str, session_id: str) -> PlainTextResponse:
    phone = _clean_phone(choice)
    session["state"] = "main_menu"

    if len(re.sub(r"\D", "", phone)) < 10:
        return PlainTextResponse("END Invalid number. Dial again and enter a valid phone number.")

    device = _find_owned_device(phone, session["phone"])
    if not device:
        return PlainTextResponse("END No Magneetar device found for this number on your account.")

    if not _issue_command(device["id"], "alarm"):
        return PlainTextResponse("END Could not queue the siren command. Try again.")

    return PlainTextResponse(
        f"END Siren command sent to {device['model']}.\n" "The alarm will sound on next connection."
    )


def _main_menu(session_id: str) -> PlainTextResponse:
    return PlainTextResponse(
        "CON Welcome to Magneetar\n"
        "Anti-theft protection for your phone\n\n"
        "1. Check device status\n"
        "2. Lock my phone\n"
        "3. Trigger siren\n\n"
        "0. Back"
    )
