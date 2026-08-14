# Magneetar — G1 Validation Tracker

Fill this in as devices report. One row per device per condition. A condition
is PASS only when it survived a real scenario (not a lab simulation).
Supporting artifacts live next to this file: the recruitment message
(`docs/tester-recruitment-message.md`), the feedback form
(`docs/tester-feedback-form.md`), and the program rules
(`docs/REAL_WORLD_VALIDATION_PLAN.md`).

> Gate: **G1 exit (ALL must hold)** — zero open P0s (and none in the final 7
> days), no silent-tracking-death (`last_seen` gap > 30 min while armed),
> recovery drill 12/12 on EVERY device, battery drain within band, ≥80% of
> testers "keep using / recommend", all findings closed or owner-accepted.

---

## 1. Device roster

| Slot | Device (model) | Android | RAM | Tester | Install date | 2-week window ends | Status |
|---|---|---|---|---|---|---|---|
| 1 | Samsung SM-A037F (fleet) |  |  |  |  |  | ☐ running |
| 2 | Tecno / Infinix / Itel (Transsion) |  |  |  |  |  | ☐ running |
| 3 | Xiaomi / Redmi |  |  |  |  |  | ☐ running |
| 4 | Low-end 2–3 GB RAM |  |  |  |  |  | ☐ running |
| 5 | Android 14/15 device |  |  |  |  |  | ☐ running |
| 6 | AOSP image — **no "network" provider** (regression: v1.4.2 crash fix) |  |  |  |  |  | ☐ running |
| 7+ | (extra real users) |  |  |  |  |  | ☐ running |

## 2. Condition matrix (per device — mark PASS / FAIL / N-TESTED + note)

Conditions keyed to `docs/REAL_WORLD_VALIDATION_PLAN.md` §2.2. Copy this
table per device, or keep one big matrix with columns per slot.

| Condition | D1 | D2 | D3 | D4 | D5 | D6 | Notes |
|---|---|---|---|---|---|---|---|
| Background survival — full day unused; `last_seen` stays fresh (no user action) |  |  |  |  |  |  |  |
| Offline queue — 2G/3G dead zone or airplane toggle; no gaps/dups on reconnect |  |  |  |  |  |  |  |
| SIM swap — `sim_changed` always-deliver alert (alert row + FCM push) |  |  |  |  |  |  |  |
| GPS-off / location disabled — graceful, no crash |  |  |  |  |  |  |  |
| Battery saver / low battery — Find Network paces; tracking survives |  |  |  |  |  |  |  |
| Evidence capture from LOCKED screen (front photo + audio, armed response) |  |  |  |  |  |  |  |
| FGS notification visible; honest command acks |  |  |  |  |  |  |  |
| Device-admin uninstall protection + theft-signal on deactivate |  |  |  |  |  |  |  |
| App's own dialogs NOT blocked by the uninstall guard (battery-optimization grant, precise-location change) |  |  |  |  |  |  |  |
| Geofence exit → auto-action fires exactly once |  |  |  |  |  |  |  |
| Command round-trip — dashboard → device → `executed` (real network) |  |  |  |  |  |  |  |
| Play Protect install path (pause-scanning workaround) works |  |  |  |  |  |  |  |
| **Recovery drill 12/12** (theft → Sentinel → recovery request → BLE beacon → guardian sighting → close) |  |  |  |  |  |  |  |

## 3. Battery drain (48h per device)

| Slot | mAh/day app-only (settings → battery → Magneetar) | % of battery/day | Within band (≤ ~15%)? |
|---|---|---|---|
| 1 |  |  | ☐ |
| 2 |  |  | ☐ |
| 3 |  |  | ☐ |
| 4 |  |  | ☐ |
| 5 |  |  | ☐ |
| 6 |  |  | ☐ |

## 4. Feedback summary (from `docs/tester-feedback-form.md`)

| Slot | Weekly check-ins done | P0s reported | P1s | P2s | "Keep using / recommend" (yes/no) |
|---|---|---|---|---|---|
| 1 | ☐/2 |  |  |  |  |
| 2 | ☐/2 |  |  |  |  |
| 3 | ☐/2 |  |  |  |  |
| 4 | ☐/2 |  |  |  |  |
| 5 | ☐/2 |  |  |  |  |
| 6 | ☐/2 |  |  |  |  |

## 5. Server-side signals (checked at exit)

| Signal | Where | Result |
|---|---|---|
| `error_log` rows during the window | server logs / dashboard Errors tab |  |
| Unexplained `last_seen` gaps > 30 min while armed | dashboard device list / DB |  |
| `/health` uptime + DB health over the window | api.magneetar.me/health |  |
| Sentry events (if DSN configured) | Sentry project dashboard |  |

## 6. G1 exit checklist (ALL boxes required to pass)

- [ ] Device roster: ≥6 devices / ≥4 OEMs (incl. Transsion + no-network-provider regression device)
- [ ] Each device ran ≥2 continuous weeks as a daily driver
- [ ] Condition matrix fully populated — no N-TESTED left where it must be tested
- [ ] Recovery drill 12/12 on every device
- [ ] Battery drain within band on every device
- [ ] Zero open P0s; none new in the final 7 days
- [ ] No silent-tracking-death in the final week
- [ ] ≥80% of testers "keep using / recommend"; all P1/P2 findings closed or owner-accepted
- [ ] Exit documented (drill logs + feedback results + fix list) → **then start G2 (closed testing)**
