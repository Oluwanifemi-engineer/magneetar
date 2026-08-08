# Google Play Store Submission Checklist

## Overview

This document outlines the complete process for submitting Magneetar to the Google Play Store.

**Timeline**: 2-4 weeks (including closed testing requirement)

**Cost**: $25 USD (one-time developer account fee)

---

## Prerequisites

### 1. Developer Account Setup
- [ ] Create Google Play Console account at https://play.google.com/console
- [ ] Pay $25 USD registration fee
- [ ] Provide legal/contact details
- [ ] Verify email address

### 2. Technical Requirements
- [ ] Android App Bundle (.aab) format
- [ ] Target SDK 36+ (required Aug 31, 2026)
- [ ] Signed with release keystore
- [ ] No SMS permissions (already handled via Play flavor)

---

## App Content Requirements

### 3. Store Listing

**Short Description** (80 characters max):
```
Anti-theft protection: track, lock, and recover your stolen phone.
```

**Full Description** (4,000 characters max):
```
Magneetar is a powerful anti-theft app that protects your Android phone from theft and loss.

CORE FEATURES:
• Real-time GPS tracking with turn-by-turn navigation
• Remote lock and alarm activation
• Remote wipe (factory reset) for data protection
• Photo and audio evidence capture
• Sentinel AI theft detection
• Guardian Network for community recovery

HOW IT WORKS:
1. Install Magneetar and link it to your account
2. If your phone is stolen, use the web dashboard to:
   - Track its real-time location
   - Lock it remotely
   - Trigger a loud alarm
   - Capture photos and audio evidence
   - Wipe all data if recovery is impossible

PRIVACY & SECURITY:
• End-to-end encryption for all data
• No ads, no tracking, no data selling
• Open source and transparent
• You control all your data

PERMISSIONS:
• Location: Required for theft tracking
• Camera/Microphone: For evidence capture (only when armed)
• Notifications: For theft alerts and command results

Magneetar is designed for device owners who want to protect their phones from theft. It is not designed for surveillance or monitoring others without their consent.
```

### 4. Graphics & Media

- [ ] **App Icon**: 512 x 512 px PNG with transparency
- [ ] **Feature Graphic**: 1024 x 500 px JPEG or PNG
- [ ] **Phone Screenshots**: Minimum 2 screenshots (16:9 or 9:16 aspect ratio)
  - Screenshot 1: Dashboard showing device location
  - Screenshot 2: Command panel with lock/wipe options
  - Screenshot 3: Evidence capture results
  - Screenshot 4: Guardian Network view

### 5. Privacy Policy

Create a privacy policy page at `https://magneetar.me/privacy` with:

- What data is collected (location, device info, photos/audio)
- How data is used (theft recovery only)
- How data is stored (encrypted, user-controlled)
- How to delete data (account deletion)
- Contact information for privacy questions

---

## Data Safety Form

### 6. Complete Data Safety Section

**Data Collection:**
| Data Type | Purpose | Required? | Shared? |
|-----------|---------|-----------|---------|
| Location | Theft tracking | Yes | No |
| Device IDs | Device identification | Yes | No |
| Photos/Videos | Evidence capture | Optional | No |
| Audio | Evidence capture | Optional | No |
| App Activity | Theft detection | Yes | No |

**Security Practices:**
- [ ] Data is encrypted in transit
- [ ] Data is encrypted at rest
- [ ] Users can request data deletion
- [ ] Data is not sold to third parties

---

## Testing Requirements

### 7. Closed Testing (Required for New Accounts)

For personal developer accounts created after Nov 13, 2023:

- [ ] Create closed testing track
- [ ] Recruit minimum 12 testers
- [ ] Run test for minimum 14 consecutive days
- [ ] Collect feedback and fix any issues
- [ ] Document test results

**Tester Requirements:**
- Must be opted-in continuously for 14 days
- Should test on different Android versions
- Should test core features: tracking, lock, alarm

---

## Submission Checklist

### 8. Pre-Submission Verification

- [ ] App builds successfully with `./gradlew bundlePlayRelease`
- [ ] App installs on test device
- [ ] All features work correctly
- [ ] No crashes or errors
- [ ] Privacy policy URL is accessible
- [ ] Store listing is complete
- [ ] Screenshots are uploaded
- [ ] Data safety form is complete
- [ ] Content rating is complete

### 9. Upload to Play Console

- [ ] Upload AAB to production track
- [ ] Add release notes
- [ ] Review all sections
- [ ] Submit for review

### 10. Review Process

- [ ] Wait for Google review (typically 3-7 days)
- [ ] Address any rejection feedback
- [ ] Resubmit if needed

---

## Common Rejection Reasons to Avoid

1. **SMS Permissions**: Already removed in Play flavor ✅
2. **Background Location Disclosure**: Add prominent in-app disclosure ✅
3. **Device Admin Explanation**: Clearly explain lock/wipe purpose
4. **Demo Credentials**: Provide test account for reviewers
5. **Misleading Description**: Don't claim features app doesn't have

---

## Post-Approval

### 11. Production Release

- [ ] Release to production track
- [ ] Monitor crash reports
- [ ] Respond to user reviews
- [ ] Plan regular updates

### 12. Ongoing Compliance

- [ ] Update target SDK when required
- [ ] Respond to policy changes
- [ ] Maintain privacy policy
- [ ] Address user feedback

---

## Resources

- [Play Console Help](https://support.google.com/googleplay/android-developer)
- [Developer Program Policies](https://support.google.com/googleplay/android-developer/answer/9858738)
- [Data Safety Requirements](https://support.google.com/googleplay/android-developer/answer/10787469)
- [Location Permissions](https://support.google.com/googleplay/android-developer/answer/9799150)
