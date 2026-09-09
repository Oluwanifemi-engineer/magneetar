'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import {
  Shield, Smartphone, MapPin, Radio,
  ArrowRight, Check, ChevronRight, Zap, X
} from 'lucide-react';

// Onboarding state management
const ONBOARDING_KEY = 'magneetar_onboarding_complete';

export function useOnboarding() {
  const [showOnboarding, setShowOnboarding] = useState(false);
  const { isConnected, devices } = useStore();

  useEffect(() => {
    // Check if onboarding was already completed
    const completed = localStorage.getItem(ONBOARDING_KEY);
    if (completed) return;

    // Show onboarding if no devices
    if (isConnected && devices.length === 0) {
      setShowOnboarding(true);
    }
  }, [isConnected, devices.length]);

  const completeOnboarding = useCallback(() => {
    localStorage.setItem(ONBOARDING_KEY, 'true');
    setShowOnboarding(false);
  }, []);

  const skipOnboarding = useCallback(() => {
    localStorage.setItem(ONBOARDING_KEY, 'true');
    setShowOnboarding(false);
  }, []);

  return { showOnboarding, completeOnboarding, skipOnboarding };
}

interface OnboardingStep {
  id: number;
  icon: typeof Shield;
  title: string;
  description: string;
  highlight?: string;
  color: string;
}

const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: 1,
    icon: Smartphone,
    title: 'Install Magneetar',
    description: 'Download the APK and install it on your Android device. Grant all permissions for full protection.',
    highlight: 'Takes less than 2 minutes',
    color: 'emerald',
  },
  {
    id: 2,
    icon: Shield,
    title: 'Activate theft detection',
    description: 'Theft detection learns your phone patterns and spots theft automatically. It runs silently in the background.',
    highlight: 'Zero battery impact',
    color: 'blue',
  },
  {
    id: 3,
    icon: MapPin,
    title: 'Protect Your Circle',
    description: 'Invite family and friends to share locations. Everyone stays safe together.',
    highlight: 'Unlimited members',
    color: 'purple',
  },
];

export function OnboardingFlow({
  onComplete,
  onSkip,
}: {
  onComplete: () => void;
  onSkip: () => void;
}) {
  const [currentStep, setCurrentStep] = useState(0);

  const step = ONBOARDING_STEPS[currentStep];
  const Icon = step.icon;
  const isLast = currentStep === ONBOARDING_STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-[9999] bg-gray-950 flex flex-col">
      {/* Close button */}
      <button
        onClick={onSkip}
        className="absolute top-4 right-4 z-10 w-10 h-10 flex items-center justify-center rounded-xl hover:bg-gray-800 transition-colors"
      >          <X size={20} className="text-mag-text-muted" />
      </button>

      {/* Progress dots */}
      <div className="flex justify-center gap-2 pt-8">
        {ONBOARDING_STEPS.map((s, i) => (
          <div
            key={s.id}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === currentStep
                ? 'w-8 bg-emerald-500'
                : i < currentStep
                  ? 'w-1.5 bg-emerald-500/50'
                  : 'w-1.5 bg-gray-700'
            }`}
          />
        ))}
      </div>

      {/* Step content */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 text-center max-w-md mx-auto">
        {/* Icon */}
        <div className={`w-20 h-20 rounded-2xl flex items-center justify-center mb-8 animate-fade-in bg-${step.color}-500/10 border border-${step.color}-500/20`}>
          <Icon size={32} className={`text-${step.color}-400`} />
        </div>

        {/* Title */}
        <h2 className="text-2xl font-bold text-white mb-3 animate-fade-in">
          {step.title}
        </h2>

        {/* Description */}          <p className="text-mag-text-muted text-base leading-relaxed mb-4 animate-fade-in">
          {step.description}
        </p>

        {/* Highlight badge */}
        {step.highlight && (
          <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-8 animate-fade-in">
            <Zap size={12} className="text-emerald-400" />
            <span className="text-[11px] font-mono font-bold text-emerald-400 uppercase tracking-wider">
              {step.highlight}
            </span>
          </div>
        )}
      </div>

      {/* Bottom actions */}
      <div className="px-6 pb-8 max-w-md mx-auto w-full">
        {/* Continue button */}
        <button
          onClick={() => {
            if (isLast) {
              onComplete();
            } else {
              setCurrentStep(currentStep + 1);
            }
          }}
          className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl bg-white text-gray-950 font-bold text-sm transition-all duration-200 hover:bg-gray-100 active:scale-[0.98]"
        >
          {isLast ? (
            <>
              Get Started
              <ArrowRight size={16} />
            </>
          ) : (
            <>
              Continue
              <ChevronRight size={16} />
            </>
          )}
        </button>

        {/* Skip link */}
        {!isLast && (
          <button
            onClick={onSkip}              className="w-full py-3 text-mag-text-muted text-sm font-bold hover:text-mag-text transition-colors"
          >
            Skip for now
          </button>
        )}
      </div>
    </div>
  );
}
