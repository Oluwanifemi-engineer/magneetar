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
      <div className="h-screen flex items-center justify-center bg-mag-bg mag-grid-bg">
        <div className="text-center animate-fade-in">
          <div className="text-mag-text text-2xl font-display font-bold tracking-[0.3em] mb-4">
            MAGNEETAR
          </div>
          <div className="flex items-center justify-center gap-2 text-mag-text-dim/60 text-xs font-mono">
            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
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
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}
