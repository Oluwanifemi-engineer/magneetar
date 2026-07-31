#!/usr/bin/env python3
"""
Magneetar — Twilio Configuration Checker
─────────────────────────────────────────
Verifies that the Twilio credentials in server/.env are valid and reports
what alert channels are actually usable.

Usage:
    python3 scripts/twilio-config-check.py

What it checks (and NEVER prints secret values):
  1. Format of MT_TWILIO_SID (must be 34 chars, start with "AC")
  2. Format of MT_TWILIO_AUTH_TOKEN (must be 32 chars)
  3. LIVE authentication against the Twilio REST API
  4. SMS-capable numbers on the account (what MT_TWILIO_SMS_FROM must be)
  5. Which alert channels are currently wired (WhatsApp / SMS / push / email)

Exit codes: 0 = all OK, 1 = config/credential problem, 2 = network error.
"""

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def load_env(path: Path) -> dict:
    """Parse an .env file into a dict (last active value wins, no expansion)."""
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        # Strip surrounding matching quotes (single or double)
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def api_call(sid: str, token: str, path: str) -> tuple:
    """Call the Twilio REST API. Returns (status_code, parsed_json_or_text).

    status_code == 0 signals a network error (not an HTTP response).
    """
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}{path}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
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
    env_path = repo_root / "server" / ".env"
    if not env_path.exists():
        print(f"❌ server/.env not found at {env_path}")
        return 1

    env = load_env(env_path)
    sid = env.get("MT_TWILIO_SID", "")
    token = env.get("MT_TWILIO_AUTH_TOKEN", "")
    sms_from = env.get("MT_TWILIO_SMS_FROM", "")
    wa_from = env.get("MT_TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    alert_phone = env.get("MT_ALERT_PHONE", "")
    termii = env.get("MT_TERMII_KEY", "")
    sendgrid = env.get("MT_SENDGRID_KEY", "")

    problems = 0
    network_error = False
    auth_ok = False

    print("═" * 62)
    print("  Magneetar — Twilio Configuration Checker")
    print("═" * 62)

    # ── 1. SID format ────────────────────────────────────────────────────
    sid_ok = len(sid) == 34 and sid.startswith("AC")
    print(f"\n[1] MT_TWILIO_SID:        {'✅ valid' if sid_ok else '❌ INVALID'} "
          f"(len={len(sid)}, prefix={sid[:2]!r})")
    if not sid_ok:
        print("    → Twilio Account SIDs are 34 chars starting with 'AC'.")
        print("      It is NOT the 6-digit code from your authenticator app.")
        print("      Find it at console.twilio.com → Dashboard → Account Info.")
        problems += 1

    # ── 2. Auth Token format ─────────────────────────────────────────────
    token_ok = len(token) == 32
    print(f"[2] MT_TWILIO_AUTH_TOKEN: {'✅ valid length' if token_ok else '❌ INVALID'} "
          f"(len={len(token)})")
    if not token_ok:
        print("    → Twilio Auth Tokens are exactly 32 characters.")
        problems += 1

    # ── 3. Live API auth ─────────────────────────────────────────────────
    print("\n[3] LIVE Twilio API authentication:")
    if sid_ok and token_ok:
        status, body = api_call(sid, token, ".json")
        if status == 200:
            auth_ok = True
            name = body.get("friendly_name") or body.get("name") or "unknown"
            acct_type = body.get("type", "unknown")
            print(f"    ✅ Authenticated as '{name}' ({acct_type})")
        elif status == 401:
            print("    ❌ HTTP 401 — credentials rejected by Twilio.")
            print("      Causes: SID and Auth Token are from DIFFERENT accounts,")
            print("      or the Auth Token was regenerated (old token dies instantly),")
            print("      or a copy/paste added spaces/newlines.")
            print("      Fix: console.twilio.com → Account Info → copy SID AND token")
            print("      from the SAME account, paste both, re-run this script.")
            problems += 1
        elif status == 0:
            network_error = True
            msg = body.get("message", body) if isinstance(body, dict) else body
            print(f"    ⚠️  Network error (could not reach Twilio): {str(msg)[:160]}")
            print("      Check internet connectivity and try again.")
        else:
            msg = body.get("message", body) if isinstance(body, dict) else body
            print(f"    ⚠️  HTTP {status}: {str(msg)[:160]}")
            problems += 1
    else:
        print("    ⏭  skipped (fix SID/token format first)")
        problems += 1

    # ── 4. SMS-capable numbers ───────────────────────────────────────────
    print("\n[4] SMS-capable numbers on the account:")
    if auth_ok:
        status, body = api_call(sid, token, "/IncomingPhoneNumbers.json?PageSize=20")
        if status == 200:
            nums = body.get("incoming_phone_numbers", [])
            if not nums:
                print("    ⚠️  No numbers found. On a trial account, a trial number")
                print("      exists — set MT_TWILIO_SMS_FROM to it (see Console →")
                print("      Phone Numbers). Verify the recipient before SMS works.")
            for n in nums:
                cap = n.get("capabilities", {})
                print(f"    • {n.get('friendly_name')}  SMS={cap.get('sms')}  "
                      f"Voice={cap.get('voice')}  ({n.get('status')})")
        else:
            print("    ⏭  skipped (numbers list request failed)")
    else:
        print("    ⏭  skipped (credentials must authenticate first)")

    # ── 5. Channel wiring summary ────────────────────────────────────────
    print("\n[5] Alert channel wiring:")
    if auth_ok:
        print(f"    WhatsApp: ✅ wired (From={wa_from})")
    else:
        print(f"    WhatsApp: ❌ blocked (credentials not authenticating) "
              f"(From={wa_from})")
    if auth_ok and sms_from:
        print(f"    SMS:      ✅ wired (From={sms_from})")
    elif termii:
        print("    SMS:      ⚠️  Twilio SMS From missing — falls back to Termii")
    else:
        print("    SMS:      ❌ no sender (set MT_TWILIO_SMS_FROM or MT_TERMII_KEY)")
    print(f"    Push:     {'✅ wired' if env.get('MT_FIREBASE_KEY') else '❌ not configured'}")
    print(f"    Email:    {'✅ wired' if sendgrid else '⏸ parked (SendGrid key empty)'}")
    print(f"    Alert phone (MT_ALERT_PHONE): "
          f"{'✅ set' if alert_phone else '❌ NOT SET — alerts cannot deliver'}")

    print("\n" + "═" * 62)
    if network_error:
        print("  ⚠️  Network error prevented full verification — retry.")
        return 2
    if problems == 0:
        print("  ✅ All Twilio checks passed.")
        if not alert_phone:
            print("  ⚠️  Still set MT_ALERT_PHONE so alerts have a recipient.")
        return 0
    print(f"  ❌ {problems} problem(s) found — see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
