#!/usr/bin/env bash
# Soak-health check — verifies a device has been reporting continuously.
#
# Purpose: the G1 exit checklist requires every device to run ≥2 continuous
# weeks as a daily driver with NO silent-tracking-death. This script turns
# the ad-hoc DB queries used during the field validation into one command,
# so a dedicated 24h soak phone can be verified at a glance.
#
# Usage:
#   bash scripts/check-soak.sh <device_id> [hours]
#   bash scripts/check-soak.sh mt-9be468c1 24
#
# Checks (all on the live DB):
#   - heartbeats seen in the window (a rough liveness floor)
#   - gaps > 30 min between consecutive heartbeats (silent-tracking-death)
#   - last_seen freshness vs now
#   - sentinel score / stolen state (soak must stay calm)
#
# Exit code 0 = healthy, 1 = gaps found / device not reporting.
set -uo pipefail

DEVICE_ID="${1:?usage: check-soak.sh <device_id> [hours]}"
HOURS="${2:-24}"

echo "═══ Soak check: $DEVICE_ID over the last $HOURS hour(s) ═══"
docker exec -i magneetar-server python3 - "$DEVICE_ID" "$HOURS" <<'EOF'
import sqlite3, sys, datetime

device_id, hours = sys.argv[1], int(sys.argv[2])
conn = sqlite3.connect("/app/data/magneetar.db")
c = conn.cursor()

# Device row
row = c.execute(
    "SELECT last_seen, sentinel_score, is_stolen FROM devices WHERE id=?",
    (device_id,),
).fetchone()
if not row:
    print("✗ device not found in DB")
    sys.exit(1)
last_seen, score, stolen = row
now = datetime.datetime.now(datetime.timezone.utc)
if last_seen:
    age = (now - datetime.datetime.fromisoformat(last_seen)).total_seconds()
else:
    age = float("inf")
print(f"  last_seen: {last_seen}  (age {age:.0f}s)  score: {score}  stolen: {stolen}")

# Heartbeats in the window + gap analysis
c.execute(
    "SELECT timestamp FROM heartbeats WHERE device_id=? AND timestamp > datetime('now', ?) ORDER BY timestamp",
    (device_id, f"-{hours} hours"),
)
rows = c.fetchall()
print(f"  heartbeats in window: {len(rows)}")
gaps = []
prev = None
for (ts,) in rows:
    t = datetime.datetime.fromisoformat(ts)
    if prev:
        gap = (t - prev).total_seconds()
        if gap > 30 * 60:
            gaps.append((prev.isoformat(), ts, f"{gap/60:.1f} min"))
    prev = t
if gaps:
    print(f"  ✗ {len(gaps)} gap(s) > 30 min:")
    for g in gaps[:5]:
        print(f"      {g[0]} → {g[1]}  ({g[2]})")
    sys.exit(1)
else:
    print("  ✓ 0 gaps > 30 min")

ok = age < 600 and score == 0 and not stolen
print("  ✓ SOAK HEALTHY" if ok else "  ⚠ check device (stale/score/stolen)")
sys.exit(0 if ok else 1)
EOF
