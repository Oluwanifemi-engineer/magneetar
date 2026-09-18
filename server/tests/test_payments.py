"""
Tests for the Paystack payment routes — the revenue path.

Historically this module was the least-tested code in the repo while carrying
the worst fail-open: a forged webhook could upgrade any account, and /verify
wrote a tier from client-supplied metadata. These tests pin the security
properties as first-class behaviour.
"""

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from unittest.mock import patch

# Own DB file, set BEFORE config/database import (mirrors test_api.py: env →
# config.settings.DB_PATH → database.DB_PATH → init_db). Both overrides are
# needed because whichever test module imports config first wins under
# full-suite collection.
_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)
os.environ["MT_DB_PATH"] = _test_db_path

import config  # noqa: E402 (env set above)

config.settings.DB_PATH = _test_db_path

import database  # noqa: E402

database.DB_PATH = _test_db_path

import plans  # noqa: E402
import pytest  # noqa: E402
from config import settings  # noqa: E402
from database import init_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

# Build the full schema before any test touches the app (mirrors test_api.py).
init_db(_test_db_path)

client = TestClient(app)

PAYSTACK_SECRET = "sk_test_paystack-secret"


@pytest.fixture(autouse=True)
def _clear_rate_buckets():
    """Clear rate limits between tests — registration is capped per IP and
    this file registers many users. Import database at MODULE level (see
    test_api.py's convention): under full-suite collection test_e2e evicts
    and re-imports database, so a function-local import could resolve a
    module bound to a different DB file."""
    with database.get_db_context() as conn:
        conn.execute("DELETE FROM rate_limits")
        conn.commit()
    yield


@pytest.fixture(scope="module", autouse=True)
def _leave_no_rows_behind():
    """This suite writes users/payments rows into ITS OWN db file, but when a
    later module pins the shared DB to THIS module's path (import-order
    dependent), test_multi_user's reset() hits FK violations on payments rows
    it does not know about. Empty the billing tables on the way out."""
    yield
    try:
        with database.get_db_context() as conn:
            conn.execute("DELETE FROM payments")
            conn.execute("DELETE FROM users")
            conn.commit()
    except Exception:
        pass  # table set differs across module generations — nothing to clean


def _signed_webhook(payload: dict, secret: str = PAYSTACK_SECRET) -> object:
    """POST a Paystack webhook with a valid HMAC-SHA512 signature."""
    raw = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    return client.post(
        "/api/payments/webhook",
        content=raw,
        headers={"x-paystack-signature": sig, "Content-Type": "application/json"},
    )


def _register_and_login() -> tuple:
    """Create a user; return (user_id, auth_header)."""
    email = f"pay-{secrets.token_hex(5)}@example.com"
    resp = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass1", "display_name": "Pay Tester"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body.get("token")
    if not token:
        login = client.post("/api/auth/login", json={"email": email, "password": "StrongPass1"})
        assert login.status_code == 200, login.text
        token = login.json()["token"]

    # Resolve the id from the DB — register's response shape isn't guaranteed.
    with database.get_db_context() as db:
        row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    return row["id"], {"Authorization": f"Bearer {token}"}


@pytest.fixture
def paystack_configured(monkeypatch):
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", PAYSTACK_SECRET)
    monkeypatch.setattr(settings, "PAYSTACK_WEBHOOK_SECRET", "")
    return PAYSTACK_SECRET


@pytest.fixture
def webhook_secret_configured(monkeypatch):
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "")
    monkeypatch.setattr(settings, "PAYSTACK_WEBHOOK_SECRET", PAYSTACK_SECRET)
    return PAYSTACK_SECRET


# ─── Plan catalogue ──────────────────────────────────────────────────────────


class TestPlansEndpoint:
    def test_plans_public_and_matches_single_source_of_truth(self):
        """The public plan list must equal plans.py — the pricing page and the
        checkout must never drift again."""
        resp = client.get("/api/payments/plans")
        assert resp.status_code == 200
        served = {p["id"]: p for p in resp.json()["plans"]}
        assert set(served) == set(plans.PLANS)
        for tier, plan in plans.PLANS.items():
            assert served[tier]["price_ngn"] == plan["price_ngn"]
            assert served[tier]["device_limit"] == plan["device_limit"]

    def test_free_tier_is_one_device(self):
        resp = client.get("/api/payments/plans")
        free = next(p for p in resp.json()["plans"] if p["id"] == "free")
        assert free["device_limit"] == 1

    def test_sold_prices_match_pricing_page(self):
        """Landing page: Personal ₦500, Guardian ₦1,500 — the checkout must
        charge what the site promises."""
        resp = client.get("/api/payments/plans")
        served = {p["id"]: p for p in resp.json()["plans"]}
        assert served["personal"]["price_ngn"] == 500
        assert served["guardian"]["price_ngn"] == 1500


