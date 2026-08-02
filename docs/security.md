# Magneetar — Security Notes: Uninstall Protection

This document explains how Magneetar protects itself against being removed
from a device, and why Android's platform model shapes those protections.

## Threat

A thief who steals a phone can simply **uninstall** a security app before the
owner reacts. A stolen Magneetar install that can be removed in two taps is
useless — so Magneetar implements uninstall protection in layers.

## The two protection layers

Android offers **no public API** that lets a normal app demand a *custom
password* at uninstall time. The strongest supported primitives are:

### Layer 1 — Active Device Admin (works on every device, zero setup)

While `AdminReceiver` is an **active device administrator**:

- Android **refuses to uninstall** Magneetar until the admin is deactivated
  in `Settings → Security → Device admin apps`.
- Deactivation is gated behind a **system confirmation dialog** that shows
  `AdminReceiver.DISABLE_WARNING` — a plain-language list of exactly what the
  user gives up (uninstallability, remote lock/wipe/siren, camera/audio
  capture).
- If the admin is still deactivated, `AdminReceiver.onDisabled` fires an
  **immediate heartbeat** with `device_admin_active=false`, so the dashboard's
  Sentinel score jumps to ≥40 (device-admin removal is a weighted theft
  signal) instead of waiting up to a minute for the next heartbeat.

**This is the baseline.** Onboarding now routes users through Device Admin
activation by default; skipping it requires an explicit, informed
acknowledgement (`admin_skip_acknowledged` in prefs), and `MainActivity`
sends users back to the permissions screen if admin protection is later
removed without that acknowledgement.

### Layer 2 — Device Owner + `setUninstallBlocked(true)` (hard block)

When Magneetar runs as the **device owner** (or a profile owner), it calls
`DevicePolicyManager.setUninstallBlocked(admin, true)`:

- The Settings "Uninstall" entry is **disabled entirely** — no dialog, no way
  to get there.
- `adb uninstall com.magneetar.app` **fails**.
- The block is re-asserted on every app launch, every admin (re)activation,
  and at tracking-service start, so a data wipe or restore can't silently
  drop it.

Becoming a device owner requires one-time provisioning (because Android
reserves device-owner privileges for managed devices):

```bash
# Requirements: USB debugging on, NO accounts set up on the device
# (remove Google/other accounts first, or run during fresh setup).
bash scripts/enable-uninstall-protection.sh
```

The script runs `adb shell dpm set-device-owner com.magneetar.app/.AdminReceiver`,
checks prerequisites, and prints verification/removal commands. To remove the
hard block later:

```bash
adb shell dpm remove-active-admin com.magneetar.app/.AdminReceiver
```

## Design guarantees

- **Fail-open, never fail-closed:** every protection call is wrapped so a DPM
  failure can never crash the app or break tracking.
- **Honest status:** the Home screen shows the current state —
  `HARD BLOCKED (device owner)` / `ACTIVE (device admin)` / `OFF`, with an
  "Activate Device Admin" button when protection is off.
- **No password, honestly:** the user-visible limitation — Android provides no
  API for a custom uninstall password — is documented here rather than
  faked. Layers 1–2 are the maximum protection the platform permits for a
  non-root app.

## Related code

| Concern | Location |
|---|---|
| Warning + instant alert on deactivation | `android-app/.../AdminReceiver.kt` |
| Hard-block helper (device/profile owner) | `android-app/.../UninstallProtection.kt` |
| Onboarding gate + skip acknowledgement | `android-app/.../PermissionsActivity.kt`, `MainActivity.kt` |
| Home status row + activate button | `android-app/.../HomeActivity.kt`, `res/layout/activity_home.xml` |
| ADB provisioning script | `scripts/enable-uninstall-protection.sh` |
