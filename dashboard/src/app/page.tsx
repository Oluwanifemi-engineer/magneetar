'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');

    if (serverUrl && apiKey) {
      router.replace('/dashboard');
    } else {
      router.replace('/login');
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-mag-bg relative overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0 mag-grid-bg opacity-30" />
      {/* Scan line */}
      <div className="absolute left-1/4 right-1/4 h-px bg-gradient-to-r from-transparent via-white/[0.03] to-transparent animate-scan-line pointer-events-none" />
      
      <div className="text-center relative z-10 animate-fade-slide">
        {/* M Logo */}
        <div className="inline-flex items-center justify-center mb-6">
          <img src="/m-logo.svg" alt="M" className="w-16 h-16" />
        </div>
        
        <div className="text-mag-text text-2xl font-display font-bold tracking-[0.3em] mb-2">
          MAGNEETAR
        </div>
        <div className="text-mag-text-dim/40 text-[10px] font-mono tracking-[0.4em] uppercase font-bold">
          Tactical Command Center
        </div>
        <div className="mt-8 flex items-center justify-center gap-3">
          <div className="w-2 h-2 rounded-full bg-mag-accent/60 animate-pulse-slow" />
          <span className="text-mag-text-dim/40 text-xs font-mono animate-pulse">
            INITIALIZING...
          </span>
        </div>
      </div>
    </div>
  );
}
