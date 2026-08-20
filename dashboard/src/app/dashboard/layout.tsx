'use client';

import { useEffect, useState } from 'react';
import { useStore } from '@/store/useStore';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { useDevices } from '@/hooks/useDevices';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ToastProvider } from '@/components/ui/Toast';
import { KeyboardShortcutsHelp } from '@/components/ui/KeyboardShortcuts';
import { OnboardingFlow, useOnboarding } from '@/components/onboarding/OnboardingFlow';
import { useRouter } from 'next/navigation';

function PremiumLoadingScreen() {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('Initializing...');

  useEffect(() => {
    const steps = [
      { progress: 20, status: 'Connecting to server...' },
      { progress: 40, status: 'Authenticating...' },
      { progress: 60, status: 'Loading devices...' },
      { progress: 80, status: 'Establishing secure channel...' },
      { progress: 95, status: 'Almost ready...' },
    ];

    let currentStep = 0;
    const interval = setInterval(() => {
      if (currentStep < steps.length) {
        setProgress(steps[currentStep].progress);
        setStatus(steps[currentStep].status);
        currentStep++;
      }
    }, 400);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="h-screen flex items-center justify-center bg-mag-bg relative overflow-hidden">
      {/* Ambient aurora effects */}
      <div className="absolute -top-32 -left-32 w-[480px] h-[480px] rounded-full bg-mag-primary/[0.07] blur-[120px] animate-aurora pointer-events-none" />
      <div className="absolute -bottom-40 -right-32 w-[520px] h-[520px] rounded-full bg-mag-secondary/[0.05] blur-[130px] animate-aurora pointer-events-none" style={{ animationDelay: '4s' }} />
      <div className="absolute inset-0 mag-grid-bg opacity-20" />

      {/* Center content */}
      <div className="text-center relative z-10">
        {/* Logo */}
        <img
          src="/magneetar-mhalf.svg"
          alt="Magneetar"
          className="w-20 h-20 rounded-2xl mb-8"
        />

        {/* Brand name */}
        <div className="text-2xl font-display font-bold tracking-[0.3em] mb-2 text-white">
          MAGNEETAR
        </div>
        <div className="text-[10px] font-mono text-white/40 tracking-[0.25em] mb-8">
          COMMAND CENTER
        </div>

        {/* Progress bar */}
        <div className="w-64 mx-auto mb-4">
          <div className="h-1 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-mag-primary to-mag-secondary rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Status text */}
        <div className="flex items-center justify-center gap-2 text-white/50 text-[11px] font-mono font-bold">
          <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          {status}
        </div>

        {/* Security badge */}
        <div className="mt-8 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/10 bg-white/[0.03]">
          <div className="w-1.5 h-1.5 rounded-full bg-mag-primary animate-pulse" />
          <span className="text-[9px] font-mono font-bold text-white/40 tracking-wider">SECURE CHANNEL</span>
        </div>
      </div>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated } = useStore();
  const [mounted, setMounted] = useState(false);
  const { showOnboarding, completeOnboarding, skipOnboarding } = useOnboarding();
  const router = useRouter();

  // Mount the data layer ONCE for the whole dashboard: device list polling,
  // locations/commands/media refresh, and the real-time WebSocket stream.
  // Without these, the store stays empty — the sidebar shows "No devices",
  // the map has no markers, and the command panel can't send anything
  // (selectedDeviceId is never set).
  useDevices();
  useWebSocket();

  useEffect(() => {
    setMounted(true);
  }, []);

  // Check auth on mount
  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');

    if (!serverUrl || !apiKey) {
      window.location.href = '/login';
      return;
    }

    // Restore credentials from sessionStorage
    if (!isAuthenticated) {
      useStore.getState().setCredentials(serverUrl, apiKey);
      useStore.getState().setConnected(true);
    }
  }, [isAuthenticated]);

  if (!isAuthenticated || !mounted) {
    return <PremiumLoadingScreen />;
  }

  return (
    <ToastProvider>
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Ambient aurora — same design language as the auth pages */}
      <div className="fixed -top-40 -left-40 w-[560px] h-[560px] rounded-full bg-mag-primary/[0.05] blur-[130px] animate-aurora pointer-events-none z-0" />
      <div className="fixed -bottom-48 -right-40 w-[600px] h-[600px] rounded-full bg-mag-secondary/[0.04] blur-[140px] animate-aurora pointer-events-none z-0" style={{ animationDelay: '6s' }} />
      {/* Subtle background grid */}
      <div className="fixed inset-0 mag-grid-bg opacity-[0.03] pointer-events-none z-0" />

      <Header />
      <div className="flex flex-1 overflow-hidden relative z-10">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>

      {/* Keyboard shortcuts help */}
      <KeyboardShortcutsHelp />

      {/* Onboarding flow for new users */}
      {showOnboarding && (
        <OnboardingFlow
          onComplete={completeOnboarding}
          onSkip={skipOnboarding}
        />
      )}
    </div>
    </ToastProvider>
  );
}
