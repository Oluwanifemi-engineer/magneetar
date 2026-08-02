'use client';

import { useEffect, useRef, useState, type MouseEvent, type FormEvent } from 'react';
import Link from 'next/link';
import { useStore } from '@/store/useStore';
import { extractErrorMessage } from '@/lib/api';
import { Mail, Lock, User, ArrowRight, Globe, Check, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';

const PERKS = [
  'Track unlimited smart devices under one email',
  'Sentinel AI theft detection with instant alerts',
  'Remote lock, wipe, siren & evidence capture',
  'Forensic-grade PDF reports for recovery',
];

export default function SignupPage() {
  const { setCredentials, setConnected } = useStore();

  const [serverUrl, setServerUrl] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMounted(true); }, []);

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

  const handleSignup = async (e: FormEvent) => {
    e.preventDefault();
    if (!serverUrl) {
      setError('Please enter your server URL.');
      return;
    }
    if (!email || !password) {
      setError('Please enter your email and password.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    setError('');

    const baseUrl = serverUrl.replace(/\/+$/, '');

    try {
      const res = await fetch(`${baseUrl}/api/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          display_name: displayName || undefined,
        }),
      });
      if (!res.ok) {
        throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Registration failed'));
      }
      const data = await res.json();
      sessionStorage.setItem('mt_server_url', baseUrl);
      sessionStorage.setItem('mt_api_key', data.token);
      sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
      sessionStorage.setItem('mt_auth_mode', 'user');
      setCredentials(baseUrl, data.token);
      setConnected(true);

      window.location.href = '/dashboard';
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.');
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
                    stroke="url(#signup-grad)"
                    strokeWidth="17"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <defs>
                    <linearGradient id="signup-grad" x1="27" y1="38" x2="93" y2="88">
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
              One account.
              <br />
              <span className="text-gradient-primary animate-gradient-x">Every device protected.</span>
            </h1>
            <p className="mt-5 text-white/45 leading-relaxed max-w-md text-[15px] animate-fade-slide" style={{ animationDelay: '0.1s' }}>
              Register your email, then link every smart device you own to a single command center.
            </p>
          </div>

          {/* Perks */}
          <div className="relative my-10 space-y-4 animate-fade-slide" style={{ animationDelay: '0.15s' }}>
            {PERKS.map((perk) => (
              <div key={perk} className="flex items-start gap-3.5">
                <div className="w-6 h-6 rounded-full border border-[#22C55E]/25 bg-[#22C55E]/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Check size={12} className="text-[#22C55E]" />
                </div>
                <span className="text-white/55 text-[13.5px] leading-relaxed">{perk}</span>
              </div>
            ))}
          </div>

          {/* Live stat strip */}
          <div className="relative grid grid-cols-3 gap-3 max-w-md animate-fade-slide" style={{ animationDelay: '0.2s' }}>
            {[
              { value: 'FREE', label: 'to start' },
              { value: '24/7', label: 'stealth tracking' },
              { value: '∞', label: 'devices per email' },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3">
                <div className="text-white text-sm font-bold font-mono tabular-nums">{stat.value}</div>
                <div className="text-[9px] font-mono text-white/35 uppercase tracking-wider mt-0.5 font-semibold">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>

          {/* Footer strip */}
          <div className="mt-10 flex items-center gap-3 animate-fade-slide" style={{ animationDelay: '0.25s' }}>
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
            </span>
            <span className="text-[11px] font-mono font-bold tracking-wider text-white/40">
              FREE TO START · NO CARD REQUIRED
            </span>
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
                <ShieldCheck size={11} className="text-[#06B6D4]" />
                <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">FREE · NO CARD REQUIRED</span>
              </div>
              <h2 className="text-2xl font-display font-extrabold tracking-tight text-white">Create your account</h2>
              <p className="mt-2 text-white/40 text-sm">
                Free forever for individuals. Set up in under a minute.
              </p>
            </div>

            {/* Spotlight glass card */}
            <div
              ref={cardRef}
              onMouseMove={handleCardMove}
              className="spotlight-card relative rounded-2xl border border-white/[0.08] bg-[#0d0d14]/85 backdrop-blur-xl p-7 sm:p-8 shadow-2xl shadow-black/50"
            >
              <div className="relative z-10">
                <form onSubmit={handleSignup} noValidate>
                  <div className="space-y-4">
                    {/* Server URL */}
                    <div className="space-y-1.5">
                      <label htmlFor="signup-server-url" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Server URL
                      </label>
                      <div className="relative">
                        <Globe size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="signup-server-url"
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

                    {/* Display name */}
                    <div className="space-y-1.5">
                      <label htmlFor="signup-name" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Display Name <span className="text-white/20 normal-case">(optional)</span>
                      </label>
                      <div className="relative">
                        <User size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="signup-name"
                          name="displayName"
                          type="text"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          placeholder="Jane Doe"
                          autoComplete="name"
                          className={inputClass}
                        />
                      </div>
                    </div>

                    {/* Email */}
                    <div className="space-y-1.5">
                      <label htmlFor="signup-email" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Email
                      </label>
                      <div className="relative">
                        <Mail size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="signup-email"
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

                    {/* Password */}
                    <div className="space-y-1.5">
                      <label htmlFor="signup-password" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Password
                      </label>
                      <div className="relative">
                        <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="signup-password"
                          name="password"
                          type={showPassword ? 'text' : 'password'}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="Min. 8 characters"
                          autoComplete="new-password"
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

                    {/* Confirm */}
                    <div className="space-y-1.5">
                      <label htmlFor="signup-confirm" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                        Confirm Password
                      </label>
                      <div className="relative">
                        <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                        <input
                          id="signup-confirm"
                          name="confirm"
                          type="password"
                          value={confirmPassword}
                          onChange={(e) => setConfirmPassword(e.target.value)}
                          placeholder="Repeat your password"
                          autoComplete="new-password"
                          className={inputClass}
                        />
                      </div>
                    </div>

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
                            <span>Creating account...</span>
                          </>
                        ) : (
                          <>
                            <span>Create Account</span>
                            <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                          </>
                        )}
                      </span>
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Login prompt */}
            <p className="mt-7 text-center text-[13px] text-white/40">
              Already have an account?{' '}
              <Link href="/login" className="text-[#06B6D4] hover:text-[#22D3EE] font-semibold transition-colors">
                Sign in
              </Link>
            </p>

            {/* Security strip */}
            <div className="mt-8 flex items-center justify-center gap-5">
              {[
                { icon: Lock, label: 'BCRYPT' },
                { icon: ShieldCheck, label: 'RATE-LIMITED' },
                { icon: Mail, label: 'AUDITED' },
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
