#!/usr/bin/env python3
"""
Magneetar — SIM-Change Live Probe (one-shot verification)
──────────────────────────────────────────────────────────
Fires a real `sim_changed` telemetry ping at the LIVE server through the
same public device API the Android app uses, and verifies the always-deliver
alert actually fires (alerts table gains sim_changed rows).

Use this after:
  1. your Twilio account is recharged (or you've wired a working SMS/WhatsApp
     channel), AND
  2. you want proof the SIM-swap path works end-to-end in production.

What it does:
  [1] registers a throwaway probe device (x-api-key = MT_DEVICE_KEY — the
      same low-privilege key the public APK embeds),
  [2] posts one location ping with sim_changed=true (Lagos coords, exactly
      like server/tests/test_sim_change.py does),
  [3] reads the alerts table from the running server container and confirms
      ≥1 sim_changed row exists for the probe device,
  [4] deletes the probe device + its alerts/locations/heartbeats (self-clean).

Exit codes:
  0 = alert fired & delivered (all channels)
  1 = alert did not fire (setup/verification failure)
  2 = verification impossible (docker/container/DB unreachable)
  3 = alert fired but one or more channels failed to deliver

Never prints secret values (device key, tokens).
"""

import ast
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("MT_API_BASE", "https://api.magneetar.me")
CONTAINER = os.environ.get("MT_SERVER_CONTAINER", "magneetar-server")
# Read the live version from the repo VERSION file so the probe always
# reports the CURRENT build (the UA mimics the real Android app).
_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
APP_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "1.4.4"


def load_env(path: Path) -> dict:
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
    return os.environ.get(key, "") or file_env.get(key, "")


def call(method: str, path: str, headers: dict, payload: dict = None):
    """Returns (status, parsed body-or-text)."""
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = dict(headers)
    # Cloudflare's edge bot-scoring flags the default urllib UA; a real
    # mobile-ish UA keeps the probe hitting the app (same as the Android app).
    hdrs.setdefault("User-Agent", f"MagneetarAndroid/{APP_VERSION} (okhttp/4.12)")
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"detail": str(e)}
    except Exception as e:
        return 0, {"detail": str(e)}


