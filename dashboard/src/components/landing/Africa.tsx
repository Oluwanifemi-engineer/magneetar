'use client';

import { Smartphone, BellRing, BatteryCharging, FileCheck2 } from 'lucide-react';

/**
 * Built for Africa — Magneetar's core differentiator.
 *
 * All stats are sourced from Nigeria's National Bureau of Statistics,
 * "Crime Experience and Security Perception Survey" (CESPS) 2024, which
 * covered the May 2023 – April 2024 reference period.
 */
const AFRICA_STATS = [
  {
    value: '25M+',
    label: 'phones stolen in Nigeria in one year',
    detail: '25,354,417 thefts recorded across a single 12-month period',
    accent: '#E91E8C',
  },
  {
    value: '1.2s',
    label: 'between phone thefts',
    detail: 'One phone stolen roughly every 1.2 seconds — the most common crime in the country',
    accent: '#06B6D4',
  },
  {
    value: '11.7%',
    label: 'of reported stolen phones are recovered',
    detail: 'Fewer than 1 in 8 thefts reported to the police end in recovery',
    accent: '#22C55E',
  },
];

const AFRICA_POINTS = [
  {
    icon: BellRing,
    title: 'Alerts that reach you',
    description:
      'Multi-channel alerts tuned for Nigerian networks — SMS, WhatsApp, and push — so you know the moment something is wrong.',
  },
  {
    icon: BatteryCharging,
    title: 'Survives the phones people use',
    description:
      'OEM-aware persistence engineered for Huawei, Xiaomi, Oppo, Vivo, and Realme — the battery killers that end most trackers.',
  },
  {
    icon: FileCheck2,
    title: 'Evidence that holds up',
    description:
      'SHA-256-chained photo, audio, and location evidence, packaged into PDF reports ready for law enforcement.',
  },
];

export function Africa() {
  return (
    <section
      id="africa"
      className="relative py-24 sm:py-32 bg-mag-panel/30 border-y border-white/[0.05] scroll-mt-20 overflow-hidden"
    >
      <div className="absolute inset-0 landing-grid opacity-30 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[640px] h-[320px] rounded-full bg-[#22C55E]/6 blur-[120px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">WHY MAGNEETAR</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white leading-tight">
            Built for <span className="text-gradient-primary">Africa.</span>
          </h2>
          <p className="mt-5 text-white/45 leading-relaxed">
            Phone theft is the most common crime in Nigeria — and fewer than 1 in 8 reported thefts ever
            end in recovery. Magneetar was designed to change that number, and to keep families and
            teams connected while it does.
          </p>
        </div>

        {/* Stats */}
        <div className="grid sm:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {AFRICA_STATS.map((stat) => (
            <div key={stat.label} className="relative group card-glow rounded-2xl border border-white/[0.07] bg-[#0d0d14]/80 backdrop-blur-xl p-7 text-center overflow-hidden">
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                style={{ background: `radial-gradient(ellipse at top, ${stat.accent}12 0%, transparent 60%)` }}
              />
              <div
                className="relative text-4xl sm:text-5xl font-extrabold font-mono tabular-nums"
                style={{ color: stat.accent }}
              >
                {stat.value}
              </div>
              <div className="relative mt-3 text-white/70 font-semibold text-sm leading-snug">{stat.label}</div>
              <div className="relative mt-2 text-[12px] leading-relaxed text-white/35">{stat.detail}</div>
            </div>
          ))}
        </div>

        {/* Magneetar's answer */}
        <div className="mt-14 grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {AFRICA_POINTS.map((point) => (
            <div
              key={point.title}
              className="flex items-start gap-4 rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-xl p-6 group"
            >
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

        {/* Source footnote */}
        <div className="mt-10 flex items-center justify-center gap-2 text-[11px] font-mono text-white/25">
          <Smartphone size={11} />
          <span>
            Source: National Bureau of Statistics — Crime Experience &amp; Security Perception Survey, 2024
            (May 2023 – Apr 2024 reference period)
          </span>
        </div>
      </div>
    </section>
  );
}
