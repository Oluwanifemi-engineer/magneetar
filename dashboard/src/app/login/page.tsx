'use client';

import { useEffect, useRef, useState, type MouseEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { useStore } from '@/store/useStore';
import { extractErrorMessage } from '@/lib/api';
import {
  ShieldCheck,
  Radar,
  Camera,
  MapPin,
  ArrowRight,
  Mail,
  Lock,
  KeyRound,
  Eye,
  EyeOff,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type LoginMode = 'account' | 'apikey';

const BRAND_POINTS = [
  { icon: Radar, title: 'Live real-time tracking', text: 'WebSocket streaming to your command center' },
  { icon: Camera, title: 'Remote evidence capture', text: 'Photo & audio you can take to the police' },
  { icon: ShieldCheck, title: 'Theft detection', text: 'Automatic theft scoring with false-positive prevention' },
  { icon: MapPin, title: 'Geofencing & alerts', text: 'Instant exit alerts via push, email & SMS (WhatsApp in development)' },
];

const TICKER_LINES = [
  'PING #4821 · 38 km/h · battery 84%',
  'HEARTBEAT OK · wifi · 12s ago',
  'EVIDENCE SEALED · TAMPER-PROOF',
  'GEOFENCE OK · SAFE ZONE ACTIVE',
  'SIM UNCHANGED · THEFT MODE ARMED',
];

export default function LoginPage() {
  const { setCredentials, setConnected } = useStore();

  const [mode, setMode] = useState<LoginMode>('account');
  const serverUrl = 'https://api.magneetar.me';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [step2fa, setStep2fa] = useState(false);
  const [twoFactorToken, setTwoFactorToken] = useState('');
  const [code, setCode] = useState('');
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMounted(true); }, []);



  const handleCardMove = (e: MouseEvent<HTMLDivElement>) => {
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`);
    el.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`);
  };

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true); setError('');
    const baseUrl = serverUrl.replace(/\/+$/, '');
    try {
      if (mode === 'account') {
        if (!email || !password) { setError('Please enter your email and password.'); setLoading(false); return; }
        const res = await fetch(`${baseUrl}/api/auth/user/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Invalid email or password'));
        const data = await res.json();
        if (data.requires_2fa && data.two_factor_token) {
          setTwoFactorToken(data.two_factor_token); setCode(''); setStep2fa(true); setLoading(false); return;
        }
        sessionStorage.setItem('mt_server_url', baseUrl);
        sessionStorage.setItem('mt_api_key', data.token);
        sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
        sessionStorage.setItem('mt_auth_mode', 'user');
        setCredentials(baseUrl, data.token); setConnected(true);
      } else {
        if (!apiKey) { setError('Please enter your API key.'); setLoading(false); return; }
        const res = await fetch(`${baseUrl}/api/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: apiKey }),
        });
        if (!res.ok) throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Server unreachable or invalid API key'));
        const data = await res.json();
        sessionStorage.setItem('mt_server_url', baseUrl);
        sessionStorage.setItem('mt_api_key', data.token || '');
        sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
        sessionStorage.setItem('mt_auth_mode', 'apikey');
        setCredentials(baseUrl, data.token || ''); setConnected(true);
      }
      window.location.href = '/dashboard';
    } catch (err: any) { setError(err.message || 'Connection failed. Check your credentials.'); }
    finally { setLoading(false); }
  };

  const handleTwoFactorSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code.trim())) { setError('Enter the 6-digit code from your authenticator app.'); return; }
    setLoading(true); setError('');
    const baseUrl = serverUrl.replace(/\/+$/, '');
    try {
      const res = await fetch(`${baseUrl}/api/auth/user/login/2fa`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ two_factor_token: twoFactorToken, code: code.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        if (res.status === 429) setError('Too many attempts. Wait a few minutes and try again.');
        else setError(extractErrorMessage(body, 'Invalid or expired code — try again.'));
        setLoading(false); return;
      }
      const data = await res.json();
      sessionStorage.setItem('mt_server_url', baseUrl);
      sessionStorage.setItem('mt_api_key', data.token);
      sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
      sessionStorage.setItem('mt_auth_mode', 'user');
      setCredentials(baseUrl, data.token); setConnected(true);
      window.location.href = '/dashboard';
    } catch (err: any) { setError(err.message || 'Connection failed. Check your credentials.'); }
    finally { setLoading(false); }
  };

  const inputClass =
    'w-full pl-10 pr-4 py-3 bg-mag-surface border-mag-border rounded-xl text-mag-text text-sm ' +
    'placeholder:text-mag-text-muted/40 focus:outline-none focus:border-emerald-500/50 focus:bg-mag-surface-raised ' +
    'focus:ring-1 focus:ring-emerald-500/20 transition-all duration-200';

  return (
    <div className="min-h-screen bg-mag-bg text-mag-text relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-20 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-emerald-500/[0.04] blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-teal-500/[0.03] blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />
      <div className="absolute -bottom-40 -left-24 w-[520px] h-[380px] rounded-full bg-cyan-500/[0.03] blur-[130px] animate-aurora pointer-events-none" style={{ animationDelay: '-11s' }} aria-hidden="true" />
      {/* Floating particles */}
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          aria-hidden="true"
          className="absolute w-1 h-1 rounded-full bg-emerald-500/30 animate-float-particle"
          style={{ left: `${8 + i * 20}%`, top: `${20 + (i % 3) * 28}%`, animationDelay: `${i * 1.9}s` }}
        />
      ))}

      {/* Split Layout */}
      <div className="relative min-h-screen grid lg:grid-cols-2">
        {/* Left — Brand Showcase */}
        <div className="hidden lg:flex flex-col justify-between p-12 xl:p-16 border-r border-mag-border/50 bg-mag-bg relative overflow-hidden">
          <div className="grid-floor" aria-hidden="true" />

          <div className="relative">
            <Link href="/" className="inline-flex items-center gap-2.5 group">
              <img src="/magneetar-mhalf.svg" alt="Magneetar" className="w-9 h-9 rounded-lg" />
              <div className="leading-none">
                <div className="text-mag-text text-[15px] font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-mag-text-muted tracking-[0.3em] mt-1">COMMAND CENTER</div>
              </div>
            </Link>

            <h1 className="mt-14 text-4xl xl:text-[42px] font-display font-extrabold tracking-tight leading-[1.12] animate-fade-slide" style={{ animationDelay: '0.05s' }}>
              Your devices,
              <br />
              <span className="text-mag-text-muted">under your command.</span>
            </h1>
            <p className="mt-5 text-mag-text-muted leading-relaxed max-w-md text-[15px] animate-fade-slide" style={{ animationDelay: '0.1s' }}>
              Sign in to track, protect, and recover every device in your fleet — with intelligent
              detection and forensic-grade evidence.
            </p>
          </div>

          {/* Live Command-Center Telemetry */}
          <div className="relative my-10 animate-fade-slide" style={{ animationDelay: '0.15s' }}>
            <div className="relative rounded-2xl border-mag-border/50 bg-mag-surface shadow-2xl shadow-black/60 overflow-hidden">
              {/* Window chrome */}                <div className="flex items-center gap-2 px-4 py-3 border-b border-mag-border/50 bg-mag-surface">
                <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
                <span className="ml-3 text-[9px] font-mono text-white/20 tracking-widest font-bold">
                  MAGNEETAR — COMMAND CENTER
                </span>
                <span className="ml-auto flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-mag-surface border-mag-border">
                  <Radar size={9} className="text-amber-400" />
                  <span className="text-[8px] font-mono font-bold tracking-wider text-amber-400">DEMO</span>
                </span>
              </div>

              {/* Map area */}
              <div className="relative h-44 overflow-hidden">
                <div className="absolute inset-0 landing-grid opacity-60" />
                <div className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent animate-scan-line" aria-hidden="true" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-14" aria-hidden="true">
                  <span className="absolute inset-0 rounded-full border border-emerald-400/40 animate-radar-ping" />
                  <span className="absolute inset-0 rounded-full border border-emerald-400/25 animate-radar-ping" style={{ animationDelay: '1.2s' }} />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-emerald-500 shadow-[0_0_16px_rgba(16,185,129,0.8)]" />
                </div>
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 220" fill="none" preserveAspectRatio="none" aria-hidden="true">
                  <path d="M40 180 C 120 150, 160 90, 240 110 S 360 60, 380 50" stroke="url(#route-grad-dk)" strokeWidth="1.5" className="dash-flow" />
                  <circle cx="40" cy="180" r="3" fill="#10b981" />
                  <circle cx="380" cy="50" r="3" fill="#6B7280" />
                  <defs>
                    <linearGradient id="route-grad-dk" x1="40" y1="180" x2="380" y2="50">
                      <stop offset="0%" stopColor="#10b981" />
                      <stop offset="100%" stopColor="#6B7280" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute top-3 left-3 px-2.5 py-1.5 rounded-lg bg-mag-bg/80 border-mag-border/50 backdrop-blur-md">
                  <span className="text-[9px] font-mono font-bold tracking-wider text-mag-text-dim">6.5244° N, 3.3792° E</span>
                </div>
                <div className="absolute bottom-3 right-3 px-2.5 py-1.5 rounded-lg bg-mag-bg/80 border-mag-border/50 backdrop-blur-md flex items-center gap-1.5">
                  <MapPin size={10} className="text-mag-text-muted" />
                  <span className="text-[9px] font-mono font-bold tracking-wider text-mag-text-dim">12 m · 38 km/h</span>
                </div>
              </div>

              {/* Readouts */}
              <div className="grid grid-cols-3 gap-px bg-mag-surface border-t border-mag-border/50">
                <div className="bg-mag-surface px-4 py-3">
                  <div className="text-[8px] font-mono text-mag-text-muted tracking-widest font-bold mb-1.5">THREAT</div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]" />
                    <span className="text-mag-text-dim text-sm font-bold font-mono">SAFE</span>
                  </div>
                </div>
                <div className="bg-mag-surface px-4 py-3">
                  <div className="text-[8px] font-mono text-mag-text-muted tracking-widest font-bold mb-1.5">SENTINEL</div>
                  <div className="flex items-center gap-2">
                    <span className="text-mag-text text-sm font-bold font-mono">12</span>
                    <div className="flex-1 h-1 rounded-full border-mag-border/50 overflow-hidden">
                      <div className="bar-sweep h-full rounded-full bg-gradient-to-r from-emerald-500 to-emerald-400" />
                    </div>
                  </div>
                </div>
                <div className="bg-mag-surface px-4 py-3">
                  <div className="text-[8px] font-mono text-mag-text-muted tracking-widest font-bold mb-1.5">EVIDENCE</div>
                  <div className="flex items-center gap-1.5">
                    <Camera size={12} className="text-mag-text-muted" />
                    <span className="text-mag-text-dim text-sm font-bold font-mono">3 files</span>
                  </div>
                </div>
              </div>

              {/* Live ticker */}
              <div className="border-t border-mag-border/50 bg-mag-surface/25 overflow-hidden h-7">
                <div className="ticker-scroll">
                  {[0, 1].map((copy) => (
                    <div key={copy}>
                      {TICKER_LINES.map((line) => (
                        <div key={`${copy}-${line}`} className="px-4 py-1 text-[9px] font-mono text-mag-text-muted tracking-wider whitespace-nowrap leading-[18px]">
                          <span className="text-emerald-500/50 mr-1.5">▸</span>
                          {line}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Floating chips */}
            <div className="absolute -top-4 -right-3 sm:-right-6 px-3.5 py-2 rounded-xl border-mag-border/50 bg-mag-surface shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-500" />
              </span>
              <span className="text-[10px] font-mono font-bold text-mag-text-dim">Galaxy S24 · Demo device</span>
            </div>
            <div className="absolute -bottom-4 -left-3 sm:-left-6 px-3.5 py-2 rounded-xl border-mag-border/50 bg-mag-surface shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2" style={{ animationDelay: '-2.5s' }}>
              <span className="w-4 h-4 rounded-full bg-emerald-500/[0.1] border border-emerald-500/20 flex items-center justify-center">
                <Check size={9} className="text-emerald-400" />
              </span>
              <span className="text-[10px] font-mono font-bold text-mag-text-dim">Recovery enabled</span>
            </div>
          </div>
        </div>

        {/* Right — Form */}
        <div className="flex items-center justify-center px-5 sm:px-8 py-14">
          <div className={cn('w-full max-w-md transition-all duration-700', mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4')}>
            {/* Mobile brand */}
            <Link href="/" className="lg:hidden inline-flex items-center gap-2.5 mb-10">
              <img src="/magneetar-mhalf.svg" alt="Magneetar" className="w-9 h-9 rounded-lg" />
              <div className="leading-none">
                <div className="text-mag-text text-[15px] font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-mag-text-muted tracking-[0.3em] mt-1">COMMAND CENTER</div>
              </div>
            </Link>

            {/* Heading */}
            <div className="mb-8">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-4">
                <span className="relative flex w-1.5 h-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-emerald-500" />
                </span>
                <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-muted">SECURE ACCESS</span>
              </div>
              <h2 className="text-2xl font-display font-extrabold tracking-tight text-mag-text">Welcome back</h2>
              <p className="mt-2 text-mag-text-muted text-sm">
                Sign in to access your command center.
              </p>
            </div>

            {/* Glass card */}
            <div
              ref={cardRef}
              onMouseMove={handleCardMove}
              className="spotlight-card relative rounded-2xl border-mag-border/50 bg-mag-surface/80 backdrop-blur-xl p-7 sm:p-8 shadow-2xl shadow-black/50"
            >
              <div className="relative z-10">
                {step2fa ? (
                  <div className="animate-fade-in">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="w-10 h-10 rounded-xl bg-mag-surface border-mag-border flex items-center justify-center">
                        <ShieldCheck size={17} className="text-emerald-400" />
                      </div>
                      <div>
                        <h3 className="text-[15px] font-display font-extrabold tracking-tight text-mag-text">Two-factor authentication</h3>
                        <div className="text-[10px] font-mono text-mag-text-muted font-bold mt-0.5">SECOND FACTOR REQUIRED</div>
                      </div>
                    </div>
                    <p className="text-[12px] text-mag-text-muted leading-relaxed mb-6">
                      Enter the 6-digit code from your authenticator app
                      <span className="block mt-1 text-white/20 font-mono text-[10px]">for {email}</span>
                    </p>

                    <form onSubmit={handleTwoFactorSubmit} noValidate>
                      <div className="space-y-4">
                        <div className="space-y-1.5">
                          <label htmlFor="login-2fa-code" className="text-[10px] font-mono text-mag-text-muted uppercase tracking-[0.2em] font-bold">
                            Authenticator code
                          </label>
                          <input
                            id="login-2fa-code"
                            name="code"
                            inputMode="numeric"
                            autoComplete="one-time-code"
                            value={code}
                            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                            placeholder="000000"
                            className={cn('mag-field-strong pl-4 text-center tracking-[0.5em] font-mono text-lg', 'text-lg')}
                            autoFocus
                          />
                        </div>

                        {error && (
                          <div key={error} className="flex items-center gap-3 text-red-400/90 text-[12px] font-mono bg-red-500/[0.06] border border-red-500/15 rounded-xl px-4 py-3 animate-shake" role="alert">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0" aria-hidden="true">
                              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                            </svg>
                            <span>{error}</span>
                          </div>
                        )}

                        <button type="submit" disabled={loading}
                          className="group relative w-full py-3.5 rounded-xl text-[12px] font-bold uppercase tracking-[0.2em] font-mono bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/35 hover:brightness-110 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] overflow-hidden">
                          {loading ? (
                            <span className="flex items-center justify-center gap-2.5">
                              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                              Verifying...
                            </span>
                          ) : (
                            <span className="flex items-center justify-center gap-2.5">
                              Verify &amp; Connect
                              <ArrowRight size={14} />
                            </span>
                          )}
                        </button>

                        <button type="button" onClick={() => { setStep2fa(false); setTwoFactorToken(''); setCode(''); setError(''); }} disabled={loading}
                          className="w-full py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-mag-text-muted hover:text-mag-text transition-colors">
                          ← Back to sign in
                        </button>
                      </div>
                    </form>
                  </div>
                ) : (
                  <>
                    {/* Mode toggle */}
                    <div role="group" aria-label="Login mode" className="relative flex bg-mag-surface rounded-xl p-1 mb-7 border-mag-border/50">
                      <div
                        aria-hidden="true"
                        className={cn(
                          'absolute top-1 bottom-1 left-1 w-[calc(50%-4px)] rounded-lg bg-mag-surface-raised border-mag-border shadow-sm transition-transform duration-300 ease-out',
                          mode === 'apikey' ? 'translate-x-full' : 'translate-x-0'
                        )}
                      />
                      <button type="button" aria-pressed={mode === 'account'} onClick={() => { setMode('account'); setError(''); }}
                        className={cn('relative flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 font-mono', mode === 'account' ? 'text-mag-text' : 'text-mag-text-muted hover:text-mag-text-dim')}>
                        Account
                      </button>
                      <button type="button" aria-pressed={mode === 'apikey'} onClick={() => { setMode('apikey'); setError(''); }}
                        className={cn('relative flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 font-mono', mode === 'apikey' ? 'text-mag-text' : 'text-mag-text-muted hover:text-mag-text-dim')}>
                        API Key
                      </button>
                    </div>

                    <form onSubmit={handleLogin} noValidate>
                      <div className="space-y-4">
                        {mode === 'account' ? (
                          <>
                            <div className="space-y-1.5">
                              <label htmlFor="login-email" className="text-[10px] font-mono text-mag-text-muted uppercase tracking-[0.2em] font-bold">Email</label>
                              <div className="relative">
                                <Mail size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/15 pointer-events-none" />
                                <input id="login-email" name="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                                  placeholder="you@example.com" autoComplete="email" className={inputClass} />
                              </div>
                            </div>

                            <div className="space-y-1.5">
                              <div className="flex items-center justify-between">
                                <label htmlFor="login-password" className="text-[10px] font-mono text-mag-text-muted uppercase tracking-[0.2em] font-bold">Password</label>
                                <Link href="/forgot-password" className="text-[10px] font-mono text-mag-text-muted hover:text-mag-text font-bold transition-colors">Forgot password?</Link>
                              </div>
                              <div className="relative">
                                <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-mag-text-muted pointer-events-none" />
                                <input id="login-password" name="password" type={showPassword ? 'text' : 'password'} value={password}
                                  onChange={(e) => setPassword(e.target.value)} placeholder="Enter your password" autoComplete="current-password"
                                  className={cn(inputClass, 'pr-11')} />                                  <button type="button" onClick={() => setShowPassword((v) => !v)}
                                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                                  className="absolute right-3 top-1/2 -translate-y-1/2 text-mag-text-muted hover:text-mag-text transition-colors">
                                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                                </button>
                              </div>
                            </div>
                          </>
                        ) : (
                          <div className="space-y-1.5">
                            <label htmlFor="api-key-input" className="text-[10px] font-mono text-mag-text-muted uppercase tracking-[0.2em] font-bold">API Key</label>
                            <div className="relative">
                              <KeyRound size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-mag-text-muted pointer-events-none" />
                              <input id="api-key-input" name="apiKey" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                                placeholder="Enter your master API key" autoComplete="off" className={inputClass} />
                            </div>
                          </div>
                        )}

                        {error && (
                          <div key={error} className="flex items-center gap-3 text-red-400/90 text-[12px] font-mono bg-red-500/[0.06] border border-red-500/15 rounded-xl px-4 py-3 animate-shake" role="alert">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0" aria-hidden="true">
                              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                            </svg>
                            <span>{error}</span>
                          </div>
                        )}

                        <button type="submit" disabled={loading}
                          className="group relative w-full py-3.5 rounded-xl text-[12px] font-bold uppercase tracking-[0.2em] font-mono bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/35 hover:brightness-110 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] overflow-hidden">
                          <span className="absolute inset-y-0 -left-full w-1/2 bg-white/15 blur-md animate-shimmer" />
                          <span className="relative flex items-center justify-center gap-2.5">
                            {loading ? (
                              <>
                                <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                                <span>Authenticating...</span>
                              </>
                            ) : (
                              <>
                                <span>Sign In</span>
                                <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                              </>
                            )}
                          </span>
                        </button>
                      </div>
                    </form>
                  </>
                )}
              </div>
            </div>

            {/* Signup prompt */}
            <p className="mt-7 text-center text-[13px] text-mag-text-muted">
              New to Magneetar?{' '}
              <Link href="/signup" className="text-emerald-400 hover:text-emerald-300 font-semibold transition-colors">
                Create an account
              </Link>
            </p>

            {/* Security strip */}
            <div className="mt-8 flex items-center justify-center gap-5">
              {[
                { icon: Lock, label: 'TOTP 2FA' },
                { icon: KeyRound, label: 'BCRYPT' },
                { icon: ShieldCheck, label: 'RATE-LIMITED' },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5 text-mag-text-muted/60">
                  <item.icon size={10} />
                  <span className="text-[9px] font-mono font-bold tracking-wider text-mag-text-muted/60">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
