'use client';

import { Smartphone, Map, ShieldCheck, ArrowRight } from 'lucide-react';

const STEPS = [
  {
    icon: Smartphone,
    step: '01',
    title: 'Install & connect in minutes',
    description:
      'Download the APK or Play Store build, sign in once, and grant permissions. Link your device to your account, then add family, coworkers, or your team — no configuration, no setup.',
  },
  {
    icon: Map,
    step: '02',
    title: 'Stay in sync, always',
    description:
      'Live locations stream to your circles so everyone knows everyone is safe. And when a device moves, SIM-swaps, or drops battery — Sentinel scores it silently in real time.',
  },
  {
    icon: ShieldCheck,
    step: '03',
    title: 'Theft detected — recover it',
    description:
      'The moment theft is confirmed, Magneetar locks in: live tracking with a navigation route straight to the device, plus remote photo and audio capture for evidence.',
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-24 sm:py-32 bg-mag-panel/30 border-y border-white/[0.05] scroll-mt-20">
      <div className="absolute inset-0 landing-grid opacity-30 pointer-events-none" />
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="max-w-2xl mx-auto text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">HOW IT WORKS</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white">
            Connected in <span className="text-gradient-primary">three steps</span>
          </h2>
          <p className="mt-4 text-white/45 leading-relaxed">
            From first launch to full recovery — Magneetar keeps your devices protected and your people close.
          </p>
        </div>

        {/* Steps */}
        <div className="grid md:grid-cols-3 gap-6 relative">
          {/* Connector line */}
          <div className="hidden md:block absolute top-16 left-[16%] right-[16%] h-px bg-gradient-to-r from-[#E91E8C]/40 via-white/15 to-[#06B6D4]/40" />

          {STEPS.map((step, i) => (
            <div key={step.step} className="relative group">
              <div
                className="relative rounded-2xl border border-white/[0.07] bg-[#0d0d14]/80 backdrop-blur-xl p-7 h-full card-glow"
              >
                {/* Step number */}
                <div className="absolute top-5 right-6 text-[40px] font-mono font-bold text-white/[0.05] leading-none select-none">
                  {step.step}
                </div>

                {/* Icon */}
                <div className="relative w-12 h-12 rounded-xl bg-gradient-to-br from-[#E91E8C]/20 to-[#06B6D4]/15 border border-white/[0.08] flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300">
                  <step.icon size={22} className="text-white/80" />
                </div>

                <h3 className="text-white font-bold text-lg tracking-tight">{step.title}</h3>
                <p className="mt-3 text-[13px] leading-relaxed text-white/40">{step.description}</p>

                {i < STEPS.length - 1 && (
                  <ArrowRight
                    size={16}
                    className="hidden md:block absolute -right-[12px] top-1/2 -translate-y-1/2 text-white/20 z-10"
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
