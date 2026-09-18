'use client';

import { Quote, Star, ShieldCheck, Lock, Code, EyeOff } from 'lucide-react';

const TESTIMONIALS = [
  {
    quote: 'My Samsung was stolen at a bus stop in Lagos. Magneetar locked it, captured photos of the person holding it, and I had the evidence for police within 20 minutes.',
    name: 'Adaeze K.',
    role: 'University student, Lagos',
    device: 'Samsung A03s',
  },
  {
    quote: 'I manage 8 delivery riders. The fleet dashboard lets me see everyone in real time — when a phone went missing last month, we recovered it in under an hour.',
    name: 'Tunde M.',
    role: 'Operations lead, logistics startup',
    device: '5× Xiaomi Redmi',
  },
  {
    quote: 'The family circle feature means I can see my kids\' phones are safe without constantly calling them. It just works in the background.',
    name: 'Ngozi E.',
    role: 'Parent, Abuja',
    device: '2× Oppo A78',
  },
];

const TRUST_SIGNALS = [
  { value: '256-bit', label: 'Encryption', icon: Lock },
  { value: 'Tamper-evident', label: 'Evidence integrity', icon: ShieldCheck },
  { value: 'Open', label: 'Source code', icon: Code },
  { value: 'Zero', label: 'Data sold', icon: EyeOff },
];

export function Testimonials() {
  return (
    <section className="py-28 sm:py-36 bg-gray-950 relative overflow-hidden">
      {/* Subtle glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-emerald-500/[0.015] rounded-full blur-[100px] pointer-events-none" />

      <div className="relative max-w-6xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 mb-5">
            <Quote size={10} className="text-emerald-400" />
            <span className="text-[11px] font-mono font-bold tracking-[0.2em] text-emerald-400/80">REAL USERS</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4">
            Trusted by families &amp; teams.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            From university students to logistics companies — Magneetar protects what matters.
          </p>
        </div>

        {/* Testimonial cards */}
        <div className="grid md:grid-cols-3 gap-5">
          {TESTIMONIALS.map((t) => (
            <div
              key={t.name}
              className="relative rounded-2xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border p-6 hover:border-emerald-500/15 transition-all duration-400 group"
            >
              {/* Top emerald accent */}
              <div className="absolute top-0 left-10 right-10 h-px bg-gradient-to-r from-transparent via-emerald-500/0 to-transparent group-hover:via-emerald-500/30 transition-all duration-500" />

              {/* Stars */}
              <div className="flex gap-0.5 mb-4">
                {[...Array(5)].map((_, i) => (
                  <Star key={i} size={13} className="text-emerald-400 fill-emerald-400" />
                ))}
              </div>

              {/* Quote */}
              <p className="text-[13px] leading-relaxed text-mag-text-dim mb-5">
                &ldquo;{t.quote}&rdquo;
              </p>

              {/* Author */}
              <div className="flex items-center justify-between pt-4 border-t border-mag-border/50">
                <div>
                  <div className="text-[12px] font-bold text-mag-text">{t.name}</div>
                  <div className="text-[11px] font-mono text-mag-text-muted">{t.role}</div>
                </div>
                <span className="text-[11px] font-mono text-mag-text-muted px-2 py-1 rounded border-mag-border/50 bg-mag-surface">
                  {t.device}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Trust signals bar */}
        <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-4">
          {TRUST_SIGNALS.map((s) => (
            <div key={s.label} className="text-center py-5 rounded-xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border hover:border-emerald-500/10 transition-all duration-300 group">
              <s.icon size={16} className="text-mag-text-muted mx-auto mb-3 group-hover:text-emerald-400/60 transition-colors" />
              <div className="text-lg font-extrabold text-mag-text font-mono tabular-nums">{s.value}</div>
              <div className="text-[11px] font-mono text-mag-text-muted uppercase tracking-wider mt-1">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
