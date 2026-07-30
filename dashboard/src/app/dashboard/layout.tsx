'use client';

import { useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated } = useStore();

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
        {/* Grid effect */}
        <div className="absolute inset-0 mag-grid-bg opacity-20" />

        <div className="text-center animate-fade-in relative z-10">
          {/* M Logo */}
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl border border-white/[0.06] bg-white/[0.02] mb-5 animate-m-glow">
            <svg viewBox="0 0 120 120" className="w-8 h-8" fill="none">
              <path d="M24 88L24 32L48 60L60 44L72 60L96 32L96 88"
                    stroke="white" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div className="text-mag-text text-xl font-display font-bold tracking-[0.3em] mb-3">
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
    <div className="h-screen flex flex-col overflow-hidden">
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
  );
}
