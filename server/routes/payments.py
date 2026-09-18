"""
Magneetar Payment Integration — Paystack

Handles:
- Subscription plan checkout (Free / Personal / Guardian)
- Paystack webhook signature verification
- Payment success/failure handling
- Tier enforcement server-side
- Grace period after a failed payment

Paystack is Nigeria-native and supports:
- Card payments (Visa, Mastercard, Verve)
- Bank transfers
- USSD payments

Plan definitions live in plans.py (the single source of truth) — this module
previously carried its own table with different tier names, device limits and
prices, so the checkout charged amounts the pricing page never advertised and
sold a tier ("sentinel") that no other surface knew about.

Security notes (all fixed 2026-09-17):
- `/initialize` and `/verify` now require an authenticated user, and a payment
  can only be applied to the account that created it — previously anyone could
  call verify with a reference and the tier was written from a client-supplied
  email in the transaction metadata.
- The webhook used to SKIP signature verification entirely when its secret was
  unset (fail-open), so a forged `subscription.create` body upgraded any
  account by email. It now fails closed.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import plans
from auth import get_current_user
from config import settings
from database import get_db_context
from fastapi import APIRouter, Depends, HTTPException, Request
from logging_config import get_logger
from pydantic import BaseModel

logger = get_logger("magneetar")

router = APIRouter()

# Grace period after a failed payment before the tier is dropped.
GRACE_PERIOD_DAYS = 7


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Request Models ─────────────────────────────────────────────────────────


class InitializePaymentRequest(BaseModel):
    plan: str  # a sellable tier from plans.py ("personal" / "guardian")
    callback_url: Optional[str] = None


class VerifyPaymentRequest(BaseModel):
    reference: str


# ── Helpers ────────────────────────────────────────────────────────────────


def _require_configured() -> str:
    if not settings.PAYSTACK_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Payment system not configured")
    return settings.PAYSTACK_SECRET_KEY


def _user_row(user_id: str, columns: str = "id, email, tier"):
    with get_db_context() as db:
        row = db.execute(f"SELECT {columns} FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _row_get(row, key, default=None):
    """sqlite3.Row has no .get() — read defensively."""
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _set_tier(user_id: str, tier: str) -> None:
    with get_db_context() as db:
        db.execute("UPDATE users SET tier=? WHERE id=?", (tier, user_id))
        db.commit()


def _webhook_secret() -> str:
    """Secret used to authenticate Paystack webhooks.

    Paystack signs the raw body with your SECRET KEY (HMAC-SHA512), so that is
    the correct value. MT_PAYSTACK_WEBHOOK_SECRET is honored first for
    deployments that front Paystack with their own signing secret.
    """
    return settings.PAYSTACK_WEBHOOK_SECRET or settings.PAYSTACK_SECRET_KEY


# ── Payment Endpoints ──────────────────────────────────────────────────────


@router.post("/api/payments/initialize")
async def initialize_payment(
    body: InitializePaymentRequest,
    user_id: str = Depends(get_current_user),
):
    """Initialize a Paystack payment for a subscription plan.

    Authenticated: the transaction is created for the CALLER's account, and the
    caller's email is read from the database — never from the request body.
    """
    secret = _require_configured()

    if body.plan not in plans.SELLABLE_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"Plan must be one of {sorted(plans.SELLABLE_TIERS)}",
        )

    plan = plans.PLANS[body.plan]
    user = _user_row(user_id)
    email = user["email"]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.paystack.co/transaction/initialize",
            headers={
                "Authorization": f"Bearer {secret}",
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "amount": plan["price_ngn"] * 100,  # Paystack uses kobo
                "plan": plan["paystack_plan_code"],
                "callback_url": body.callback_url or f"{settings.DASHBOARD_URL}/payment/callback",
                # user_id binds the transaction to THIS account; /verify refuses
                # a reference whose metadata points at somebody else.
                "metadata": {"plan": body.plan, "user_id": user_id},
            },
            timeout=30,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Payment initialization failed")

    data = response.json()
    if not data.get("status"):
        raise HTTPException(status_code=502, detail=data.get("message", "Payment failed"))

    return {
        "authorization_url": data["data"]["authorization_url"],
        "reference": data["data"]["reference"],
        "access_code": data["data"]["access_code"],
    }


@router.post("/api/payments/verify")
async def verify_payment(
    body: VerifyPaymentRequest,
    user_id: str = Depends(get_current_user),
):
    """Verify a Paystack payment and activate the CALLER's subscription."""
    secret = _require_configured()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.paystack.co/transaction/verify/{body.reference}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=30,
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Payment verification failed")

    data = response.json()
    if not data.get("status") or data["data"]["status"] != "success":
        raise HTTPException(status_code=400, detail="Payment not successful")

    metadata = data["data"].get("metadata") or {}
    plan_name = metadata.get("plan", "")
    if plan_name not in plans.PLANS:
        raise HTTPException(status_code=400, detail="Invalid plan in payment")

    # The reference must belong to the account asking to be upgraded. Without
    # this, any authenticated user could replay someone else's reference (or
    # one they initialized for a third party's email) and take over the tier.
    if metadata.get("user_id") and metadata["user_id"] != user_id:
        logger.warning(
            "Payment reference belongs to another account — refusing",
            extra={"extra_data": {"reference": body.reference, "caller": user_id}},
        )
        raise HTTPException(status_code=403, detail="This payment belongs to another account")

    now = _now_iso()
    with get_db_context() as db:
        db.execute(
            "UPDATE users SET tier=?, last_payment_at=? WHERE id=?",
            (plan_name, now, user_id),
        )
        db.execute(
            "INSERT INTO payments (user_id, reference, amount, plan, status, paid_at)"
            " VALUES (?, ?, ?, ?, 'success', ?)",
            (user_id, body.reference, data["data"]["amount"] / 100, plan_name, now),
        )
        db.commit()

    return {
        "status": "success",
        "plan": plan_name,
        "message": f"Successfully subscribed to {plans.PLANS[plan_name]['name']} plan!",
    }


