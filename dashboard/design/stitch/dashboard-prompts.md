# Dashboard Stitch prompt pack — Magneetar

Use exactly like the Android pack: seed prompt first, then one screen/area per prompt,
save/export each accepted design before moving on. Screens are ordered by dependency —
the workspace shell sets the layout grammar; panels are designed against that grammar.

## 1 — Seed prompt (paste once, creates the theme)

```
A premium web dashboard for "Magneetar", an anti-theft device tracking and recovery service.
Dark theme only: near-black background (#0A0A0F), elevated glass panels (#111118 with subtle blur
and 1px borders at 8% white). White primary text, 60% white secondary, 30% tertiary.

Single brand accent: deep aubergine magenta (#8E2A6E) for primary actions, active states, focus
rings, and armed/selected states — lighter magenta (#C0549C) for links and pressed states.
Status colors appear ONLY as small state indicators, never as decoration:
  emerald green  = online / protected / success / safe zone
  amber          = attention needed / elevated risk / offline
  red            = threat / destructive / stolen / critical error

Typography: Inter for headings and body, JetBrains Mono for labels, metrics, and technical values —
uppercase tracking-wider for micro-labels. Rounded-xl cards, pill buttons, thin 1.5px line icons.

The overall feel: a calm mission-control console for device security — dense with information but
never cluttered, like Linear meets a security operations console, not a generic admin panel.
The most important thing on screen should be obvious in under one second.

DISTINCTIVENESS DIRECTION (read this before every screen prompt below):
This is not a generic fleet dashboard. It is a single-device recovery console. The dominant
relationship on screen is: "here is one device, here is its situation right now, here is what you
can do about it." The map is the narrative, not the background. Protection state is the headline,
not a score. Commands are framed by intent ("find it / get evidence / lock it down / erase it"),
not as a raw command list. Evidence feels like a case file, not a secondary tab. Chrome is quiet;
the real thing on screen is the device and its state. Do not design another admin panel — design a
calm, deliberate, consumer-facing recovery console that happens to be dense with real information.
```

## 2 — Workspace shell (desktop, paste first)

This is the layout grammar every panel inherits. Real structure from
`src/app/dashboard/page.tsx`: sidebar (device list) + full-screen map + right panel (w-80,
7 tabs via Tabs.tsx). Real tab names from `PANEL_TABS`: Sentinel, Commands, Location, Zones,
Media, Evidence, Errors.

```
Web dashboard workspace, desktop, dark theme. Full-screen map fills the main area and is the
narrative core — the device pin, trail, zone, and distance read-out live on the map and are the first
thing the eye hits. A left sidebar shows a device list (device name, online status dot, last seen,
sentinel score) with a Magneetar wordmark at top — quiet chrome, not the hero.

On the right, a w-80 panel. Its header is deliberately understated: a small mono "LIVE" tag in the
accent color (not a big emerald pill), the active panel name in mono, and a close button. Below the
header, a tight horizontal row of 7 tab buttons — Sentinel, Commands, Location, Zones, Media,
Evidence, Errors — each with a thin line icon, mono uppercase label, active state in accent color,
and a tiny possible badge for alerts. The tab row is a compact glass strip, not a bordered box.
The panel body scrolls; the map does not.

Visual hierarchy rule: the map and the active panel content are the story; the sidebar and tabs are
quiet chrome. No emerald washed across the screen — the only green should be real online/protected
status. The accent color appears for: active tab, primary button, focus ring, armed/selected state.

Distinctiveness rule: this should not feel like a generic fleet console. It should feel like you have
opened one device and are looking at its current situation — the map tells you where it is and what
has happened, the active panel tells you its state and what you can do. The sidebar exists to switch
devices; everything else is subordinate to the device you are looking at.
```

## 3 — Sentinel panel (the protection-state panel, paste second)

Real content from `SentinelPanel.tsx`: one big sentinel score number, state label (SECURE /
ELEVATED / HIGH RISK / STOLEN), score bar, 4 KPI tiles (Battery, Speed, Accuracy, Last Seen),
optional stolen alert block. State color is status-only.