# ─── Initialize / Verify ─────────────────────────────────────────────────────


class TestInitialize:
    def test_initialize_requires_auth(self, paystack_configured):
        resp = client.post("/api/payments/initialize", json={"plan": "personal"})
        assert resp.status_code in (401, 403)

    def test_initialize_requires_paystack_config(self, monkeypatch):
        monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "")
        _, auth = _register_and_login()
        resp = client.post("/api/payments/initialize", json={"plan": "personal"}, headers=auth)
        assert resp.status_code == 503

    def test_initialize_rejects_unknown_plan(self, paystack_configured):
        _, auth = _register_and_login()
        resp = client.post(
            "/api/payments/initialize",
            json={"plan": "sentinel"},  # retired tier must not be buyable
            headers=auth,
        )
        assert resp.status_code == 400

    def test_initialize_rejects_free_and_enterprise(self, paystack_configured):
        """free (price 0) and enterprise (sales-led, no price) are not
        self-serve checkouts."""
        _, auth = _register_and_login()
        for tier in ("free", "enterprise"):
            resp = client.post("/api/payments/initialize", json={"plan": tier}, headers=auth)
            assert resp.status_code == 400, f"{tier} should not be purchasable"

    def test_initialize_binds_caller_account_and_charges_advertised_price(self, paystack_configured):
        """The transaction is created for the CALLER (email from the DB, not
        the request body) and charges the plan-table price."""
        user_id, auth = _register_and_login()
        captured = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "status": True,
                    "data": {
                        "authorization_url": "https://checkout.paystack.com/abc",
                        "reference": "ref-123",
                        "access_code": "ac_123",
                    },
                }

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, **kwargs):
                captured["url"] = url
                captured["json"] = kwargs.get("json")
                return _Resp()

        with patch("routes.payments.httpx.AsyncClient", return_value=_Client()):
            resp = client.post("/api/payments/initialize", json={"plan": "personal"}, headers=auth)

        assert resp.status_code == 200, resp.text
        sent = captured["json"]
        assert sent["metadata"]["user_id"] == user_id
        assert sent["metadata"]["plan"] == "personal"
        assert sent["amount"] == 500 * 100  # ₦500 in kobo
        assert "@" in sent["email"]


class TestVerify:
    def _verify_stub(self, metadata, success=True, amount=50000):
        class _Resp:
            status_code = 200

            def json(self):
                return {
                    "status": True,
                    "data": {
                        "status": "success" if success else "failed",
                        "amount": amount,
                        "metadata": metadata,
                    },
                }

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, **kwargs):
                return _Resp()

        return _Client()

    def test_verify_requires_auth(self, paystack_configured):
        resp = client.post("/api/payments/verify", json={"reference": "ref-x"})
        assert resp.status_code in (401, 403)

    def test_verify_activates_caller_subscription(self, paystack_configured):
        user_id, auth = _register_and_login()
        with patch(
            "routes.payments.httpx.AsyncClient",
            return_value=self._verify_stub({"plan": "guardian", "user_id": user_id}),
        ):
            resp = client.post("/api/payments/verify", json={"reference": "ref-ok"}, headers=auth)
        assert resp.status_code == 200, resp.text
        assert resp.json()["plan"] == "guardian"

        status = client.get("/api/payments/status", headers=auth)
        assert status.status_code == 200
        assert status.json()["tier"] == "guardian"

    def test_verify_refuses_reference_of_another_account(self, paystack_configured):
        """A reference initialized for account A cannot upgrade account B —
        the previous tier-takeover hole."""
        _, attacker_auth = _register_and_login()
        victim_id = f"user-{secrets.token_hex(6)}"
        with patch(
            "routes.payments.httpx.AsyncClient",
            return_value=self._verify_stub({"plan": "enterprise", "user_id": victim_id}),
        ):
            resp = client.post(
                "/api/payments/verify",
                json={"reference": "ref-stolen"},
                headers=attacker_auth,
            )
        assert resp.status_code == 403

        # ...and the attacker gained nothing.
        status = client.get("/api/payments/status", headers=attacker_auth)
        assert status.json()["tier"] == "free"

    def test_verify_rejects_unknown_plan_metadata(self, paystack_configured):
        user_id, auth = _register_and_login()
        with patch(
            "routes.payments.httpx.AsyncClient",
            return_value=self._verify_stub({"plan": "sentinel", "user_id": user_id}),
        ):
            resp = client.post("/api/payments/verify", json={"reference": "ref-bad"}, headers=auth)
        assert resp.status_code == 400

    def test_verify_rejects_unsuccessful_payment(self, paystack_configured):
        user_id, auth = _register_and_login()
        with patch(
            "routes.payments.httpx.AsyncClient",
            return_value=self._verify_stub({"plan": "personal", "user_id": user_id}, success=False),
        ):
            resp = client.post("/api/payments/verify", json={"reference": "ref-fail"}, headers=auth)
        assert resp.status_code == 400


