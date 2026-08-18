"""
Magneetar Paired-P2P Pairing Tests (docs/offline-network-design.md §4)

Two of the OWNER's devices pair once over the internet: device A initiates
and gets a single-use 8-hex code; device B confirms with the code and
receives the shared pair_secret; device A pulls the same secret via status.
After that the devices can authenticate offline via HMAC (P2pPairing.kt) —
the server is never in the P2P data path.
"""

import os
import secrets
import sqlite3
import tempfile

from fastapi.testclient import TestClient

# ── Test Environment Setup ───────────────────────────────────────────────────
_test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["MT_API_KEY"] = "p2p-test-key-" + "a" * 32
os.environ["MT_JWT_SECRET"] = "p2p-jwt-secret-" + "b" * 64
os.environ["MT_ENCRYPTION_KEY"] = secrets.token_hex(32)
os.environ["MT_DB_PATH"] = test_db_path

import config  # noqa: E402

config.settings.DB_PATH = test_db_path

import database  # noqa: E402

database.DB_PATH = test_db_path

from database import init_db  # noqa: E402

init_db(test_db_path)

from main import app  # noqa: E402

client = TestClient(app)

TEST_USER_PASSWORD = "StrongPass1"


def register_user(email: str) -> str:
    resp = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_USER_PASSWORD,
            "display_name": "P2P Test User",
        },
    )
    assert resp.status_code == 200, f"register_user failed: {resp.text}"
    return resp.json()["token"]


def user_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Helpers ──────────────────────────────────────────────────────────────────


def initiate_pairing(token: str, device_id: str) -> dict:
    resp = client.post("/api/p2p/pair/initiate", json={"device_id": device_id}, headers=user_headers(token))
    assert resp.status_code == 200, f"initiate failed: {resp.text}"
    return resp.json()


def confirm_pairing(token: str, device_id: str, pair_code: str) -> dict:
    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": device_id, "pair_code": pair_code},
        headers=user_headers(token),
    )
    assert resp.status_code == 200, f"confirm failed: {resp.text}"
    return resp.json()


def pair_status(token: str, device_id: str) -> list:
    resp = client.get(f"/api/p2p/pair/status?device_id={device_id}", headers=user_headers(token))
    assert resp.status_code == 200, f"status failed: {resp.text}"
    return resp.json()["pairings"]


# ── Tests ────────────────────────────────────────────────────────────────────


def test_full_pairing_flow_both_devices_get_same_secret():
    """Initiate → confirm → both devices can pull the identical 64-hex secret."""
    token = register_user("pair-flow@test.dev")
    dev_a, dev_b = "mt-device-alpha", "mt-device-beta"

    init = initiate_pairing(token, dev_a)
    assert init["pair_code"] and len(init["pair_code"]) == 8
    assert init["expires_in_s"] == 15 * 60
    assert init["pair_id"].startswith("p2p-")

    conf = confirm_pairing(token, dev_b, init["pair_code"])
    assert conf["device_a"] == dev_a
    assert conf["device_b"] == dev_b
    assert len(conf["pair_secret"]) == 64  # 32 bytes hex

    # device A pulls the same secret via status
    a_status = pair_status(token, dev_a)
    b_status = pair_status(token, dev_b)
    assert len(a_status) == 1 and len(b_status) == 1
    assert a_status[0]["pair_id"] == conf["pair_id"]
    assert a_status[0]["pair_secret"] == conf["pair_secret"]
    assert b_status[0]["pair_secret"] == conf["pair_secret"]


def test_pair_code_is_single_use():
    """After a successful confirm, the same code is dead (404, not a replay)."""
    token = register_user("pair-single-use@test.dev")
    init = initiate_pairing(token, "mt-device-sua")

    confirm_pairing(token, "mt-device-sub", init["pair_code"])

    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": "mt-device-suc", "pair_code": init["pair_code"]},
        headers=user_headers(token),
    )
    assert resp.status_code == 404


