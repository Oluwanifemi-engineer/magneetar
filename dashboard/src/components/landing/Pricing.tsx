'use client';

import Link from 'next/link';
import { Check, Crown, Smartphone, Users, ShieldCheck, Building2, ArrowRight } from 'lucide-react';

const TIERS = [
  {
    icon: Smartphone,
    name: 'Free',
    price: '₦0',
    period: 'free forever',
    devices: '1 device',
    tagline: 'Protect your main phone.',
    features: [
      'Full theft detection (Sentinel AI)',
      'Live tracking + route to device',
      'Evidence capture (photo & audio)',
      'Family & team circles',
      'Guardian Network access',
    ],
    cta: { label: 'Get Started Free', href: '/signup', primary: true },
  },
  {
    icon: Users,
    name: 'Personal',
    price: '₦500',
    period: 'per month · or ₦5,000/year',
    devices: 'Up to 3 devices',
    tagline: 'You plus the phones closest to you.',
    features: [
      'Everything in Free',
      'Protect up to 3 devices on one account',
      'Family & coworker circles',
      'Priority alert delivery',
    ],
    cta: { label: 'Start Free', href: '/signup', primary: false },
  },
  {
    icon: ShieldCheck,
    name: 'Guardian',
    price: '₦1,500',
    period: 'per month · or ₦15,000/year',
    devices: 'Up to 10 devices',
    tagline: 'The whole family — or a small business.',
    features: [
      'Everything in Personal',
      'Protect up to 10 devices',
      'Whole-fleet command center',
      'Multi-owner team access',
    ],
    cta: { label: 'Start Free', href: '/signup', primary: false },
    bestValue: true,
  },
  {
    icon: Building2,
    name: 'Enterprise',
    price: 'Custom',
    period: 'tailored to your organisation',
    devices: 'Unlimited devices',
    tagline: 'Fleets, schools, and security teams.',
    features: [
      'Everything in Guardian',
      'Unlimited device allowance',
      'Custom integrations & onboarding',
      'Dedicated support & SLAs',
    ],
    cta: { label: 'Talk to us', href: 'mailto:sales@magneetar.me', primary: false },
  },
];

export function Pricing({ authed }: { authed: boolean }) {
  return (
    <section id="pricing" className="relative py-24 sm:py-32 bg-white scroll-mt-20 overflow-hidden">
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-2xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-200 bg-gray-50 mb-5">
            <Crown size={12} className="text-gray-500" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-gray-500">PRICING</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-gray-900 leading-tight">
            Protection that scales with
            <br />
            <span className="text-gray-400">your family &amp; team.</span>
          </h2>
          <p className="mt-5 text-gray-500 leading-relaxed">
            Every plan includes every feature — theft detection, live tracking, evidence capture, the
            whole command center. The only difference is how many devices you protect.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {TIERS.map((tier, i) => {
            const cta = authed && tier.cta.href === '/signup'
              ? { label: 'Open Command Center', href: '/dashboard', primary: true }
              : tier.cta;
            return (
              <div
                key={tier.name}
                className={`relative flex flex-col rounded-2xl border p-7 transition-all duration-300 hover:-translate-y-1 ${
                  tier.bestValue
                    ? 'border-gray-900 bg-gray-900 text-white'
                    : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-lg hover:shadow-gray-900/[0.04]'
                }`}
              >
                {tier.bestValue && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-white text-[9px] font-mono font-bold tracking-[0.2em] text-gray-900 shadow-lg whitespace-nowrap">
                    BEST VALUE
                  </div>
                )}

                <div className={`w-10 h-10 rounded-lg border flex items-center justify-center mb-5 ${tier.bestValue ? 'border-white/10 bg-white/10' : 'border-gray-200 bg-gray-50'}`}>
                  <tier.icon size={17} className={tier.bestValue ? 'text-white/70' : 'text-gray-600'} />
                </div>

                <div className={`font-bold text-sm tracking-wide ${tier.bestValue ? 'text-white' : 'text-gray-900'}`}>{tier.name}</div>
                <div className="mt-3 flex items-baseline gap-1.5">
                  <span className={`text-3xl font-display font-extrabold tracking-tight ${tier.bestValue ? 'text-white' : 'text-gray-900'}`}>{tier.price}</span>
                  {tier.price !== 'Custom' && <span className={`text-[10px] font-mono font-semibold ${tier.bestValue ? 'text-white/50' : 'text-gray-400'}`}>/MO</span>}
                </div>
                <div className={`text-[10px] font-mono mt-1 ${tier.bestValue ? 'text-white/50' : 'text-gray-400'}`}>{tier.period}</div>

                <div className={`mt-4 inline-flex self-start px-2.5 py-1 rounded-md border text-[10px] font-mono font-bold tracking-wider ${tier.bestValue ? 'border-white/10 bg-white/10 text-white/80' : 'border-gray-200 bg-gray-50 text-gray-700'}`}>
                  {tier.devices}
                </div>

                <p className={`mt-3 text-[12px] leading-relaxed ${tier.bestValue ? 'text-white/60' : 'text-gray-500'}`}>{tier.tagline}</p>

                <ul className="mt-5 space-y-2.5 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className={`flex gap-2.5 text-[12px] leading-relaxed ${tier.bestValue ? 'text-white/70' : 'text-gray-600'}`}>
                      <Check size={13} className={`${tier.bestValue ? 'text-white/50' : 'text-gray-400'} mt-0.5 shrink-0`} />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                {cta.href.startsWith('mailto:') ? (
                  <a
                    href={cta.href}
                    className={`group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider transition-all duration-200 ${
                      tier.bestValue
                        ? 'border border-white/20 text-white hover:bg-white/10'
                        : 'border border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300'
                    }`}
                  >
                    {cta.label}
                    <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                  </a>
                ) : (
                  <Link
                    href={cta.href}
                    className={`group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider transition-all duration-200 ${
                      cta.primary || tier.bestValue
                        ? 'bg-gray-900 text-white hover:bg-gray-800 shadow-lg shadow-gray-900/10'
                        : 'border border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300'
                    }`}
                  >
                    {cta.label}
                    <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                  </Link>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-10 max-w-3xl mx-auto space-y-3">
          <div className="flex items-start gap-2.5 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
            <Check size={14} className="text-gray-500 mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-gray-500">
              Yearly billing gives you <span className="text-gray-900 font-semibold">2 months free</span> — ₦5,000/year
              for Personal, ₦15,000/year for Guardian. Upgrade or cancel anytime.
            </p>
          </div>
          <div className="flex items-start gap-2.5 rounded-xl border border-gray-200 bg-white px-4 py-3">
            <Smartphone size={14} className="text-gray-500 mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-gray-500">
              Online payment is rolling out soon. Until then, upgrades are activated by our team after a bank
              transfer — email{' '}
              <a href="mailto:sales@magneetar.me" className="text-gray-900 font-semibold hover:underline transition-colors">
                sales@magneetar.me
              </a>{' '}
              and we&apos;ll switch your plan the same day.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
