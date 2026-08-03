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
    <section id="pricing" className="relative py-24 sm:py-32 scroll-mt-20 overflow-hidden">
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute top-24 left-0 w-[420px] h-[420px] rounded-full bg-[#E91E8C]/6 blur-[120px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="max-w-2xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <Crown size={12} className="text-[#06B6D4]" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">PRICING</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white leading-tight">
            Protection that scales with
            <br />
            <span className="text-gradient-primary">your family &amp; team.</span>
          </h2>
          <p className="mt-5 text-white/45 leading-relaxed">
            Every plan includes every feature — theft detection, live tracking, evidence capture, the
            whole command center. The only difference is how many devices you protect.
          </p>
        </div>

        {/* Tier cards */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {TIERS.map((tier) => {
            // Signed-in users don't get signup CTAs — they already have an
            // account, so plan cards route them to the command center.
            const cta = authed && tier.cta.href === '/signup'
              ? { label: 'Open Command Center', href: '/dashboard', primary: true }
              : tier.cta;
            return (
            <div
              key={tier.name}
              className={`relative flex flex-col rounded-2xl border p-7 card-glow transition-all duration-300 hover:-translate-y-1 ${
                tier.bestValue
                  ? 'border-[#06B6D4]/30 bg-gradient-to-b from-[#06B6D4]/[0.08] to-[#0d0d14]/90'
                  : 'border-white/[0.07] bg-[#0d0d14]/80 backdrop-blur-xl hover:border-white/[0.15]'
              }`}
            >
              {tier.bestValue && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-[9px] font-mono font-bold tracking-[0.2em] text-white shadow-lg shadow-black/40 whitespace-nowrap">
                  BEST VALUE
                </div>
              )}

              <div className="w-10 h-10 rounded-lg border border-white/[0.08] bg-white/[0.03] flex items-center justify-center mb-5">
                <tier.icon size={17} className="text-[#06B6D4]" />
              </div>

              <div className="text-white font-bold text-sm tracking-wide">{tier.name}</div>
              <div className="mt-3 flex items-baseline gap-1.5">
                <span className="text-3xl font-display font-extrabold tracking-tight text-white">{tier.price}</span>
                {tier.price !== 'Custom' && <span className="text-[10px] font-mono text-white/35 font-semibold">/MO</span>}
              </div>
              <div className="text-[10px] font-mono text-white/35 mt-1">{tier.period}</div>

              <div className="mt-4 inline-flex self-start px-2.5 py-1 rounded-md border border-white/[0.08] bg-white/[0.03] text-[10px] font-mono font-bold text-white/70 tracking-wider">
                {tier.devices}
              </div>

              <p className="mt-3 text-[12px] text-white/40 leading-relaxed">{tier.tagline}</p>

              <ul className="mt-5 space-y-2.5 flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2.5 text-[12px] leading-relaxed text-white/55">
                    <Check size={13} className="text-emerald-400 mt-0.5 shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              {cta.href.startsWith('mailto:') ? (
                <a
                  href={cta.href}
                  className="group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider border border-white/12 text-white/70 hover:text-white hover:bg-white/[0.05] hover:border-white/25 transition-all duration-200 active:scale-[0.97]"
                >
                  {cta.label}
                  <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                </a>
              ) : (
                <Link
                  href={cta.href}
                  className={`group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider transition-all duration-200 active:scale-[0.97] ${
                    cta.primary
                      ? 'bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-lg shadow-[#E91E8C]/20 hover:shadow-[#E91E8C]/40 hover:brightness-110'
                      : 'border border-white/12 text-white/70 hover:text-white hover:bg-white/[0.05] hover:border-white/25'
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

        {/* Notes */}
        <div className="mt-10 max-w-3xl mx-auto space-y-3">
          <div className="flex items-start gap-2.5 rounded-xl border border-emerald-500/15 bg-emerald-500/[0.04] px-4 py-3">
            <Check size={14} className="text-emerald-400 mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-white/50">
              Yearly billing gives you <span className="text-white font-semibold">2 months free</span> — ₦5,000/year
              for Personal, ₦15,000/year for Guardian. Upgrade or cancel anytime.
            </p>
          </div>
          <div className="flex items-start gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
            <Smartphone size={14} className="text-[#06B6D4] mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-white/45">
              Online payment is rolling out soon. Until then, upgrades are activated by our team after a bank
              transfer — email{' '}
              <a href="mailto:sales@magneetar.me" className="text-[#06B6D4] hover:text-[#22D3EE] font-semibold transition-colors">
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