# ─── Webhook ─────────────────────────────────────────────────────────────────


class TestWebhook:
    def test_fails_closed_without_any_secret(self, monkeypatch):
        """The original fail-open: with no secret configured the event was
        trusted and any account could be upgraded. Now it is rejected."""
        monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", "")
        monkeypatch.setattr(settings, "PAYSTACK_WEBHOOK_SECRET", "")
        resp = client.post("/api/payments/webhook", json={"event": "subscription.create", "data": {}})
        assert resp.status_code == 503

    def test_rejects_unsigned_body(self, webhook_secret_configured):
        resp = client.post(
            "/api/payments/webhook",
            json={"event": "subscription.create", "data": {}},
            headers={"x-paystack-signature": ""},
        )
        assert resp.status_code == 401

    def test_rejects_bad_signature(self, webhook_secret_configured):
        raw = json.dumps({"event": "subscription.create", "data": {}}).encode()
        resp = client.post(
            "/api/payments/webhook",
            content=raw,
            headers={"x-paystack-signature": "0" * 128},
        )
        assert resp.status_code == 401

    def test_subscription_create_upgrades_by_plan_code(self, webhook_secret_configured):
        email = f"wh-{secrets.token_hex(5)}@example.com"
        reg = client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass1", "display_name": "WH"},
        )
        assert reg.status_code == 200

        payload = {
            "event": "subscription.create",
            "data": {
                "plan": {"plan_code": plans.PLANS["personal"]["paystack_plan_code"]},
                "customer": {"email": email},
                "metadata": {},
            },
        }
        resp = _signed_webhook(payload)
        assert resp.status_code == 200

        # The account was upgraded through the email→user resolution.
        with database.get_db_context() as db:
            row = db.execute("SELECT tier FROM users WHERE email=?", (email,)).fetchone()
        assert row["tier"] == "personal"

    def test_subscription_disable_downgrades(self, webhook_secret_configured):
        email = f"wh-off-{secrets.token_hex(5)}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass1", "display_name": "WH"},
        )

        with database.get_db_context() as db:
            uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
            db.execute("UPDATE users SET tier='personal' WHERE id=?", (uid,))
            db.commit()

        payload = {
            "event": "subscription.disable",
            "data": {"customer": {"email": email}, "metadata": {}},
        }
        assert _signed_webhook(payload).status_code == 200
        with database.get_db_context() as db:
            row = db.execute("SELECT tier FROM users WHERE email=?", (email,)).fetchone()
        assert row["tier"] == "free"

    def test_unknown_plan_code_changes_nothing(self, webhook_secret_configured):
        email = f"wh-unk-{secrets.token_hex(5)}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass1", "display_name": "WH"},
        )
        payload = {
            "event": "subscription.create",
            "data": {
                "plan": {"plan_code": "sentinel_monthly"},
                "customer": {"email": email},
                "metadata": {},
            },
        }
        assert _signed_webhook(payload).status_code == 200

        with database.get_db_context() as db:
            row = db.execute("SELECT tier FROM users WHERE email=?", (email,)).fetchone()
        assert row["tier"] == "free"

    def test_payment_failed_starts_grace_period_without_dropping_tier(self, webhook_secret_configured):
        email = f"wh-grace-{secrets.token_hex(5)}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "StrongPass1", "display_name": "WH"},
        )

        with database.get_db_context() as db:
            uid = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
            db.execute("UPDATE users SET tier='guardian' WHERE id=?", (uid,))
            db.commit()

        payload = {
            "event": "invoice.payment_failed",
            "data": {"customer": {"email": email}, "metadata": {}},
        }
        assert _signed_webhook(payload).status_code == 200

        with database.get_db_context() as db:
            row = db.execute("SELECT tier, payment_failed_at FROM users WHERE email=?", (email,)).fetchone()
        assert row["tier"] == "guardian"  # grace period keeps the tier
        assert row["payment_failed_at"] is not None


# ─── Status ──────────────────────────────────────────────────────────────────


class TestStatus:
    def test_status_requires_auth(self):
        resp = client.get("/api/payments/status")
        assert resp.status_code in (401, 403)

    def test_status_shape(self):
        _, auth = _register_and_login()
        resp = client.get("/api/payments/status", headers=auth)
        assert resp.status_code == 200
        body = resp.json()
        assert body["tier"] == "free"
        assert body["device_limit"] == 1
        assert body["grace_period_active"] is False
