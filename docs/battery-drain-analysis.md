# Magneetar — Battery Drain Analysis & Fix Plan

**Date:** 2026-08-22 (analysis) · Fix shipped same day
**Device:** Samsung SM-A037F (Galaxy A03s, ~5000 mAh)
**Status:** ✅ Fix implemented (commit `0fadc89`, adaptive cadence) —
**48h field re-measurement on D1 still pending** (this doc's numbers are the
PRE-fix measurement; do not quote 21.6%/day as current reality)

---

## 1. The problem

| Metric | Measured | Budget | Delta |
|--------|----------|--------|-------|
| Armed-mode drain | **~0.9%/h** (204 mAh / 4h29m) | — | Design band: 0.5–1.5%/h ✅ |
| Daily drain (24h armed) | **~21.6%/day** | **≤15%/day** | **+44% over budget** 🔴 |

The armed-mode drain is within the audio design band (0.5–1.5%/h), but the **device stays armed 24/7** as a daily driver — so the hourly rate compounds to 21.6%/day, exceeding the 15%/day G1 exit budget.

## 2. Root cause

`LOCATION_INTERVAL_MS = 3_000L` (3 seconds) in `TrackingService.kt` — the fused + raw GPS + raw network location update interval is **constant at 3 seconds**, regardless of whether the device is moving or stationary.

**Breakdown of 0.9%/h:**

| Component | Frequency | Estimated drain |
|-----------|-----------|-----------------|
| GPS fused location updates | Every 3s | ~0.5–0.6%/h (dominant) |
| Raw GPS + network fallback listeners | Every 3s (gated) | ~0.1–0.2%/h |
| 60s heartbeat POST | Every 60s | ~0.05%/h |
| Watchdog + persistence checks | Every 5min/1min | ~0.05%/h |
| P2P beacon scanning | Every 5min | ~0.05%/h |
| Armed audio watch (trigger-first) | Mic closed when idle | ~0.0%/h (zero when not capturing) |
| **Total** | | **~0.8–1.0%/h** |

The GPS radio is the #1 battery consumer. At 3s intervals, the GPS chipset wakes 20 times/minute, 1200 times/hour. At 30s intervals, that drops to 120 times/hour — a **10× reduction** in GPS wakeups.

## 3. The fix: adaptive cadence

The `LocationFilter` already exposes a `stationary` boolean (line 139–140 of `LocationFilter.kt`). The detection exists — the interval just isn't adaptive.

### Proposed cadence

| State | GPS interval | Expected drain | Rationale |
|-------|-------------|----------------|-----------|
| **Moving** (speed > 0.5 m/s) | 3s (current) | ~0.9%/h | Full accuracy for live tracking |
| **Stationary** (speed < 0.5 m/s for >60s) | **30s** | ~0.3%/h | Position locked by Kalman; 30s is fresh enough for theft detection |
| **Battery saver** (≤15%) | **60s** | ~0.15%/h | Emergency mode; tracking continues but less frequently |

**Projected daily drain with adaptive cadence:**

- Realistic scenario: ~16h stationary + ~8h moving per day
- Stationary: 16h × 0.3%/h = **4.8%**
- Moving: 8h × 0.9%/h = **7.2%**
- Heartbeat + overhead: ~1.0%
- **Total: ~13%/day** ✅ (under the 15% budget)

### Implementation approach

1. Add `adaptiveIntervalMs` state to `TrackingService` (default: 3000ms)
2. On each Kalman update, check `filtered.stationary`:
   - If stationary for >60s consecutive → set interval to 30_000ms
   - If moving → reset interval to 3_000ms
3. Re-register fused + raw listeners with the new interval (remove + re-request)
4. Add battery-saver gate: if `currentBatteryPercent ≤ 15`, force 60s interval
5. Server-side: the 60s heartbeat already covers the gap (position + battery + state)

### Key invariant: no accuracy loss when moving

The 3s interval is only reduced when the Kalman filter confirms the device is stationary. When the device starts moving again, the interval drops back to 3s immediately — the filter's `stationary` flag flips on the first moving fix, and the next fused callback re-registers at 3s. The dashboard sees continuous updates during movement.

## 4. Files to modify

| File | Change |
|------|--------|
| `android-app/app/src/main/java/com/magneetar/app/TrackingService.kt` | Adaptive interval logic + battery-saver gate |
| `android-app/app/src/test/java/com/magneetar/app/TrackingServiceTest.kt` | Unit tests for interval transitions |

## 5. Risk assessment

| Risk | Mitigation |
|------|------------|
| Re-registering fused listener causes a gap | Remove + re-request is atomic on the main looper; old callbacks are cancelled before new ones start |
| Stationary detection is noisy (jitter) | 60s debounce before switching to 30s; moving→3s switch is instant (no debounce needed) |
| OEM battery killers override the interval | Already handled by the watchdog/persistence layer; adaptive cadence reduces the kill surface |
| 30s interval misses a fast theft | The Sentinel score accumulates over multiple signals (SIM, unlock, geofence); 30s is within the detection window |

## 6. Timeline

| Step | Effort | Status |
|------|--------|--------|
| Analysis + root cause | Done | ✅ |
| Implement adaptive cadence | 1 day | ✅ Shipped 2026-08-22 (`TrackingService.resolveLocationInterval` + `reRegisterLocationListeners`) |
| Unit tests for interval transitions | 0.5 day | ✅ `AdaptiveCadenceTest.kt` — 15 JVM tests (debounce boundaries, moving/stationary, battery-saver overrides, charging) |
| Field test on D1 (48h battery measurement) | 2 days | 🔲 OPEN — the honest next step before quoting a new %/day number |
| Update G1 tracker with new battery numbers | — | 🔲 Depends on the field test above |
