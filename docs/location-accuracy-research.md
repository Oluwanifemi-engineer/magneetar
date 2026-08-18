# Magneetar — Location Accuracy: Why Errors Remain & How Premium Trackers Beat It

**Date:** 2026-08-18 · **Status:** research + implemented (G1-17) · **Scope:**
root-cause the remaining location "errors", survey how standard/premium tracking
systems (Google Find My Device, AirTag, Life360-class apps, GNSS-grade hardware)
achieve high accuracy, and land the fixes that are free for us.

---

## Part 1 — Where the remaining "errors" come from

The pipeline is `TrackingService.kt` (Android) → `LocationFilter.kt` (Kalman +
outlier gates) → `location_validator.py` / `sentinel.py` (server) → dashboard.
The app-level *bugs* that produced dramatic errors were root-caused and fixed
across the G1 program:

| Symptom | Root cause | Fix |
|---|---|---|
| Pin jumped ~55 km | Kalman anchored on a cached first fix | G1-13/15: init guard + re-anchor escape hatch |
| Accuracy blew up to ±152,000 km | unbounded accuracy in the filter | G1-4: accuracy clamping |
| Dashboard froze at last fix in background | GMS fused subscription silently died | G1-16: keep the stream alive + stationary-silence refresh |
| Stale/poison fixes fed the filter | cached last-known delivered mid-stream | G1-13: elapsedRealtimeNanos staleness gate |
| User in Battery-saving mode silently degraded | only on/off location check existed | **G1-17 (this session): location MODE detection + nudge** |

What remains is **three distinct things**, and only one was a real defect left
to fix:

### 1. The physical ceiling of the device (biggest factor — not a bug)

