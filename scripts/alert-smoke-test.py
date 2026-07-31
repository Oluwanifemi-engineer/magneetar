#!/usr/bin/env python3
"""
Magneetar — Alert Delivery Smoke Test
─────────────────────────────────────
Sends ONE real WhatsApp + SMS alert through Twilio and verifies delivery.
Designed to be run:
  - locally:  python3 scripts/alert-smoke-test.py  (reads server/.env)
  - in CI:    workflow_dispatch job that passes secrets as env vars

Never prints secret values (SID/token). Exit codes:
  0 = all configured channels delivered
  1 = config/format problem or auth failure
  2 = network error (could not reach Twilio during the auth check)
  3 = one or more channels failed to deliver (incl. network errors during send)
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env(path: Path) -> dict:
    """Parse an .env file (skip comments, last active value wins, strip quotes)."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def get_value(file_env: dict, key: str) -> str:
    """Env vars (CI secrets) take priority; fall back to the .env file."""
    return os.environ.get(key, "") or file_env.get(key, "")


def api_call(sid: str, token: str, path: str, data: dict = None) -> tuple:
    """Call Twilio REST API. Returns (status, parsed_json). status 0 = network error."""
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    if data:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}", data=body, headers=headers
        )
    else:
        req = urllib.request.Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}", headers=headers
        )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"message": str(e)}
    except Exception as e:
        return 0, {"message": str(e)}


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    file_env = load_env(repo_root / "server" / ".env")

    sid = get_value(file_env, "MT_TWILIO_SID")
    token = get_value(file_env, "MT_TWILIO_AUTH_TOKEN")
    sms_from = get_value(file_env, "MT_TWILIO_SMS_FROM")
    wa_from = get_value(file_env, "MT_TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"
    alert_phone = get_value(file_env, "MT_ALERT_PHONE")

    print("═" * 62)
    print("  Magneetar — Alert Delivery Smoke Test")
    print("═" * 62)

    problems = 0

    # ── Credential format checks ─────────────────────────────────────────
    sid_ok = len(sid) == 34 and sid.startswith("AC")
    token_ok = len(token) == 32
    print(f"[1] SID:      {'✅' if sid_ok else '❌'}  (len={len(sid)}, prefix={sid[:2]!r})")
    print(f"[2] Token:    {'✅' if token_ok else '❌'}  (len={len(token)})")
    if not sid_ok or not token_ok:
        print("    Fix MT_TWILIO_SID (34 chars, starts AC) and MT_TWILIO_AUTH_TOKEN (32 chars).")
        problems += 1

    phone_ok = alert_phone.startswith("+") and len(alert_phone) >= 8
    # Redact the middle digits — the phone is PII, not a secret, but keep the
    # script's 'never leaks' posture consistent.
    redacted_phone = alert_phone[:4] + "***" + alert_phone[-2:] if len(alert_phone) > 8 else alert_phone
    print(f"[3] Phone:    {'✅' if phone_ok else '❌'}  MT_ALERT_PHONE={redacted_phone}")
    if not phone_ok:
        print("    MT_ALERT_PHONE must be E.164 (e.g. +2348081234567).")
        problems += 1

    sms_ok = sms_from.startswith("+") if sms_from else False
    print(f"[4] SMS From: {'✅' if sms_ok else '⚠️  unset (SMS skipped)'}  {sms_from or ''}")

    if problems:
        print(f"  ❌ {problems} config problem(s) — fix and re-run.")
        return 1

    # ── Live auth ────────────────────────────────────────────────────────
    status, body = api_call(sid, token, ".json")
    if status == 200:
        print(f"\n[5] Auth: ✅ Authenticated as '{body.get('friendly_name', '?')}'")
    elif status == 0:
        print(f"\n[5] Auth: ⚠️  Network error: {str(body.get('message'))[:120]}")
        return 2
    else:
        print(f"\n[5] Auth: ❌ HTTP {status}: {str(body.get('message'))[:120]}")
        print("    SID and Auth Token must belong to the SAME Twilio account.")
        return 1

    # ── Send real alerts ─────────────────────────────────────────────────
    failures = 0

    print("\n[6] WhatsApp send (real):")
    st, res = api_call(
        sid, token, "/Messages.json",
        {"To": f"whatsapp:{alert_phone}", "From": wa_from, "Body": "MAGNEETAR SMOKE TEST: Alert pipeline verified."},
    )
    if st in (200, 201):
        print(f"    ✅ Delivered (sid={res.get('sid', '?')})")
    else:
        msg = str(res.get("message", res))[:200]
        print(f"    ❌ HTTP {st}: {msg}")
        if any(c in msg for c in ("63010", "63016", "63017", "63018")):
            print("      → Template required outside the 24h window. Set")
            print("        MT_TWILIO_WHATSAPP_TEMPLATE_SID or test within the window.")
        failures += 1

    if sms_ok:
        print("\n[7] SMS send (real):")
        st, res = api_call(
            sid, token, "/Messages.json",
            {"To": alert_phone, "From": sms_from, "Body": "MAGNEETAR SMOKE TEST: SMS pipeline verified."},
        )
        if st in (200, 201):
            print(f"    ✅ Delivered (sid={res.get('sid', '?')})")
        else:
            print(f"    ❌ HTTP {st}: {str(res.get('message', res))[:200]}")
            failures += 1
    else:
        print("\n[7] SMS: ⏭  skipped (MT_TWILIO_SMS_FROM unset)")

    print("\n" + "═" * 62)
    if failures == 0:
        print("  ✅ All configured channels delivered.")
        return 0
    print(f"  ❌ {failures} channel(s) failed — see above.")
    return 3


if __name__ == "__main__":
    sys.exit(main())
