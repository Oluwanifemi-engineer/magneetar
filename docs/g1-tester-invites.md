# Magneetar — Play internal-testing tester invites (G1/G2)

> **What this is:** the Google Play **internal testing** track is the official
> install channel for the G1 (real-world validation) and G2 (closed testing)
> cohorts (ADR-0007). Modern Android hard-blocks sideloading Magneetar's
> permission profile, so Play internal testing is the only friction-free path
> that keeps the "no public release before validation" rule intact.
>
> **Status (2026-08-16):** v1.4.4 AAB (versionCode 11) is staged for the
> internal track. This doc is the invite checklist + email copy. **Owner
> step:** add the tester emails in the Play Console, then send the invite
> links (or share this email).

---

## The 30-second version (owner)

1. Play Console → **Magneetar** → **Testing → Internal testing** →
   **Testers** (or the "Create release" flow on this track).
2. Add tester **email addresses** (below — replace with the real cohort).
3. **Copy the invite link** (shown on the same page) — every tester opens
   that link, opts in, and the app becomes installable for them.
4. Upload the AAB (v1.4.4, versionCode 11) if not already on the track, and
   **Create release**.
5. Send each tester the invite email (copy below) with their invite link.

> Note: each tester must be **opted-in with their link before** the release is
> live for them. If someone gets "not allowed to test", re-share the link.

---

## Tester checklist (G1 — real-world validation)

| # | Role | Device(s) needed | Criteria |
|---|---|---|---|
| 1 | Primary tester (owner) | Daily driver (Samsung A037F, Android 13) | Already in the program |
| 2 | Family member | Any Android 10+ | Real usage, ≥2 weeks |
| 3 | Friend/colleague | Transsion device (Tecno/Infinix/Itel) | Nigerian market representative |
| 4 | Friend/colleague | Second Transsion or budget device | No-network-provider regression device |
| 5 | Tester | Android 14/15 device | Boot/background-restriction coverage |
| 6 | Tester | Android 10/11 device | Older-OS coverage |

**G1 minimum:** ≥5 devices, ≥4 OEMs, ≥2 weeks each as a daily driver,
recovery drill 12/12 per device, battery within band, ≥80% "keep using /
recommend" (see `docs/g1-validation-tracker.md` exit checklist).

**G2 minimum (after G1 exit):** ≥12 testers, ≥14 days continuous opt-in on
the closed track, tester sign-off (Play's closed-testing requirement for new
developer accounts).

---

## Invite email (copy-paste)

Subject: **Help test Magneetar — anti-theft for Android**

Hi [NAME],

I'm building Magneetar, an anti-theft app for Android that detects theft
signals (SIM change, failed unlocks, leaving a safe zone), tracks the device,
and captures evidence — no root needed. It's in real-world validation before
any public release, and I'd like you to be one of the first testers.

**What you get:**
- The app installs normally from the Play Store (no sideloading, no warnings).
- Free use for the whole test period, with full anti-theft features.

**What it will ask:**
- Location (including in the background) — used only for theft tracking.
- Camera + microphone — used ONLY during an active theft response to capture
  evidence; nothing is recorded in normal use.
- Device admin — keeps the protection running; you'll confirm this yourself
  at setup and can remove it any time.

**What I ask of you:**
- Install it on your main phone and carry it normally for at least 2 weeks.
- Keep tracking enabled (the app tells you how to stop the phone's battery
  optimizer from killing it).
- Tell me about anything that breaks, drains battery, or feels wrong —
  that's exactly what this phase is for.

**How to install:**
1. Open this link on your phone: [INVITE LINK]
2. Tap "Accept invitation", then install Magneetar from the Play Store.
3. Open the app, create an account with your email, and follow setup.

Your data stays on our server, encrypted; you can delete your account and all
your data from the app at any time. No ads, no selling data, source
published.

Thanks for helping make this thing reliable!

— [YOUR NAME]

---

## Safety notes for testers

- The app is real anti-theft software: if it's armed and the phone sees
  repeated failed unlock attempts or a SIM change, it will capture a photo /
  audio and alert the owner. Tell testers to expect this and to test the
  disarm flow.
- Battery: the armed watch is designed for ≤1.5%/h. If a tester sees more,
  that's a P1 finding — log it in the tracker.
- The Play build deliberately has NO SMS command relay and NO accessibility
  service (Play policy) — those are sideload-flavor only. Don't test SMS
  commands on the Play build.