The test device is a budget Samsung SM-A037F whose GNSS reports a steady
**~83 m MEDIUM** accuracy and takes minutes to first-fix. A Kalman filter can
only be as good as the fixes it is fed — it cannot invent precision the
receiver doesn't deliver. On this class of hardware, **10–30 m outdoors and
100–500 m indoors is the honest ceiling**; the app's own live validation
already concluded this ("GMS reports 'no fix available' indoors — the honest
OS ceiling"). Per-OEM differences are expected until the 6-device validation
roster fills (1 of 6 devices so far).

### 2. GPS-denied environments (physics, not code)

Indoors and urban canyons leave only cell/WiFi fingerprint fixes at
100–500 m. The app now handles this *honestly*: LOW confidence, 999 m coast
clamp, network fallback gated on fused silence. A parked phone in a building
sits at "last known ± ~1 km" — even Apple's AirTag needs a UWB beacon within
~10 m to beat that, and without UWB it relies on crowdsourcing (below).

### 3. System location MODE (the one real defect — fixed in G1-17)

`isLocationEnabled()` only knows on/off. **Battery-saving** mode (GPS off,
network-only fixes at 100–500 m) and **GPS-only** mode (WiFi/cell scanning
off — no fixes indoors at all) both read "enabled". The old code silently
accepted degraded fixes all day. **Fixed this session:**

- `LocationModeReader` reads `Settings.Secure.LOCATION_MODE` and reports
  `high_accuracy` / `battery_saving` / `gps_only` / `off` on the 60 s
  heartbeat (`location_mode` field — server now persists it on the devices
  row and exposes it on `/api/dashboard/devices`).
- `LocationModePolicy` (pure JVM, unit-tested) decides when accuracy is
  degraded; `TrackingService` fires a once-per-24 h notification nudging the
  owner to switch to High accuracy (tap opens location settings).
- WiFi RTT (below) gives the app a real indoor fix source that works even in
  degraded modes.

> Also worth stating: several server guards (accuracy > 1000 m reject, (0,0)
> reject, land-bounding-box check) intentionally throw away garbage — those
> "errors" in the logs are the system working, not failing.

---

## Part 2 — How standard & premium tracking systems get high accuracy

Research across Android platform docs, GNSS literature, and the
AirTag/Find-My/Tile ecosystem shows a **ladder of technologies** — most of it
infrastructure-scale, not app cleverness:

### 1. Multi-constellation + multi-frequency GNSS (hardware)

Modern phones fuse GPS + GLONASS + Galileo + BeiDou; dual-band (L1+L5)
receivers reject multipath (urban reflections) and roughly halve error.
Budget single-band phones sit at the bottom of this ladder — this is most of
the gap between a $90 Samsung and a $900 Pixel, *before any software runs*.
[GPS World: "How to achieve 1-meter accuracy in Android"](https://www.gpsworld.com/how-to-achieve-1-meter-accuracy-in-android/) —
carrier-phase (RTK-class) processing of Android `GnssMeasurement` raw data can
reach sub-meter outdoors, but it needs multi-band receivers, a correction
stream (RTK base station / PPP), and heavy CPU — none of which a budget
anti-theft phone provides.

### 2. Sensor fusion (what our Kalman approximates)

FusedLocationProvider (Google Play Services) blends GPS + WiFi + cell towers
with accelerometer/gyro dead-reckoning for 3–15 m outdoors and continuity in
tunnels. This is why GMS-first is the app's primary path. Our `LocationFilter`
adds the outlier gates and coast clamp on top.

### 3. WiFi RTT / 802.11mc (the fix we can actually ship — G1-17)

When GPS is dead indoors, WiFi RTT measures the **round-trip time** to nearby
RTT-capable access points; on Android 10+ (API 29) each AP reports its own
position (LCI/LCR), so ranging to ≥3 APs and trilaterating yields a fix
accurate to **1–2 m** — real measured distances instead of a fingerprint
lookup. [Android developer docs: Wi-Fi location: RTT ranging](https://developer.android.com/develop/connectivity/wifi/wifi-rtt).
**Implemented this session:** `WifiRttLocator` (ranging) +
`RttTrilateration` (linear-LS + Gauss-Newton, JVM-tested) fed into the same
Kalman path as GPS. Honest ceilings: requires `FEATURE_WIFI_RTT` hardware,
APs that answer FTM *and* report LCI/LCR, location + Wi-Fi scanning on, and
`NEARBY_WIFI_DEVICES` (API 33+) / `ACCESS_FINE_LOCATION` runtime permission.
Every failure is a silent no-op — the fused/GPS/network streams are
untouched. On the current budget test device (no RTT APs), this is a
graceful no-op by design: never a fake fix.

### 4. UWB precision finding (Apple AirTag / Find My)

Ultra-wideband measures time-of-flight between two UWB radios to ~10 cm —
but only within ~10 m and only when the *finder's* phone has UWB. Everything
beyond that is crowdsourcing: AirTag relies on the **Find My network** — the
location of *any* passing iPhone — for its last-known. That is infrastructure
scale (billions of devices), not something an app ships. Our equivalent is the
planned **Magneetar Find Network** (Phase B) — the crowdsourced last-known is
the only way a stolen budget phone is ever precisely located.

### 5. Crowdsourced WiFi/cell databases (Tile, Life360-class apps, Google)

Network providers (Google, Apple, Skyhook) fuse *aggregate* device reports
into continuously-updated WiFi/cell-to-position databases; a phone in a dense
area gets a 20–100 m network fix that improves as the area's device density
grows. The app already uses this via the `network` provider and GMS.

### 6. Map-snapping (presentation-layer accuracy)

Consumer trackers snap the displayed marker to the nearest road. This makes a
30–80 m fix *look* street-accurate without touching the underlying data.
It is a display cosmetic — see Part 3 for the honest way to do it.

---

## Part 3 — Dashboard map-snapping: investigation & recommendation

**Current state (`dashboard/src/components/map/MapView.tsx`):** the device
marker renders the raw server lat/lng with an honest accuracy `<Circle>`
(radius = `latestLocation.accuracy`), live follow at z16–17, satellite view,
OSRM routing. There is no snapping today.

**Recommendation: snap the *displayed* marker to the nearest road only when
the fix is coarse, and never mutate the underlying data.**

1. **Where:** client-side, in `MapView` — a display transform, not a data
   change. Server lat/lng, history/trail, and the evidence chain stay raw.
2. **When:** only when `accuracy >= ~30 m` (a 3–15 m GPS fix is already on
   the road; snapping it would fight the truth). Below the threshold, render
   the raw point.
3. **How:** OSRM's `/nearest/v1/driving/{lng},{lat}` endpoint (the project
   already uses OSRM for routing — free, no key, same stack). Snap the marker
   to the returned road point, keep the accuracy circle centered on the
   *raw* point so the operator sees both the fix quality and the street
   estimate.
4. **Don'ts:** never snap the trail/replay polyline (would falsify a theft
   path), never snap sub-30 m fixes, never persist a snapped point, and keep
   an "estimated" annotation on the popup when snapped. Snapping is cosmetic;
   the accuracy circle is the truth.

**Effort:** small (~60 lines in `MapView.tsx` + a `snapToRoad` helper in
`dashboard/src/services/navigation.ts`, where `getOSRMRoute` already lives).

---

## Part 4 — What was shipped this session (G1-17)

| Piece | Where | Verified |
|---|---|---|
| `LocationMode` enum + `LocationModeReader` | `android-app/.../LocationMode.kt` | unit test |
| Nudge policy (pure JVM) | `android-app/.../LocationModePolicy.kt` | 4 tests pass |
| RTT trilateration math (pure JVM) | `android-app/.../RttTrilateration.kt` | 6 tests pass |
| WiFi RTT ranging + AP-position fix | `android-app/.../WifiRttLocator.kt` | compile + tests |
| Kalman integration + 24 h nudge + heartbeat field | `TrackingService.kt` | compile |
| Permissions (manifest + runtime, optional) | `AndroidManifest.xml`, `PermissionsActivity.kt` | compile |
| Heartbeat `location_mode` persisted + exposed | `server/models.py`, `routes/devices.py`, `routes/dashboard.py`, migration 15 | heartbeat test passes |
| Full verification | Android: 112 JVM tests green; server: 558 passed / 0 failed | — |

**Honest expected impact:** the location-mode nudge fixes the one *silent
software* accuracy bug (users unknowingly in Battery-saving mode). WiFi RTT is
infrastructure insurance — it unlocks 1–2 m indoor fixes on RTT-capable
hardware/APs (modern offices, malls, airports), which is exactly where the
current test device is weakest. On the budget SM-A037F with no RTT APs, the
remaining "errors" are the physics of the receiver, not the code.

---

## Sources

- GPS World — *How to achieve 1-meter accuracy in Android* (GNSS raw
  measurements / carrier-phase): https://www.gpsworld.com/how-to-achieve-1-meter-accuracy-in-android/
- Android developers — *Wi-Fi location: RTT ranging* (802.11mc, API 28+,
  LCI/LCR, 1–2 m accuracy): https://developer.android.com/develop/connectivity/wifi/wifi-rtt
- Google support — location accuracy / how Google determines location
  (GPS + WiFi + cell triangulation; High accuracy vs Battery saving):
  https://support.google.com/android/answer/15157297
- Apple — Find My / AirTag (UWB precision finding ~10 m + crowdsourced Find
  My network): https://www.apple.com/airtag/
- Android developers — FusedLocationProviderClient / location accuracy best
  practices: https://developer.android.com/develop/sensors-and-location/location/optimize-location
