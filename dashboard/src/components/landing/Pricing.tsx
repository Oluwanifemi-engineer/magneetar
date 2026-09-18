'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { Check, Crown, Smartphone, Users, ShieldCheck, Building2, ArrowRight, ExternalLink } from 'lucide-react';


const TIERS = [
  {
    icon: Smartphone,
    name: 'Free',
    price: '₦0',
    period: 'free forever',
    devices: '1 device',
    tagline: 'Protect your main phone.',
    plan: null,
    features: [
      'Full theft detection',
      'Live tracking + route to device',
      'Evidence capture (photo & audio)',
      'Family & team circles',
      'Device sharing with others',
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
    plan: 'personal_monthly',
    yearlyPlan: 'personal_yearly',
    yearlyPrice: '₦5,000',
    yearlyPeriod: 'per year',
    features: [
      'Everything in Free',
      'Protect up to 3 devices on one account',
      'Family & coworker circles',
      'Priority alert delivery',
    ],
    cta: { label: 'Upgrade', href: '/signup', primary: false },
  },
  {
    icon: ShieldCheck,
    name: 'Guardian',
    price: '₦1,500',
    period: 'per month · or ₦15,000/year',
    devices: 'Up to 10 devices',
    tagline: 'The whole family — or a small business.',
    plan: 'guardian_monthly',
    yearlyPlan: 'guardian_yearly',
    yearlyPrice: '₦15,000',
    yearlyPeriod: 'per year',
    features: [
      'Everything in Personal',
      'Protect up to 10 devices',
      'Whole-fleet command center',
      'Multi-owner team access',
    ],
    cta: { label: 'Upgrade', href: '/signup', primary: false },
    bestValue: true,
  },
  {
    icon: Building2,
    name: 'Enterprise',
    price: 'Custom',
    period: 'tailored to your organisation',
    devices: 'Unlimited devices',
    tagline: 'Fleets, schools, and security teams.',
    plan: null,
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
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');

  const handleUpgrade = (tier: typeof TIERS[0]) => {
    if (!tier.plan) return;
    if (!authed) {
      window.location.href = '/signup';
      return;
    }
    window.location.href = 'mailto:sales@magneetar.me?subject=Upgrade to ' + tier.name;
  };

  return (
    <section id="pricing" className="relative py-28 sm:py-36 scroll-mt-20 overflow-hidden bg-gradient-to-b from-gray-950 via-[#060a10] to-gray-950">
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-2xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 mb-5">
            <Crown size={12} className="text-emerald-400" />
            <span className="text-[11px] font-mono font-bold tracking-[0.2em] text-emerald-400/80">PRICING</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
            Protection that scales with
            <br />
            <span className="bg-gradient-to-r from-gray-400 to-gray-500 bg-clip-text text-transparent">your family &amp; team.</span>
          </h2>
          <p className="mt-5 text-mag-text-muted leading-relaxed">
            Every plan includes every feature — theft detection, live tracking, evidence capture, the
            whole command center. The only difference is how many devices you protect.
          </p>

          {/* Billing toggle */}
          <div className="mt-6 inline-flex items-center gap-1 p-1 rounded-xl bg-mag-surface border-mag-border">
            <button
              onClick={() => setBillingCycle('monthly')}
              className={`px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wider transition-all ${
                billingCycle === 'monthly'
                  ? 'bg-mag-surface-raised text-mag-text'
                  : 'text-mag-text-muted hover:text-mag-text'
              }`}
            >
              MONTHLY
            </button>
            <button
              onClick={() => setBillingCycle('yearly')}
              className={`px-4 py-2 rounded-lg text-[11px] font-mono font-bold tracking-wider transition-all ${
                billingCycle === 'yearly'
                  ? 'bg-mag-surface-raised text-mag-text'
                  : 'text-mag-text-muted hover:text-mag-text'
              }`}
            >
              YEARLY
              <span className="ml-1 text-emerald-400 text-[11px]">SAVE 2MO</span>
            </button>
          </div>
        </div>



        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {TIERS.map((tier) => {
            const isYearly = billingCycle === 'yearly' && tier.yearlyPlan;
            const displayPrice = isYearly ? tier.yearlyPrice : tier.price;
            const displayPeriod = isYearly ? tier.yearlyPeriod : tier.period;
            const isPaid = tier.plan && tier.plan !== null;
            const isFree = tier.name === 'Free';
            const isEnterprise = tier.name === 'Enterprise';

            return (
              <div
                key={tier.name}
                className={`relative flex flex-col rounded-2xl border p-7 transition-all duration-400 hover:-translate-y-1 ${
                  tier.bestValue
                    ? 'border-emerald-500/30 bg-gradient-to-b from-emerald-500/8 to-transparent shadow-glow-sm'
                    : 'border-mag-border bg-gradient-to-b from-mag-surface to-mag-bg hover:border-mag-border/50'
                }`}
              >
                {tier.bestValue && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-emerald-500 text-[11px] font-mono font-bold tracking-[0.2em] text-white shadow-glow-md whitespace-nowrap">
                    BEST VALUE
                  </div>
                )}

                <div className={`w-10 h-10 rounded-lg border flex items-center justify-center mb-5 ${
                  tier.bestValue ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-mag-border bg-mag-surface'
                }`}>
                  <tier.icon size={17} className={tier.bestValue ? 'text-emerald-400' : 'text-mag-text-muted'} />
                </div>                 <div className={`font-bold text-sm tracking-wide ${tier.bestValue ? 'text-white' : 'text-mag-text-muted'}`}>
                  {tier.name}
                </div>
                <div className="mt-3 flex items-baseline gap-1.5">
                  <span className="text-3xl font-display font-extrabold tracking-tight text-white">{displayPrice}</span>
                  {displayPrice !== 'Custom' && displayPrice !== '₦0' && (
                    <span className={`text-[11px] font-mono font-semibold ${tier.bestValue ? 'text-emerald-400/60' : 'text-mag-text-muted'}`}>
                      {isYearly ? '/YEAR' : '/MO'}
                    </span>
                  )}
                </div>
                <div className={`text-[11px] font-mono mt-1 ${tier.bestValue ? 'text-emerald-400/40' : 'text-mag-text-muted'}`}>{displayPeriod}</div>

                <div className={`mt-4 inline-flex self-start px-2.5 py-1 rounded-md border text-[11px] font-mono font-bold tracking-wider ${
                  tier.bestValue ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border-mag-border/50 bg-mag-surface text-mag-text-muted'
                }`}>
                  {tier.devices}
                </div>

                <p className={`mt-3 text-[12px] leading-relaxed ${tier.bestValue ? 'text-mag-text-dim' : 'text-mag-text-muted'}`}>{tier.tagline}</p>

                <ul className="mt-5 space-y-2.5 flex-1">
                  {tier.features.map((f) => (
                    <li key={f} className={`flex gap-2.5 text-[12px] leading-relaxed ${tier.bestValue ? 'text-mag-text-dim' : 'text-mag-text-muted'}`}>
                      <Check size={13} className={`${tier.bestValue ? 'text-emerald-400/60' : 'text-mag-text-muted'} mt-0.5 shrink-0`} />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                {/* CTA Button */}
                {isEnterprise ? (
                  <a
                    href={tier.cta.href}
                    className="group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider border-mag-border/50 text-mag-text-muted hover:bg-mag-surface hover:border-mag-border hover:text-mag-text transition-all duration-300"
                  >
                    {tier.cta.label}
                    <ExternalLink size={11} className="opacity-50" />
                  </a>
                ) : isFree ? (
                  authed ? (
                    <Link
                      href="/dashboard"
                      className="group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider border-mag-border/50 text-mag-text-muted hover:bg-mag-surface hover:border-mag-border hover:text-mag-text transition-all duration-300"
                    >
                      Current Plan
                    </Link>
                  ) : (
                    <Link
                      href="/signup"
                      className="group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider bg-emerald-500 text-white hover:bg-emerald-400 shadow-glow-md hover:shadow-glow-lg transition-all duration-300"
                    >
                      Get Started Free
                      <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                    </Link>
                  )
                ) : (
                  <button
                    onClick={() => handleUpgrade(tier)}
                    className={`group mt-7 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[11px] font-bold uppercase tracking-wider transition-all duration-300 w-full ${
                      tier.bestValue
                        ? 'bg-emerald-500 text-white hover:bg-emerald-400 shadow-glow-md hover:shadow-glow-lg'
                        : 'border-mag-border/50 text-mag-text-muted hover:bg-mag-surface hover:border-mag-border hover:text-mag-text'
                    }`}
                  >
                    {authed ? 'Upgrade Now' : 'Get Started'}
                    <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        <div className="mt-10 max-w-3xl mx-auto space-y-3">
          <div className="flex items-start gap-2.5 rounded-xl border-mag-border/50 bg-mag-surface px-4 py-3">
            <Check size={14} className="text-emerald-400 mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-mag-text-muted">
              Yearly billing gives you <span className="text-mag-text font-semibold">2 months free</span> — ₦5,000/year
              for Personal, ₦15,000/year for Guardian. Upgrade or cancel anytime.
            </p>
          </div>
          <div className="flex items-start gap-2.5 rounded-xl border-mag-border/50 bg-mag-surface px-4 py-3">
            <Smartphone size={14} className="text-mag-text-muted mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-mag-text-muted">
              Payments are processed securely via{' '}
              <span className="text-mag-text font-semibold">Paystack</span> — Nigeria&apos;s leading payment gateway.
              We never see or store your card details.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