```
Sentinel panel for the Magneetar dashboard — the protection-state screen, dark theme.
This is the panel that answers "is this device protected right now?", so protection state is the
headline, not the raw score.

Top: a single, clear protection state as the dominant message — the state label (SECURE / ELEVATED /
HIGH RISK / STOLEN) as the primary read, in status color only (emerald / amber / red). The sentinel
score (e.g. "12") is the supporting detail: a large mono numeral, but deliberately secondary to the
state label — consumers think in "protected / at risk / stolen", not in "47 out of 100". Below the
score, a thin score bar (rounded-full) with the score as width, colored by state. A quiet mono
sub-label "SENTINEL SCORE" so the number has context.

Below the hero: a 2x2 grid of small stat tiles — Battery (%), Speed (km/h), Accuracy (±m), Last Seen
— each with a tiny mono label and a tabular value, in panel chrome. These are supporting facts about
the device's current situation, not the headline.

State handling: if the device is marked stolen, the hero block shifts to red-tinted but stays calm —
no big red banner screaming. The stolen state is a real status, not decoration. The panel should feel
like a calm read of the device's protection state, with the score as evidence for that read.

Distinctiveness rule: this is not a generic "big number in a rounded box" widget. It is a calm,
deliberate protection-state read — state first, score second, facts third. The accent color is not
used here (this is a status panel, not an action panel); status colors carry the only color, and only
as status.
```

## 4 — Commands panel (the actions-by-intent panel, paste third)

Real content from `CommandPanel.tsx`: 4 command groups (Locate, Evidence, Control, Danger) with
collapsible sections, 9 commands total, command history table, wipe confirmation with password,
offline SMS relay notice. State colors are status-only.

```
Commands panel for the Magneetar dashboard — the action screen, dark theme.
This is the panel where you act on the device, so it should be framed by what the user wants to
achieve, not by a raw command inventory.

Top: a compact state note — e.g. "Offline — SMS mode" when the device is offline and SMS relay is
active — in a quiet colored strip, not a banner. This is the one piece of "right now" context the
panel leads with.

Command sections framed by intent, not by technical group name. The four sections still exist
(Locate, Evidence, Control, Danger) but they should read as the user's intents: "find it", "get
evidence", "lock it down", "erase it". Each section is a collapsible block with a thin line icon, a
mono uppercase label, and a count. When open, a 2-column grid of command buttons appears. Each button
is a compact pill or small card with an icon, a short uppercase label (PING, PHOTO, AUDIO, BURST,
LOCK, SIREN, LOST MODE, WIPE), and a tone that reflects its seriousness — primary for find-it
actions, accent for evidence, warning for lock-down, danger-red for erase. The danger actions should
feel deliberately more serious — red-tinted, separated, not just another button in the grid.

Command history below the actions: a clean mono table — command name, time, status — sorted with
failed first, then pending, then executed. Status is a small colored chip, color = state only. The
table is quiet reference chrome; failed/pending rows are subtly tinted so the eye can scan for
problems.

Wipe confirmation: a focused security gate — password field, explicit "Permanent Wipe / This erases
ALL data" text, confirm/cancel. This is the one place the panel becomes deliberately heavy; it should
feel like a real confirmation, not a generic modal.

Distinctiveness rule: this is not a generic "9 buttons in groups" console. It is a calm action panel
organized by what the user is trying to do to the device. The accent color is for the primary actions;
red is for destructive actions and failed states; status colors are for real state, not decoration.
```

## 5 — Location / Device panel (paste fourth)

Real content from `DevicePanel.tsx`: device header with status pills (archived, access role, location
mode), device ID/registered/last seen/capture state, coordinate display, location details (provider,
accuracy, speed, altitude, bearing), Open in Google Maps, export CSV, sharing section, alert settings
(channels, types, quiet hours), offline SMS commands, delete device.

