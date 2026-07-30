# Magneetar — Strategic Roadmap

**Version:** 2.0  
**Last Updated:** 2026-07-29  
**Status:** 🟢 Active Development  

---

## Vision Statement

> Build the most trusted, intelligent, and resilient anti-theft ecosystem — one that protects assets across mobile, web, and embedded hardware while maintaining absolute user privacy and security.

---

## Current Position (v1.0.0)

The Magneetar ecosystem is production-ready with:
- **Android app** with stealth tracking, evidence capture, and remote commands
- **Backend API** with Sentinel AI theft detection and multi-channel alerts
- **Dashboard** with real-time map, command center, and evidence viewer
- **3-layer background persistence** (dual foreground services + AlarmManager watchdog + WorkManager health checks) — with Huawei PowerGenie wakelock bypass
- **OEM-specific survival** — auto-start guidance, delayed boot, and locked-app instructions for Xiaomi, Huawei, Oppo, Vivo, Realme
- **Full onboarding flow** with sign-up, sign-in, guided permissions, and battery optimization exemption
- **CI/CD pipeline** — automated release build, version bumping, ProGuard, signing, and git tagging (`scripts/build-release.sh`)
- **Firebase automation** — Firebase CLI setup script for FCM push notifications (`scripts/firebase-setup.sh`)

---

## 🚩 Milestone 1: Production Hardening (Weeks 1-3)

**Theme:** *"Make it bulletproof"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **Setup FCM push notifications** | ✅ Scripted via `scripts/firebase-setup.sh` — requires manual `firebase login` auth, then automates project creation + config download | 1 hour |
| 🔴 P0 | **Android release to Play Store** | Generate production signing key, create Play Store listing, submit for review | 1 week |
| 🔴 P0 | **ProGuard audit** | Verify no critical code is stripped in release builds; test release APK on 5+ device models | 2 days |
| 🟡 P1 | **Crash reporting** | Integrate Sentry or Firebase Crashlytics into the Android app | 2 days |
| 🟡 P1 | **Analytics** | Add anonymous usage analytics (crash-free rate, active devices, command success rate) | 3 days |
| 🟢 P2 | **Performance profiling** | Measure battery drain, network usage, memory footprint on low-end devices | 3 days |

### Deliverables
- [ ] Firebase FCM configured and verified with end-to-end push test
- [ ] Release APK signed with production key, uploaded to Google Play Console
- [ ] Crash reporting operational with 48h of data
- [ ] Performance benchmarks documented

---

## 🚩 Milestone 2: Multi-User & Device Ownership (Weeks 4-6)

**Theme:** *"One account, many devices"*

| Priority | Task | Details | Effort |
|----------|------|---------|--------|
| 🔴 P0 | **Device → User linking** | When a user signs in on Android, link the device to their account via device registration API | 3 days |
| 🔴 P0 | **Multi-device dashboard** | Show all devices owned by a user; filter by device, group by location | 3 days |
| 🟡 P1 | **Role-based access** | Admin, viewer, and device-only roles for dashboard users | 4 days |
| 🟡 P1 | **Device sharing** | Allow sharing device access with another user (e.g., family member) | 5 days |
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
| 🔴 P0 | **SOS signal from app** | When device is stolen, broadcasts encrypted SOS via BLE + Wi-Fi direct | 1 week |
| 🟡 P1 | **Crowd-sourced location** | Guardian Network nodes report sightings of stolen devices (opt-in, privacy-preserving) | 2 weeks |
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
| 🔴 P0 | **SIM change detection** | Detect SIM card swap and auto-activate theft mode | 2 days |
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

- [ ] **Week 1:** Setup Firebase — run `bash scripts/firebase-setup.sh`
- [ ] **Week 1:** Install APK on 5+ device models — run `bash scripts/install-apk.sh` per device
- [ ] **Week 1:** Document findings in `docs/TEST_PLAN.md`
- [ ] **Week 2:** Create Google Play Developer account ($25 one-time fee)
- [ ] **Week 2:** Prepare store listing (screenshots, description, privacy policy)
- [ ] **Week 2:** Generate production signing key (separate from dev keystore)
- [ ] **Week 3:** Submit first release to Play Store (closed track)

---

*This roadmap is a living document. Review and update monthly based on actual velocity, user feedback, and emerging priorities.*
