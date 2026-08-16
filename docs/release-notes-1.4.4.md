# Magneetar v1.4.4

**Anti-theft that works on stock Android — no root, no jailbreak.** Magneetar
turns a normal phone into a theft-resistant device: continuous tracking,
trigger-based evidence capture (front camera + ambient audio), and
always-deliver alerts, all encrypted in transit and at rest.

---

## Highlights

- **Armed Camera + Armed Audio evidence watch** — when theft signals escalate
  the device to EVIDENCE mode, it captures a front-camera photo burst at the
  60s cadence plus VAD-gated ambient audio, both landing in one evidence case
  with a SHA-256 chain of custody. Verified end-to-end on real devices.
- **Failed-unlock "theftie" detection** — repeated failed unlock attempts
  (≥5) are detected on-device, scored by Sentinel, and trigger an automatic
  evidence capture + always-deliver alert. Fixed and live-verified (the
  detector was silently dead; SCREEN_ON/OFF now reach a context-registered
  receiver, the session state persists across events, and the reaction is
  bounded to one capture window so it can never flood the device's network).
- **Sentinel theft scoring** — SIM change, failed unlocks, location
  disabled, airplane mode, admin disabled, velocity, geofence exits and more
  feed a weighted score; crossing the threshold auto-activates stolen mode.
  The location-disabled and airplane-mode signals now actually report (they
  were dead) via the 60s heartbeat.
- **End-to-end security** — TOTP 2FA with a single-purpose challenge token,
  AES-256-GCM location encryption at rest, role-based device sharing
  (viewer / admin / device-only privacy tier), step-up password verification
  for destructive actions, and a checksum-verified self-updater.
- **Signed, expiring APK downloads** — every download link is minted per
  request and serves a documented SHA-256 checksum.

## Security fixes in this release

- Fixed-unlock theft detection dead-on-arrival bug (G1-8)
- Theft-flood network-block failure mode (G1-9) — the capture reaction is now
  bounded to one pair per evidence window
- Dead `location_disabled` / `airplane_mode_on` Sentinel signals (G1-10)
- SMS relay number removed from the public config endpoint
- Tampered download links return a clean 403 (JSON), never the binary

## Install

- **Google Play (recommended, private testing):** join the waitlist on the
  download page.
- **Sideload:** the APK is served from the download page with a signed
  expiring link + SHA-256.

## Source

This release's source is published as a tarball (no git history, no secrets,
no build artifacts) for transparency — `magneetar-1.4.4-source.tar.gz` with
its `.sha256`, also served at `/apk/source` from the product site.

## Checksums

```
APK (play-clean):  5c8fb9ab00ce2d801c6489ab2b29b30a3936268f51b6be8beda3e307ed47d752  (magneetar-v1.4.4-release.apk — what /apk/download serves)
Play AAB (v12):    3cc83b5c560966571abda20aeb8d413430b127283617b73fdf4183d01f6e0bcb  (magneetar-v1.4.4-play.aab — internal-testing upload)
Source:            cad1337cbc14e40f5a81f77152a36423e8f4e925079fd8c59170ca475f20691d  (magneetar-1.4.4-source.tar.gz)
Sideload APK:      60330fb93993bd10cb9405c9106bf38f05ca2045c35053bf042b1fa4f5b25a7b  (magneetar-v1.4.4-sideload-release.apk — SMS-capable, archived)
```

> Full APK SHA-256 is published on the download page's Verify section next to
> the live download link.
