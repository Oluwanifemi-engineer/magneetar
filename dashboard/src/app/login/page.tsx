'use client';

import { useState, useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';

type LoginMode = 'account' | 'apikey';

export default function LoginPage() {
  const { setCredentials, setConnected } = useStore();

  const [mode, setMode] = useState<LoginMode>('account');
  const [serverUrl, setServerUrl] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!serverUrl) {
      setError('Please enter your server URL.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const api = getAPI(serverUrl);

      if (mode === 'account') {
        if (!email || !password) {
          setError('Please enter your email and password.');
          setLoading(false);
          return;
        }
        // User login with email/password
        const res = await fetch(`${serverUrl}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Login failed' }));
          throw new Error(err.detail || 'Invalid credentials');
        }
        const data = await res.json();
        sessionStorage.setItem('mt_server_url', serverUrl);
        sessionStorage.setItem('mt_api_key', data.token);
        sessionStorage.setItem('mt_refresh_token', data.refresh_token);
        sessionStorage.setItem('mt_auth_mode', 'user');
        setCredentials(serverUrl, data.token);
        setConnected(true);
      } else {
        // API key login (backward compat)
        if (!apiKey) {
          setError('Please enter your API key.');
          setLoading(false);
          return;
        }
        await api.healthCheck();
        sessionStorage.setItem('mt_server_url', serverUrl);
        sessionStorage.setItem('mt_api_key', apiKey);
        sessionStorage.setItem('mt_auth_mode', 'apikey');
        setCredentials(serverUrl, apiKey);
        setConnected(true);
      }

      window.location.href = '/dashboard';
    } catch (e: any) {
      setError(e.message || 'Connection failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 login-grid opacity-40" />
      <div className="absolute inset-0 pointer-events-none login-scanlines" />
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.7) 100%)' }} />

      {/* HUD corners */}
      <div className="absolute top-8 left-8 w-12 h-12 border-l-2 border-t-2 border-white/10 rounded-tl-sm" />
      <div className="absolute top-8 right-8 w-12 h-12 border-r-2 border-t-2 border-white/10 rounded-tr-sm" />
      <div className="absolute bottom-8 left-8 w-12 h-12 border-l-2 border-b-2 border-white/10 rounded-bl-sm" />
      <div className="absolute bottom-8 right-8 w-12 h-12 border-r-2 border-b-2 border-white/10 rounded-br-sm" />

      {/* Status bars */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      <div className="absolute top-3 left-0 right-0 flex justify-between px-10">
        <span className="text-[10px] font-mono text-white/20 tracking-[0.3em] uppercase">System Online</span>
        <span className="text-[10px] font-mono text-white/20 tracking-[0.3em] uppercase">v1.0.0</span>
      </div>

      <div className={`relative z-10 w-full max-w-md mx-6 transition-all duration-700 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
        {/* Logo */}
        <div className="text-center mb-10">
          <div className={`transition-all duration-1000 delay-200 ${mounted ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}`}>
            <img src="/logo.svg" alt="Magneetar" className="h-16 mx-auto mb-6 drop-shadow-[0_0_30px_rgba(255,255,255,0.05)]" />
          </div>
          <div className={`transition-all duration-700 delay-500 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
            <div className="flex items-center justify-center gap-3 mb-3">
              <div className="h-px w-12 bg-gradient-to-r from-transparent to-white/20" />
              <div className="w-1.5 h-1.5 rounded-full bg-white/30" />
              <div className="h-px w-12 bg-gradient-to-l from-transparent to-white/20" />
            </div>
            <p className="text-white/30 text-sm font-mono tracking-[0.4em] uppercase">Tactical Command Center</p>
          </div>
        </div>

        {/* Login Card */}
        <div className={`relative transition-all duration-700 delay-300 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
          <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-white/[0.06] via-white/[0.02] to-transparent" />
          <div className="relative bg-[#111111]/90 backdrop-blur-xl border border-white/[0.06] rounded-2xl p-8 shadow-2xl shadow-black/50">

            {/* Mode Toggle */}
            <div className="flex bg-white/[0.03] rounded-xl p-1 mb-6">
              <button
                onClick={() => setMode('account')}
                className={`flex-1 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                  mode === 'account'
                    ? 'bg-white/[0.08] text-white border border-white/[0.1]'
                    : 'text-white/30 hover:text-white/50'
                }`}
              >
                Account Login
              </button>
              <button
                onClick={() => setMode('apikey')}
                className={`flex-1 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-all duration-200 ${
                  mode === 'apikey'
                    ? 'bg-white/[0.08] text-white border border-white/[0.1]'
                    : 'text-white/30 hover:text-white/50'
                }`}
              >
                API Key
              </button>
            </div>

            {/* Section Header */}
            <div className="flex items-center gap-3 mb-8">
              <div className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.08] flex items-center justify-center">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-white/50">
                  {mode === 'account' ? (
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/>
                  ) : (
                    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
                  )}
                </svg>
              </div>
              <div>
                <h2 className="text-white/90 text-lg font-bold tracking-wide">
                  {mode === 'account' ? 'Sign In' : 'API Access'}
                </h2>
                <p className="text-white/25 text-xs font-mono mt-0.5">
                  {mode === 'account' ? 'Access your Magneetar account' : 'Connect with master API key'}
                </p>
              </div>
            </div>

            <form onSubmit={handleLogin} className="space-y-5">
              {/* Server URL — always shown */}
              <div className="space-y-2">
                <label className="text-xs font-mono text-white/40 uppercase tracking-[0.2em] font-bold">Server URL</label>
                <div className="relative">
                  <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
                      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={serverUrl}
                    onChange={(e) => setServerUrl(e.target.value)}
                    placeholder="https://api.magneetar.me"
                    className="w-full pl-10 pr-4 py-3.5 bg-white/[0.03] border border-white/[0.08] rounded-xl text-white/90 text-sm font-sans placeholder:text-white/20 focus:outline-none focus:border-white/20 focus:bg-white/[0.05] focus:ring-1 focus:ring-white/10 transition-all duration-200"
                    autoFocus
                  />
                </div>
              </div>

              {/* Account mode fields */}
              {mode === 'account' && (
                <>
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-white/40 uppercase tracking-[0.2em] font-bold">Email</label>
                    <div className="relative">
                      <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                          <polyline points="22,6 12,13 2,6"/>
                        </svg>
                      </div>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        className="w-full pl-10 pr-4 py-3.5 bg-white/[0.03] border border-white/[0.08] rounded-xl text-white/90 text-sm font-sans placeholder:text-white/20 focus:outline-none focus:border-white/20 focus:bg-white/[0.05] focus:ring-1 focus:ring-white/10 transition-all duration-200"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-mono text-white/40 uppercase tracking-[0.2em] font-bold">Password</label>
                    <div className="relative">
                      <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                        </svg>
                      </div>
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Enter your password"
                        className="w-full pl-10 pr-4 py-3.5 bg-white/[0.03] border border-white/[0.08] rounded-xl text-white/90 text-sm font-sans placeholder:text-white/20 focus:outline-none focus:border-white/20 focus:bg-white/[0.05] focus:ring-1 focus:ring-white/10 transition-all duration-200"
                      />
                    </div>
                  </div>
                </>
              )}

              {/* API Key mode */}
              {mode === 'apikey' && (
                <div className="space-y-2">
                  <label className="text-xs font-mono text-white/40 uppercase tracking-[0.2em] font-bold">API Key</label>
                  <div className="relative">
                    <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
                      </svg>
                    </div>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="Enter your master API key"
                      className="w-full pl-10 pr-4 py-3.5 bg-white/[0.03] border border-white/[0.08] rounded-xl text-white/90 text-sm font-sans placeholder:text-white/20 focus:outline-none focus:border-white/20 focus:bg-white/[0.05] focus:ring-1 focus:ring-white/10 transition-all duration-200"
                    />
                  </div>
                </div>
              )}

              {/* Error */}
              {error && (
                <div key={error} className="flex items-center gap-3 text-red-400/90 text-sm font-mono bg-red-500/[0.06] border border-red-500/20 rounded-xl px-4 py-3 animate-shake">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>{error}</span>
                </div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className="group relative w-full py-4 rounded-xl text-sm font-bold uppercase tracking-[0.2em] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed overflow-hidden"
              >
                <div className="absolute inset-0 bg-white/[0.06] border border-white/[0.12] rounded-xl group-hover:bg-white/[0.1] group-hover:border-white/[0.2] group-active:scale-[0.98] transition-all duration-200" />
                <div className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ background: 'radial-gradient(ellipse at center, rgba(255,255,255,0.03) 0%, transparent 70%)' }} />
                <span className="relative flex items-center justify-center gap-3 text-white/80 group-hover:text-white/95 transition-colors">
                  {loading ? (
                    <>
                      <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                      <span>Authenticating...</span>
                    </>
                  ) : (
                    <>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/>
                        <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1"/>
                      </svg>
                      <span>Connect</span>
                    </>
                  )}
                </span>
              </button>

              <div className="flex items-center justify-center gap-2 pt-2">
                <div className="w-1 h-1 rounded-full bg-emerald-400/40" />
                <span className="text-[11px] font-mono text-white/20 tracking-wider">End-to-end encrypted</span>
                <div className="w-1 h-1 rounded-full bg-emerald-400/40" />
              </div>
            </form>
          </div>
        </div>

        {/* Footer */}
        <div className={`text-center mt-8 transition-all duration-700 delay-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <div className="flex items-center justify-center gap-4 text-[11px] font-mono text-white/15 tracking-wider font-bold">
            <span>MAGNEETAR.ME</span>
            <span className="text-white/10">•</span>
            <span>MILITARY GRADE</span>
            <span className="text-white/10">•</span>
            <span>AES-256</span>
          </div>
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />
      <div className="absolute bottom-3 left-0 right-0 flex justify-between px-10">
        <span className="text-[10px] font-mono text-white/15 tracking-[0.3em] uppercase font-bold">Protocol Active</span>
        <span className="text-[10px] font-mono text-white/15 tracking-[0.3em] uppercase font-bold">Shield Enabled</span>
      </div>
    </div>
  );
}
