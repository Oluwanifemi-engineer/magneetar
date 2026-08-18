# Magneetar Offline Device Network — Design

**Date:** 2026-08-18 · **Status:** design + locked wire contracts (Phase A)
· **Scope:** devices running Magneetar communicate with each other **offline,
within range** — relay mesh (lost-beacon store-and-forward) + paired P2P
(offline location & commands between the owner's own devices).

Builds directly on the live **Find Network Phase 1** (`SosBeacon.kt`,
`SosBeaconBroadcaster`, `GuardianBeaconScanner`, server `guardian.py`): a
lost phone BLE-advertises an opaque `beacon_token`; opted-in guardians scan
(30s on / 60s off, battery-scaled), dedup (2h), and report sightings with
their **own** coordinates. The request id never goes on the air; the token is
meaningless without the server mapping.

---

## 1. Goal, non-goals, and the honest ceiling

**Goal:** any two Magneetar phones can exchange *useful anti-theft data*
with no internet when they are within radio range, and lost-device beacons
can hop through a chain of phones to reach the cloud later.

**Non-goals (explicitly out):**
- Real-time multi-hop routing with seconds-latency delivery. Stock Android
  throttles background BLE scans (~1 scan start per 30 min when backgrounded,
  Android 8+; OEM battery killers throttle harder), so the ambient network is
  **store-and-forward with scheduled scanning** — Apple's Find My works the
  same way; it only looks instant because of billions of devices.
- High-bandwidth P2P file/media transfer over the mesh. Cluster-mode payloads
  are small (KB-scale).
- Bypassing Android's battery-saver / Doze policy.

**Honest ceiling to communicate to owners:** the offline network updates a
lost device's **last-known**, not a live position. Freshness is *when a
Magneetar phone passed within range*, which can be hours. Per-hop range:
~10–30 m (BLE) / ~100 m (Nearby Connections). This is the physics, and the
product copy must say so.

## 2. Architecture — three layers

| Layer | What it does | Status |
|---|---|---|
| **L1 Broadcast** | Lost device advertises its opaque beacon (v1 UUID). | ✅ live |
| **L2 Relay mesh** | Guardians *carry* beacons they've seen: store (encrypted envelope), re-advertise with bounded TTL/hop, flush sightings when any node has internet. | 🔨 Phase A (this doc + codecs) |
| **L3 Paired P2P** | The owner's own paired devices (same account) talk directly offline: last-known exchange + offline commands (siren/lock). | 🔨 Phase A (this doc + codecs) |

Transports, in priority order (chosen by decision 2026-08-18: **BLE + Nearby
Connections**, BLE fallback for no-GMS devices):

| Transport | Range | GMS needed | Role |
|---|---|---|---|
| BLE advertising/scanning | 10–30 m | no | L1/L2 ambient discovery + relay; L3 fallback |
| Nearby Connections `P2P_CLUSTER` | ~100 m | yes | L3 active sessions (higher bandwidth, encrypted, mesh topology) |

## 3. Layer 2 — relay mesh

### 3.1 Wire format v2 (backward compatible)

The v1 16-byte service UUID stays **byte-identical** so existing Phase-1
scanners keep working. Relay metadata rides in the **manufacturer data**
field of the same advertisement (extended advertising, Android 8+/BLE 5.0;
fits in legacy 31-byte packets too — the UUID leaves ~10 bytes spare).

```
Manufacturer data (Android manufacturer id 0xFFFF + payload):
[ 0x4D 0x47 ] [ 0x02 ] [ 8 raw token bytes ] [ hop:1 ] [ origin_ts:4 ] [ flags:1 ] [ reserved:2 ]
   magic      version              token                    TTL-ish    unix secs   bit0: relayed
```

- `hop` — how many guardian relays this beacon has passed through.
  `MAX_HOP = 3`. A beacon with `hop >= MAX_HOP` is never re-advertised.
- `origin_ts` — when the lost device started advertising (unix seconds,
  big-endian). A relay drops beacons older than `RELAY_TTL_S = 24h`.
- `flags` bit0 — `relayed`: set by a guardian re-advertising; the lost
  device's own advertisement has it clear, so a scanner can tell origin vs
  relay and weight trust accordingly.

Codec: `MeshBeacon.kt` (pure JVM, `MeshBeaconTest.kt` — same tripwire
philosophy as `SosBeacon.kt`; drift silently breaks the mesh, the test
catches it).

### 3.2 Relay rules

1. A guardian that decodes a v2 beacon with `hop < MAX_HOP` and
   `origin_ts` fresh stores the token + its own sighting in the **offline
   outbox** (persisted, bounded at ~500 entries, LRU).
2. On the next scan cycle, the guardian re-advertises the beacon with
   `hop+1`, `relayed=1` for a short burst (`RELAY_ADVERTISE_MS = 20s`),
   respecting Android's shared BLE advertiser slots (one advertiser per app;
   sequential, never concurrent with the SOS broadcaster's own advertising).
3. Dedup stays in `SosBeaconTracker` (2h seen-set, now keyed on
   `token+hop` so a fresher hop of the same token still relays).
4. The outbox flushes to `POST /api/recovery/sightings` when the device has
   internet (existing sighting path + new metadata below). Flush is
   idempotent: the server's existing rate limit + the tracker's 2h dedup
   guard double-flush.

### 3.3 Server changes (Phase B, spec'd now)

- `recovery_sightings`: add `hop_count INTEGER DEFAULT 0` and
  `relayed BOOLEAN DEFAULT 0` (guarded ALTER + `ensure_initialized` staleness
  list + pg parity — the device_shares no-op bug class).
- `RecoverySightingCreate`: optional `hop_count`, `relayed`.
- Dashboard sighting rows surface hop/relayed so the owner sees
  "relayed by 2 guardians" vs "seen directly".
- No change to token→request resolution or rate limits.

## 4. Layer 3 — paired P2P

### 4.1 Pairing (requires one online moment — like AirTag setup)

- **Server-mediated**: device A (e.g. the owner's tablet) calls
  `POST /api/p2p/pair/initiate` → server mints a one-time `pair_code`
  (8 hex chars, 15 min TTL, single use). Device B enters/verifies the code
  via `POST /api/p2p/pair/confirm`. Both devices receive the same
  **`pair_secret`** (32 random bytes, stored in the Keystore-backed
  `TokenVault`), bound to the account + both device ids.
- After pairing, the devices carry the secret and can authenticate and
  exchange data **fully offline forever**.

### 4.2 Offline authentication (locked codec: `P2pPairing.kt`)

- Deterministic service id for discovery:
  `service_uuid = UUID(nameUUIDFromBytes("mg-p2p:" + sha256(pair_secret)[:8]))`
  — only paired devices derive the same UUID, so scanners don't even see
  each other's traffic.
- Handshake on connect: 16-byte random `challenge`; responder returns
  `HMAC-SHA256(pair_secret, challenge || device_id_a || device_id_b)[:16]`.
  Verifier recomputes; mismatch → drop. (Binding the device ids prevents a
  relayed/chosen-prefix replay between other paired pairs.)

### 4.3 Message types (payload = encrypted JSON, AES-GCM with the pair secret)

| Type | Direction | Payload |
|---|---|---|
| `HELLO` | either | device id, app version, device nickname |
| `LAST_KNOWN` | either | last-known lat/lng/accuracy/provider/timestamp (the honest offline snapshot) |
| `CMD` | owner→device | one of: `siren`, `lock`, `lost_mode`, `ping` — executed by the device's existing command handlers |
| `SIGHTING_CARRIER` | either | a relayed beacon envelope the other device should also carry (mesh density via P2P) |

Offline command semantics are the **same** as the online command path:
siren/lock execute locally (no internet needed); a command that needs the
cloud (e.g. media upload) is queued in the existing `OfflineOutbox` and
flushed later. Exactly-once is best-effort: the device acks with the
command id; the sender re-sends on reconnect until acked (dedup by command
id on the receiver).

### 4.4 Battery posture

- Nearby `P2P_CLUSTER` discovery is **never always-on**. It activates when:
  (a) the owner opens the **Offline Find** screen on either device, or
  (b) a paired device is in **lost mode** (it advertises; the owner's other
  device scans on-demand). BLE ambient scanning for L1/L2 stays on the
  existing guardian cadence (30s/60s, battery-scaled).
- Lost-mode P2P advertising is a foreground service with a visible
  notification (honest disclosure), same as the SOS broadcaster.

## 5. Permissions (all already granted or install-time — no new Play-gated ones)

- BLE: `BLUETOOTH_SCAN` / `BLUETOOTH_ADVERTISE` / `BLUETOOTH_CONNECT`
  (runtime on API 31+, already in the permission flow for Phase 1).
- Nearby Connections needs `ACCESS_FINE_LOCATION` (already granted) +
  `CHANGE_WIFI_STATE` (install-time).
- `PLAY_POLICY_ANALYSIS.md` already cleared BLE Find Network as
  Play-safe with a scan declaration.

## 6. Security & privacy model (unchanged philosophy)

1. **Finders learn nothing.** Relay envelopes are opaque to relays — the
   token stays meaningless without the server mapping, and sightings carry
   the *guardian's* coords, never the lost device's.
2. **Paired P2P is authenticated + encrypted end-to-end** (HMAC challenge +
   AES-GCM with the pair secret); discovery UUID is derived from the secret,
   so non-paired phones don't see P2P traffic.
3. **No new server data beyond what Phase 1 already stores** (sightings +
   the new hop/relayed metadata).
4. Pairing is account-bound + single-use codes with a short TTL.

## 7. Test plan (locked by code, mirroring Phase 1's philosophy)

- `MeshBeaconTest` — codec round-trip, hop increment, TTL expiry, magic/version
  rejection, malformed payload rejection, v1 UUID compatibility unchanged.
- `P2pPairingTest` — deterministic service id, HMAC handshake accepts the
  right secret, rejects wrong secret / wrong device-id binding, pair_code
  derivation (server parity).
- Server: sighting with hop/relayed metadata persists; without them defaults
  to 0/false; `ensure_initialized` column check; pg parity test updated.

## 8. Roadmap

| Phase | Contents | Gate |
|---|---|---|
| **A (shipped 2026-08-18)** | Design doc + `MeshBeacon.kt` + `P2pPairing.kt` + tests; server sighting metadata (columns + payload + tests) | wire contracts locked by JVM tests |
| **B (shipped 2026-08-18)** | Android relay: `RelayOutbox` (persisted offline sightings + re-advertise bookkeeping, 11 tests), envelope decode + metadata sightings + queue-on-offline + relay re-advertising (hop+1, relayed=1, 10s bursts, 15-min per-beacon cooldown, MAX_HOP/24h-TTL gated) + flush-on-internet, all inside `GuardianBeaconScanner` | 139 JVM tests per flavor; field E2E (2 phones, 1 offline) is a G1 roster task |
| **C (shipped 2026-08-18)** | Android P2P: server pairing endpoints (`/api/p2p/pair/*`, table + migration 17 + 9 tests), `PairingApi` + `PairingActivity` UI (generate/enter code, vault sync), `PairVault` (Keystore-backed pair secrets), `P2pMessage` (AES-GCM codec, 11 tests), `P2pOfflineService` (Nearby CLUSTER advertise/discover, mutual HMAC handshake, HELLO/LAST_KNOWN/CMD/ACK/SIGHTING_CARRIER, command dedup + execution through TrackingService, lost-mode auto-advertise) | offline siren/lock between paired devices, both offline (field E2E on the roster: 2 paired phones, both offline) |
| **D** | Offline Find UI on dashboard (device sees "last seen via mesh"), battery/telemetry monitoring, Play disclosure copy | G1-field-tested on the roster |

**Decision log (2026-08-18):** both layers; BLE + Nearby Connections with
BLE fallback; opt-in guardians (current privacy/battery model).
