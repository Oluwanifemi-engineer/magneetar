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
    <div className="h-screen flex items-center justify-center bg-white relative overflow-hidden">
      {/* Subtle grid background */}
      <div className="absolute inset-0 mag-grid-bg opacity-40" />

      {/* Center content */}
      <div className="text-center relative z-10">
        {/* Logo */}
        <img
          src="/magneetar-mhalf.svg"
          alt="Magneetar"
          className="w-20 h-20 rounded-2xl mb-8"
        />

        {/* Brand name */}
        <div className="text-2xl font-display font-bold tracking-[0.3em] mb-2 text-gray-900">
          MAGNEETAR
        </div>
        <div className="text-[10px] font-mono text-gray-400 tracking-[0.25em] mb-8">
          COMMAND CENTER
        </div>

        {/* Progress bar */}
        <div className="w-64 mx-auto mb-4">
          <div className="h-1 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-gray-900 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Status text */}
        <div className="flex items-center justify-center gap-2 text-gray-500 text-[11px] font-mono font-bold">
          <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          {status}
        </div>

        {/* Security badge */}
        <div className="mt-8 inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-200 bg-gray-50">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[9px] font-mono font-bold text-gray-400 tracking-wider">SECURE CHANNEL</span>
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
      {/* Subtle background grid — military feel */}
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
