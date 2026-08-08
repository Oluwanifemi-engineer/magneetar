'use client';

import { useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { useDevices } from '@/hooks/useDevices';
import { useWebSocket } from '@/hooks/useWebSocket';
import { ToastProvider } from '@/components/ui/Toast';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated } = useStore();

  // Mount the data layer ONCE for the whole dashboard: device list polling,
  // locations/commands/media refresh, and the real-time WebSocket stream.
  // Without these, the store stays empty — the sidebar shows "No devices",
  // the map has no markers, and the command panel can't send anything
  // (selectedDeviceId is never set).
  useDevices();
  useWebSocket();

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

  if (!isAuthenticated) {
    return (
      <div className="h-screen flex items-center justify-center bg-mag-bg relative overflow-hidden">
        {/* Ambient aurora + grid */}
        <div className="absolute -top-32 -left-32 w-[480px] h-[480px] rounded-full bg-mag-primary/[0.07] blur-[120px] animate-aurora pointer-events-none" />
        <div className="absolute -bottom-40 -right-32 w-[520px] h-[520px] rounded-full bg-cyan-500/[0.05] blur-[130px] animate-aurora pointer-events-none" style={{ animationDelay: '4s' }} />
        <div className="absolute inset-0 mag-grid-bg opacity-20" />

        <div className="text-center animate-fade-in relative z-10">
          {/* M Logo — magenta tile + white M (same brand mark as the launcher icon) */}
          <img
            src="/m-logo.svg"
            alt="Magneetar"
            className="w-14 h-14 mb-5 animate-m-glow drop-shadow-[0_0_30px_rgba(233,30,140,0.4)]"
          />
          <div className="text-xl font-display font-bold tracking-[0.3em] mb-3 text-gradient-primary">
            MAGNEETAR
          </div>
          <div className="flex items-center justify-center gap-2 text-mag-text-dim/50 text-[10px] font-mono font-bold">
            <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
            </svg>
            AUTHENTICATING...
          </div>
        </div>
      </div>
    );
  }

  return (
    <ToastProvider>
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Ambient aurora — same design language as the auth pages */}
      <div className="fixed -top-40 -left-40 w-[560px] h-[560px] rounded-full bg-mag-primary/[0.05] blur-[130px] animate-aurora pointer-events-none z-0" />
      <div className="fixed -bottom-48 -right-40 w-[600px] h-[600px] rounded-full bg-cyan-500/[0.04] blur-[140px] animate-aurora pointer-events-none z-0" style={{ animationDelay: '6s' }} />
      {/* Subtle background grid */}
      <div className="fixed inset-0 mag-grid-bg opacity-[0.03] pointer-events-none z-0" />

      <Header />
      <div className="flex flex-1 overflow-hidden relative z-10">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
    </ToastProvider>
  );
}
