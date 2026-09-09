import { readdirSync, readFileSync, statSync } from 'fs';
import { join, extname, resolve, dirname } from 'path';

// Jest runs with cwd = dashboard root. Walk dashboard/src for authored UI.
const SRC_ROOT = resolve('src');

// What we catch: hand-authored surface/border/text-opacity literals in JSX
// that should be mag tokens (bg-mag-*, border-mag-*, text-mag-*) or the
// globals.css primitives (glass-card, mag-panel, mag-badge, etc.).
//
// NOT caught (intentional, not decay):
// - token-usage patterns like bg-emerald-500/15, text-emerald-400/70  (these
//   are mag-accent usage via opacity, not drift)
// - map-specific polyline/fill colors in leaflet pathOptions / TileLayer
// - class-name construction in utilities (lib/utils.ts)

const PROHIBITED_LITERALS = [
  // Hard-coded dark backgrounds that should be mag.bg / mag.surface / mag.surface-raised
  'bg-[#0a0a0f]',
  'bg-[#111118]',
  'bg-[#060609]',
  'bg-[#0c0c12]',
  'bg-[#0e0e14]',
  'bg-[#020609]',
  'bg-[#0a0f1a]',
  'bg-[#060a10]',
  // Hard-coded surface opacities (the main drift pattern in dashboard panels)
  'bg-white/[0.01]',
  'bg-white/[0.02]',
  'bg-white/[0.03]',
  'bg-white/[0.04]',
  'bg-white/[0.06]',
  'bg-white/[0.08]',
  'bg-white/[0.1]',
  'bg-white/[0.15]',
  // Hard-coded border opacities
  'border-white/[0.04]',
  'border-white/[0.06]',
  'border-white/[0.08]',
  'border-white/[0.1]',
  'border-white/[0.12]',
  // Hard-coded text opacities
  'text-white/[0.04]',
  'text-white/[0.06]',
  'text-white/[0.08]',
  'text-white/[0.1]',
  'text-white/[0.15]',
  'text-white/[0.2]',
  'text-white/[0.25]',
  'text-white/[0.3]',
  'text-white/[0.35]',
  'text-white/[0.4]',
  'text-white/[0.45]',
  'text-white/[0.5]',
  'text-white/[0.55]',
  'text-white/[0.6]',
  'text-white/[0.65]',
  'text-white/[0.7]',
  'text-white/[0.75]',
  'text-white/[0.8]',
  'text-white/[0.85]',
  'text-white/[0.9]',
  'text-white/[0.95]',
  // Mixed hex+opacity surfaces (catch remaining drift)
  'bg-[#111118]/80',
  'bg-[#111118]/90',
  'bg-[#111118]/95',
  'bg-[#0a0a0f]/95',
  // Low-opacity white surface/border on dark chrome (landing/marketing drift)
  'bg-white/5',
  'bg-white/10',
  'border-white/10',
  'border-white/5',
  'bg-black/60',
  'bg-black/70',
  'text-gray-400',
  'text-gray-500',
  'text-gray-600',
  'text-gray-300',
];

function collectSourceFiles(root: string): string[] {
  const results: string[] = [];
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop()!;
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      continue;
    }
    for (const entry of entries) {
      const full = join(dir, entry);
      try {
        const st = statSync(full);
        if (st.isDirectory()) {
          if (entry === 'node_modules' || entry === 'static' || entry === '__tests__' || entry === '.next') {
            continue;
          }
          stack.push(full);
        } else if (st.isFile()) {
          const ext = extname(entry);
          if (ext === '.ts' || ext === '.tsx' || ext === '.js' || ext === '.jsx') {
            results.push(full);
          }
        }
      } catch {
        continue;
      }
    }
  }
  return results;
}

/**
 * Scope: the WHOLE dashboard/src authoring surface.
 *
 * Every authored UI file in dashboard/src must use mag tokens
 * (bg-mag-*, border-mag-*, text-mag-*) or the globals.css primitives
 * (glass-card, mag-panel, mag-badge, btn-emerald, btn-ghost, badge-dark,
 * section-dark, etc.) as its source of truth. There is no separate
 * "landing has its own chrome" exemption anymore — the landing family and
 * auth routes were unified onto the same token system this phase, so the
 * gate now enforces consistency everywhere.
 *
 * Utilities that construct className strings (lib/utils.ts) are excluded.
 * The globals.css file itself is excluded (it IS the source of truth).
 */
function isInScope(file: string): boolean {
  // Excluded: utilities — not design authoring.
  if (file.endsWith('/lib/utils.ts') || file.endsWith('/lib/api.ts')) return false;
  // Excluded: the design system definition itself.
  if (file.endsWith('/app/globals.css')) return false;
  return true;
}

function findViolations(content: string, file: string): string[] {
  if (!isInScope(file)) return [];

  const violations: string[] = [];
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim().startsWith('//') || line.trim().startsWith('*') || line.trim() === '') continue;

    for (const lit of PROHIBITED_LITERALS) {
      // Per-line allowance: a line may carry one whitespace comment token
      // after the class literal (e.g. trailing // auth page chrome). We
      // still flag the literal but soften duplicates on the same logical
      // class string by counting occurrences per line.
      const count = line.split(lit).length - 1;
      for (let c = 0; c < count; c++) {
        violations.push(`L${i + 1}: ${lit}`);
      }
    }
  }

  return violations;
}

describe('mag token consistency — whole dashboard/src authoring surface', () => {
  const files = collectSourceFiles(SRC_ROOT).filter((f) => f.includes('/src/'));

  it('enforces mag tokens / globals.css primitives as the source of truth across the whole project', () => {
    const violations: Array<{ file: string; line: string }> = [];

    for (const file of files) {
      const content = readFileSync(file, 'utf8');
      const found = findViolations(content, file);
      for (const v of found) {
        violations.push({ file: file.replace(SRC_ROOT + '/', ''), line: v });
      }
    }

    expect(violations).toEqual([]);
  });
});
