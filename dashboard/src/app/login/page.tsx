'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';

export default function LoginPage() {
  const router = useRouter();
  const { setCredentials, setConnected } = useStore();

  const [serverUrl, setServerUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!serverUrl || !apiKey) {
      setError('Please enter server URL and API key.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const api = getAPI(serverUrl, apiKey);
      await api.healthCheck();

      // Store credentials
      sessionStorage.setItem('mt_server_url', serverUrl);
      sessionStorage.setItem('mt_api_key', apiKey);

      setCredentials(serverUrl, apiKey);
      setConnected(true);
      router.push('/dashboard');
    } catch (e: any) {
      setError(e.message || 'Connection failed. Check your server URL and API key.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-mag-bg mag-grid-bg relative overflow-hidden">
      {/* Background Effects */}
      <div className="absolute inset-0 bg-radial-glow pointer-events-none" />
      <div className="mag-scan-line" />

      {/* Login Card */}
      <div className="relative z-10 w-full max-w-md mx-4">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-mag-primary/10 border border-mag-primary/30 mb-4">
            <span className="text-mag-primary text-2xl font-bold">M</span>
          </div>
          <h1 className="font-display text-3xl font-bold tracking-[0.3em] text-mag-primary">
            MAGNEE<span className="text-mag-text-dim">TAR</span>
          </h1>
          <p className="text-mag-text-dim text-xs font-mono mt-2 tracking-widest uppercase">
            Tactical Command Center
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleConnect} className="mag-panel p-6 space-y-4">
          <div className="space-y-1">
            <label className="text-[10px] font-mono text-mag-text-dim uppercase tracking-widest">
              Server URL
            </label>
            <input
              type="text"
              value={serverUrl}
              onChange={(e) => setServerUrl(e.target.value)}
              placeholder="https://your-server.trycloudflare.com"
              className="mag-input"
              autoFocus
            />
          </div>

          <div className="space-y-1">
            <label className="text-[10px] font-mono text-mag-text-dim uppercase tracking-widest">
              API Key
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Enter your API key"
              className="mag-input"
            />
          </div>

          {error && (
            <div className="text-mag-danger text-xs font-mono bg-mag-danger/10 border border-mag-danger/30 rounded px-3 py-2">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mag-btn-primary w-full py-3 text-sm"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin">⟳</span> CONNECTING...
              </span>
            ) : (
              '🔗 CONNECT'
            )}
          </button>

          <div className="text-center">
            <span className="text-[10px] font-mono text-mag-text-dim/50">
              Secure connection • End-to-end encrypted
            </span>
          </div>
        </form>

        {/* Footer */}
        <div className="text-center mt-6">
          <span className="text-[10px] font-mono text-mag-text-dim/30">
            MAGNEETAR.ME • v1.0.0
          </span>
        </div>
      </div>
    </div>
  );
}
