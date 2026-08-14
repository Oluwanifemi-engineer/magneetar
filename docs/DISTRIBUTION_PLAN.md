# Magneetar — Distribution Plan

**Date:** 2026-08-14 · **Version:** 1.4.2 (versionCode 8) · **Status:** 🔒 GATED —
the submission sequence below may NOT start until the real-world validation
program passes (owner decision 2026-08-14, ADR-0006,
`docs/REAL_WORLD_VALIDATION_PLAN.md`).

This plan turns the Play Store *readiness* (docs/PLAY_STORE_LISTING.md,
docs/play-store-checklist.md) into an executed rollout with dates, gates,
channels, rollback, and monitoring. Every item marked ✅ has been verified this
session.

---

## 1. Where we are (verified this session)

| Prerequisite | Status |
|---|---|
| **Signed AAB** `android-app/app/build/outputs/bundle/playRelease/app-play-release.aab` — v1.4.2, versionCode 8, play flavor | ✅ built 2026-08-14 |
| **Signature chain** keystore → AAB → sideload APK (cert SHA-256 `02:4C:BB:34…0A:7F`) | ✅ proven via `keytool`/`jarsigner`/`apksigner` |
| **Play flavor is Play-clean** — zero SMS/phone-state perms, zero Accessibility/UninstallGuard (merged playRelease manifest inspected) | ✅ no accessibility matches |
| **Keystore backup** `~/Documents/magneetar-keystore-backup-2026-08-12/` (keystore + RECOVERY.md, byte-identical hashes) | ✅ created |
| **Public URLs** — magneetar.me, /privacy, /terms, /download, /login = 200; api.magneetar.me/api/config = 1.4.2 | ✅ all live |
| **Privacy policy** live and honest (TLS in transit, SHA-256 evidence chain, deletion paths) | ✅ checked |
| **Test standard** — backend 549 passed / 4 skipped (full-suite, CI-equivalent), dashboard 198 passed + tsc + eslint clean, Android both flavors compile + JVM tests | ✅ green |

### Still yours to do (needs a phone / console / money)

1. **6–8 phone screenshots** (set in PLAY_STORE_LISTING.md §7 — incl. the
   mandatory background-location disclosure dialog).
2. **Play Console forms** (~45 min — answers already written in
   PLAY_STORE_LISTING.md).
3. **Twilio recharge** (SMS/WhatsApp alert budget for the test + launch
   period).
4. **Move a 2nd keystore copy off-machine** (encrypted USB / password-managed
   vault — hard rule in RECOVERY.md).
5. **Reinstall the v1.4.2 APK** on the test phone (download page or adb) and
   re-link the dashboard.

---

## 2. Channel strategy

| Channel | Role | Notes |
|---|---|---|
| **Google Play** | BLOCKED until real-world validation passes (ADR-0006) | Play-installed apps bypass the sideload hard block (BIND_DEVICE_ADMIN + camera/mic + background location keep Play Protect blocking any sideload on current Android — see play-store-checklist.md). The only friction-free channel, once the gate passes. |
| **magneetar.me/download** | **PRIMARY during validation** — serves the play-clean v1.4.2 APK (verified SHA-256 `ca4c400d…`); after Play goes live it becomes the fallback for manual installs | Real users install from here during the G1 validation program (docs/REAL_WORLD_VALIDATION_PLAN.md). |
| **Sideload SMS-relay build** | Not public | Buildable only (`assembleSideloadRelease`); archived for internal testing of the offline SMS relay. |

**Decision (2026-08-14, ADR-0006):** Play submission is **gated on real-world
validation + user approval**. Until G1 passes, the download page IS the
primary channel and Play stays untouched. Only after G1 → G2 (closed testing)
pass does the page's primary CTA switch to the Play button.

---

## 3. Submission timeline

### Phase 0 — Real-world validation (BLOCKING GATE — ADR-0006)
> **Do not proceed past this phase until `docs/REAL_WORLD_VALIDATION_PLAN.md`
> passes.** G1 (≥6 devices / ≥4 OEMs, ≥2 weeks daily use, recovery drill
> 12/12, ≥5 users with ≥80% approval) then G2 (Play closed testing, ≥12
> active testers, 14 days, ≥99.5% crash-free, tester sign-off). The clock on
> the 14-day closed-testing requirement should be recruited during G1 so no
> time is lost afterward.

- [ ] Assemble the device matrix and recruit ≥5 real users (per the plan §2)
- [ ] Run G1 for ≥2 weeks of daily use; record every §2.2 condition
- [ ] Document G1 exit (drill logs + feedback results + fix list)
- [ ] THEN start Phase 1 below

### Phase 1 — Pre-flight (after G1 passes, ~1 hr)
- [ ] Capture the 6–8 screenshots (recommended set in PLAY_STORE_LISTING.md §7)
- [ ] Recharge Twilio (budget: 2–5 SMS + WhatsApp per test device per day;
      estimate ₦/month from expected alert volume)
- [ ] Move keystore 2nd copy off-machine
- [ ] Create the Play Console app (name, free, no ads)

