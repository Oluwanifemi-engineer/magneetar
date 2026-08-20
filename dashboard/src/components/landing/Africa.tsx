'use client';

import { Smartphone, BellRing, BatteryCharging, FileCheck2 } from 'lucide-react';

const AFRICA_STATS = [
  {
    value: '25M+',
    label: 'phones stolen in Nigeria in one year',
    detail: '25,354,417 thefts recorded across a single 12-month period',
  },
  {
    value: '1.2s',
    label: 'between phone thefts',
    detail: 'One phone stolen roughly every 1.2 seconds — the most common crime in the country',
  },
  {
    value: '11.7%',
    label: 'of reported stolen phones are recovered',
    detail: 'Fewer than 1 in 8 thefts reported to the police end in recovery',
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
      className="relative py-24 sm:py-32 bg-gray-50/50 border-y border-gray-100 scroll-mt-20 overflow-hidden"
    >
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-200 bg-white mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-gray-500">WHY MAGNEETAR</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-gray-900 leading-tight">
            Built for <span className="text-gray-400">Africa.</span>
          </h2>
          <p className="mt-5 text-gray-500 leading-relaxed">
            Phone theft is the most common crime in Nigeria — and fewer than 1 in 8 reported thefts ever
            end in recovery. Magneetar was designed to change that number, and to keep families and
            teams connected while it does.
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {AFRICA_STATS.map((stat) => (
            <div key={stat.label} className="relative group rounded-2xl border border-gray-200 bg-white p-7 text-center overflow-hidden hover:border-gray-300 hover:shadow-lg hover:shadow-gray-900/[0.04] transition-all duration-300">
              <div className="relative text-4xl sm:text-5xl font-extrabold font-mono tabular-nums text-gray-900">
                {stat.value}
              </div>
              <div className="relative mt-3 text-gray-700 font-semibold text-sm leading-snug">{stat.label}</div>
              <div className="relative mt-2 text-[12px] leading-relaxed text-gray-500">{stat.detail}</div>
            </div>
          ))}
        </div>

        <div className="mt-14 grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {AFRICA_POINTS.map((point) => (
            <div
              key={point.title}
              className="flex items-start gap-4 rounded-2xl border border-gray-200 bg-white p-6 group hover:border-gray-300 hover:shadow-lg hover:shadow-gray-900/[0.04] transition-all duration-300"
            >
              <div className="w-9 h-9 rounded-lg bg-gray-50 border border-gray-200 flex items-center justify-center shrink-0 group-hover:bg-gray-100 transition-colors">
                <point.icon size={16} className="text-gray-600" />
              </div>
              <div>
                <div className="text-gray-900 font-semibold text-sm">{point.title}</div>
                <div className="text-[12.5px] text-gray-500 leading-relaxed mt-1">{point.description}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-10 flex items-center justify-center gap-2 text-[11px] font-mono text-gray-400">
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
