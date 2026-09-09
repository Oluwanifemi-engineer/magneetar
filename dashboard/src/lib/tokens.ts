/**
 * Magneetar Brand Tokens — single source of truth (2026-09-09)
 *
 * ONE brand accent across web + Android: aubergine magenta. Chosen to
 * complement the black/white launcher icon and read "serious security
 * tool" on pure black surfaces.
 *
 * COLOR CONTRACT:
 *  - Brand accent (aubergine) = primary buttons, active nav/states,
 *    focus rings, links, armed states. The ONLY brand color.
 *  - Status colors are STATUS ONLY and must never be repurposed as
 *    decoration: emerald = online/protected/success, amber = attention,
 *    red = threat/destructive.
 *  - Consumers:
 *      web    → tailwind.config.ts `mag.primary` family (keep in sync)
 *               globals.css `:root { --mag-accent* }` (keep in sync)
 *      android→ res/values/colors.xml `md_theme_primary` family (keep in sync)
 *      stitch → the seed prompts reference these exact hex values
 *
 * If you change a value here, change it in all four places or the
 * platforms drift (which is exactly what this file exists to prevent).
 */

export const ACCENT = {
  /** Deep aubergine magenta — the brand accent. */
  base: '#8E2A6E',
  /** Brighter magenta — links, pressed states, on-dark small accents. */
  bright: '#C0549C',
  /** Dimmed aubergine — hover/active fills on primary buttons. */
  dim: '#71265A',
  /** RGB triplet of base, for rgba() composition. */
  rgb: '142, 42, 110',
} as const;

export const STATUS = {
  /** Online / protected / success. */
  ok: '#10B981',
  /** Attention needed. */
  warn: '#F59E0B',
  /** Threat / destructive. */
  danger: '#EF4444',
} as const;

/** Surfaces — near-black scale shared by web dashboard and app. */
export const SURFACE = {
  /** Page background (web uses #030712 via mag-bg; app uses #0B1120). */
  webBg: '#030712',
  /** Android background. */
  androidBg: '#0B1120',
  /** Elevated card. */
  raised: '#1F2937',
} as const;

/** Radii + spacing rhythm shared across platforms (dp == px at 1x). */
export const RHYTHM = {
  radiusCard: 16,
  radiusPill: 999,
  spaceUnit: 4,
} as const;

/** CSS custom properties mirroring this module (see globals.css :root). */
export const ACCENT_CSS_VARS = {
  accent: 'var(--mag-accent)',
  accentBright: 'var(--mag-accent-bright)',
  accentDim: 'var(--mag-accent-dim)',
} as const;
