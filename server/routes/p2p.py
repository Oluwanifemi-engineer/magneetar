"""
Magneetar Offline Device Network — Paired P2P Pairing Routes
(docs/offline-network-design.md §4)

Two of the OWNER's devices pair once over the internet: one device requests a
pairing and shows a single-use 8-hex code (15 min TTL); the owner types it
into the other device, which completes the pairing and receives the shared
32-byte pair_secret. The first device pulls the same secret via status.
After that the two devices can discover, authenticate (HMAC-SHA256, locked by
P2pPairing.kt) and exchange data FULLY OFFLINE — the server is never in the
P2P data path.

Security properties:
  - Everything is scoped to the authenticated owner account (get_current_user):
    you can only pair devices you own.
  - The pair_code is stored HASHED (SHA-256), single use, 15 min TTL.
  - The pair_secret is stored encrypted at rest (AES-256-GCM field-level,
    keyed on the pair id — same FieldEncryption used for at-rest location
    encryption; NoOp plaintext fallback when no key is configured).
  - A pairing is identified by the pair id; both devices receive the secret
    only through their own authenticated calls.
"""

import hashlib
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from auth import get_current_user
from database import get_db, log_audit
from encryption import get_encryption
from fastapi import APIRouter, Depends, HTTPException, Query
from models import P2pPairConfirm, P2pPairInitiate

router = APIRouter()

PAIR_CODE_TTL_MINUTES = 15
PAIR_SECRET_BYTES = 32


def _hash_code(pair_code: str) -> str:
    """SHA-256 of the pair code — the DB never stores the plaintext code."""
    return hashlib.sha256(pair_code.encode("ascii")).hexdigest()


def _require_real_user(user_id: str) -> str:
    """Pairing needs a real user account (same guard as guardian routes)."""
    if user_id == "api_key_user" or not user_id.startswith("usr-"):
        raise HTTPException(status_code=401, detail="User account authentication required")
    return user_id


def _new_pair_secret() -> str:
    """64 hex chars = 32 random bytes, matching P2pPairing.PAIR_SECRET_LENGTH."""
    return secrets.token_hex(PAIR_SECRET_BYTES)


@router.post("/api/p2p/pair/initiate")
async def pair_initiate(
    req: P2pPairInitiate,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Create a pending pairing for THIS device and return a single-use code.

    Re-initiating replaces any still-pending code (the old one dies).
    """
    user_id = _require_real_user(user_id)
    pair_code = secrets.token_hex(4)  # 8 hex chars
    expires = (datetime.now(timezone.utc) + timedelta(minutes=PAIR_CODE_TTL_MINUTES)).isoformat()
    pair_id = f"p2p-{uuid.uuid4().hex[:12]}"

    db.execute(
        "UPDATE p2p_pairings SET pair_code_hash=NULL, pair_code_expires=NULL "
        "WHERE owner_user_id=? AND pair_code_hash IS NOT NULL",
        (user_id,),
    )
    db.execute(
        """INSERT INTO p2p_pairings (id, owner_user_id, device_a, pair_code_hash, pair_code_expires)
           VALUES (?, ?, ?, ?, ?)""",
        (pair_id, user_id, req.device_id, _hash_code(pair_code), expires),
    )
    db.commit()
    log_audit("p2p_pair_initiate", actor=user_id, details=f"device={req.device_id} pair={pair_id}")

    return {
        "pair_id": pair_id,
        "pair_code": pair_code,
        "expires_in_s": PAIR_CODE_TTL_MINUTES * 60,
    }


@router.post("/api/p2p/pair/confirm")
async def pair_confirm(
    req: P2pPairConfirm,
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Complete the pairing: verify the single-use code, mint the shared secret.

    The confirming device (device_b) receives the secret here; the initiating
    device (device_a) pulls it from GET /api/p2p/pair/status.
    """
    user_id = _require_real_user(user_id)
    row = db.execute(
        "SELECT * FROM p2p_pairings WHERE owner_user_id=? AND pair_code_hash=?",
        (user_id, _hash_code(req.pair_code)),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pairing code not found or already used")
    if row["pair_code_expires"]:
        try:
            expires = datetime.fromisoformat(row["pair_code_expires"])
        except ValueError:
            expires = datetime.min.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            raise HTTPException(status_code=410, detail="Pairing code expired — start a new pairing")
    if row["device_b"]:
        raise HTTPException(status_code=409, detail="Pairing already completed — this code is single-use")
    if row["device_a"] == req.device_id:
        raise HTTPException(status_code=400, detail="The other device must enter the code")

    pair_secret = _new_pair_secret()
    pair_id = row["id"]
    enc = get_encryption()
    secret_enc = enc.encrypt_field(pair_secret, pair_id)

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE p2p_pairings
           SET device_b=?, pair_secret_enc=?, pair_code_hash=NULL, pair_code_expires=NULL, completed_at=?
           WHERE id=?""",
        (req.device_id, secret_enc, now, pair_id),
    )
    db.commit()
    log_audit("p2p_pair_confirm", actor=user_id, details=f"device={req.device_id} pair={pair_id}")

    return {"pair_id": pair_id, "device_a": row["device_a"], "device_b": req.device_id, "pair_secret": pair_secret}


@router.get("/api/p2p/pair/status")
async def pair_status(
    device_id: str = Query(..., min_length=3, max_length=64),
    db: sqlite3.Connection = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """List this owner's completed pairings involving [device_id], each with
    the shared secret (decrypted) — the initiating device fetches its secret
    here once the confirming device completes the pairing."""
    user_id = _require_real_user(user_id)
    rows = db.execute(
        """SELECT id, device_a, device_b, pair_secret_enc, completed_at
           FROM p2p_pairings
           WHERE owner_user_id=? AND completed_at IS NOT NULL
             AND (device_a=? OR device_b=?)
           ORDER BY completed_at DESC""",
        (user_id, device_id, device_id),
    ).fetchall()

    result = []
    enc = get_encryption()
    for r in rows:
        secret = None
        if r["pair_secret_enc"]:
            try:
                secret = enc.decrypt_field(r["pair_secret_enc"], r["id"])
            except Exception:
                secret = None  # never leak a half-decrypted row; still list the pairing
        result.append(
            {
                "pair_id": r["id"],
                "device_a": r["device_a"],
                "device_b": r["device_b"],
                "completed_at": r["completed_at"],
                "pair_secret": secret,
            }
        )
    return {"pairings": result}