### Phase 2 — App content + store listing (after G1 passes, ~45 min)
- [ ] Privacy policy URL → https://magneetar.me/privacy (live ✅)
- [ ] Data Safety form → answers in PLAY_STORE_LISTING.md §2
- [ ] Permissions declaration → §3 (background location, BIND_DEVICE_ADMIN,
      SCHEDULE_EXACT_ALARM, SYSTEM_ALERT_WINDOW)
- [ ] IARC rating → 18+ (honest flags, no violence)
- [ ] Store listing (short ≤80 chars, full description, icon, feature
      graphic, screenshots)

### Phase 3 — Closed testing (the user-approval gate — G2, ADR-0006)
> **Research fact (2026):** new developer accounts must complete **14
> continuous days of closed testing with ≥12 active testers** before Play
> grants production access. Internal testing (100 testers) is fast (~hours)
> and does NOT satisfy this gate. Under ADR-0006 this phase is also the
> real-world user-approval gate — the tester cohort's explicit sign-off is
> required, not just Play's compliance clock.

- [ ] **Week 0:** recruit ≥12 testers (family/WhatsApp groups work — the
      Guardian Network is literally built for this; testers install from the
      closed-track opt-in link, keep the app installed 14 days)
- [ ] Upload the v1.4.2 AAB to **Internal testing** first (fast review,
      ~hours) → smoke-test the Play-signed APKs on a real device
- [ ] Promote the same release to **Closed testing**; expect 24–72h review
      (up to 7d for a new account with device-admin)
- [ ] Run the recovery drill once with 2 testers mid-week (12/12 drill
      script) to catch anything before the production gate

### Phase 4 — Production access request (after G2 sign-off)
- [ ] After the 14-day window with ≥12 active testers → apply for production
      access (manual review 3–7 business days)
- [ ] Be ready to answer review questions referencing docs/security.md,
      docs/PLAY_STORE_LISTING.md, and this plan (device-admin is the likely
      question — Cerberus-class precedent, consumer disclosure path chosen)

### Phase 5 — Production staged rollout (the standard)
| Day | Rollout | Watch |
|---|---|---|
| 0 | **1–5%** | Crashes/ANRs (Play console), policy flags, support emails |
| 3–5 | **10–20%** | Same + server alert volume, WS connections |
| 6–10 | **50%** | Server headroom (SQLite WAL, per-instance scaling.md) |
| 11+ | **100%** | Freeze unless a regression appears |

> If the account is **already established** (production access granted), skip
> Phase 3 and go straight to Phase 5 starting at 10% per PLAY_STORE_LISTING.md
> — but never before the G1 real-world validation gate passes (ADR-0006).

---

## 4. Rollback plan

- **Play App Signing** — Play holds the signing key and can revert a release
  to the previous version in the console (one click) if a regression ships.
- **Version discipline** — every release must bump `versionCode`
  (currently 7) strictly up; a rollback is a NEW version, never a re-upload of
  an old code.
- **Server-side kill switches** — features are flaggable via
  `features_enabled` in `/api/config` (sentinel, evidence_collection,
  geofencing…); worst case the server can reject new registrations without an
  APK change.
- **Alert cost guard** — if Twilio spend spikes, SMS/WhatsApp alert
  rate-limits + per-device alert settings already cap volume server-side.

---

## 5. Post-launch monitoring (first 30 days)

| Signal | Where | Trigger for action |
|---|---|---|
| Crashes/ANRs | Play Console quality page | >0.5% daily → hotfix within 24h |
| Install→activate rate | Play console + server registrations | <20% → revisit disclosure/screenshots |
| Alert delivery failures | server logs (twilio/sms_relay) | any persistent failure → check Twilio balance |
| WebSocket/device churn | server logs (ws accept/close) | spike → scaling.md (SQLite WAL → pg adapter) |
| Play Protect/abuse flags | Play console | immediate — answer within 24h |
| Backend errors | /api/health + error_log table | 5xx rate up → rollback or hotfix |

## 6. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Play rejects BIND_DEVICE_ADMIN | Medium | Fallback already decided: drop `wipe-data` from `device_admin.xml` (one-line) and resubmit |
| 14-day closed-testing delay for a new account | High (new accounts) | Recruit the 12 testers NOW (Phase 2 week 0) so the clock runs during listing polish |
| Sideload hard block scares early users | Certain (known) | Download page CTA → Play; the block is Play's, not ours — a Play listing makes it moot |
| Twilio cost overrun | Medium | Alert settings are per-device and rate-limited; set a balance alert |
| Server capacity at 100% rollout | Low (small launch) | SQLite WAL fine to ~hundreds of devices; pg adapter + scaling.md ready |

---

## 7. Definition of done (distribution)

- [ ] **Real-world validation passed** (G1 exit documented, ADR-0006)
- [ ] **Closed-testing cohort signed off** (G2 exit documented)
- [ ] Play listing live and searchable
- [ ] magneetar.me/download primary CTA points at Play
- [ ] 30-day monitoring cadence set (check §5 weekly)
- [ ] Keystore backups in ≥2 places, RECOVERY.md verified
- [ ] Twilio auto-recharge / balance alert configured