def test_pair_code_not_shared_between_owners():
    """A code minted by one owner must not confirm under another owner."""
    token_a = register_user("pair-owner-a@test.dev")
    token_b = register_user("pair-owner-b@test.dev")
    init = initiate_pairing(token_a, "mt-device-a")

    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": "mt-device-b", "pair_code": init["pair_code"]},
        headers=user_headers(token_b),
    )
    assert resp.status_code == 404


def test_pairing_scoped_to_owner_account():
    """Each owner only sees their own pairings in status."""
    token_a = register_user("pair-scope-a@test.dev")
    token_b = register_user("pair-scope-b@test.dev")

    init = initiate_pairing(token_a, "mt-device-a")
    confirm_pairing(token_a, "mt-device-b", init["pair_code"])

    # owner B sees nothing for their (different) device ids
    assert pair_status(token_b, "mt-device-a") == []
    # owner A still sees the pairing
    assert len(pair_status(token_a, "mt-device-a")) == 1


def test_code_expired_returns_410(monkeypatch):
    """An expired code is rejected with 410 (stale pairing must restart)."""
    # Pin the app to THIS module's DB: a later-imported test module may have
    # reassigned the global database.DB_PATH, which would make the client
    # write elsewhere while we read our own temp file below.
    monkeypatch.setattr(database, "DB_PATH", test_db_path)
    token = register_user("pair-expired@test.dev")
    init = initiate_pairing(token, "mt-device-expa")

    conn = sqlite3.connect(test_db_path)
    conn.execute(
        "UPDATE p2p_pairings SET pair_code_expires=? WHERE pair_code_hash=?",
        ("2020-01-01T00:00:00+00:00", _hash_of(init["pair_code"])),
    )
    conn.commit()
    conn.close()

    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": "mt-device-expb", "pair_code": init["pair_code"]},
        headers=user_headers(token),
    )
    assert resp.status_code == 410


def _hash_of(pair_code: str) -> str:
    import hashlib

    return hashlib.sha256(pair_code.encode("ascii")).hexdigest()


def test_pair_code_stored_hashed_not_plaintext(monkeypatch):
    """The DB never stores the plaintext code."""
    # Same DB-path pin as test_code_expired_returns_410 (cross-file isolation).
    monkeypatch.setattr(database, "DB_PATH", test_db_path)
    token = register_user("pair-hash@test.dev")
    init = initiate_pairing(token, "mt-device-hasha")

    conn = sqlite3.connect(test_db_path)
    row = conn.execute("SELECT pair_code_hash FROM p2p_pairings").fetchall()
    conn.close()
    assert row  # at least one pairing exists
    # the plaintext code appears nowhere; the new code's hash is stored
    hashes = [r[0] for r in row if r[0] is not None]
    assert hashes
    for stored_hash in hashes:
        assert init["pair_code"] not in stored_hash
    assert _hash_of(init["pair_code"]) in hashes


def test_same_device_cannot_confirm_own_code():
    """The initiating device cannot confirm its own code (someone must type it
    into the OTHER device — that's the human-in-the-loop bootstrap)."""
    token = register_user("pair-self@test.dev")
    init = initiate_pairing(token, "mt-device-self")

    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": "mt-device-self", "pair_code": init["pair_code"]},
        headers=user_headers(token),
    )
    assert resp.status_code == 400


def test_initiate_replaces_old_pending_code():
    """Re-initiating kills any still-pending code (old one dies)."""
    token = register_user("pair-reinit@test.dev")
    first = initiate_pairing(token, "mt-device-ri")
    second = initiate_pairing(token, "mt-device-ri")

    assert first["pair_code"] != second["pair_code"]

    # the first code is now dead
    resp = client.post(
        "/api/p2p/pair/confirm",
        json={"device_id": "mt-device-rj", "pair_code": first["pair_code"]},
        headers=user_headers(token),
    )
    assert resp.status_code == 404


def test_pairing_requires_real_user_account():
    """API-key-only auth is rejected — pairing is owner-scoped."""
    resp = client.post(
        "/api/p2p/pair/initiate",
        json={"device_id": "mt-device-nouser"},
        headers={"x-api-key": config.settings.API_KEY},
    )
    assert resp.status_code in (401, 403)