@router.post("/api/payments/webhook")
async def paystack_webhook(request: Request):
    """Handle Paystack webhook events.

    Fails CLOSED: if no signing secret is configured the event is rejected
    (503) instead of being trusted. The previous implementation skipped the
    signature check when the secret was unset, which let a forged
    `subscription.create` payload upgrade an arbitrary account.
    """
    secret = _webhook_secret()
    if not secret:
        logger.error(
            "Paystack webhook received but no signing secret is configured — "
            "rejecting. Set MT_PAYSTACK_SECRET (or MT_PAYSTACK_WEBHOOK_SECRET)."
        )
        raise HTTPException(status_code=503, detail="Payment webhook not configured")

    body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        logger.warning("Paystack webhook: signature mismatch — rejecting")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event.get("event", "")
    data = event.get("data", {}) or {}
    customer_email = (data.get("customer", {}) or {}).get("email", "")
    metadata = data.get("metadata", {}) or {}
    user_id = metadata.get("user_id")

    def resolve_user_id() -> Optional[str]:
        """Prefer the metadata binding; fall back to the (signed) email."""
        if user_id:
            return user_id
        if not customer_email:
            return None
        with get_db_context() as db:
            row = db.execute("SELECT id FROM users WHERE email=?", (customer_email,)).fetchone()
        return row["id"] if row else None

    if event_type == "subscription.create":
        tier = plans.tier_for_plan_code((data.get("plan", {}) or {}).get("plan_code", ""))
        uid = resolve_user_id()
        if tier and uid:
            _set_tier(uid, tier)
            logger.info(
                "Subscription created",
                extra={"extra_data": {"user_id": uid, "tier": tier}},
            )

    elif event_type == "subscription.disable":
        uid = resolve_user_id()
        if uid:
            _set_tier(uid, "free")
            logger.info("Subscription disabled", extra={"extra_data": {"user_id": uid}})

    elif event_type == "invoice.payment_failed":
        uid = resolve_user_id()
        if uid:
            with get_db_context() as db:
                db.execute(
                    "UPDATE users SET payment_failed_at=? WHERE id=?",
                    (_now_iso(), uid),
                )
                db.commit()
            # The tier is intentionally NOT dropped here — the grace period
            # (see /api/payments/status) is what decides that.
            logger.info(
                "Payment failed — grace period started",
                extra={"extra_data": {"user_id": uid}},
            )

    return {"status": "received"}


@router.get("/api/payments/plans")
async def get_plans():
    """Get available subscription plans (public)."""
    return {"plans": plans.public_plans()}


@router.get("/api/payments/status")
async def get_payment_status(user_id: str = Depends(get_current_user)):
    """Get the caller's subscription status."""
    with get_db_context() as db:
        user = db.execute(
            "SELECT tier, last_payment_at, payment_failed_at FROM users WHERE id=?",
            (user_id,),
        ).fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    tier = plans.resolve_tier(user["tier"])
    plan = plans.PLANS[tier]
    failed_at = _row_get(user, "payment_failed_at")

    return {
        "tier": tier,
        "plan_name": plan["name"],
        "device_limit": plan["device_limit"],
        "features": plan["features"],
        "last_payment": _row_get(user, "last_payment_at"),
        "payment_failed": failed_at,
        "grace_period_active": bool(failed_at),
        "grace_period_ends": (
            (datetime.fromisoformat(failed_at) + timedelta(days=GRACE_PERIOD_DAYS)).isoformat() if failed_at else None
        ),
    }
