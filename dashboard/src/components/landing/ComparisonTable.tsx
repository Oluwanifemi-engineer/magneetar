'use client';

import { Check } from 'lucide-react';
import { Spotlight } from '@/components/ui/Spotlight';

const WHY_MAGNEETAR = [
  {
    title: 'It works when your phone is off',
    description: 'Most tracking apps die when the phone goes offline. Magneetar queues location data and uploads it the moment the phone reconnects.',
  },
  {
    title: 'Built for the phones Nigerians actually use',
    description: 'Huawei, Xiaomi, Oppo, Vivo, Realme — these phones kill most tracking apps to save battery. Magneetar survives because it was designed for them.',
  },
  {
    title: 'Evidence you can take to the police',
    description: 'Not just a location pin. Photos of whoever has your phone, audio recordings, and a timeline of everything that happened.',
  },
  {
    title: 'Alerts that reach you on any network',
    description: 'Push, email, and SMS alerts tuned for MTN, Airtel, Glo, and 9mobile — you know the moment something is wrong. WhatsApp alerting is in development.',
  },
  {
    title: 'Lock it remotely, one tap',
    description: 'See your phone on the map? Lock the screen, trigger a siren, or wipe your data — all from your dashboard in one click.',
  },
  {
    title: 'Free to protect your main phone',
    description: 'No credit card required. No hidden fees. Protect your primary phone for free, and upgrade only when you want to protect more devices.',
  },
];

export function ComparisonTable() {
  return (
    <Spotlight className="py-20 sm:py-28 bg-gray-950 relative overflow-hidden" color="rgba(16,185,129,0.06)">
      <div className="max-w-6xl mx-auto px-5 sm:px-8">
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-5">
            <Check size={10} className="text-emerald-400" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-muted">WHY MAGNEETAR</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-4">
            Not just another tracker.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            Google Find My Device doesn&apos;t work on most budget phones. Samsung only works on Samsung.
            Magneetar was built for everyone else.
          </p>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {WHY_MAGNEETAR.map((item) => (
            <div
              key={item.title}
              className="flex flex-col rounded-2xl border-mag-border bg-gradient-to-b from-mag-surface to-mag-bg p-6 hover:border-emerald-500/15 transition-all duration-400 group"
            >
              <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/15 transition-all mb-4">
                <Check size={16} className="text-emerald-400/70 group-hover:text-emerald-400 transition-colors" />
              </div>
              <div className="text-mag-text font-semibold text-sm group-hover:text-emerald-50 transition-colors">{item.title}</div>
              <div className="text-[12.5px] text-mag-text-muted leading-relaxed mt-2">{item.description}</div>
            </div>
          ))}
        </div>          <p className="text-[9px] font-mono text-mag-text-muted text-center mt-8">
          Built in Lagos, Nigeria. Designed for the 25M+ phones stolen every year.
        </p>
      </div>
    </Spotlight>
  );
}
