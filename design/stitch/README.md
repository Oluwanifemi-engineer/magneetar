# Stitch Design Intake

Approved screens from Google Stitch land here before being ported into the
app (`android-app/app/src/main/res/layout/`) and dashboard
(`dashboard/src/components/`).

## What to save per screen

1. **Full-screen screenshot** (primary artifact) — `NN-<screen>.png`
   e.g. `01-onboarding.png`, `02-permissions.png`, `03-home.png`
2. **HTML/CSS export** from Stitch if available — same name, `.html`

## Screen numbering (app)

| NN | Screen | Ports into |
|----|--------|------------|
| 01 | Onboarding | `activity_onboarding.xml` |
| 02 | Sign in | `activity_signin.xml` |
| 03 | Permissions (Enable Protection) | `activity_permissions.xml` |
| 04 | Home tab | `fragment_home.xml` |
| 05 | Map tab | `fragment_map.xml` |
| 06 | Devices tab | `fragment_devices.xml` |
| 07 | Alerts tab | `fragment_alerts.xml` |
| 08 | Security tab | `fragment_security.xml` |
| 09 | Lost Mode lock screen | `activity_lost_mode.xml` |
| 10 | Pairing | `activity_pairing.xml` |

## Porting rules (for the implementer)

- Design = structure, spacing, hierarchy, copy. Behavior stays untouched:
  every existing `android:id` binding must survive the port.
- Colors come from `res/values/colors.xml` (aubergine accent) and
  `dashboard/src/lib/tokens.ts` — never hardcoded hex in layouts.
- Status colors (emerald/amber/red) are STATUS ONLY per the contract in
  `tokens.ts`; the aubergine accent never replaces a status indicator.
- One screen per port, APK rebuilt and verified before moving on.
