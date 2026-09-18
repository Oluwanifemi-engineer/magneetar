'use client';

import { KeyRound, Lock, FileCheck2, Fingerprint, Globe } from 'lucide-react';

const SECURITY_POINTS = [
  {
    icon: KeyRound,
    title: 'Your phone has its own lock',
    description:
      'Every phone gets a unique key when you install the app — even if someone copies the app, they cannot access your data.',
  },
  {
    icon: Lock,
    title: 'Your password is protected',
    description:
      'We never store your actual password. Even if our servers were hacked, your credentials would be safe.',
  },
  {
    icon: FileCheck2,
    title: 'Evidence that holds up',
    description:
      'Every photo and recording is sealed so it cannot be altered — evidence you can take to the police.',
  },
  {
    icon: Fingerprint,
    title: 'Lost your login? Kill it instantly',
    description:
      'If someone gets into your account, you can shut them out immediately from any device.',
  },
  {
    icon: Globe,
    title: 'Everything is encrypted',
    description:
      'Your location, commands, and evidence are all encrypted — scrambled so only you can read them.',
  },
];

export function Security() {
  return (
    <section id="security" className="relative py-28 sm:py-36 overflow-hidden scroll-mt-20"
      style={{ background: 'linear-gradient(180deg, #030712 0%, #060a10 50%, #030712 100%)' }}>
      {/* Ambient glow */}
      <div className="absolute top-1/2 right-0 w-[400px] h-[400px] bg-emerald-500/[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-14 items-center">
        {/* Copy */}
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 mb-5">
            <Lock size={10} className="text-emerald-400" />
            <span className="text-[11px] font-mono font-bold tracking-[0.2em] text-emerald-400/80">SECURITY</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
            Your phone. Your data.
            <br />
            <span className="bg-gradient-to-r from-gray-400 to-gray-500 bg-clip-text text-transparent">Protected at every step.</span>
          </h2>
          <p className="mt-5 text-mag-text-muted leading-relaxed max-w-lg">
            Magneetar protects your location, evidence, and account with multiple layers of security — so even if something goes wrong, your data stays safe.
          </p>

          <div className="mt-8 space-y-4">
            {SECURITY_POINTS.map((point) => (
              <div key={point.title} className="flex items-start gap-4 group">
                <div className="w-9 h-9 rounded-lg bg-mag-surface border-mag-border flex items-center justify-center shrink-0 group-hover:bg-emerald-500/10 group-hover:border-emerald-500/20 transition-all">
                  <point.icon size={16} className="text-mag-text-muted group-hover:text-emerald-400 transition-colors" />
                </div>
                <div>
                  <div className="text-mag-text font-semibold text-sm">{point.title}</div>
                  <div className="text-[12.5px] text-mag-text-muted leading-relaxed mt-1">{point.description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Shield visual */}
        <div className="relative flex items-center justify-center py-10">
          <div className="relative w-72 h-72 sm:w-80 sm:h-80">
            {/* Rotating rings */}
            <div className="absolute inset-0 rounded-full border border-emerald-500/10 animate-slow-spin">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-glow-sm" />
            </div>
            <div
              className="absolute inset-6 rounded-full border border-dashed border-mag-border/50 animate-slow-spin"
              style={{ animationDirection: 'reverse', animationDuration: '18s' }}
            >
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-mag-text-muted/50" />
            </div>

            {/* Core shield */}
            <div className="absolute inset-16 rounded-full bg-gradient-to-b from-emerald-500/[0.06] to-transparent border border-emerald-500/10 flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="w-16 h-16 text-emerald-400/70" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="M9 12l2 2 4-4" />
              </svg>
            </div>

            {/* Status chips */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full border border-emerald-500/20 bg-mag-landing text-[11px] font-mono font-bold text-emerald-400/80 shadow-elevation-2">
              2FA PROTECTED
            </div>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full border border-mag-border/50 bg-mag-landing text-[11px] font-mono font-bold text-mag-text-dim shadow-elevation-2">
              ENCRYPTED
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