```
Device / Location panel for the Magneetar dashboard — the device detail screen, dark theme.
This is the panel that tells you about one device: who it is, where it is, and how it is configured.

Top: a clean device header — device name (bold, the largest text in the panel), with small mono status
pills beside it for archived / access role / location mode. Each pill is quiet chrome with a status
tint only when it carries real state (e.g. location-mode-off = danger, safe zone = secure). Below the
name, a quiet row of mono facts: Device ID, Registered, Last Seen, Capture (Armed / Unarmed /
Unknown) — tabular, dim, reference-style.

If there is a live location, show a coordinate display block prominently but calmly — latitude and
longitude in mono, tabular-nums, not a giant number. Below that, a location details section: provider,
accuracy, speed, altitude, bearing — each as a label/value row in panel chrome. These are the device's
current situation facts; they should feel like the supporting evidence for the map, not a separate
screen.

Actions: a quiet "Open in Google Maps" button and an "Export Location History (CSV)" button, both
modest, not loud.

Configuration sections (Sharing, Alert Settings, Offline SMS Commands): each is a collapsible section
with a mono header and a small chevron. Alert settings show channels and alert types as small toggle
pills — active = secure green, inactive = muted. Quiet hours as two compact selects. These sections are
reference and configuration, so they should feel quieter than the header and coordinates — the hierarchy
is device identity > live location > configuration, with visual weight dropping as you go down.

Delete device: a danger button at the bottom, deliberately separated and quiet until activated — this is
a destructive action and should not compete visually with the device info.

Distinctiveness rule: this is not a generic device settings panel. It is a single-device situation
report — identity, live location, then configuration as reference. The accent color appears for primary
save actions; status colors appear only for real device state.
```

## 6 — Media panel (paste fifth)

Real content from `MediaGallery.tsx`: photo/audio viewer, grid of captured media, manage mode with
multi-select, delete with password confirmation.

```
Media panel for the Magneetar dashboard — the captured evidence gallery, dark theme.

When viewing a single item: a clean viewer — for a photo, the image fills the panel area with quiet
chrome; for audio, a centered play/pause control with a download link. Above the viewer, a mono
header: "PHOTO — TIMESTAMP" or "AUDIO — TIMESTAMP", with a back button and, for owners, a delete
button. Below the viewer, a compact location row (lat, lng) if available.

When browsing: a 2-column grid of capture cards — each card is a quiet rounded rectangle with a small
icon placeholder (camera or microphone), a mono type label (PHOTO / AUDIO), and a timestamp. In
manage mode, cards get a selection state (check mark, subtle green tint) and multi-select actions
appear (Select all, Clear, Delete N).

Delete confirmation: a focused modal — password field, explicit "N items · irreversible" text,
confirm/cancel. This is a security gate, not a generic dialog.

Overall: the gallery should feel like evidence — quiet, forensic, deliberate. The accent color is
for primary actions; red is for destructive. Status colors are minimal here — media is evidence, not
a status screen.
```

## 7 — Evidence panel (paste sixth)

Real content from `EvidencePanel.tsx`: case ID, status, location/photo/audio counts, SHA-256 chain,
export recovery dossier (PDF) button.

```
Evidence panel for the Magneetar dashboard — the case file screen, dark theme.

This is the screen where the device's recovery evidence lives, so it should feel like a case file you
could hand to police or an insurer, not a generic dashboard widget.

Top: a quiet header "EVIDENCE LOCKER" in mono. Below, a case-summary block in panel chrome: Case ID
e.g. #MT-4821 as a mono label, status (ACTIVE / CLOSED) as a small status pill in status color only.
Below that, a 3-column row of count tiles — LOCATIONS, PHOTOS, AUDIO — each a mono big number with a
tiny label underneath. These counts are the shape of the case; they should feel like evidence, not
analytics.

If available, show the SHA-256 integrity chain as a quiet mono line — first 32 chars, break-all, dim
text, "INTEGRITY CHAIN:" label. This is proof the case has not been tampered with, so it should be
visible but not loud — it is the quiet credibility line.

Bottom: a single full-width button "EXPORT RECOVERY DOSSIER (PDF)" — the primary action of this panel,
in accent color, understated but clear. Below it, a one-line description of what the dossier contains
(device info, location trail, command timeline, tamper-proof photos & audio, alert history). The
export is the action; the case file is the evidence.

Empty state: a calm empty card — no active evidence case yet, with a short note that evidence is created
automatically when theft is detected. No loud empty state; just a quiet "no case yet".

Distinctiveness rule: this is not a generic "counts + export button" panel. It is a calm case file —
case ID, status, what is in it, and the proof it is intact. Status colors are for case status only; the
accent is for the export action. The panel should feel like something you can trust, not something you
just glance at.
```

