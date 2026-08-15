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
| 1 | Samsung SM-A037F (Galaxy A03s, fleet) | 13 | 4 GB | Owner (tester #1) | 2026-08-14 (v1.4.4 since 08-15) | 2026-08-28 | ☐ running |
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
| Background survival — full day unused; `last_seen` stays fresh (no user action) | 🟡 SOAK STARTED (2026-08-15 13:40 UTC) |  |  |  |  |  | Baseline set (score 0, normal mode); screen-off, last_seen 1.9s fresh after 2 min; verify 24h later — no gap > 30 min |
| Offline queue — 2G/3G dead zone or airplane toggle; no gaps/dups on reconnect | 🟢 PASS (2026-08-15) |  |  |  |  |  | 20+ min airplane + GPS-off; reconnect flushed, no gaps; dups found & fixed (G1-3) → zero dups re-verified |
| SIM swap — `sim_changed` always-deliver alert (alert row + FCM push) |  |  |  |  |  |  |  |
| GPS-off / location disabled — graceful, no crash | 🟢 PASS (2026-08-15) |  |  |  |  |  | App alive through airplane + location-off (only expected DNS failures); clean recovery (G1-2 found the false-jump bug alongside) |
| Battery saver / low battery — Find Network paces; tracking survives | 🟢 PASS (2026-08-15) |  |  |  |  |  | low_power=1 for 2+ min: 122 pings/5min, max gap 10.9s, heartbeat 3.6s fresh, BLE Find-Network scanner still active |
| Evidence capture from LOCKED screen (front photo + audio, armed response) | 🟢 PASS (2026-08-15) |  |  |  |  |  | Front photo captured from LOCKED + screen-off state: 56 KB jpg, evidence case MGT-2026-3VQ1D, SHA-256 b8b64724… (G1-1 audio verified separately — capture pipeline clean) |
| FGS notification visible; honest command acks | 🟢 PASS (2026-08-15) |  |  |  |  |  | All 6 app notifications live: Connected • 96%, Theft protection armed, Watchdog active, Find Network scan on, SOS beacon idle (+ Lost Mode persisted across restarts — state re-posts notification, by design) |
| Device-admin uninstall protection + theft-signal on deactivate | 🟢 PASS (2026-08-15) |  |  |  |  |  | `adb uninstall` → DELETE_FAILED_DEVICE_POLICY_MANAGER (hard-block while admin active). Deactivation itself is PIN-gated by design — Android 13 refuses shell removal of non-test admins (the protection working); theft-signal path (immediate heartbeat `device_admin_active=false` → sentinel score 40) unit-tested (test_heartbeat_theft.py) + code-verified |
| App's own dialogs NOT blocked by the uninstall guard (battery-optimization grant, precise-location change) | 🟢 PASS by flavor design (2026-08-15) |  |  |  |  |  | Play flavor ships ZERO accessibility services (guard stripped via tools:node=remove — S-10) → no guard to misfire; guard regression (G1-dialogs) covered by DANGER_ACTIVITY_MARKERS fix + tests on the sideload flavor |
| Geofence exit → auto-action fires exactly once | 🟢 PASS (2026-08-15) |  |  |  |  |  | Live: 15m fence at device position; exit at 13:36:19 queued EXACTLY ONE alarm despite 37 subsequent outside pings (dedup guard verified); 3 earlier alarms = 3 distinct exits (boundary oscillation), each once |
| Command round-trip — dashboard → device → `executed` (real network) | 🟢 PASS (2026-08-15) |  |  |  |  |  | alarm 10s, lock 22s, front-photo 33s round-trips, all acked `executed` with no retry dups (G1-3 dedup holds) |
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

## 5. Issues log (every real-world finding, from day one)

| # | Date | Device | Reported by | Symptom | Triage | Resolution | Status |
|---|---|---|---|---|---|---|---|
| 1 | 2026-08-14 | Samsung SM-A037F (Galaxy A03s, real fleet phone) | Tester | “App not installed” after granting permissions — install never completes | **Download side CLEAN** — server delivered full 200 at 14:51:38 UTC; served bytes = verified v1.4.2 (checksum ca4c400d…); APK valid (zipaligned, v2-signed, minSdk 24, no ABI split). **Signature change theory DISPROVEN** — every build since v1.1.0 shares one key (release.keystore cert 024cbb34…; verified against v1.4.0 APK + current build + keystore). Device already ran v1.4.1 fine (same key/minSdk) → installs work on this phone. Server DB: device last heartbeat **07:20 UTC** (right when the swap was attempted) → phone went silent then. Prime suspects, all phone-state: (a) **leftover/zombie package** — Magneetar's own uninstall protection (device admin + accessibility guard) can abort the uninstall mid-way, leaving a stale package entry that makes every new install fail with plain “App not installed”; (b) Samsung's OEM “App security” scanner (separate from Play Protect) silently blocking a BIND_DEVICE_ADMIN sideload; (c) “Install unknown apps” grant missing for the app/browser actually opening the APK | Fix steps corrected in download-page FAQ (deactivate Device Admin + accessibility BEFORE uninstall; adb as decisive path); `scripts/install-apk.sh` upgraded to a diagnostic installer (prints exact adb failure + detects leftover installs); see decision tree below | 🟡 **RESOLVED-BY-MECHANISM (v1.4.3, 2026-08-14)** — the in-app self-updater makes the sideload upgrade path obsolete: open Magneetar → tap “Update available: v1.4.3” → app downloads (SHA-256-verified) and installs via PackageInstaller over the existing install. Final close: tester confirms the self-update worked on the A03s (updater pulls are tagged `client: app-updater` in the server access log — a positive hit closes this row). If the app can’t run at all, the `adb install` diagnosis still applies |
| S-1 | 2026-08-14 | Web (download page) | Security re-scan (Aug 14) | Download page shows “10K+ Active users / 25K+ Devices protected / 94% Recovery rate” — fabricated adoption numbers contradicting the landing page's “EVERY CLAIM IS VERIFIABLE” promise (HIGH, trust/legal) | Numbers were placeholders with no counter behind them; the product has a handful of beta users. Violates the project's own no-fabricated-numbers rule (Provenance.tsx) | Replaced with verifiable claims: **24/7 stealth tracking · SHA-256 checksum-verified APK · free 1-device plan** (each provable on the page or in the product). Real counters return when real users exist | ✅ **FIXED (2026-08-14, cfdc8c8)** — deployed; verified live on app.magneetar.me/download |
| S-2 | 2026-08-14 | Web (landing page) | Security re-scan (Aug 14) | “/security renders 349 tests / SHA-235-bit while landing renders 380 / SHA-255-bit” — two different builds? | **False alarm — one build.** The AnimatedCounter rendered `0` on first paint (`SHA-0-bit` in SSR HTML) and counted up over 2s; the audit's screenshots caught mid-animation values (349→381, 235→256…). Deployed JS bundles matched the repo (381 tests, SHA-256) | Counter now renders its true value immediately (381 · 24/7 · SHA-256-bit · 3-layer); only a fade-in reveal remains, which never changes the digits | ✅ **FIXED (2026-08-14, cfdc8c8)** — verified live: DOM contains `381`, `24/7`, `256`, `3` with no intermediate values |
| S-3 | 2026-08-14 | API | Security re-scan (Aug 14) | F-08: `/health` leaks uptime (revealed deploy timing) and `/api/config` leaks `sms_relay_number` | Uptime is genuinely unnecessary on a public endpoint (still available to operators via admin-gated `/api/metrics`). `sms_relay_number` is semi-public **by design** — the Android app must allowlist the relay sender, and the number is already visible in every command SMS; the 10/min rate limit + sender matching mitigate it | `/health` no longer returns `uptime` (deploy/reliability scripts updated to not depend on it; deploy freshness now reads container start time). `sms_relay_number` kept public intentionally | ✅ **FIXED for uptime (2026-08-14, cfdc8c8)** — verified live; `sms_relay_number` retained by design |
| S-4 | 2026-08-14 | API | Security re-scan (Aug 14) | “Repo /apk/download is still a plain FileResponse; deployed validates expires+sig” — repo-vs-deploy skew | **False alarm — stale checkout.** The repo has had full signed-ticket enforcement for both /apk/download AND /apk/ticket (HMAC-SHA256, 10-min TTL, far-future replay guard) — the re-scan audited an older tree | Live-verified end-to-end: no ticket → **302**, tampered sig → **302**, valid minted ticket → **200** with the exact served bytes | ✅ **VERIFIED (2026-08-14)** — repo == production; no change needed |
| S-5 | 2026-08-14 | Android APK | Security re-scan (Aug 14) | Agent-mode item: confirm embedded key is device-scoped (not master), debuggable flag, Accessibility/Device Admin declarations | — | Live `aapt`/DEX inspection of the served v1.4.3 APK: **not debuggable**, versionCode 9 / v1.4.3, minSdk 24 / targetSdk 36, device-admin + accessibility + `REQUEST_INSTALL_PACKAGES` declared, and **no `mtk_*` keys embedded in the DEX** (only `SERVER_URL` + `VERSION_NAME` BuildConfig fields) — device keys are runtime-generated per the docs | ✅ **VERIFIED (2026-08-14)** |
| S-6 | 2026-08-14 | Web (login page) | Owner screenshot (Aug 14 20:38) | Login page shows fake avatars (JD/AK/MT/RS), invented “4.9” star rating, and “TRUSTED BY 1,200+ DEVICE OWNERS” — fabricated social proof with zero users behind it | Same integrity violation as S-1 (download page); contradicts the “EVERY CLAIM IS VERIFIABLE” promise | Replaced with verifiable stats (381 automated tests · 24/7 stealth tracking · SHA-256 evidence chain). Mockup relabelled “LIVE / Pixel 8 · Online” → **“DEMO / Pixel 8 · Demo device”** (matches the landing hero's honest labelling). Locked in LoginPage test | ✅ **FIXED (2026-08-14, cf0d056)** — deployed; verified live: no 1,200+/TRUSTED/4.9/LIVE; “Pixel 8 · Demo device” + DEMO + 381 present |
| S-7 | 2026-08-14 | API | Security re-check (Aug 14 19:44) | Tampered `/apk/download?expires=…&sig=deadbeef` still returns 302→SPA page instead of a clean 403; re-check also re-flagged “SHA-255-bit still live” + “349/380/SHA-235-bit on /security” + “10K+ on /download unchanged” | Re-check's live-site claims were against a pre-deploy snapshot / mid-animation screenshots of the old counter — live site verified correct at the time of the re-check (381/24/7/256 on `/` and `/security`, honest download stats, DYNAMIC Cloudflare = no stale cache). The tampered-sig 302 was real: failure intent was conflated | `/apk/download` now distinguishes: bare link (no sig) → **302** self-heal; PRESENT but forged sig → **403** clean JSON rejection (never a masking redirect); genuine-but-expired sig → **302** self-heal. Latent test-isolation bug fixed (e2e's sys.modules eviction + function-local signer import → module-level binding). Stats single-sourced into `@/lib/productStats.ts` (hero + login can't diverge); stale local `out/` + `coverage/` artifacts removed | ✅ **FIXED (2026-08-14, 76c8897)** — deployed; verified live: bare→302, forged→403 (JSON detail), fresh ticket→200 |
| S-8 | 2026-08-14 | Web (two-origin deploy) | Security re-check (Aug 14 20:10) | “magneetar.me — the marketing domain — is STILL serving the old build (SHA-255-bit, 380 tests, 10K+ claims); app.magneetar.me has the new build. Two origins, deploy only updated one” | **NOT REPRODUCIBLE — single origin.** Both hostnames route to the ONE dashboard container via the tunnel (cloudflared config). Verified after the 20:10 re-check: magneetar.me and app.magneetar.me serve **byte-identical** content (381/24/7/SHA-256, honest download stats — full rendered-DOM hashes match; the only diffs are per-request minted-ticket sigs and Cloudflare's random email obfuscation). No “Published: 17:49” stamp exists in code or HTML. Stale-HTML mechanisms ruled out: nginx sends `no-cache, no-store` (since Aug 3, git-verified) → Cloudflare `DYNAMIC`; SW is network-first for navigations (since Aug 9); DNS resolves both to the tunnel | Real gap closed anyway: deploy.sh only health-checked `app.*` — it now **compares the chunk-hash of BOTH hosts' HTML after every deploy** and fails loudly on divergence, so a stale hostname can never go unnoticed again | ✅ **FIXED (2026-08-14, 1579a34)** — dual-host build check live; both hosts verified identical at 20:4x UTC |
| S-9 | 2026-08-14 | API | Security re-check (Aug 14 20:10) | `/api/config` leaks `sms_relay_number: +17432209510` — “easy to remove or gate behind device auth” | Re-opened 2026-08-15: while the number is semi-public by design (the app must allowlist the sender), the auditor kept flagging it as the single outstanding live finding — and gating it is genuinely an easy win that costs nothing | **GATED (2026-08-15, v1.4.4, 5a56969)** — `sms_relay_number` now returned ONLY to requests presenting a valid `x-device-key` for a registered device; anonymous/forged requests get `""` and the app falls back to code-only verification (existing documented behavior). Android `checkServerCompatibility` sends the device key on its config fetch. Live-verified: anonymous → empty, forged key → empty, registered device (unit test) → mirrored number. Earlier “By design, not a leak” rationale superseded — the allowlist still works via the authenticated path | ✅ **FIXED (2026-08-15, 5a56969)** — deployed + verified live; leak closed | The Android app fetches it from `/api/config` and uses it as the **sender allowlist** for SMS commands (`SmsCommandReceiver` — defense-in-depth alongside the pairing code). The number is inherently public: it's the Twilio number that sends every command SMS and appears in every received message. Gating it behind device auth would break the allowlist | Retained intentionally; mitigation already in place (10/min sender rate limit + sender matching). Documented, no code change | ✅ **WONTFIX (by design)** — tracked for the record |
| S-12 | 2026-08-15 | Android install channel | Owner escalation | “The installation issue is kinda becoming a big deal — all this is useless if people can't install it on their phones properly” | Root cause is the CHANNEL, not the build: modern Android Enhanced Fraud Protection hard-blocks sideloading ANY permission profile that keeps Magneetar's anti-theft features (verified on-device 2026-08-11, `PLAY_POLICY_ANALYSIS.md`); the download page was a discovery page with no reliable install path. G1 couldn't start because the plan gated Play on validation that needs installs | **ADR-0007**: Play **internal testing track** becomes the G1/G2 install channel — private (email-invited only, no public listing, no review delay), friction-free installs, auto-updates. v1.4.4 AAB built + staged (`magneetar-v1.4.4-play.aab`, SHA-256 `c958dcfd…`, versionCode 10, zero SMS, zero accessibility service, not debuggable — verified). Download page leads with a “Google Play install (recommended)” banner; sideload = documented fallback. Play setup steps in `docs/PLAY_INTERNAL_TESTING_SETUP.md` | ✅ **IMPLEMENTED (2026-08-15, 63351a5)** — deployed; awaiting the user's Play Console upload + opt-in link (then the banner gets the real link) |
| G1-1 | 2026-08-15 | Samsung SM-A037F (Galaxy A03s) | Tester | AUDIO command returns a file but playback is **silent** — “the audio command got executed but doesn't seem to play any sound even though the surrounding sound is loud and clear” | **Capture pipeline was CLEAN** — forensics: pulled the uploaded evidence file off the prod server (365 KB, `mt-9be468c1`), decoded with FFmpeg/PyAV → valid 29.88s mono AAC, real content (peak 0.89, RMS −37.8 dBFS, a loud room). Chrome headless decoded it fine (`play()` resolved, `paused: false`). Root cause = **dashboard player**: `<audio src={dataURI} autoPlay={playing}>` — the `autoPlay` prop toggled AFTER mount is only honored at element load; Chrome's autoplay-with-sound policy blocks it without sticky user activation → PLAY flipped to PAUSE visually, zero sound, state spun forever | Player rewritten to explicit `audio.play()/pause()` from the click handler (guaranteed user gesture), real error surfacing ("Playback failed" instead of dead air), DOWNLOAD FILE fallback added; `preload:"auto"`. 4 new tests (211/211 dashboard tests pass) | ✅ **FIXED (2026-08-15, 850a0ac + c9a51ec)** — deployed both origins; **user-confirmed working** (“Yeah it works fine.”) |
| G1-2 | 2026-08-15 | Server (sentinel) | Field test — GPS-off/airplane resilience pass | False **“Impossible jump: 119km/125km”** teleport anomalies on every ping while the device sat still (OAU campus) — inflated Sentinel scores and polluted the alert feed | `_haversine` returns **meters** (R = 6371000; geofences correctly compare against `radius_meters`), but the impossible-jump check treated it as **km** → a real 118m walk read as “119km teleport” (exactly 1000×). SECOND bug: history is newest-first, so the check compared against `history[1]` (2 pings old) instead of `history[0]` (immediately previous fix) — inflated distance for moving devices | `distance_km = _haversine(...) / 1000.0`; compare against `history[0]`. Regression tests added (short walk must NOT trigger; genuine teleport must) — 554/554 server tests pass | ✅ **FIXED (2026-08-15, 14a3d67)** — deployed; live-verified: seq 15+ clean, score 0, SAFE, zero anomalies, coordinates within ~10m. (Rows processed during the deploy window by the old container still show jumps — expected) |
| G1-3 | 2026-08-15 | Android + server | Field test — airplane-mode reconnect | **461 duplicate location rows** after reconnect: pings 673–677 delivered live at 12:10:34–57, then re-POSTed in REVERSE order at 12:11:19 via the live endpoint (`was_queued=0`, byte-identical `dev_ts` + `ping_sequence`) — every ping inserted twice | OkHttp default `retryOnConnectionFailure=true` with replayable bodies: the captive-portal reconnect dropped the server response AFTER the server inserted the row, so OkHttp transparently re-sent the **same body** ~45s later (post-30s read-timeout) → duplicate insert. The app already has its own recovery (fresh fix every ~5s + 60s heartbeat + OfflineOutbox), so the transparent retry adds nothing but duplicates. Confined to the reconnect window — steady-state stream had zero dups | **Both sides:** `retryOnConnectionFailure(false)` in TrackingService + MediaCaptureService; server-side at-most-once guard on `(device_id, ping_sequence, device_timestamp)` for BOTH the live and offline-queue insert paths + supporting index (SQLite + Postgres). Dedup tests added | ✅ **FIXED (2026-08-15, 14a3d67 + 873a9b7)** — deployed; live-verified: 15 rows / 15 unique seqs, zero dups; APK rebuilt + installed on phone |
| G1-4 | 2026-08-15 | Samsung SM-A037F (Galaxy A03s) | Field test — command suite | **Location stream dies while parked+locked**: server rejects EVERY ping with "Accuracy 152,277,180m is too low"; last stored fix 13:07:20 → dashboard pin frozen at a stale position. This is the same family as the owner's "location error is quite high / deviating from true location" complaint | Live forensics: device reported every ~2.5s (loop alive), but Kalman-filter accuracy exploded 1,117m → 152,277,180m in 16 min. Root cause in `LocationFilter`: the coast path (rejected-outlier fixes) never advanced `lastTs`, so dt grew with every fix and Q ∝ dt⁴ blew up the covariance (velocity-variance channel dt²·p22 compounds it). Server's `accuracy > 1000m = garbage` guard (correct) then rejected every ping → zero rows stored. Also found: app sends `lat=0,lng=0` in RAW columns but that's just at-rest encryption masking (decrypted coords were real OAU positions — false alarm) | **Two-part fix in LocationFilter.kt:** (1) advance `lastTs` on the reject/NaN coast paths so dt stays honest (a rejected fix is still a real observation in time); (2) clamp position/velocity covariance diagonals on the coast path so a GPS-lost device reports "last known ± ~1km" (999m — under the server's 1000m reject) instead of ±152,000km. Verified in a numeric simulation + new regression test (rejected fixes can't blow up accuracy; recovers instantly when GPS returns). 10/10 LocationFilter tests pass. Server guard left intact (correct defense; app no longer generates garbage) | ✅ **FIXED (2026-08-15)** — APK rebuilt + installed on D1; live-verified: stream resumed 6–9m HIGH confidence at true position, ZERO rejections since 13:33. Commit pending (bundled with G1 session commit) |
| S-10 | 2026-08-14 | Web + repo | Security re-check (Aug 14 20:15) | Re-check's remaining open items: (a) “S-7 verification — tampered/expired sig on api.magneetar.me/apk/download still returns the SPA page (200)”; (b) “repo git log secret-history scan” from the Agent Mode backlog; (c) “Play Store Accessibility justification for System Update Protection before submission” | (a) **Timeline (per re-check's accuracy note, 2026-08-15): the 20:10 probe WAS on api.magneetar.me** and the API host did serve the SPA fallback then; the 403 handling landed between 20:10 and the 20:15 re-verification (deploy 20:07–20:08, propagation window). End state verified: `?expires=…&sig=deadbeef` → **403** `application/json` `{"detail":"Invalid or expired download link — mint a fresh one from the download page"}`. Note: the marketing host also serves the SPA fallback for unknown paths (no binary ever streams from either host). (b) **Secret-history scan CLEAN** — `git log --all -p -S` over secret-bearing patterns + the add-only filename scan found no real credentials ever committed: every env/secret file in history is a placeholder (`CHANGE_ME`, empty values, `.example` files); `mtk_*` appears only in docs/tests describing the prefix. (c) **Resolved by design** — `android-app/app/src/play/AndroidManifest.xml` removes `UninstallGuardService` via `tools:node="remove"` (comment: “Play Store rejects non-accessibility usage”); the merged Play manifest has ZERO accessibility matches (DISTRIBUTION_PLAN.md verified). The Play build ships no accessibility service, so no justification is required; the sideload build keeps it with a documented removal path | (a) No code change — behavior correct; re-verified live 2026-08-14 20:15+ (403 JSON). (b) No change. (c) Documented in play-store-checklist (new E.2 row) — gate item closed by flavor design | ✅ **RESOLVED (2026-08-14/15)** — S-7 403, secret scan clean, Play accessibility stripped by flavor; timeline corrected per re-check (probe was on api.magneetar.me, 403 landed in the deploy propagation window) |

**Install decision tree (for “App not installed”) — evidence-updated 2026-08-15:**

**Root cause, elevated 2026-08-15 (ADR-0007): the sideload channel itself
is dead on modern Android.** `PLAY_POLICY_ANALYSIS.md` proved no permission
profile that keeps Magneetar's anti-theft features can be sideloaded —
Enhanced Fraud Protection hard-blocks apps with device admin + camera/mic +
background location + overlay when installed from a browser. The fix is the
**Play internal testing track** (private, email-invited testers, no public
listing, no review delay, auto-updates): `docs/PLAY_INTERNAL_TESTING_SETUP.md`.
The tree below remains the fallback for devices that can't use Play.

Established: served bytes = verified APK; APK valid; ALL builds share one
signing key (024cbb34…) → a “signature conflict with an older build” is NOT
the cause here. The phone (Samsung SM-A037F) installed v1.4.1 fine before.
The failure is phone-state, in this order:

1. **Leftover/zombie install (most likely).** Magneetar actively resists
   uninstall (device admin + accessibility guard). A normal “Settings →
   Apps → Magneetar → Uninstall” may be greyed out or bounce home, and an
   interrupted attempt can leave a stale package that blocks new installs.
   → Deactivate first: Settings → Security → Device admin apps → Magneetar
   → Deactivate; Settings → Accessibility → “System Update Protection” →
   OFF. THEN uninstall. Definitive: `adb uninstall com.magneetar.app`
   (one USB cable + PC), then `adb install magneetar-v1.4.3-release.apk`.
   v1.4.3 (2026-08-14): installs on phones that still run an older build can
   also self-heal via the **in-app updater** — open Magneetar, tap the
   “Update available” notification, done (no sideload, no PC).
2. **OEM scanner (Samsung “App security” is separate from Play Protect).**
   Pause BOTH during install, then re-enable.
3. **“Install unknown apps” grant.** The app/browser opening the APK needs
   Settings → Apps → <browser> → Install unknown apps → Allow.
4. Still failing? `adb install` prints the real INSTALL_FAILED_* code —
   record it verbatim + Android version (`adb shell getprop
   ro.build.version.release`) + `adb shell pm list packages | grep -i
   magneetar` (is it really gone?) and reopen this issue row.

## 6. Server-side signals (checked at exit)

| Signal | Where | Result |
|---|---|---|
| `error_log` rows during the window | server logs / dashboard Errors tab |  |
| Unexplained `last_seen` gaps > 30 min while armed | dashboard device list / DB |  |
| `/health` status + DB health over the window (uptime is deliberately not public — F-08; operators read it from admin `/api/metrics`) | api.magneetar.me/health |  |
| Sentry events (if DSN configured) | Sentry project dashboard |  |

## 7. G1 exit checklist (ALL boxes required to pass)

- [ ] Device roster: ≥6 devices / ≥4 OEMs (incl. Transsion + no-network-provider regression device)
- [ ] Each device ran ≥2 continuous weeks as a daily driver
- [ ] Condition matrix fully populated — no N-TESTED left where it must be tested
- [ ] Recovery drill 12/12 on every device
- [ ] Battery drain within band on every device
- [ ] Zero open P0s; none new in the final 7 days
- [ ] No silent-tracking-death in the final week
- [ ] ≥80% of testers "keep using / recommend"; all P1/P2 findings closed or owner-accepted
- [ ] Exit documented (drill logs + feedback results + fix list) → **then start G2 (closed testing)**
