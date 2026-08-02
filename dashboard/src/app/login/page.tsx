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
  Globe,
  Eye,
  EyeOff,
  Star,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type LoginMode = 'account' | 'apikey';

const BRAND_POINTS = [
  { icon: Radar, title: 'Live real-time tracking', text: 'WebSocket streaming to your command center' },
  { icon: Camera, title: 'Remote evidence capture', text: 'Photo & audio with SHA-256 chain of custody' },
  { icon: ShieldCheck, title: 'Sentinel AI detection', text: 'Theft scoring with false-positive prevention' },
  { icon: MapPin, title: 'Geofencing & alerts', text: 'Instant exit alerts via SMS, WhatsApp & push' },
];

const TICKER_LINES = [
  'PING #4821 · 38 km/h · battery 84%',
  'HEARTBEAT OK · wifi · 12s ago',
  'EVIDENCE SEALED · SHA-256 CHAIN',
  'GEOFENCE OK · SAFE ZONE ACTIVE',
  'SIM UNCHANGED · THEFT MODE ARMED',
];

const AVATARS = ['JD', 'AK', 'MT', 'RS'];

export default function LoginPage() {
  const { setCredentials, setConnected } = useStore();

  const [mode, setMode] = useState<LoginMode>('account');
  const [serverUrl, setServerUrl] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMounted(true); }, []);

  // Pre-fill server URL
  useEffect(() => {
    if (!serverUrl) setServerUrl('https://api.magneetar.me');
  }, []);

  // Write spotlight position straight to CSS custom properties so the glow
  // follows the cursor without re-rendering the page on every mousemove.
  const handleCardMove = (e: MouseEvent<HTMLDivElement>) => {
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${((e.clientX - rect.left) / rect.width) * 100}%`);
    el.style.setProperty('--my', `${((e.clientY - rect.top) / rect.height) * 100}%`);
  };

  const handleLogin = async (e: FormEvent) => {
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
        const res = await fetch(`${baseUrl}/api/auth/user/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Invalid email or password'));
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
        // API key validation — the login endpoint is the authoritative check
        const res = await fetch(`${baseUrl}/api/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: apiKey }),
        });
        if (!res.ok) {
          throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Server unreachable or invalid API key'));
        }
        sessionStorage.setItem('mt_server_url', baseUrl);
        sessionStorage.setItem('mt_api_key', apiKey);
        sessionStorage.setItem('mt_auth_mode', 'apikey');
        setCredentials(baseUrl, apiKey);
        setConnected(true);
      }

      window.location.href = '/dashboard';
    } catch (err: any) {
      setError(err.message || 'Connection failed. Check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    'w-full pl-10 pr-4 py-3 bg-white/[0.02] border border-white/[0.07] rounded-xl text-white/85 text-sm ' +
    'placeholder:text-white/15 focus:outline-none focus:border-[#E91E8C]/40 focus:bg-white/[0.03] ' +
    'focus:ring-1 focus:ring-[#E91E8C]/15 transition-all duration-200';

  return (
    <div className="min-h-screen bg-mag-bg text-white relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-[#06B6D4]/8 blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />
      <div className="absolute -bottom-40 -left-24 w-[520px] h-[380px] rounded-full bg-[#7C3AED]/8 blur-[130px] animate-aurora pointer-events-none" style={{ animationDelay: '-11s' }} aria-hidden="true" />
      {/* Floating particles */}
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          aria-hidden="true"
          className="absolute w-1 h-1 rounded-full bg-white/25 animate-float-particle"
          style={{ left: `${8 + i * 20}%`, top: `${20 + (i % 3) * 28}%`, animationDelay: `${i * 1.9}s` }}
        />
      ))}

      {/* ─── Split Layout ─────────────────────────────────────────────────── */}
      <div className="relative min-h-screen grid lg:grid-cols-2">
        {/* ─── Left — Brand Showcase ─────────────────────────────────────── */}
        <div className="hidden lg:flex flex-col justify-between p-12 xl:p-16 border-r border-white/[0.06] bg-mag-panel/30 backdrop-blur-xl relative overflow-hidden">
          {/* Perspective grid floor */}
          <div className="grid-floor" aria-hidden="true" />

          <div className="relative">
            {/* Brand */}
            <Link href="/" className="inline-flex items-center gap-2.5 group">
              <div className="w-9 h-9 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center overflow-hidden">
                <svg viewBox="0 0 120 120" className="w-5 h-5" fill="none" aria-label="Magneetar logo">
                  <path
                    d="M27 88L27 38L60 82L93 38L93 88"
                    stroke="url(#login-grad)"
                    strokeWidth="17"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <defs>
                    <linearGradient id="login-grad" x1="27" y1="38" x2="93" y2="88">
                      <stop offset="0%" stopColor="#FFFFFF" />
                      <stop offset="100%" stopColor="#F3D3E6" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              <div className="leading-none">
                <div className="text-white text-[15px] font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-white/30 tracking-[0.3em] mt-1">COMMAND CENTER</div>
              </div>
            </Link>

            {/* Headline */}
            <h1 className="mt-14 text-4xl xl:text-[42px] font-display font-extrabold tracking-tight leading-[1.12] animate-fade-slide" style={{ animationDelay: '0.05s' }}>
              Your devices,
              <br />
              <span className="text-gradient-primary animate-gradient-x">under your command.</span>
            </h1>
            <p className="mt-5 text-white/45 leading-relaxed max-w-md text-[15px] animate-fade-slide" style={{ animationDelay: '0.1s' }}>
              Sign in to track, protect, and recover every device in your fleet — with intelligent
              detection and forensic-grade evidence.
            </p>
          </div>

          {/* ─── Live Command-Center Telemetry ──────────────────────────── */}
          <div className="relative my-10 animate-fade-slide" style={{ animationDelay: '0.15s' }}>
            <div className="relative rounded-2xl border border-white/10 bg-[#0d0d14]/90 backdrop-blur-xl shadow-2xl shadow-black/60 overflow-hidden">
              {/* Window chrome */}
              <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
                <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
                <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
                <span className="ml-3 text-[9px] font-mono text-white/30 tracking-widest font-bold">
                  MAGNEETAR — COMMAND CENTER
                </span>
                <span className="ml-auto flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20">
                  <Radar size={9} className="text-emerald-400" />
                  <span className="text-[8px] font-mono font-bold tracking-wider text-emerald-300">LIVE</span>
                </span>
              </div>

              {/* Map area */}
              <div className="relative h-44 overflow-hidden">
                <div className="absolute inset-0 landing-grid opacity-80" />
                {/* Scan line */}
                <div className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#22D3EE]/50 to-transparent animate-scan-line" aria-hidden="true" />
                {/* Radar ping */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-14" aria-hidden="true">
                  <span className="absolute inset-0 rounded-full border border-[#22C55E]/40 animate-radar-ping" />
                  <span className="absolute inset-0 rounded-full border border-[#22C55E]/25 animate-radar-ping" style={{ animationDelay: '1.2s' }} />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-[#22C55E] shadow-[0_0_16px_rgba(34,197,94,0.8)]" />
                </div>
                {/* Decorative route */}
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 220" fill="none" preserveAspectRatio="none" aria-hidden="true">
                  <path
                    d="M40 180 C 120 150, 160 90, 240 110 S 360 60, 380 50"
                    stroke="url(#route-grad)"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    className="dash-flow"
                  />
                  <circle cx="40" cy="180" r="3" fill="#E91E8C" />
                  <circle cx="380" cy="50" r="3" fill="#06B6D4" />
                  <defs>
                    <linearGradient id="route-grad" x1="40" y1="180" x2="380" y2="50">
                      <stop offset="0%" stopColor="#E91E8C" />
                      <stop offset="100%" stopColor="#06B6D4" />
                    </linearGradient>
                  </defs>
                </svg>
                {/* HUD chips */}
                <div className="absolute top-3 left-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md">
                  <span className="text-[9px] font-mono font-bold tracking-wider text-white/50">
                    6.5244° N, 3.3792° E
                  </span>
                </div>
                <div className="absolute bottom-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md flex items-center gap-1.5">
                  <MapPin size={10} className="text-[#06B6D4]" />
                  <span className="text-[9px] font-mono font-bold tracking-wider text-white/60">12 m · 38 km/h</span>
                </div>
              </div>

              {/* Readouts */}
              <div className="grid grid-cols-3 gap-px bg-white/[0.05] border-t border-white/[0.06]">
                <div className="bg-[#0d0d14]/95 px-4 py-3">
                  <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">THREAT</div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.7)]" />
                    <span className="text-white text-sm font-bold font-mono">SAFE</span>
                  </div>
                </div>
                <div className="bg-[#0d0d14]/95 px-4 py-3">
                  <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">SENTINEL</div>
                  <div className="flex items-center gap-2">
                    <span className="text-white text-sm font-bold font-mono">12</span>
                    <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                      <div className="bar-sweep h-full rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]" />
                    </div>
                  </div>
                </div>
                <div className="bg-[#0d0d14]/95 px-4 py-3">
                  <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">EVIDENCE</div>
                  <div className="flex items-center gap-1.5">
                    <Camera size={12} className="text-[#06B6D4]" />
                    <span className="text-white text-sm font-bold font-mono">3 files</span>
                  </div>
                </div>
              </div>

              {/* Live ticker */}
              <div className="border-t border-white/[0.06] bg-white/[0.01] overflow-hidden h-7">
                <div className="ticker-scroll">
                  {[0, 1].map((copy) => (
                    <div key={copy}>
                      {TICKER_LINES.map((line) => (
                        <div key={`${copy}-${line}`} className="px-4 py-1 text-[9px] font-mono text-white/35 tracking-wider whitespace-nowrap leading-[18px]">
                          <span className="text-[#E91E8C]/70 mr-1.5">▸</span>
                          {line}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Floating chips */}
            <div className="absolute -top-4 -right-3 sm:-right-6 px-3.5 py-2 rounded-xl border border-white/10 bg-[#111118]/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
              </span>
              <span className="text-[10px] font-mono font-bold text-white/70">Pixel 8 · Online</span>
            </div>
            <div className="absolute -bottom-4 -left-3 sm:-left-6 px-3.5 py-2 rounded-xl border border-white/10 bg-[#111118]/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2" style={{ animationDelay: '-2.5s' }}>
              <span className="w-4 h-4 rounded-full bg-[#22C55E]/15 border border-[#22C55E]/30 flex items-center justify-center">
                <Check size={9} className="text-[#22C55E]" />
              </span>
              <span className="text-[10px] font-mono font-bold text-white/70">Recovery enabled</span>
            </div>
          </div>

          {/* ─── Social proof ───────────────────────────────────────────── */}
          <div className="flex items-center gap-4 animate-fade-slide" style={{ animationDelay: '0.2s' }}>
            <div className="flex -space-x-2.5">
              {AVATARS.map((initials, i) => (
                <div
                  key={initials}
                  className="w-8 h-8 rounded-full border-2 border-[#0d0d14] bg-gradient-to-br from-[#E91E8C]/35 to-[#06B6D4]/35 flex items-center justify-center text-[9px] font-mono font-bold text-white/80"
                  style={{ zIndex: AVATARS.length - i }}
                >
                  {initials}
                </div>
              ))}
            </div>
            <div>
              <div className="flex items-center gap-0.5 text-[#F5B93E]">
                {[0, 1, 2, 3, 4].map((s) => (
                  <Star key={s} size={11} fill="currentColor" strokeWidth={0} />
                ))}
                <span className="ml-1.5 text-[10px] font-mono font-bold text-white/60">4.9</span>
              </div>
              <div className="mt-0.5 text-[10px] font-mono font-bold tracking-wider text-white/35">
                TRUSTED BY 1,200+ DEVICE OWNERS
              </div>
            </div>
          </div>

          {/* Footer strip */}
          <div className="mt-10 flex items-center gap-3 animate-fade-slide" style={{ animationDelay: '0.25s' }}>
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
            </span>
            <span className="text-[11px] font-mono font-bold tracking-wider text-white/40">
              ALL SYSTEMS OPERATIONAL
            </span>
            <span className="hidden xl:inline text-[11px] font-mono text-white/20 ml-2">24/7 · AES-256 · 3-LAYER PERSISTENCE</span>
          </div>
        </div>

        {/* ─── Right — Form ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-center px-5 sm:px-8 py-14">
          <div className={cn('w-full max-w-md transition-all duration-700', mounted ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4')}>
            {/* Mobile brand */}
            <Link href="/" className="lg:hidden inline-flex items-center gap-2.5 mb-10">
              <div className="w-9 h-9 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center overflow-hidden">
                <svg viewBox="0 0 120 120" className="w-5 h-5" fill="none" aria-label="Magneetar logo">
                  <path d="M27 88L27 38L60 82L93 38L93 88" stroke="url(#mob-grad)" strokeWidth="17" strokeLinecap="round" strokeLinejoin="round" />
                  <defs>
                    <linearGradient id="mob-grad" x1="27" y1="38" x2="93" y2="88">
                      <stop offset="0%" stopColor="#FFFFFF" />
                      <stop offset="100%" stopColor="#F3D3E6" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              <div className="leading-none">
                <div className="text-white text-[15px] font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-white/30 tracking-[0.3em] mt-1">COMMAND CENTER</div>
              </div>
            </Link>

            {/* Heading */}
            <div className="mb-8">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-4">
                <span className="relative flex w-1.5 h-1.5">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full w-1.5 h-1.5 bg-emerald-400" />
                </span>
                <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">SECURE ACCESS</span>
              </div>
              <h2 className="text-2xl font-display font-extrabold tracking-tight text-white">Welcome back</h2>
              <p className="mt-2 text-white/40 text-sm">
                Sign in to access your command center.
              </p>
            </div>

            {/* Spotlight glass card */}
            <div
              ref={cardRef}
              onMouseMove={handleCardMove}
              className="spotlight-card relative rounded-2xl border border-white/[0.08] bg-[#0d0d14]/85 backdrop-blur-xl p-7 sm:p-8 shadow-2xl shadow-black/50"
            >
              <div className="relative z-10">
                {/* Mode toggle */}
                <div role="group" aria-label="Login mode" className="relative flex bg-white/[0.02] rounded-xl p-1 mb-7 border border-white/[0.05]">
                  <div
                    aria-hidden="true"
                    className={cn(
                      'absolute top-1 bottom-1 left-1 w-[calc(50%-4px)] rounded-lg bg-gradient-to-r from-[#E91E8C]/20 to-[#06B6D4]/15 border border-white/[0.08] shadow-sm transition-transform duration-300 ease-out',
                      mode === 'apikey' ? 'translate-x-full' : 'translate-x-0'
                    )}
                  />
                  <button
                    type="button"
                    aria-pressed={mode === 'account'}
                    onClick={() => { setMode('account'); setError(''); }}
                    className={cn(
                      'relative flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 font-mono',
                      mode === 'account' ? 'text-white' : 'text-white/30 hover:text-white/60'
                    )}
                  >
                    Account
                  </button>
                  <button
                    type="button"
                    aria-pressed={mode === 'apikey'}
                    onClick={() => { setMode('apikey'); setError(''); }}
                    className={cn(
                      'relative flex-1 py-2.5 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-colors duration-200 font-mono',
                      mode === 'apikey' ? 'text-white' : 'text-white/30 hover:text-white/60'
                    )}
                  >
                    API Key
                  </button>
                </div>

                <form onSubmit={handleLogin} noValidate>
                  <div className="space-y-4">
                    {/* Server URL */}
                    <div className="space-y-1.5">
                      <label htmlFor="server-url" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Server URL
                      </label>
                      <div className="relative">
                        <Globe size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="server-url"
                          name="serverUrl"
                          type="text"
                          value={serverUrl}
                          onChange={(e) => setServerUrl(e.target.value)}
                          placeholder="https://api.magneetar.me"
                          autoComplete="url"
                          className={inputClass}
                          autoFocus
                        />
                      </div>
                    </div>

                    {mode === 'account' ? (
                      <>
                        <div className="space-y-1.5">
                          <label htmlFor="login-email" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                            Email
                          </label>
                          <div className="relative">
                            <Mail size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                            <input
                              id="login-email"
                              name="email"
                              type="email"
                              value={email}
                              onChange={(e) => setEmail(e.target.value)}
                              placeholder="you@example.com"
                              autoComplete="email"
                              className={inputClass}
                            />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <label htmlFor="login-password" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                            Password
                          </label>
                          <div className="relative">
                            <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                            <input
                              id="login-password"
                              name="password"
                              type={showPassword ? 'text' : 'password'}
                              value={password}
                              onChange={(e) => setPassword(e.target.value)}
                              placeholder="Enter your password"
                              autoComplete="current-password"
                              className={cn(inputClass, 'pr-11')}
                            />
                            <button
                              type="button"
                              onClick={() => setShowPassword((v) => !v)}
                              aria-label={showPassword ? 'Hide password' : 'Show password'}
                              className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/70 transition-colors"
                            >
                              {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                            </button>
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="space-y-1.5">
                        <label htmlFor="api-key-input" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                          API Key
                        </label>
                        <div className="relative">
                          <KeyRound size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                          <input
                            id="api-key-input"
                            name="apiKey"
                            type="password"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            placeholder="Enter your master API key"
                            autoComplete="off"
                            className={inputClass}
                          />
                        </div>
                      </div>
                    )}

                    {/* Error */}
                    {error && (
                      <div
                        key={error}
                        className="flex items-center gap-3 text-red-400/90 text-[12px] font-mono bg-red-500/[0.05] border border-red-500/15 rounded-xl px-4 py-3 animate-shake"
                        role="alert"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="shrink-0" aria-hidden="true">
                          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        <span>{error}</span>
                      </div>
                    )}

                    {/* Submit */}
                    <button
                      type="submit"
                      disabled={loading}
                      className="group relative w-full py-3.5 rounded-xl text-[12px] font-bold uppercase tracking-[0.2em] font-mono bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-lg shadow-[#E91E8C]/20 hover:shadow-[#E91E8C]/35 hover:brightness-110 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] overflow-hidden"
                    >
                      <span className="absolute inset-y-0 -left-full w-1/2 bg-white/15 blur-md animate-shimmer" />
                      <span className="relative flex items-center justify-center gap-2.5">
                        {loading ? (
                          <>
                            <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                            <span>Authenticating...</span>
                          </>
                        ) : (
                          <>
                            <span>Connect</span>
                            <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                          </>
                        )}
                      </span>
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Signup prompt */}
            <p className="mt-7 text-center text-[13px] text-white/40">
              New to Magneetar?{' '}
              <Link href="/signup" className="text-[#06B6D4] hover:text-[#22D3EE] font-semibold transition-colors">
                Create an account
              </Link>
            </p>

            {/* Security strip */}
            <div className="mt-8 flex items-center justify-center gap-5">
              {[
                { icon: Lock, label: 'AES-256' },
                { icon: KeyRound, label: 'BCRYPT' },
                { icon: ShieldCheck, label: 'RATE-LIMITED' },
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-1.5 text-white/25">
                  <item.icon size={10} />
                  <span className="text-[9px] font-mono font-bold tracking-wider">{item.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
