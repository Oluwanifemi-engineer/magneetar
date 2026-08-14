# ADR-0006: Play Store production submission gated on real-world validation + user approval

- **Status:** Accepted (2026-08-14, product-owner decision)
- **Related:** `docs/REAL_WORLD_VALIDATION_PLAN.md`, ADR-0001 (SQLite),
  `docs/PLAY_READINESS_VERDICT.md`, `docs/DISTRIBUTION_PLAN.md`

## Context

Magneetar is technically ~85% submission-ready (see
`docs/PLAY_READINESS_VERDICT.md`): fresh signed AAB, play-clean permission
profile, live privacy policy, store-listing assets, paste-ready declaration
answers. All verification to date has been **developer-driven** — automated
suites (549 backend / 198 dashboard / Android JVM), live E2E scripts against
production, and a single-fleet-phone recovery drill.

What has NOT happened is validation by **real users under real-world
conditions**: OEM battery killers across the low-end Android market
(Samsung A-series, Tecno, Infinix, Itel, Xiaomi), Android 14/15 background
execution rules, poor networks with the offline queue, SIM swaps, actual
prolonged daily use, and — most important for an anti-theft product — real
people trusting it with their phone. The failure mode that matters is not a
Play policy rejection; it is shipping a product that silently dies in the
field (the exact class of bug the v1.4.2 batch fixed: a missing location
provider crash-looping the tracking service).

Play's own rules already force a form of this: new developer accounts must
complete **14 continuous days of closed testing with ≥12 active testers**
before production access. This decision makes real-world validation a
first-class product gate instead of a compliance chore to rush through.

## Decision

**No Play Store production submission — and no production-access request —
until Magneetar has passed a real-world validation program: real devices,
real-world conditions, and explicit user approval.** Two gates:

- **G1 — Sideload / download-page validation**: real users run the v1.4.2
  play-clean build as their daily driver on a spread of real devices for a
  defined period; exit = zero critical bugs + documented user approval
  (criteria in `docs/REAL_WORLD_VALIDATION_PLAN.md` §3).
- **G2 — Play closed testing**: only after G1 passes, the v1.4.2 AAB enters
  Play's closed track (≥12 active testers, 14 days). Testers are real users;
  their approval + a crash-free window is the gate to requesting production
  access. Production rollout then stays staged (1–5% → 10–20% → 50% → 100%).

"Approved by users" is defined operationally in the validation plan (feedback
forms, tester counts, drill results) — not by developer judgment.

## Consequences

- **Positive:** real-world bugs surface while the distribution channel is
  still the controlled download page; Play review questions about device-admin
  / background location are answered with real-user evidence; the 14-day
  closed-testing clock is not wasted on an unvalidated build.
- **Positive:** the download page (magneetar.me/download) becomes the primary
  distribution channel during validation — it already serves the play-clean
  v1.4.2 build — rather than a stopgap waiting for Play.
- **Neutral:** Play Console prep work (screenshots, declaration forms,
  listing) may continue in parallel — nothing is lost by preparing; only the
  Upload / Submit action waits.
- **Neutral:** Twilio SMS/WhatsApp alerts are already on hold (owner: no
  credits); validation relies on FCM push + Resend email, which are live and
  verified. Recharging Twilio stays a prerequisite for launch-day alert
  coverage, not for G1/G2.
- **Cost:** production availability is delayed by the length of G1 + G2
  (minimum ~4–6 weeks from now); accepted by the owner in exchange for a
  field-proven launch.
