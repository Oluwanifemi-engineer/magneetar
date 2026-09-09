'use client';

import { Smartphone, BellRing, BatteryCharging, FileCheck2, TrendingDown } from 'lucide-react';

const AFRICA_STATS = [
  {
    value: '25M+',
    label: 'phones stolen in Nigeria',
    detail: 'Recorded across a single 12-month period',
  },
  {
    value: '₦45,000+',
    label: 'to attempt recovery',
    detail: 'And even then, there are no guarantees',
  },
  {
    value: '11.7%',
    label: 'recovery rate',
    detail: 'Fewer than 1 in 8 thefts end in recovery',
  },
];

const AFRICA_POINTS = [
  {
    icon: BellRing,
    title: 'Alerts that reach you',
    description:
      'Multi-channel alerts tuned for Nigerian networks — push, email, and SMS — so you know the moment something is wrong. WhatsApp alerting is in development.',
  },
  {
    icon: BatteryCharging,
    title: 'Survives the phones people use',
    description:
      'Survives battery-saving modes on Huawei, Xiaomi, Oppo, Vivo, and Realme — phones that kill most tracking apps.'
  },
  {
    icon: FileCheck2,
    title: 'Evidence that holds up',
    description:
      'Tamper-evident photo, audio, and location evidence, packaged into PDF reports you can take to the police.'
  },
];

export function Africa() {
  return (
    <section id="africa" className="relative py-28 sm:py-36 scroll-mt-20 overflow-hidden bg-gray-950">
      {/* Red accent glow at top */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[200px] bg-red-500/[0.02] rounded-full blur-[100px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-red-500/20 bg-red-500/5 mb-5">
            <TrendingDown size={10} className="text-red-400" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-red-400/80">THE PROBLEM</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
            Built for{' '}
            <span className="bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">Africa.</span>
          </h2>
          <p className="mt-5 text-mag-text-muted leading-relaxed">
            Phone theft is the most common crime in Nigeria — and fewer than 1 in 8 reported thefts ever
            end in recovery. Magneetar was designed to change that number.
          </p>
        </div>

        {/* Stats — red accent cards */}
        <div className="grid sm:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {AFRICA_STATS.map((stat) => (
            <div
              key={stat.label}
              className="relative rounded-2xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border p-7 text-center hover:border-red-500/15 transition-all duration-400 group"
            >
              {/* Red accent line at top */}
              <div className="absolute top-0 left-10 right-10 h-px bg-gradient-to-r from-transparent via-red-500/30 to-transparent group-hover:via-red-500/50 transition-all duration-500" />

              <div className="text-4xl sm:text-5xl font-extrabold font-mono tabular-nums text-mag-text group-hover:text-red-50 transition-colors duration-300">
                {stat.value}
              </div>
              <div className="mt-3 text-mag-text-dim font-semibold text-sm leading-snug">{stat.label}</div>
              <div className="mt-2 text-[12px] leading-relaxed text-mag-text-muted">{stat.detail}</div>
            </div>
          ))}
        </div>

        {/* Points — emerald accent cards */}
        <div className="mt-14 grid md:grid-cols-3 gap-4 max-w-5xl mx-auto">
          {AFRICA_POINTS.map((point) => (
            <div
              key={point.title}
              className="flex items-start gap-4 rounded-2xl border-mag-border bg-gradient-to-b from-mag-surface to-mag-bg p-6 hover:border-emerald-500/15 transition-all duration-400 group"
            >
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/15 transition-all">
                <point.icon size={16} className="text-emerald-400/70 group-hover:text-emerald-400 transition-colors" />
              </div>
              <div>
                <div className="text-mag-text font-semibold text-sm group-hover:text-emerald-50 transition-colors">{point.title}</div>
                <div className="text-[12.5px] text-mag-text-muted leading-relaxed mt-1">{point.description}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 flex items-center justify-center gap-2 text-[11px] font-mono text-mag-text-muted">
          <Smartphone size={11} />
          <span>Source: National Bureau of Statistics — Crime Experience &amp; Security Perception Survey, 2024</span>
        </div>
      </div>
    </section>
  );
}
