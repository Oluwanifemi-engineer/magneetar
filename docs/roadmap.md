# Magneetar — Strategic Roadmap

**Version:** 3.1  
**Last Updated:** 2026-08-14  
**Status:** 🟢 Active Development  

---

## Vision Statement

> Build the most trusted, intelligent, and resilient anti-theft ecosystem — one that protects assets across mobile, web, and embedded hardware while maintaining absolute user privacy and security.

---

## Current Position (v1.4.2)

The Magneetar ecosystem is production-ready with:
- **Android app** with stealth tracking, evidence capture, and remote commands
- **Backend API** with Sentinel AI theft detection and multi-channel alerts
- **Dashboard** with real-time map, command center, and evidence viewer
- **3-layer background persistence** (dual foreground services + AlarmManager watchdog + WorkManager health checks) — with Huawei PowerGenie wakelock bypass
- **OEM-specific survival** — auto-start guidance, delayed boot, and locked-app instructions for Xiaomi, Huawei, Oppo, Vivo, Realme
- **Full onboarding flow** with sign-up, sign-in, guided permissions, and battery optimization exemption
- **CI/CD pipeline** — automated release build, version bumping, ProGuard, signing, and git tagging (`scripts/build-release.sh`)
- **Firebase automation** — Firebase CLI setup script for FCM push notifications (`scripts/firebase-setup.sh`)
- **Guardian Network + Find Network Phase 1 live** — SOS BLE beacon broadcast + opt-in guardian sightings end-to-end (v1.6)
- **Session tokens encrypted at rest** — AndroidKeyStore AES-256-GCM vault; no plaintext credentials on disk (v1.4.2)
- **Transactional email delivering** — Resend provider: reset/verify links finally reach users (v1.4.2)
- **Developer API keys live** — scoped `mtk_` keys with a read-only type + usage metering (v1.7)
- **Test suite** — 549 backend + 198 dashboard, all green (2026-08-14)

---

## 🚩 Milestone 1: Production Hardening (Weeks 1-3)

**Theme:** *"Make it bulletproof"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **Setup FCM push notifications** | ✅ Scripted via `scripts/firebase-setup.sh` — requires manual `firebase login` auth, then automates project creation + config download | 1 hour |
| 🔴 P0 | **Android release to Play Store** | Generate production signing key, create Play Store listing, submit for review | 1 week | 🔒 **GATED (ADR-0006)** — production submission blocked until real-world validation + user approval pass (docs/REAL_WORLD_VALIDATION_PLAN.md) |
| 🔴 P0 | **ProGuard audit** | Verify no critical code is stripped in release builds; test release APK on 5+ device models | 2 days |
| 🟡 P1 | **Crash reporting** | Integrate Sentry or Firebase Crashlytics into the Android app | 2 days |
| 🟡 P1 | **Analytics** | Add anonymous usage analytics (crash-free rate, active devices, command success rate) | 3 days |
| 🟢 P2 | **Performance profiling** | Measure battery drain, network usage, memory footprint on low-end devices | 3 days |

### Deliverables
- [ ] Firebase FCM configured and verified with end-to-end push test
- [x] Release APK signed with production key, ready for upload (v1.4.2 AAB built + verified 2026-08-14)
- [ ] **Real-world validation passed** (G1 — docs/REAL_WORLD_VALIDATION_PLAN.md) then uploaded to Google Play Console (ADR-0006 gate)
- [ ] Crash reporting operational with 48h of data
- [ ] Performance benchmarks documented

---

## 🚩 Milestone 2: Multi-User & Device Ownership (Weeks 4-6)

**Theme:** *"One account, many devices"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **Device → User linking** | When a user signs in on Android, link the device to their account via device registration API | 3 days |
| 🔴 P0 | **Multi-device dashboard** | Show all devices owned by a user; filter by device, group by location | 3 days |
| 🟡 P1 | **Role-based access** | Admin, viewer, and device-only roles for dashboard users | ✅ **DONE** — `_assert_device_access(db, id, auth, min_role)` role floors on every device endpoint; device list tags `access_role`/`is_owner` |
| 🟡 P1 | **Device sharing** | Allow sharing device access with another user (e.g., family member) | ✅ **DONE** — `device_shares` table + `POST/GET/DELETE .../shares` (owner-only, idempotent upsert), Sharing card UI, WS live updates for shared devices, `device_only` privacy tier |
| 🟢 P2 | **Organization accounts** | Multi-user teams with shared device pools | 1 week |

