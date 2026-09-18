'use client';

import { ShieldCheck, Lock, EyeOff, Users, Zap, Globe } from 'lucide-react';

/**
 * SocialProof — replaces fictional testimonials with verifiable metrics.
 * No made-up names, no fake quotes. Just honest, auditable claims.
 */

const VERIFIABLE_CLAIMS = [
  {
    metric: '3s',
    label: 'location updates',
    detail: 'Accurate, street-level GPS coordinates',
    icon: Zap,
  },
  {
    metric: 'Tamper-evident',
    label: 'evidence for police',
    detail: 'Photos, audio, and location records that cannot be altered',
    icon: Lock,
  },
  {
    metric: 'Works',
    label: 'offline',
    detail: 'Location pings queue when offline and sync when reconnected',
    icon: ShieldCheck,
  },
  {
    metric: 'Zero',
    label: 'data sold',
    detail: 'We never sell, share, or monetize your location data',
    icon: EyeOff,
  },
];

const ARCHITECTURE_FACTS = [
  {
    icon: Globe,
    title: 'Built for Africa',
    description: 'Designed for Nigerian networks — works on MTN, Airtel, Glo, and 9mobile. Tuned for the phones people actually use.',
  },
  {
    icon: Users,
    title: 'Share with family',
    description: 'Protect your spouse, kids, or teammates from one account. See everyone on a single dashboard.',
  },
  {
    icon: EyeOff,
    title: 'Your data stays yours',
    description: 'We don\'t sell, share, or monetize your location data. Your information stays on secure servers.',
  },
];

export function SocialProof() {
  return (
    <section className="py-28 sm:py-36 bg-gray-950 relative overflow-hidden">
      <div className="relative max-w-6xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 mb-5">
            <ShieldCheck size={10} className="text-emerald-400" />
            <span className="text-[11px] font-mono font-bold tracking-[0.2em] text-emerald-400/80">WHY MAGNEETAR</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4">
            Why people trust Magneetar.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            Built for the moment your phone disappears. Here's what makes Magneetar different.
          </p>
        </div>

        {/* Verifiable metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-14">
          {VERIFIABLE_CLAIMS.map((item) => (
            <div key={item.label} className="text-center py-6 rounded-xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border hover:border-emerald-500/10 transition-all duration-300 group">
              <item.icon size={18} className="text-mag-text-muted mx-auto mb-3 group-hover:text-emerald-400/60 transition-colors" />
              <div className="text-2xl font-extrabold text-mag-text font-mono tabular-nums">{item.metric}</div>
              <div className="text-[11px] font-mono text-mag-text-muted uppercase tracking-wider mt-1.5 font-semibold">{item.label}</div>
              <div className="text-[11px] text-mag-text-muted mt-1.5 leading-relaxed">{item.detail}</div>
            </div>
          ))}
        </div>

        {/* Architecture facts */}
        <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {ARCHITECTURE_FACTS.map((fact) => (
            <div key={fact.title} className="flex items-start gap-4 rounded-2xl border-mag-border bg-gradient-to-b from-mag-surface to-mag-bg p-6 hover:border-emerald-500/15 transition-all duration-400 group">
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/15 transition-all">
                <fact.icon size={16} className="text-emerald-400/70 group-hover:text-emerald-400 transition-colors" />
              </div>
              <div>
                <div className="text-mag-text font-semibold text-sm">{fact.title}</div>
                <div className="text-[12.5px] text-mag-text-muted leading-relaxed mt-1">{fact.description}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Trust note */}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 text-[11px] font-mono text-mag-text-muted">
          <span>BUILT IN NIGERIA · FOR NIGERIA</span>
          <span className="w-1 h-1 rounded-full bg-emerald-500/30" />
          <span className="text-emerald-400/60">FREE TO START · NO CREDIT CARD</span>
        </div>
      </div>
    </section>
  );
}