## 8 — Geofence panel (paste seventh)

Real content from `GeofencePanel.tsx`: zone list (name, coordinates, radius, safe/restricted pill,
auto-action chip), add zone form (name, lat, lng, radius, safe zone toggle, auto-action radio:
Alert only / Capture / Siren).

```
Geofence panel for the Magneetar dashboard — the safe-zone editor, dark theme.

Top: a quiet header "GEOFENCE ZONES" in mono, with a small count label ("3 zones" / "No zones").

Zone list: each zone is a single quiet row — a status dot (emerald for safe zone, amber for
restricted), the zone name or "Zone #N", a small status pill (Safe / Restricted), the coordinates
and radius in dim mono, and an auto-action chip (ALERT / CAPTURE / SIREN) with a tiny icon. Rows are
chrome with hover states; the dot and pill carry the only color, and only as status.

Add zone form: a clean form in panel chrome — name (optional), latitude, longitude, radius (meters),
a safe-zone toggle (quiet checkbox with a clear label "Safe zone (alert when device LEAVES it)"),
and an auto-action radio group (Alert only / Capture / Siren) with short hints. The form should feel
precise and technical, not like a marketing form — these are coordinates and meters.

Delete: a small chip on each row; on hover/tap it becomes a confirm state — deliberate, not a big
destructive button. Danger color only in the confirm state.

Overall: the panel should feel like a precise spatial configuration tool — coordinates, radii,
policies. Status colors are for safe vs restricted; accent is for the primary create action.
```

## 9 — Errors panel (paste eighth)

Real content from `ErrorPanel.tsx`: error list with level (CRITICAL / WARNING), request path, message,
timestamp, client IP, device ID, optional traceback, resolved state, mark-resolve action, unresolved
filter, refresh.

```
Errors panel for the Magneetar dashboard — the error log / triage screen, dark theme.

Top: a header "ERROR LOG" in mono, with a small status pill when there are unresolved errors
("N open" in danger red), and a refresh button. Below, a filter toggle "Unresolved only" and a total
count ("N total") — quiet chrome.

Error list: each error is a collapsible row — header shows level (CRITICAL = red, WARNING = amber) as
a small status pill, the request path in dim mono, the error message in medium text, and a quiet row
of meta (timestamp, client IP, device ID) in tiny mono. Expanding the row reveals a clean details
block: method, path, client IP, device ID, optional traceback in a monospace pre block, and a resolve
action (or a "Resolved by X at TIME" note if already resolved).

Color discipline: red is for CRITICAL and unresolved danger; amber is for WARNING; resolved errors are
quieted (lower opacity). The panel should feel like a triage console — you scan for red, then dig into
details.

Empty state: "All clear" or "All resolved" with a calm note — no errors, or all resolved.

Overall: the panel should feel like an operations log — calm, scannable, technical. Status colors are
for error severity and resolution state; the accent color is not used here (this is a log, not an
action panel).
```

## 10 — Landing page (public, paste ninth, optional)

Real structure from `src/app/page.tsx`: LandingNav, Hero, ProductShowcase, ComparisonTable,
SocialProof, Africa, OurStory, Features, Security, Pricing, CTA, Footer. Real vocabulary from the
page.

```
Marketing landing page for "Magneetar", an anti-theft phone security service, dark theme.
Top nav: white magnet-arch logo mark with "MAGNEETAR" wordmark, links Features / How it works /
Download, and a magenta pill button "Get started". Hero: bold headline "Your phone. Stolen-proof."
with subtitle "Real-time tracking, silent intruder capture, and remote lockdown — running 24/7 on
your device." and two buttons: magenta pill "Download the app", ghost "Sign in". Hero visual: a phone
mockup on a dark map showing a device pin.

Below, honest sections that match the real product: a three-card feature row (location pin "Real-time
tracking" / camera "Intruder capture" / shield "Remote lock & wipe"), each a dark glass card with a
thin icon and one-line description; a comparison table against generic alternatives; a "Built for
Africa" section; a security section; a pricing section that says what's real today (free plan, 1
device, checksum-verified APK) and what's under development; a CTA; a footer with Privacy, Terms.

The page should feel premium and calm, lots of black space, aubergine accent for the primary CTA and
active nav only. Status colors (green/amber/red) are not used on the landing page — it's marketing,
not a status screen. Every claim should be honest: no fabricated adoption numbers.
```

