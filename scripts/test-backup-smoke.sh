#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# MAGNEETAR — Backup/restore smoke test (CI-safe, no Docker required)
# Exercises the two mechanisms backup-db.sh relies on:
#   1. SQLite online backup API — snapshot a temp DB, restore it into a fresh
#      DB, verify data + PRAGMA integrity_check (the DB half of a backup).
#   2. Media-store tarball round-trip — tar the per-device media tree exactly
#      like backup-db.sh does (tar -C <root> <mediadir>), extract into a fresh
#      dir, verify every file's bytes survive byte-for-byte (the v1.4 media
#      half — evidence files live on disk, NOT inside the SQLite file).
# Exit 0 = pass, 1 = fail.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT

SRC_DB="$WORKDIR/source.db"
RESTORED_DB="$WORKDIR/restored.db"
SNAPSHOT_DB="$WORKDIR/snapshot.db"

MEDIA_SRC="$WORKDIR/media"          # mimics /app/media in the container
MEDIA_RESTORED="$WORKDIR/media_restored"
MEDIA_TARBALL="$WORKDIR/magneetar_media_test.tar.gz"

echo "🧪 Backup/restore smoke test (workdir: $WORKDIR)"

# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — SQLite online-backup round-trip
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — Media-store tarball round-trip (v1.4: evidence files on disk)
# ═══════════════════════════════════════════════════════════════════════════════

# 1. Seed a media tree exactly like the server's media_store.py layout:
#    <root>/<device_id>/<uuid>.<ext> — with binary content (JPEG-ish bytes).
python3 - "$MEDIA_SRC" <<'PY'
import os, sys
root = sys.argv[1]
# photo (JPEG magic), audio (ID3 magic), video (ftyp box) — realistic shapes
files = [
    ("mt-dev-aaaa", "photo.jpg", b"\xff\xd8\xff\xe0" + b"\x01" * 300),
    ("mt-dev-aaaa", "photo2.jpg", b"\xff\xd8\xff\xe1" + b"\x02" * 512),
    ("mt-dev-bbbb", "audio.mp3", b"ID3\x03\x00\x00\x00" + b"\x03" * 400),
    ("mt-dev-cccc", "video.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x04" * 600),
]
for dev, name, data in files:
    d = os.path.join(root, dev)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
print("   seeded media tree: 4 files across 3 device dirs")
for dev, name, data in files:
    d = os.path.join(root, dev)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
print("   seeded media tree: 4 files across 3 device dirs")
PY

# 2. Tar the media dir EXACTLY like backup-db.sh does:
#    docker exec ... tar -czf - -C /app media  →  top-level dir "media/"
tar -czf "$MEDIA_TARBALL" -C "$WORKDIR" media
echo "   media tarball created (top-level dir: media/)"

# 3. Verify tarball integrity + extract into a fresh tree
gzip -t "$MEDIA_TARBALL"
tar -tzf "$MEDIA_TARBALL" >/dev/null
mkdir -p "$MEDIA_RESTORED"
tar -xzf "$MEDIA_TARBALL" -C "$MEDIA_RESTORED"
echo "   tarball verified + extracted"

# 4. Byte-for-byte verification of every file
python3 - "$MEDIA_SRC" "$MEDIA_RESTORED/media" <<'PY'
import os, sys
src_root, dst_root = sys.argv[1], sys.argv[2]
src_files = []
for dirpath, _dirs, files in os.walk(src_root):
    for name in files:
        src_files.append(os.path.relpath(os.path.join(dirpath, name), src_root))
assert src_files, "source media tree unexpectedly empty"
for rel in src_files:
    with open(os.path.join(src_root, rel), "rb") as f:
        src_bytes = f.read()
    dst = os.path.join(dst_root, rel)
    assert os.path.exists(dst), f"missing after restore: {rel}"
    with open(dst, "rb") as f:
        assert f.read() == src_bytes, f"byte mismatch after restore: {rel}"
print(f"   verified: {len(src_files)} media files byte-identical after round-trip")
PY

echo "✅ Backup/restore smoke test PASSED (DB + media store)"
