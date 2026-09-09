# Magneetar — Delivery Tier Map

**Principle:** Underpromise and overdeliver. Never the opposite.

This document is the single source of truth for what we ship, what's ready,
and what we're honest about. Update it whenever status changes.

Last updated: 2026-09-04

---

## Tier 1: Bulletproof (Ship-Ready)

These features work end-to-end, have test coverage, handle edge cases,
and are safe to promise to users today.

| Feature | Backend | Dashboard | Android | Tests | Status |
|---------|---------|-----------|---------|-------|--------|
| **Real-time GPS tracking** (3s intervals) | ✅ Full | ✅ Live map | ✅ Foreground service | ✅ | 🟢 Ship |
| **Device registration + JWT auth** | ✅ Full | ✅ Login flow | ✅ Onboarding | ✅ | 🟢 Ship |
| **Remote commands** (lock, siren, wipe, photo, audio) | ✅ Full | ✅ Command UI | ✅ Executor | ✅ | 🟢 Ship |
| **Theft detection** (Sentinel scoring engine) | ✅ Full | ✅ Score display | ✅ Local scoring | ✅ | 🟢 Ship |
| **Evidence capture** (auto-photo, audio on theft) | ✅ Full | ✅ Evidence viewer | ✅ Media capture | ✅ | 🟢 Ship |
| **SMS relay** (offline command delivery) | ✅ Full | ⚠️ Status only | ⚠️ Basic | ✅ | 🟢 Ship |

**Promise level:** "These work. You can rely on them."

---

## Tier 2: Functional (Works, Needs Polish)

These features work but have rough edges. We can mention them but should
be honest that they're improving.

| Feature | Backend | Dashboard | Android | Tests | Gaps |
|---------|---------|-----------|---------|-------|------|
| **Geofencing** (safe zones + exit alerts) | ✅ Full | ✅ CRUD + map | ⚠️ Basic | ✅ | Edge cases covered (14 tests) |
| **Push alerts** (FCM, SMS, email) | ✅ Full | ✅ Alert feed | ✅ FCM received | ✅ | WhatsApp channel stub only |
| **Family circles** (shared locations) | ✅ Full | ✅ Circle UI | ⚠️ "Needs polish" | ✅ | Android UX needs work |
| **Web dashboard** (live map, devices) | ✅ Full | ✅ Deployed | N/A | ✅ | Mobile responsive needs work |
| **Websocket real-time** (live updates) | ✅ Full | ✅ Connected | N/A | ✅ | Multi-worker edge cases |

**Promise level:** "These work. Some parts are being polished."

---

## Tier 3: Backend-Only (No User-Facing UI Yet)

These features have working backend code but no (or minimal) dashboard/Android UI.
They function via API but aren't discoverable by regular users.

| Feature | Backend | Dashboard | Android | Status |
|---------|---------|-----------|---------|--------|
| **IMEI vault** (secure storage) | ✅ | ✅ Basic | ⚠️ | 🔧 API-ready |
| **Police report generation** (PDF) | ✅ | ✅ Download | ❌ | 🔧 API-ready |
| **Developer API keys** (third-party) | ✅ | ⚠️ Admin only | N/A | 🔧 API-ready |
| **Data export** (GDPR) | ✅ | ⚠️ Admin only | N/A | 🔧 API-ready |
| **Consent management** (GDPR) | ✅ | ⚠️ | ⚠️ | 🔧 API-ready |
| **BLE mesh** (offline finding) | ✅ | ⚠️ Basic | ⚠️ | 🔧 Experimental |
| **Guardian network** (community recovery) | ✅ | ⚠️ | ⚠️ | 🔧 Experimental |
| **USSD menu** (feature phones) | ✅ | N/A | N/A | 🔧 API-ready |

**Promise level:** "Available via API. UI coming."

---

## Tier 4: Planned (Design Phase, No Code)

Features we've designed but not built. These are NOT in any release notes,
NOT on the landing page, and NOT promised to users.

| Feature | Status | Blocked By |
|---------|--------|-----------|
| Smart geofencing (ML-based) | Design only | Needs ML pipeline |
| Offline P2P relay | Design only | Needs Android P2P implementation |
| Digital inheritance | Design only | Needs legal review |
| Recovery bounties | Design only | Needs payment escrow |
| USSD payments | Design only | Needs Paystack USSD integration |
| Community watch (analytics) | Design only | Needs privacy framework |

**Promise level:** "We're thinking about it. Not committed."

---

## What We Tell Users

### Landing page / README (public-facing):
> "Magneetar tracks your phone in real-time, detects theft, captures evidence,
> and lets you lock or alarm it remotely — even when it's offline."

That's the honest pitch. It covers Tier 1 features only.

### Feature list (secondary):
> "Geofencing, family sharing, push alerts, and a web dashboard."

That's Tier 2.

### Everything else:
Don't mention it until it's Tier 1.

---

## Rules

1. **No feature gets added to Tier 1 without:** working backend + working UI + tests passing
2. **No feature appears in marketing until:** it's Tier 1 or Tier 2
3. **Tier 3 features are documented for developers only:** API docs, not user docs
4. **Tier 4 features never leave this document:** no code, no flags, no promises
5. **This document is updated every Friday:** the team reviews what moved tiers

---

## Current Score: 5.5/10 → Target

| Metric | Today | 30-day target | 90-day target |
|--------|-------|---------------|---------------|
| Tier 1 features | 6 | 8 (+ geofencing, push alerts) | 10 (all Tier 2 → Tier 1) |
| Test coverage | 652 tests ✅ | 700+ tests | 800+ tests |
| main.py size | 258 lines ✅ | <200 lines | <150 lines |
| Android UI | "Needs polish" | Functional | Polished |
| Dead code/flags | 7 removed | 0 | 0 |
| Architecture score | 5.5/10 | 6.5/10 | 8/10 |
