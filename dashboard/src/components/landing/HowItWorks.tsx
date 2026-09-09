'use client';

import Link from 'next/link';
import { Smartphone, Map, ShieldCheck, ArrowRight } from 'lucide-react';

const STEPS = [
  {
    icon: Smartphone,
    step: '01',
    title: 'Install & connect',
    description: (
      <>
        Download the APK from the{' '}
        <Link href="/download" className="text-emerald-400 font-semibold hover:underline transition-colors">
          official download page
        </Link>
        , sign in once, and grant permissions. Add family, coworkers, or your team — no configuration.
      </>
    ),
  },
  {
    icon: Map,
    step: '02',
    title: 'Stay in sync',
    description:
      'Live locations stream to your circles. When a device moves, SIM-swaps, or drops battery — Sentinel scores it silently in real time.',
  },
  {
    icon: ShieldCheck,
    step: '03',
    title: 'Recover it',
    description:
      'Theft confirmed? Live tracking with navigation straight to the device, plus remote photo and audio capture for evidence.',
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-28 sm:py-36 scroll-mt-20 overflow-hidden"
      style={{ background: 'linear-gradient(180deg, #060a10 0%, #030712 50%, #060a10 100%)' }}>
      {/* Ambient glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-emerald-500/[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-2xl mx-auto text-center mb-14">
          <div className="badge-dark mb-5 mx-auto w-fit">
            <span>HOW IT WORKS</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white">
            Connected in{' '}
            <span className="bg-gradient-to-r from-gray-400 to-gray-500 bg-clip-text text-transparent">three steps</span>
          </h2>
          <p className="mt-4 text-mag-text-muted leading-relaxed">
            From first launch to full recovery — Magneetar keeps your devices protected and your people close.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6 relative max-w-5xl mx-auto">
          {/* Connecting line */}
          <div className="hidden md:block absolute top-20 left-[20%] right-[20%] h-px">
            <div className="w-full h-full bg-gradient-to-r from-transparent via-emerald-500/20 to-transparent" />
          </div>

          {STEPS.map((step, i) => (
            <div key={step.step} className="relative group">
              <div className="relative rounded-2xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border p-7 h-full hover:border-emerald-500/20 transition-all duration-400">
                {/* Big step number */}
                <div className="text-[48px] font-mono font-bold text-mag-text-muted/10 leading-none select-none group-hover:text-emerald-500/[0.06] transition-colors duration-500 mb-2">
                  {step.step}
                </div>

                <div className="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-5 group-hover:bg-emerald-500/15 transition-all duration-300">
                  <step.icon size={20} className="text-emerald-400/70 group-hover:text-emerald-400 transition-colors duration-300" />
                </div>

                <h3 className="text-mag-text font-bold text-lg tracking-tight">{step.title}</h3>
                <p className="mt-3 text-[13px] leading-relaxed text-mag-text-muted">{step.description}</p>

                {/* Arrow between steps */}
                {i < STEPS.length - 1 && (
                  <ArrowRight
                    size={14}
                    className="hidden md:block absolute -right-[11px] top-20 text-emerald-500/20 z-10"
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
