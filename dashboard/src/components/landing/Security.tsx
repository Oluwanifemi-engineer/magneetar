'use client';

import { KeyRound, Lock, FileCheck2, Fingerprint, Globe } from 'lucide-react';

const SECURITY_POINTS = [
  {
    icon: KeyRound,
    title: 'Unique per-device keys',
    description:
      'Every device generates its own 256-bit secret on first launch — generated at runtime, never compiled into the APK.',
  },
  {
    icon: Lock,
    title: 'Zero plaintext secrets',
    description:
      'The server stores only SHA-256 hashes of device keys and bcrypt password hashes. A database breach cannot leak credentials.',
  },
  {
    icon: FileCheck2,
    title: 'Chain of custody',
    description:
      'Every piece of evidence is hashed and chained, producing forensic-grade SHA-256 reports admissible in recovery cases.',
  },
  {
    icon: Fingerprint,
    title: 'Token revocation',
    description:
      'JWT access and refresh tokens can be revoked instantly. Stolen sessions are invalidated server-side on detection.',
  },
  {
    icon: Globe,
    title: 'Hardened transport',
    description:
      'Rate-limited endpoints, request timeouts, CORS hardening in production, and AES-256 encryption at rest.',
  },
];

export function Security() {
  return (
    <section id="security" className="relative py-24 sm:py-32 overflow-hidden scroll-mt-20">
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-14 items-center">
        {/* Copy */}
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">SECURITY</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white leading-tight">
            Built like it protects
            <br />
            <span className="text-gradient-primary">something precious.</span>
          </h2>
          <p className="mt-5 text-white/45 leading-relaxed max-w-lg">
            Because it does. Magneetar treats every device as a vault — with per-device secrets,
            cryptographic evidence, and instant session revocation.
          </p>

          {/* Feature list */}
          <div className="mt-8 space-y-4">
            {SECURITY_POINTS.map((point) => (
              <div key={point.title} className="flex items-start gap-4 group">
                <div className="w-9 h-9 rounded-lg border border-white/[0.08] bg-white/[0.03] flex items-center justify-center shrink-0 group-hover:border-[#22C55E]/30 transition-colors">
                  <point.icon size={16} className="text-[#22C55E]" />
                </div>
                <div>
                  <div className="text-white font-semibold text-sm">{point.title}</div>
                  <div className="text-[12.5px] text-white/40 leading-relaxed mt-1">{point.description}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Shield visual */}
        <div className="relative flex items-center justify-center py-10">
          <div className="relative w-72 h-72 sm:w-80 sm:h-80">
            {/* Rotating rings */}
            <div className="absolute inset-0 rounded-full border border-white/[0.06] animate-slow-spin">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[#E91E8C] shadow-[0_0_12px_rgba(233,30,140,0.9)]" />
            </div>
            <div
              className="absolute inset-6 rounded-full border border-dashed border-white/[0.08] animate-slow-spin"
              style={{ animationDirection: 'reverse', animationDuration: '18s' }}
            >
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[#06B6D4] shadow-[0_0_12px_rgba(6,182,212,0.9)]" />
            </div>

            {/* Core shield */}
            <div className="absolute inset-16 rounded-full bg-gradient-to-br from-[#E91E8C]/15 to-[#06B6D4]/10 border border-white/[0.08] backdrop-blur-xl flex items-center justify-center shadow-2xl shadow-black/50">
              <svg viewBox="0 0 24 24" className="w-16 h-16 text-white/90" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <path d="M9 12l2 2 4-4" />
              </svg>
            </div>

            {/* Status chips */}
            <div className="absolute -top-2 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full border border-white/10 bg-[#111118]/95 backdrop-blur-xl text-[10px] font-mono font-bold text-white/70 shadow-lg shadow-black/40">
              AES-256
            </div>
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 px-3 py-1.5 rounded-full border border-white/10 bg-[#111118]/95 backdrop-blur-xl text-[10px] font-mono font-bold text-[#22C55E] shadow-lg shadow-black/40">
              SHA-256 CHAIN
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
