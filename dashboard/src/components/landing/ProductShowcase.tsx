'use client';

import { useState } from 'react';
import { Shield, Camera, Lock, ChevronRight, Monitor } from 'lucide-react';

/**
 * ProductShowcase — shows what the real dashboard looks like.
 *
 * These are REAL logged-in captures of the shipped dashboard
 * (design/stitch/captures → dashboard/public/screenshots), not mockups.
 * The chrome around them is honest: a plain window frame and a URL pill,
 * no fake video controls, no simulated "live" data.
 */

const SCREENSHOTS = [
  {
    id: 'dashboard',
    label: 'Command Center',
    description: 'Full-screen map with device tracking, floating actions, and device drawer',
    src: '/screenshots/command-center.webp',
    alt: 'Magneetar dashboard: full-screen map tracking a device, with the device drawer open',
  },
  {
    id: 'sentinel',
    label: 'Theft Detection',
    description: 'Automatic theft scoring across 8 signals',
    src: '/screenshots/theft-detection.webp',
    alt: 'Magneetar dashboard: Sentinel theft-detection panel scoring device signals',
  },
  {
    id: 'evidence',
    label: 'Evidence Capture',
    description: 'Tamper-evident photos and audio you can take to the police',
    src: '/screenshots/evidence-capture.webp',
    alt: 'Magneetar dashboard: evidence panel listing captured photos and audio with hashes',
  },
  {
    id: 'commands',
    label: 'Remote Commands',
    description: 'Lock, siren, wipe, lost mode — one click execution',
    src: '/screenshots/remote-commands.webp',
    alt: 'Magneetar dashboard: remote commands panel with lock, siren, and wipe actions',
  },
] as const;

/* ── Honest window frame ─────────────────────────────────────────────── */

function ScreenshotFrame({ src, alt }: { src: string; alt: string }) {
  return (
    <figure className="bg-mag-landing rounded-xl overflow-hidden border border-mag-border/50 shadow-elevation-4">
      {/* Window chrome — deliberately plain, no fake controls */}
      <div className="flex items-center gap-2 px-3 py-2 bg-mag-landing-chrome border-b border-mag-border/50">
        <div className="flex gap-1.5" aria-hidden="true">
          <div className="w-2.5 h-2.5 rounded-full bg-mag-text-muted/30" />
          <div className="w-2.5 h-2.5 rounded-full bg-mag-text-muted/30" />
          <div className="w-2.5 h-2.5 rounded-full bg-mag-text-muted/30" />
        </div>
        <span className="mx-auto px-3 py-0.5 rounded-md bg-mag-surface text-[11px] font-mono text-mag-text-dim">
          magneetar.me/dashboard
        </span>
        {/* Spacer to keep the URL pill centered */}
        <div className="w-10" aria-hidden="true" />
      </div>

      {/* The real capture. Intrinsic 1440×810 — attrs reserve space, no CLS. */}
      <img
        src={src}
        alt={alt}
        width={1440}
        height={810}
        loading="lazy"
        decoding="async"
        className="block w-full h-auto"
      />
    </figure>
  );
}

/* ── Section ─────────────────────────────────────────────────────────── */

export function ProductShowcase() {
  const [activeTab, setActiveTab] = useState(0);
  const active = SCREENSHOTS[activeTab];

  return (
    <section className="py-28 sm:py-36 bg-black relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-mag-border/50 bg-mag-surface mb-5">
            <Monitor size={12} className="text-emerald-400" />
            <span className="text-xs font-mono font-bold tracking-[0.2em] text-mag-text-muted">THE PRODUCT</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4">
            What you actually get.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            No mockups. No concept art. This is the real Magneetar command center, captured from a logged-in session.
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-6 items-start">
          {/* Screenshot — takes 3 columns */}
          <div className="lg:col-span-3">
            <div className="transition-all duration-500">
              <ScreenshotFrame src={active.src} alt={active.alt} />
              <figcaption className="mt-3 text-xs font-mono text-mag-text-muted text-center">
                Live capture from the shipped dashboard — not a rendering.
              </figcaption>
            </div>
          </div>

          {/* Tab selector — takes 2 columns */}
          <div className="lg:col-span-2 space-y-2">
            {SCREENSHOTS.map((s, i) => (
              <button
                key={s.id}
                onClick={() => setActiveTab(i)}
                aria-pressed={i === activeTab}
                className={
                  'w-full text-left p-3.5 rounded-xl border transition-all duration-300 ' +
                  (i === activeTab
                    ? 'bg-mag-surface-raised border-emerald-500/20 shadow-glow-sm'
                    : 'border-mag-border/25 hover:bg-mag-surface hover:border-mag-border/50')
                }
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all ${
                      i === activeTab
                        ? 'bg-emerald-500/10 border border-emerald-500/20'
                        : 'bg-mag-surface border border-mag-border'
                    }`}
                  >
                    {i === 0 ? (
                      <Monitor size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} />
                    ) : i === 1 ? (
                      <Shield size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} />
                    ) : i === 2 ? (
                      <Camera size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} />
                    ) : (
                      <Lock size={16} className={i === activeTab ? 'text-emerald-400' : 'text-mag-text-muted'} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span
                      className={`text-sm font-bold transition-colors ${
                        i === activeTab ? 'text-white' : 'text-mag-text-muted'
                      }`}
                    >
                      {s.label}
                    </span>
                    {i === activeTab && (
                      <p className="text-xs text-mag-text-muted mt-0.5 leading-relaxed">{s.description}</p>
                    )}
                  </div>
                  {i === activeTab && <ChevronRight size={14} className="text-emerald-400/50 shrink-0" />}
                </div>
              </button>
            ))}

            {/* Trust badges */}
            <div className="flex items-center gap-4 pt-4 border-t border-mag-border mt-3">
              {['Uninstall-resistant', 'Encrypted', 'Source-available'].map((label) => (
                <span key={label} className="text-xs font-mono text-mag-text-muted">
                  {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