def read_alert_rows(device_id: str):
    """Query the live server DB for sim_changed alert rows for this device.

    Returns:
      list  — rows found (possibly empty = alert never logged)
      None  — verification was IMPOSSIBLE (docker/container unreachable),
              so "no rows" must NOT be interpreted as "alert didn't fire"
    """
    py = (
        "import sqlite3,os,sys;"
        "db=sqlite3.connect(os.environ.get('MT_DB_PATH') or '/app/data/magneetar.db');"
        "db.row_factory=sqlite3.Row;"
        "rows=db.execute(\"SELECT channel, delivered, sent_at FROM alerts "
        "WHERE device_id=? AND alert_type='sim_changed' ORDER BY id\", (sys.argv[1],)).fetchall();"
        "[print(dict(r)) for r in rows]"
    )
    try:
        out = subprocess.run(
            ["docker", "exec", CONTAINER, "python3", "-c", py, device_id],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        print("    ⚠️  docker not available on this host — cannot verify DB rows.")
        return None
    except subprocess.TimeoutExpired:
        print("    ⚠️  docker exec timed out — cannot verify DB rows.")
        return None
    if out.returncode != 0:
        print(f"    ⚠️  docker exec failed: {out.stderr.strip()[:200]}")
        return None
    rows = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            # docker stdout carries Python dict reprs (single-quoted) — not
            # valid JSON, so ast.literal_eval is the correct parser.
            try:
                rows.append(ast.literal_eval(line))
            except (ValueError, SyntaxError):
                pass
    return rows


def cleanup(device_id: str):
    """Best-effort removal of every row the probe can create. The device_id is
    passed as argv (never interpolated into SQL) so parameter binding applies
    everywhere — matching the parameterized style of read_alert_rows.

    Tables covered (all device_id-keyed, plus audit_log's actor column which
    register writes as the device id): alerts, locations, heartbeats,
    fcm_tokens, commands, media, evidence_cases, geofences,
    recovery_requests, audit_log. (rate_limits is keyed by identifier and
    recovery_sightings by request_id — the probe flow never writes them.)
    """
    py = (
        "import sqlite3,os,sys;"
        "db=sqlite3.connect(os.environ.get('MT_DB_PATH') or '/app/data/magneetar.db');"
        "cur=db.cursor(); did=sys.argv[1];"
        "[cur.execute(f'DELETE FROM {t} WHERE device_id=?', (did,)) "
        "for t in ('alerts','locations','heartbeats','fcm_tokens','commands',"
        "'media','evidence_cases','geofences','recovery_requests')];"
        "cur.execute('DELETE FROM audit_log WHERE actor=?', (did,));"
        "cur.execute('DELETE FROM devices WHERE id=?', (did,));"
        "db.commit(); print('cleaned')"
    )
    try:
        out = subprocess.run(
            ["docker", "exec", CONTAINER, "python3", "-c", py, device_id],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode != 0:
            print(f"    ⚠️  cleanup warning: {out.stderr.strip()[:150]}")
    except Exception as e:
        print(f"    ⚠️  cleanup skipped: {e}")


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    file_env = load_env(repo_root / "server" / ".env")
    device_key = get_value(file_env, "MT_DEVICE_KEY")
    if not device_key:
        print("❌ MT_DEVICE_KEY not found in server/.env — cannot authenticate the probe.")
        return 1

    device_id = "mt-probe-" + secrets.token_hex(4)
    print("═" * 62)
    print("  Magneetar — SIM-Change Live Probe")
    print("═" * 62)
    print(f"  API:      {API_BASE}")
    print(f"  Device:   {device_id}")
    print()

    # ── [1] Register the throwaway device ──────────────────────────────
    status, body = call(
        "POST", "/api/device/register",
        {"x-api-key": device_key, "Content-Type": "application/json"},
        {
            "device_id": device_id,
            "fingerprint": "sim-probe-fingerprint",
            "model": "SIM Probe",
            "os_version": "probe",
            "app_version": APP_VERSION,
        },
    )
    if status != 200:
        print(f"❌ [1] Register failed: HTTP {status} {str(body)[:200]}")
        return 1
    token = body.get("token") or body.get("access_token")
    if not token:
        print(f"❌ [1] Register succeeded but no token in response: {str(body)[:200]}")
        cleanup(device_id)
        return 1
    print("✅ [1] Device registered (device-scope JWT issued)")

    # ── [2] Fire the SIM-change telemetry ping ─────────────────────────
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    status, body = call(
        "POST", "/api/device/location", headers,
        {
            "device_id": device_id,
            "lat": 6.5244,
            "lng": 3.3792,
            "accuracy_horizontal": 12.0,
            "speed": 1.0,
            "provider": "gps",
            "confidence_level": "HIGH",
            "is_location_enabled": True,
            "is_airplane_mode": False,
            "sim_changed": True,
            "ping_sequence": 1,
        },
    )
    if status != 200:
        print(f"❌ [2] Location post failed: HTTP {status} {str(body)[:200]}")
        cleanup(device_id)
        return 1
    print("✅ [2] sim_changed=true location ping accepted by server")
    print("      (alert dispatch runs async — polling for delivery attempt...)")

    # ── [3] Verify the alert was logged (poll: rows land per-channel as each
    #        send completes — email ~0s, push ~3s, slow providers later) ─────
    rows = None
    for _ in range(8):
        rows = read_alert_rows(device_id)
        if rows is None:
            print("⚠️  [3] Could NOT verify the alert — docker/container unreachable.")
            print("      The ping WAS accepted; re-run after checking the server container.")
            cleanup(device_id)
            return 2
        if rows:
            break
        time.sleep(2)
    if not rows:
        print("❌ [3] No sim_changed alert rows found in the server DB.")
        print("      The always-deliver alert did NOT fire.")
        cleanup(device_id)
        return 1
    print(f"✅ [3] sim_changed alert logged ({len(rows)} channel row(s)):")
    for r in rows:
        delivered = "✅ delivered" if r.get("delivered") else "❌ failed"
        print(f"      • {r.get('channel', '?'):<9} {delivered}  @ {r.get('sent_at')}")

    # ── [4] Self-clean ─────────────────────────────────────────────────
    cleanup(device_id)
    print("🧹 [4] Probe device + its rows cleaned from the DB")
    print("\n" + "═" * 62)
    failed = [r for r in rows if not r.get("delivered")]
    if failed:
        print("  ⚠️  Alert FIRED but some delivery channels failed (see rows above).")
        print("     Run scripts/twilio-config-check.py + scripts/alert-smoke-test.py")
        print("     to diagnose the failing channel(s).")
        return 3
    print("  ✅ SIM-swap path verified end-to-end: alert fired AND delivered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
