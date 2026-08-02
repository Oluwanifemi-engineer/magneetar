#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Backup/restore smoke test (CI-safe, no Docker required)
# Exercises the exact mechanism backup-db.sh relies on — the SQLite online
# backup API — against a temporary database, then verifies the restored copy
# contains the seeded data and passes PRAGMA integrity_check.
# Exit 0 = pass, 1 = fail.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

SRC_DB="$WORKDIR/source.db"
RESTORED_DB="$WORKDIR/restored.db"
SNAPSHOT_DB="$WORKDIR/snapshot.db"

echo "🧪 Backup/restore smoke test (workdir: $WORKDIR)"

# 1. Seed a source DB with real-shaped data (users + devices + locations)
python3 - "$SRC_DB" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.executescript("""
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, password_hash TEXT, display_name TEXT, created_at TEXT);
CREATE TABLE devices (id TEXT PRIMARY KEY, owner_id TEXT, model TEXT, last_seen TEXT);
CREATE TABLE locations (id INTEGER PRIMARY KEY, device_id TEXT, lat REAL, lng REAL, server_timestamp TEXT);
INSERT INTO users VALUES ('usr-test-1', 'smoke@magneetar.test', 'hash', 'Smoke', 'now');
INSERT INTO devices VALUES ('mt-smoke-1', 'usr-test-1', 'Smoke Test Device', 'now');
INSERT INTO locations (device_id, lat, lng, server_timestamp) VALUES ('mt-smoke-1', 9.08, 8.68, 'now');
""")
db.commit()
db.close()
print("   seeded source DB")
PY

# 2. Snapshot via the online backup API (same call backup-db.sh uses)
python3 - "$SRC_DB" "$SNAPSHOT_DB" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
print("   snapshot created via sqlite3 online backup API")
PY

# 3. Integrity-check the snapshot, then restore it into a fresh DB
python3 - "$SNAPSHOT_DB" "$RESTORED_DB" <<'PY'
import sqlite3, sys
chk = sqlite3.connect(sys.argv[1])
assert chk.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "snapshot integrity failed"
chk.close()
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
print("   snapshot integrity ok; restore round-trip done")
PY

# 4. Verify the restored DB has the seeded data + passes integrity
python3 - "$RESTORED_DB" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "restored DB integrity failed"
users = db.execute("SELECT count(*) FROM users").fetchone()[0]
devices = db.execute("SELECT count(*) FROM devices").fetchone()[0]
locations = db.execute("SELECT count(*) FROM locations").fetchone()[0]
assert (users, devices, locations) == (1, 1, 1), f"data mismatch: users={users} devices={devices} locations={locations}"
print(f"   verified: users={users} devices={devices} locations={locations} integrity=ok")
PY

echo "✅ Backup/restore smoke test PASSED"
