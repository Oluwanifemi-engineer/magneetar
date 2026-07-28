'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    // Check if credentials exist in sessionStorage
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');

    if (serverUrl && apiKey) {
      router.replace('/dashboard');
    } else {
      router.replace('/login');
    }
  }, [router]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-mag-bg">
      <div className="text-center">
        <div className="text-mag-text text-2xl font-display font-bold tracking-[0.3em] mb-4">
          MAGNEETAR
        </div>
        <div className="text-mag-text-dim text-xs font-mono animate-pulse">
          INITIALIZING...
        </div>
      </div>
    </div>
  );
}