### Architecture Changes
- Database: Add `user_id` foreign key to `devices` table (already has `owner_id` column)
- API: New endpoints for device ownership transfer
- Android: Register device with user token during onboarding

---

## 🚩 Milestone 3: Guardian Network (Weeks 7-10)

**Theme:** *"Community-powered recovery"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **SOS signal from app** | When device is stolen, broadcasts encrypted SOS via BLE + Wi-Fi direct | 1 week | ✅ **Phase 1 done (v1.6)** — `SosBeaconBroadcaster` BLE beacon + `GuardianBeaconScanner` |
| 🟡 P1 | **Crowd-sourced location** | Guardian Network nodes report sightings of stolen devices (opt-in, privacy-preserving) | 2 weeks | ✅ **done** — opt-in guardian sightings + recovery-request lifecycle |
| 🟡 P1 | **Geofence alerts to guardians** | Notify trusted guardians when device leaves safe zone | 3 days |
| 🟢 P2 | **Reward system** | Optional bounty for recovery assistance | 1 week |

### Privacy Considerations
- All sightings are anonymous and encrypted
- Users opt-in explicitly to Guardian Network
- No location data shared without theft confirmation

---

## 🚩 Milestone 4: Intelligent Theft Detection (Weeks 11-14)

**Theme:** *"AI that doesn't cry wolf"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **SIM change detection** | Detect SIM card swap and auto-activate theft mode | 2 days | ✅ **done (v1.4.1)** |
| 🟡 P1 | **ML-based anomaly detection** | Train model on movement patterns; detect unusual behavior | 2 weeks |
| 🟡 P1 | **False positive reduction** | Implement confirmation chain: 3 consecutive anomalies before alert | 3 days |
| 🟡 P1 | **Auto-evidence capture** | On theft detection, automatically capture front camera photo + audio | 2 days |
| 🟢 P2 | **BLE proximity detection** | Trigger alerts when known BLE tags (smartwatch, earbuds) disconnect unexpectedly | 1 week |

### Sentinel AI Enhancements
- Current: Rule-based scoring (location speed, battery drop, airplane mode)
- Future: ML model running on-device via TensorFlow Lite
- Training data: Anonymized movement patterns from opt-in users

---

## 🚩 Milestone 5: Cross-Platform & Hardware (Weeks 15-20)

**Theme:** *"Beyond Android"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🟡 P1 | **iOS app** | SwiftUI app with core tracking features | 4 weeks |
| 🟡 P1 | **BLE asset tag prototype** | Custom ESP32 firmware + 3D-printed enclosure | 3 weeks |
| 🟡 P1 | **Desktop dashboard PWA** | Progressive Web App for desktop with offline support | 2 weeks |
| 🟢 P2 | **iOS background persistence** | Work through iOS background execution restrictions | 2 weeks |
| 🟢 P2 | **BLE tag production** | FCC/CE certification, injection molding, packaging | 2 months |

---

## 🚩 Milestone 6: Enterprise & Monetization (Weeks 21+)

**Theme:** *"Sustainable growth"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🟡 P1 | **Subscription tiers** | Free (1 device, 30-day history) → Pro (5 devices, 1-year history) → Enterprise (unlimited) | 2 weeks |
| 🟡 P1 | **White-label option** | Branded version for businesses (fleet tracking, school device protection) | 3 weeks |
| 🟢 P2 | **API marketplace** | Public API for third-party integrations (home automation, insurance) | 4 weeks |
| 🟢 P2 | **Hardware store** | Sell BLE tags + installation kits directly | Ongoing |

---

## 🚩 Milestone 7: Premium Product Features (2026-08-07)

**Theme:** *"From a working system to a premium product"*