## 11 — Login page (public, paste tenth, optional)

Real content from `src/app/login/page.tsx`: email + password + API key alternate path, 2FA step,
brand showcase left panel with a mock command-center telemetry card, live ticker, security strip.

```
Sign-in page for the Magneetar dashboard, dark theme, centered single card on near-black background.
Logo mark above the card. Card: headline "Welcome back", email field, password field, both dark inputs
with 1px borders and magenta focus rings; full-width magenta pill button "Sign in"; below it a "Forgot
password?" text link in light magenta. A mode toggle between Account and API Key. Beneath the card:
"Don't have an account? Create one" link, and a muted note "Protecting a device with a pairing code?
Use the app instead." One quiet link bottom-right: "Download APK". A small security strip: TOTP 2FA,
BCRYPT, RATE-LIMITED.

If you design the brand showcase side (the mock command-center telemetry card with a map, radar ping,
live ticker, threat/sentinel/evidence readouts), keep it quiet and clearly a render — it should feel
like a preview of the dashboard, not a live system. The accent color is for the primary button and
focus rings; status green can appear in the mock telemetry as "SAFE" / online dots, because that's a
preview of real status.

Minimal, trustworthy, banking-grade. No decorative emerald washed across the page.
```

## 12 — Download page (public, paste eleventh, optional)

Real content from `src/app/download/page.tsx`: download button with ticket minting, feature grid,
install steps, OEM battery notes, install FAQ, verify section with SHA-256 checksum, honest "what's
under development" note.

```
Download page for Magneetar, dark theme. Centered content on near-black background. Top: a small badge
"GET THE APP", a headline "Protect your phone with Magneetar.", a short subtitle, and a few honest
quick stats (Stealth tracking 24/7, Checksum verified SHA-256, Free plan 1 device).

The download section: a clean card with a shield icon, the app name, Android version / file size /
version from the live checksum endpoint, and a feature grid listing only what the release actually
delivers (Real-time GPS tracking, Remote lock & alarm, Remote wipe, Photo & audio evidence capture,
Sentinel theft detection, Geofence safe zones, SMS relay — optional). The download button is a magenta
pill that mints a fresh secure ticket; a quiet note explains the link expires by design.

Below: install steps (Download, Allow installation, Open & sign in, Grant permissions), OEM battery
notes for Xiaomi/Huawei/OPPO/Vivo, an install FAQ in collapsible details, a verify section with the
live SHA-256 checksum (copyable), and an honest note that community recovery, offline device network,
and advanced battery features are under development.

The page should feel premium and honest — every claim verifiable on the page or in the product. The
accent color is for the download button and focus rings; status green appears only for verified/shield
icons; no decorative emerald wash.
```

## Porting notes (when you're back from Stitch)

- Design the workspace shell first (prompt 2) — it sets the layout grammar and the chrome vocabulary
  every panel inherits. Then do panels in any order, but Sentinel (prompt 3) and Commands (prompt 4)
  first — they're the two screens users act from most.
- When porting, keep every existing component contract and hook intact — this is a reskin, not a
  rewrite. The panel chrome classes in `globals.css` (`.mag-panel`, `.mag-panel-elevated`,
  `.mag-panel-header`, `.mag-panel-label`, `.mag-badge*`, `.mag-stat*`, `.mag-empty*`, `.mag-field*`)
  are the target vocabulary; Stitch should refine these, not replace them.
- Keep the mono-font micro-label + uppercase character — it's the dashboard's identity. Stitch should
  sharpen it, not throw it out.
- One honest constraint: Stitch output is the spec, not code. Porting happens in the TSX, one panel at
  a time, each behind the existing test suite. The `mag-token-consistency` test and `tsc --noEmit` gate
  run on every port.
