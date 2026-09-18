"""
Magneetar Subscription Plans — SINGLE SOURCE OF TRUTH.

Before this module, the tier vocabulary and device allowances were defined
independently in FIVE places, and they disagreed:

  * routes/payments.py PLANS ....... free/guardian/sentinel; 3/10/999; ₦2,500 & ₦5,000
  * config.PLAN_DEVICE_LIMITS ...... personal 3 / guardian 10 / enterprise 999 / admin 999
  * config.MAX_DEVICES_PER_USER .... 3 (default), while its own comment said "default 1"
  * models.PlanUpdateRequest ........ free/personal/guardian/enterprise (no "sentinel")
  * dashboard Pricing.tsx / types ... free 1 / personal 3 / guardian 10 / enterprise unlimited
                                      at ₦500 and ₦1,500

Consequences of that drift: a paying "sentinel" customer was granted the FREE
allowance (the tier key was missing from config's table, so plan_device_limit()
fell through to the free fallback), the admin upgrade path could not grant the
tier the payment path sold, and three different price lists were live at once.

Everything now resolves through this module. It is deliberately dependency-free
(pure data + helpers) so config, models, and routes can all import it without
cycles.

The tier names and prices here are the ones the public pricing page advertises
(dashboard/src/components/landing/Pricing.tsx): Free 1 device, Personal ₦500,
Guardian ₦1,500, Enterprise custom. The checkout must charge what the site
promises.
"""

from typing import Optional

# ── Free tier ────────────────────────────────────────────────────────────────
# "free forever · 1 device" is the claim on the pricing page (and the download
# page's verifiable claim). Operator-tunable via MT_MAX_DEVICES, but the
# default here is what the marketing states.
FREE_DEVICE_LIMIT = 1

# Internal operator tier — never sold, effectively unlimited.
ADMIN_TIER = "admin"
ADMIN_DEVICE_LIMIT = 999

# Every plan includes every shipped capability; the plans differ only in how
# many devices they cover (this is what the pricing page tells customers).
# Do NOT list capabilities that are not shipped end-to-end — the previous
# per-tier lists advertised family_circles/police_report/emergency_wipe, none
# of which a customer could actually use.
CAPABILITIES = (
    "real_time_tracking",
    "theft_detection",
    "evidence_capture",
    "remote_commands",
    "geofencing",
    "web_dashboard",
    "alerts",
    "device_sharing",
)


def _plan(
    name: str,
    price_ngn: Optional[int],
    yearly_price_ngn: Optional[int],
    device_limit: int,
    tagline: str,
    paystack_plan_code: Optional[str] = None,
    paystack_yearly_plan_code: Optional[str] = None,
) -> dict:
    return {
        "name": name,
        "price_ngn": price_ngn,
        "yearly_price_ngn": yearly_price_ngn,
        "device_limit": device_limit,
        "tagline": tagline,
        "features": list(CAPABILITIES),
        "paystack_plan_code": paystack_plan_code,
        "paystack_yearly_plan_code": paystack_yearly_plan_code,
    }


# ── Canonical plan table ─────────────────────────────────────────────────────
PLANS: dict = {
    "free": _plan(
        name="Free",
        price_ngn=0,
        yearly_price_ngn=0,
        device_limit=FREE_DEVICE_LIMIT,
        tagline="Protect your main phone.",
    ),
    "personal": _plan(
        name="Personal",
        price_ngn=500,
        yearly_price_ngn=5000,
        device_limit=3,
        tagline="You plus the phones closest to you.",
        # Plan codes are Paystack-side identifiers; the value here is what the
        # dashboard sends and what the webhook matches on.
        paystack_plan_code="personal_monthly",
        paystack_yearly_plan_code="personal_yearly",
    ),
    "guardian": _plan(
        name="Guardian",
        price_ngn=1500,
        yearly_price_ngn=15000,
        device_limit=10,
        tagline="The whole family — or a small business.",
        paystack_plan_code="guardian_monthly",
        paystack_yearly_plan_code="guardian_yearly",
    ),
    # Sold through sales, not self-serve: no price, no plan code.
    "enterprise": _plan(
        name="Enterprise",
        price_ngn=None,
        yearly_price_ngn=None,
        device_limit=ADMIN_DEVICE_LIMIT,
        tagline="Fleets, schools, and security teams.",
    ),
}

# Tiers that may legally appear in users.tier.
VALID_TIERS = set(PLANS) | {ADMIN_TIER}

# Tiers that can be bought through self-serve checkout (a price AND a code).
SELLABLE_TIERS = {t for t, p in PLANS.items() if p["price_ngn"] and p["paystack_plan_code"]}

# ── Legacy aliases ───────────────────────────────────────────────────────────
# routes/payments.py used to sell a "sentinel" tier that no other surface knew
# about. Accounts already carrying that value must keep their full allowance
# instead of silently dropping to the free fallback, so it resolves to the
# equivalent tier.
LEGACY_TIER_ALIASES = {"sentinel": "enterprise"}


def resolve_tier(tier: Optional[str]) -> str:
    """Normalize an arbitrary stored tier value to a known tier name.

    Unknown values resolve to "free" — never to a paid or unlimited tier, so a
    typo or a stale value can't silently grant more than the free allowance.
    """
    value = (tier or "").strip().lower()
    value = LEGACY_TIER_ALIASES.get(value, value)
    return value if value in VALID_TIERS else "free"


def device_limit(tier: Optional[str]) -> int:
    """Default device allowance for a tier (before operator overrides)."""
    resolved = resolve_tier(tier)
    if resolved == ADMIN_TIER:
        return ADMIN_DEVICE_LIMIT
    return PLANS[resolved]["device_limit"]


def default_limits() -> dict:
    """Tier -> default device allowance, for config's mergeable table."""
    limits = {tier: plan["device_limit"] for tier, plan in PLANS.items()}
    limits[ADMIN_TIER] = ADMIN_DEVICE_LIMIT
    return limits


def tier_for_plan_code(code: Optional[str]) -> Optional[str]:
    """Resolve a Paystack plan code (monthly or yearly) to its tier.

    Used by the payment webhook, which receives only the provider's plan code.
    """
    if not code:
        return None
    for tier, plan in PLANS.items():
        if code in (plan["paystack_plan_code"], plan["paystack_yearly_plan_code"]):
            return tier
    return None


def public_plans() -> list:
    """Plan list for the public /api/payments/plans endpoint."""
    return [
        {
            "id": tier,
            "name": plan["name"],
            "price_ngn": plan["price_ngn"],
            "yearly_price_ngn": plan["yearly_price_ngn"],
            "device_limit": plan["device_limit"],
            "tagline": plan["tagline"],
            "features": plan["features"],
        }
        for tier, plan in PLANS.items()
    ]