Researched 2026-08-07 against the premium landscape (Google Find Hub, Apple
Find My, Life360, Prey, Cerberus, mSpy). Key strategic finding: **Google's
crowdsourced offline-finding network is closed to third-party apps** (certified
hardware only), so Magneetar's private BLE find-network is the differentiator no
competitor offers us for free. The privacy-hostile lessons of the market
(mSpy-style hidden monitoring, Life360's location-data selling) are the brand
we must never copy.

### Phase A — Quick wins (weeks, high visible impact)

| Priority | Feature | Details | Effort |
|----------|---------|---------|-------|
| 🔴 P0 | **Lost-Mode lock screen** | Push lock + "call this number / reward if found" overlay to the stolen phone's screen; drives good-Samaritan recovery | 1 week | ✅ **DONE (v1.5)** |
| 🔴 P0 | **Recovery Dossier** | One-click police/insurer package: evidence PDF + location timeline + IMEI + theft case + Guardian sightings | 1 week | ✅ **DONE (v1.6)** — command timeline + all photos + RBAC-gated |
| 🔴 P0 | **Offline cell resolution (OpenCelliD)** | Bundle the Nigeria dump (MCC 621) for the existing `/cell-locate` endpoint — real fixes for offline stolen phones | 1 week |
| 🟡 P1 | **Trip history & heatmap** | Persistent 30-day timeline, revisits, heatmap replay (free 7-day / paid 30-day lever) | 1 week |
| 🟡 P1 | **Family/Team circles with roles** | Owner / co-admin / view-only (extends multi-user ownership) | 1 week | ✅ **DONE (v1.6)** — device sharing + RBAC (admin / viewer / device_only) |
| 🟡 P1 | **Geofence automated actions** | Per-zone policy: leave home at 2am → auto siren + front capture + alert | 1 week | ✅ **DONE (v1.5)** |
| 🟡 P1 | **Battery-smart tracking** | Adaptive cadence: stationary 60s / moving 3s / <15% battery drain-safe mode | 1 week |
| 🟢 P2 | **Multi-language** | Yoruba, Hausa, Igbo, French, Swahili (app + dashboard) | 2 weeks |
| 🟢 P2 | **In-app notification center** | Alert history with read/unread + channel traceability | 1 week |

### Phase B — Differentiators (months, the premium leap)

| Priority | Feature | Details | Effort | Dependencies |
|----------|---------|---------|-------|--------------|
| 🔴 P0 | **Magneetar Find Network** | Private crowdsourced BLE mesh: apps advertise rotating encrypted beacons; other installs report sightings via the existing Guardian sighting pipeline. Works when data/GPS are off; the on-ramp to hardware tags | 2-3 months | Guardian pipeline (exists), BLE permissions, on-device beacon code | ✅ **Phase 1 DONE (v1.6)** — mesh scale-out, beacon-permission UX, battery-aware scheduling remain |
| 🔴 P0 | **On-device edge Sentinel** | Scoring + auto-capture on the phone when offline (snatch motion, SIM removal, airplane-mode) — theft response that doesn't wait for a network round-trip | 1-2 months | Sentinel rules port to Kotlin; accelerometer access |
| 🟡 P1 | **Zero-knowledge evidence** | Media encrypted at rest with per-device keys, decrypted only on the owner's dashboard (WebCrypto) | 1-2 months | Key management on device + server |
| 🟡 P1 | **Paystack billing** | Free / Premium / Family tiers, card + direct debit, in-dashboard upgrade. Paystack is the standard for Nigerian SaaS | 2-4 weeks | `PLAN_DEVICE_LIMITS` exists; new billing endpoints + webhook |
| 🟡 P1 | **NDPA compliance center** | Granular consent records, one-click data export, right-to-erasure, retention controls, plain-language "who can see what" | 2-4 weeks | — |

### Phase C — Future & hardware

| Priority | Feature | Details | Effort |
|----------|---------|---------|-------|
| 🟡 P1 | **Magneetar Tag (BLE)** | AirTag-class tracker riding the Magneetar Find Network (wallet, keys, bags) | 3 months + cert |
| 🟡 P1 | **Wear OS companion** | Panic siren, last-known-location glance, lock from the wrist | 3 weeks |
| 🟢 P2 | **UWB precision finding** | Direction + distance arrows on supported phones once the Find Network matures | 2 months |
| 🟢 P2 | **Enterprise/B2B mode** | Org dashboard, bulk enrollment, fleet view, read-only law-enforcement dossier portal | 1-2 months |
| 🟢 P2 | **Vehicle tracker module** | Embedded hardware one step past the tag (the architecture already anticipates it) | 3+ months |

### Explicitly out of scope (brand protection)

- ❌ mSpy-style hidden monitoring (message reading, keylogging, "surround" mic) — reputational poison, stalking liability
- ❌ Selling or sharing location data (the Life360 crisis) — the trust position is the brand
- ❌ Invisible operation for non-owner use — keep owner-consent sacred; publish an anti-stalking/ethics page

### Recommended sequencing

1. **Ship Phase A** — Lost Mode + Recovery Dossier + OpenCelliD + trip history (visible, demo-able, defense-friendly)
2. **Bet on the Magneetar Find Network** — the only feature no big player offers us; Guardian already proves the sighting pipeline
3. **Monetize early (Paystack)** so every later feature pays for itself

---

## Resource Requirements

| Role | Milestone 1-2 | Milestone 3-4 | Milestone 5-6 |
|------|---------------|---------------|---------------|
| Android Developer | 1 | 1 | 2 |
| Backend Developer | 1 | 1 | 1 |
| Frontend Developer | 0.5 | 1 | 1 |
| DevOps | 0.5 | 0.5 | 1 |
| ML Engineer | 0 | 1 | 0 |
| Hardware Engineer | 0 | 0 | 1 |
| QA | 1 | 1 | 2 |

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| OEM kills background service | High | High | ✅ Implemented: 3-layer persistence + OEM detection |
| Google Play rejects anti-theft app | Medium | High | Ensure compliance with Play policy; use legitimate permission justifications |
| BLE hardware certification delays | High | Medium | Start certification early; use COTS modules |
| iOS background execution too restrictive | Medium | High | Accept limitations; focus on BLE-based alerts |
| User privacy concerns | Low | High | Publish transparency report; open-source core components |

---

## Success Metrics

| Metric | Current | Target (3 months) | Target (6 months) |
|--------|---------|-------------------|-------------------|
| Crash-free rate | Unknown | >99.5% | >99.9% |
| Background survival rate (Samsung) | Unknown | >95% | >99% |
| Background survival rate (Xiaomi) | Unknown | >80% | >95% |
| Background survival rate (Huawei) | Unknown | >70% | >90% |
| Active users | 0 | 100 | 1,000 |
| Registered devices | 0 | 150 | 2,000 |
| Success rate (theft → recovery) | — | Measure baseline | >60% |
| App rating | — | 4.0★ | 4.5★ |

---

## Immediate Next Actions

> **2026-08-14 (ADR-0006):** Play production submission is gated on real-world
> validation + user approval. Play account/listing prep may proceed in
> parallel, but the Upload/Submit action waits for `docs/REAL_WORLD_VALIDATION_PLAN.md`.

- [ ] **Week 1:** Start the real-world validation program — assemble the device
      matrix (≥6 devices / ≥4 OEMs), recruit ≥5 real users, install the
      v1.4.2 play-clean APK from magneetar.me/download
- [ ] **Week 1:** Setup Firebase — run `bash scripts/firebase-setup.sh`
- [ ] **Week 1:** Document findings in `docs/REAL_WORLD_VALIDATION_PLAN.md` (per-device pass/fail records)
- [ ] **Week 2:** Create Google Play Developer account ($25 one-time fee) — prep only
- [ ] **Week 2:** Prepare store listing (screenshots, description, privacy policy)
- [ ] **Week 2:** Generate production signing key (separate from dev keystore)
- [ ] **Week 3:** Submit first release to Play Store (closed track)

---

*This roadmap is a living document. Review and update monthly based on actual velocity, user feedback, and emerging priorities.*
