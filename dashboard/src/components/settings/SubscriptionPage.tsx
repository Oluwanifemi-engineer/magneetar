'use client';

import { useState, useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { Check, Crown, Shield, Building2, CreditCard, ExternalLink } from 'lucide-react';

/**
 * SubscriptionPage — shows current plan, upgrade options, and billing.
 * Embedded in the Settings modal.
 */

interface SubscriptionData {
  plan: string;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  tier: string;
}

const PLANS = [
  {
    id: 'free',
    name: 'Free',
    price: '₦0',
    period: 'forever',
    icon: Shield,
    color: 'gray',
    maxDevices: 1,
    features: [
      '1 device',
      '5-minute location updates',
      'Basic security score',
      'Community watch (read-only)',
      '7-day location history',
    ],
  },
  {
    id: 'personal',
    name: 'Personal',
    price: '₦1,500',
    period: '/month',
    yearlyPrice: '₦15,000/year',
    icon: Crown,
    color: 'emerald',
    maxDevices: 3,
    popular: true,
    features: [
      '3 devices',
      '3-second real-time tracking',
      'Panic Button + SOS',
      'Geofencing',
      'Remote Lock + Evidence',
      'Device Health Monitor',
      '90-day location history',
    ],
  },
  {
    id: 'family',
    name: 'Family',
    price: '₦3,000',
    period: '/month',
    yearlyPrice: '₦30,000/year',
    icon: Building2,
    color: 'violet',
    maxDevices: 10,
    features: [
      '10 devices',
      'Everything in Personal',
      'Unlimited family members',
      'Digital Inheritance',
      'AI Theft Prediction',
      'Gift a Subscription',
      'Priority support',
      '365-day location history',
    ],
  },
];

export function SubscriptionPage() {
  const { serverUrl, apiKey } = useStore();
  const [subscription, setSubscription] = useState<SubscriptionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'yearly'>('monthly');

  useEffect(() => {
    fetchSubscription();
  }, []);

  const fetchSubscription = async () => {
    setSubscription({ plan: 'free', status: 'inactive', tier: 'free', current_period_start: null, current_period_end: null });
    setLoading(false);
  };

  const handleUpgrade = (planId: string) => {
    window.location.href = 'mailto:sales@magneetar.me?subject=Upgrade to ' + planId;
  };

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <div className="h-6 bg-mag-surface rounded animate-pulse w-1/3" />
        <div className="h-32 bg-mag-surface/50 rounded-lg animate-pulse" />
      </div>
    );
  }

  const currentTier = subscription?.tier || 'free';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-lg font-display font-bold text-mag-text">Subscription</h2>
        <p className="text-xs text-mag-text-muted mt-1">
          Manage your plan and billing
        </p>
      </div>

      {/* Current Plan */}
      <div className="p-4 rounded-xl border border-mag-border bg-mag-surface">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs font-mono text-mag-text-muted uppercase tracking-wider font-bold">
              Current Plan
            </div>
            <div className="text-sm font-bold text-mag-text mt-1 capitalize">
              {currentTier}
            </div>
          </div>
          {subscription?.current_period_end && (
            <div className="text-right">
              <div className="text-[10px] font-mono text-mag-text-muted">Renews</div>
              <div className="text-xs font-mono text-mag-text">
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Billing Toggle */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setBillingCycle('monthly')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold transition-all ${
            billingCycle === 'monthly'
              ? 'bg-mag-surface-raised text-mag-text'
              : 'bg-mag-surface text-mag-text-muted hover:bg-mag-surface-raised'
          }`}
        >
          Monthly
        </button>
        <button
          onClick={() => setBillingCycle('yearly')}
          className={`px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold transition-all ${
            billingCycle === 'yearly'
              ? 'bg-mag-surface-raised text-mag-text'
              : 'bg-mag-surface text-mag-text-muted hover:bg-mag-surface-raised'
          }`}
        >
          Yearly
          <span className="ml-1 text-emerald-400">Save 17%</span>
        </button>
      </div>

      {/* Plans */}
      <div className="space-y-4">
        {PLANS.map((plan) => {
          const Icon = plan.icon;
          const isCurrent = currentTier === plan.id;
          const isUpgrade = PLANS.findIndex(p => p.id === plan.id) > PLANS.findIndex(p => p.id === currentTier);

          return (
            <div
              key={plan.id}
              className={`relative p-4 rounded-xl border transition-all ${
                isCurrent
                  ? 'border-mag-border bg-mag-surface text-mag-text'
                  : 'border-mag-border bg-mag-surface/50 hover:border-mag-border/50'
              }`}
            >
              {plan.popular && !isCurrent && (
                <div className="absolute -top-2 left-1/2 -translate-x-1/2 px-2 py-0.5 rounded-full bg-emerald-500 text-[8px] font-mono font-bold text-white">
                  POPULAR
                </div>
              )}

              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                    isCurrent ? 'bg-mag-primary/10' : 'bg-mag-surface'
                  }`}>
                    <Icon size={18} className={isCurrent ? 'text-mag-text' : 'text-mag-text-muted'} />
                  </div>
                  <div>
                    <div className={`text-sm font-bold ${isCurrent ? 'text-mag-text' : 'text-mag-text'}`}>
                      {plan.name}
                    </div>
                    <div className="flex items-baseline gap-1">
                      <span className={`text-xl font-display font-extrabold ${isCurrent ? 'text-mag-text' : 'text-mag-text'}`}>
                        {billingCycle === 'yearly' && plan.yearlyPrice
                          ? `₦${parseInt(plan.yearlyPrice.replace(/[₦,]/g, '')) / 12}`
                          : plan.price}
                      </span>
                      <span className={`text-[10px] font-mono ${isCurrent ? 'text-mag-text-muted' : 'text-mag-text-muted'}`}>
                        {billingCycle === 'yearly' ? '/month (billed yearly)' : plan.period}
                      </span>
                    </div>
                  </div>
                </div>

                {!isCurrent && isUpgrade && (
                  <button
                    onClick={() => handleUpgrade(plan.id)}
                    className="px-3 py-1.5 rounded-lg bg-mag-primary hover:bg-mag-primary-dim text-white text-[10px] font-bold transition-colors"
                  >
                    Upgrade
                  </button>
                )}

                {isCurrent && (
                  <span className="px-2 py-1 rounded-lg bg-mag-primary/10 text-[10px] font-mono font-bold text-mag-text-muted">
                    CURRENT
                  </span>
                )}
              </div>

              <ul className="mt-4 space-y-1.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2">
                    <Check size={12} className={isCurrent ? 'text-emerald-400' : 'text-emerald-500'} />
                    <span className={`text-[11px] ${isCurrent ? 'text-mag-text-muted' : 'text-mag-text-muted'}`}>
                      {feature}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      {/* Payment Method */}
      <div className="p-4 rounded-xl border border-mag-border bg-mag-surface">
        <div className="flex items-center gap-2 mb-2">
          <CreditCard size={14} className="text-mag-text-muted" />
          <span className="text-xs font-bold text-mag-text">Payment</span>
        </div>
        <p className="text-[10px] text-mag-text-muted leading-relaxed">
          Payments are processed securely via Paystack. We accept all Nigerian debit cards,
          bank transfers, and USSD. You can cancel anytime from this page.
        </p>
      </div>
    </div>
  );
}
