'use client';

import { useState, useEffect } from 'react';
import { useStore } from '@/store/useStore';

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

  // Pre-fill server URL
  useEffect(() => {
    if (!serverUrl) setServerUrl('https://api.magneetar.me');
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!serverUrl) {
      setError('Please enter your server URL.');
      return;
    }

    setLoading(true);
    setError('');

    const baseUrl = serverUrl.replace(/\/+$/, '');

    try {
      if (mode === 'account') {
        if (!email || !password) {
          setError('Please enter your email and password.');
          setLoading(false);
          return;
        }
        const res = await fetch(`${baseUrl}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Login failed' }));
          throw new Error(err.detail || 'Invalid credentials');
        }
        const data = await res.json();
        sessionStorage.setItem('mt_server_url', baseUrl);
        sessionStorage.setItem('mt_api_key', data.token);
        sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
        sessionStorage.setItem('mt_auth_mode', 'user');
        setCredentials(baseUrl, data.token);
        setConnected(true);
      } else {
        if (!apiKey) {
          setError('Please enter your API key.');
          setLoading(false);
          return;
        }
        // API key health check
        const res = await fetch(`${baseUrl}/health`, {
          headers: { 'x-api-key': apiKey },
        });
        if (!res.ok) throw new Error('Server unreachable or invalid API key');
        sessionStorage.setItem('mt_server_url', baseUrl);
        sessionStorage.setItem('mt_api_key', apiKey);
        sessionStorage.setItem('mt_auth_mode', 'apikey');
        setCredentials(baseUrl, apiKey);
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
      {/* ─── Background Effects ─────────────────────────────────────────────── */}
      <div className="absolute inset-0 login-grid opacity-40" />
      <div className="absolute inset-0 pointer-events-none login-scanlines" />
      <div className="absolute inset-0 pointer-events-none login-vignette" />

      {/* Animated scan line */}
      <div className="absolute left-1/4 right-1/4 h-px bg-gradient-to-r from-transparent via-white/5 to-transparent animate-scan-line pointer-events-none" />

      {/* ─── Corner HUD Brackets ───────────────────────────────────────────── */}
      <div className="absolute top-6 left-6 w-10 h-10 border-l-[1.5px] border-t-[1.5px] border-white/8 rounded-tl-sm" />
      <div className="absolute top-6 right-6 w-10 h-10 border-r-[1.5px] border-t-[1.5px] border-white/8 rounded-tr-sm" />
      <div className="absolute bottom-6 left-6 w-10 h-10 border-l-[1.5px] border-b-[1.5px] border-white/8 rounded-bl-sm" />
      <div className="absolute bottom-6 right-6 w-10 h-10 border-r-[1.5px] border-b-[1.5px] border-white/8 rounded-br-sm" />

      {/* Top status bar */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="absolute top-3 left-0 right-0 flex justify-between px-8">
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/60" />
          <span className="text-[9px] font-mono text-white/15 tracking-[0.3em] uppercase font-bold">System Secure</span>
        </div>
        <span className="text-[9px] font-mono text-white/15 tracking-[0.3em] uppercase font-bold">v1.0.0</span>
      </div>

      {/* ─── Main Content ───────────────────────────────────────────────────── */}
      <div className={`relative z-10 w-full max-w-md mx-6 transition-all duration-700 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>

        {/* M Logo */}
        <div className="text-center mb-10">
          <div className={`transition-all duration-1000 delay-200 ${mounted ? 'opacity-100 scale-100' : 'opacity-0 scale-90'}`}>
            {/* M Logo Mark */}
            <div className="inline-flex items-center justify-center mb-5 relative">
              {/* Outer rings */}
              <div className="absolute w-24 h-24 rounded-full border border-white/[0.06] animate-m-glow" />
              <div className="absolute w-20 h-20 rounded-full border border-white/[0.03]" />

              {/* M Icon */}
              <div className="w-16 h-16 rounded-2xl bg-white/[0.02] border border-white/[0.08] flex items-center justify-center backdrop-blur-sm">
                <svg viewBox="0 0 120 120" className="w-10 h-10" fill="none" aria-label="Magneetar logo">
                  <path d="M24 88L24 32L48 60L60 44L72 60L96 32L96 88"
                        stroke="white" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            </div>

            {/* Brand Name */}
            <div className="text-white text-2xl font-display font-bold tracking-[0.3em]">
              MAGNEETAR
            </div>
            <div className="flex items-center justify-center gap-2 mt-3 mb-2">
              <div className="h-px w-8 bg-gradient-to-r from-transparent to-white/10" />
              <div className="w-1 h-1 rounded-full bg-white/20" />
              <div className="h-px w-8 bg-gradient-to-l from-transparent to-white/10" />
            </div>
            <p className="text-white/20 text-[10px] font-mono tracking-[0.4em] uppercase font-bold">
              Tactical Command Center
            </p>
          </div>
        </div>

        {/* ─── Login Card ──────────────────────────────────────────────────── */}
        <div className={`relative transition-all duration-700 delay-300 ${mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
          {/* Card glow border */}
          <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-white/[0.04] via-white/[0.01] to-transparent pointer-events-none" />

          <div className="relative bg-[#0d0d12]/90 backdrop-blur-xl border border-white/[0.05] rounded-2xl p-8 shadow-2xl shadow-black/50">

            {/* ─── Mode Toggle ─────────────────────────────────────────────── */}
            <div className="flex bg-white/[0.02] rounded-xl p-1 mb-6 border border-white/[0.04]" role="tablist" aria-label="Login mode">
              <button
                role="tab"
                aria-selected={mode === 'account'}
                onClick={() => setMode('account')}
                className={`flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all duration-200 font-mono ${
                  mode === 'account'
                    ? 'bg-white/[0.06] text-white border border-white/[0.08] shadow-sm'
                    : 'text-white/25 hover:text-white/50'
                }`}
              >
                Account
              </button>
              <button
                role="tab"
                aria-selected={mode === 'apikey'}
                onClick={() => setMode('apikey')}
                className={`flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-all duration-200 font-mono ${
                  mode === 'apikey'
                    ? 'bg-white/[0.06] text-white border border-white/[0.08] shadow-sm'
                    : 'text-white/25 hover:text-white/50'
                }`}
              >
                API Key
              </button>
            </div>

            {/* ─── Section Header ──────────────────────────────────────────── */}
            <div className="flex items-center gap-3 mb-6">
              <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-white/40" aria-hidden="true">
                  {mode === 'account' ? (
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/>
                  ) : (
                    <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
                  )}
                </svg>
              </div>
              <div>
                <h2 className="text-white/80 text-base font-bold tracking-wide">
                  {mode === 'account' ? 'Sign In' : 'API Access'}
                </h2>
                <p className="text-white/20 text-[10px] font-mono mt-0.5 font-bold">
                  {mode === 'account' ? 'Access your Magneetar account' : 'Connect with master API key'}
                </p>
              </div>
            </div>

            {/* ─── Form ────────────────────────────────────────────────────── */}
            <form onSubmit={handleLogin} noValidate>
              <div className="space-y-4">

                {/* Server URL — always shown */}
                <div className="space-y-1.5">
                  <label htmlFor="server-url" className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em] font-bold">Server URL</label>
                  <div className="relative">
                    <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/15 pointer-events-none">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                        <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                      </svg>
                    </div>
                    <input
                      id="server-url"
                      name="serverUrl"
                      type="text"
                      value={serverUrl}
                      onChange={(e) => setServerUrl(e.target.value)}
                      placeholder="https://api.magneetar.me"
                      autoComplete="url"
                      className="w-full pl-10 pr-4 py-3 bg-white/[0.02] border border-white/[0.06] rounded-xl text-white/80 text-sm font-sans placeholder:text-white/15 focus:outline-none focus:border-white/15 focus:bg-white/[0.03] focus:ring-1 focus:ring-white/5 transition-all duration-200"
                      autoFocus
                    />
                  </div>
                </div>

                {/* Account mode fields */}
                {mode === 'account' && (
                  <>
                    <div className="space-y-1.5">
                      <label htmlFor="login-email" className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em] font-bold">Email</label>
                      <div className="relative">
                        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/15 pointer-events-none">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                            <polyline points="22,6 12,13 2,6"/>
                          </svg>
                        </div>
                        <input
                          id="login-email"
                          name="email"
                          type="email"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          placeholder="you@example.com"
                          autoComplete="email"
                          className="w-full pl-10 pr-4 py-3 bg-white/[0.02] border border-white/[0.06] rounded-xl text-white/80 text-sm font-sans placeholder:text-white/15 focus:outline-none focus:border-white/15 focus:bg-white/[0.03] focus:ring-1 focus:ring-white/5 transition-all duration-200"
                        />
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <label htmlFor="login-password" className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em] font-bold">Password</label>
                      <div className="relative">
                        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/15 pointer-events-none">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                          </svg>
                        </div>
                        <input
                          id="login-password"
                          name="password"
                          type="password"
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="Enter your password"
                          autoComplete="current-password"
                          className="w-full pl-10 pr-4 py-3 bg-white/[0.02] border border-white/[0.06] rounded-xl text-white/80 text-sm font-sans placeholder:text-white/15 focus:outline-none focus:border-white/15 focus:bg-white/[0.03] focus:ring-1 focus:ring-white/5 transition-all duration-200"
                        />
                      </div>
                    </div>
                  </>
                )}

                {/* API Key mode */}
                {mode === 'apikey' && (
                  <div className="space-y-1.5">
                    <label htmlFor="api-key-input" className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em] font-bold">API Key</label>
                    <div className="relative">
                      <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/15 pointer-events-none">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
                        </svg>
                      </div>
                      <input
                        id="api-key-input"
                        name="apiKey"
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="Enter your master API key"
                        autoComplete="off"
                        className="w-full pl-10 pr-4 py-3 bg-white/[0.02] border border-white/[0.06] rounded-xl text-white/80 text-sm font-sans placeholder:text-white/15 focus:outline-none focus:border-white/15 focus:bg-white/[0.03] focus:ring-1 focus:ring-white/5 transition-all duration-200"
                      />
                    </div>
                  </div>
                )}

                {/* Error */}
                {error && (
                  <div key={error} className="flex items-center gap-3 text-red-400/80 text-[12px] font-mono bg-red-500/[0.04] border border-red-500/15 rounded-xl px-4 py-3 animate-shake" role="alert">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0" aria-hidden="true">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                    </svg>
                    <span>{error}</span>
                  </div>
                )}

                {/* Submit */}
                <button
                  type="submit"
                  disabled={loading}
                  className="group relative w-full py-3.5 rounded-xl text-[12px] font-bold uppercase tracking-[0.2em] transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed overflow-hidden font-mono mt-2"
                >
                  <div className="absolute inset-0 bg-white/[0.04] border border-white/[0.08] rounded-xl group-hover:bg-white/[0.07] group-hover:border-white/[0.14] group-active:scale-[0.98] transition-all duration-200" />
                  <div className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300" style={{ background: 'radial-gradient(ellipse at center, rgba(255,255,255,0.03) 0%, transparent 70%)' }} />
                  <span className="relative flex items-center justify-center gap-3 text-white/60 group-hover:text-white/80 transition-colors">
                    {loading ? (
                      <>
                        <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                        <span>Authenticating...</span>
                      </>
                    ) : (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                          <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/>
                          <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1"/>
                        </svg>
                        <span>Connect</span>
                      </>
                    )}
                  </span>
                </button>

                {/* Encryption badge */}
                <div className="flex items-center justify-center gap-2 pt-1">
                  <div className="w-1 h-1 rounded-full bg-emerald-400/30" />
                  <span className="text-[9px] font-mono text-white/15 tracking-wider font-bold">AES-256 ENCRYPTED</span>
                  <div className="w-1 h-1 rounded-full bg-emerald-400/30" />
                </div>
              </div>
            </form>
          </div>
        </div>

        {/* Footer */}
        <div className={`text-center mt-8 transition-all duration-700 delay-700 ${mounted ? 'opacity-100' : 'opacity-0'}`}>
          <div className="flex items-center justify-center gap-4 text-[9px] font-mono text-white/12 tracking-wider font-bold">
            <span className="flex items-center gap-1.5">
              <svg viewBox="0 0 120 120" className="w-3 h-3" fill="none" aria-hidden="true">
                <path d="M24 88L24 32L48 60L60 44L72 60L96 32L96 88" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              MAGNEETAR.ME
            </span>
            <span className="text-white/8" aria-hidden="true">•</span>
            <span>MILITARY GRADE</span>
            <span className="text-white/8" aria-hidden="true">•</span>
            <span>AES-256</span>
          </div>
        </div>
      </div>

      {/* Bottom status bar */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      <div className="absolute bottom-3 left-0 right-0 flex justify-between px-8">
        <span className="text-[9px] font-mono text-white/12 tracking-[0.3em] uppercase font-bold">Protocol Active</span>
        <span className="text-[9px] font-mono text-white/12 tracking-[0.3em] uppercase font-bold">Shield Enabled</span>
      </div>
    </div>
  );
}
