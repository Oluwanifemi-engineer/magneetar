'use client';

import { useEffect, useState } from 'react';
import { useStore } from '@/store/useStore';
import { Sidebar } from '@/components/layout/Sidebar';
import { useDevices } from '@/hooks/useDevices';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ToastProvider } from '@/components/ui/Toast';
import { ThemeProvider } from '@/components/ui/DarkMode';
import { KeyboardShortcutsHelp } from '@/components/ui/KeyboardShortcuts';
import { PwaInstallPrompt } from '@/components/ui/PwaInstallPrompt';
import { OnboardingFlow, useOnboarding } from '@/components/onboarding/OnboardingFlow';

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
      <div className="absolute inset-0 mag-grid-bg opacity-[0.03]" />
      <div className="text-center relative z-10 flex flex-col items-center justify-center">
        <img src="/magneetar-mhalf.svg" alt="Magneetar" className="w-28 h-28 rounded-3xl mb-6" />
        <div className="text-2xl font-display font-bold tracking-[0.3em] mb-2 text-mag-text">MAGNEETAR</div>
        <div className="text-[10px] font-mono text-mag-text-muted tracking-[0.25em] mb-10">COMMAND CENTER</div>
        <div className="w-64 mx-auto mb-4">
          <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(31,41,55,0.6)' }}>
            <div
              className="h-full bg-emerald-500 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 text-mag-text-muted text-[10px] font-mono font-bold">
          <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          {status}
        </div>
        <div className="mt-8 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-mag-border bg-mag-surface/40">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[9px] font-mono text-mag-text-muted font-bold uppercase tracking-wider">SECURE CHANNEL</span>
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

  useDevices();
  useWebSocket();

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');

    if (!serverUrl || !apiKey) {
      window.location.href = '/login';
      return;
    }

    if (!isAuthenticated) {
      useStore.getState().setCredentials(serverUrl, apiKey);
      useStore.getState().setConnected(true);
    }
  }, [isAuthenticated]);

  if (!isAuthenticated || !mounted) {
    return <PremiumLoadingScreen />;
  }

  return (
    <ThemeProvider>
    <ToastProvider>
    <div className="h-screen flex overflow-hidden bg-mag-bg">
      <div className="fixed inset-0 mag-grid-bg opacity-[0.02] pointer-events-none z-0" />
      <div className="hidden md:block"><Sidebar /></div>
      <main className="flex-1 overflow-hidden relative z-10">
        {children}
      </main>
      <KeyboardShortcutsHelp />
      <PwaInstallPrompt />
      {showOnboarding && (
        <OnboardingFlow onComplete={completeOnboarding} onSkip={skipOnboarding} />
      )}
    </div>
    </ToastProvider>
    </ThemeProvider>
  );
}
