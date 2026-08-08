'use client';

import { Suspense, useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useStore } from '@/store/useStore';
import { extractErrorMessage } from '@/lib/api';
import { Lock, Eye, EyeOff, ArrowLeft, KeyRound, CheckCircle2 } from 'lucide-react';

// The password strength rules mirror the server (models.py PasswordModel):
// >= 8 chars, at least one letter and one digit.
function passwordIssues(password: string): string | null {
  if (password.length < 8) return 'Password must be at least 8 characters.';
  if (!/[a-zA-Z]/.test(password)) return 'Password must contain at least one letter.';
  if (!/\d/.test(password)) return 'Password must contain at least one number.';
  return null;
}

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const { setCredentials, setConnected } = useStore();
  const email = searchParams.get('email') || '';
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [missingLink, setMissingLink] = useState(false);

  useEffect(() => {
    if (!email || !token) setMissingLink(true);
  }, [email, token]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const issues = passwordIssues(password);
    if (issues) {
      setError(issues);
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    setError('');
    const baseUrl = (typeof window !== 'undefined' && sessionStorage.getItem('mt_server_url')) || 'https://api.magneetar.me';
    try {
      const res = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, token, new_password: password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        const message = extractErrorMessage(body, 'Invalid or expired reset link');
        setError(res.status === 401 ? 'This reset link is invalid or expired — request a new one.' : message);
        setLoading(false);
        return;
      }
      // The server returns fresh tokens — the reset also signs the user in.
      const data = await res.json();
      sessionStorage.setItem('mt_server_url', baseUrl);
      sessionStorage.setItem('mt_api_key', data.token);
      sessionStorage.setItem('mt_refresh_token', data.refresh_token || '');
      sessionStorage.setItem('mt_auth_mode', 'user');
      setCredentials(baseUrl, data.token);
      setConnected(true);
      setDone(true);
    } catch (err: any) {
      setError(err.message || 'Connection failed. Try again.');
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
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />

      <div className="relative min-h-screen flex items-center justify-center px-5 sm:px-8 py-14">
        <div className="w-full max-w-md">
          <Link href="/" className="inline-flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center overflow-hidden">
              <svg viewBox="0 0 120 120" className="w-5 h-5" fill="none" aria-label="Magneetar logo">
                <path d="M30,90 L30,30 L42,30 L42,72 L60,48 L78,72 L78,30 L90,30 L90,90 L78,90 L78,66 L60,90 L42,66 L42,90 Z" stroke="url(#rp-grad)" fill="currentColor"  />
                <defs>
                  <linearGradient id="rp-grad" x1="27" y1="38" x2="93" y2="88">
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

          <div className="relative rounded-2xl border border-white/[0.08] bg-[#0d0d14]/85 backdrop-blur-xl p-7 sm:p-8 shadow-2xl shadow-black/50 spotlight-card">
            {missingLink ? (
              <div className="animate-fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/25 flex items-center justify-center">
                    <KeyRound size={17} className="text-red-400" />
                  </div>
                  <h2 className="text-lg font-display font-extrabold tracking-tight text-white">Broken reset link</h2>
                </div>
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  This link is missing its reset token. Request a fresh one — old links expire
                  after 30 minutes and can only be used once.
                </p>
                <Link
                  href="/forgot-password"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  Request a new link
                  <KeyRound size={13} />
                </Link>
              </div>
            ) : done ? (
              <div className="animate-fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center">
                    <CheckCircle2 size={18} className="text-emerald-400" />
                  </div>
                  <h2 className="text-lg font-display font-extrabold tracking-tight text-white">Password updated</h2>
                </div>
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  You&apos;re signed in with your new password. Taking you to your command center…
                </p>
                <a
                  href="/dashboard"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  Go to dashboard
                </a>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-[#06B6D4]/10 border border-[#06B6D4]/25 flex items-center justify-center">
                    <Lock size={17} className="text-[#06B6D4]" />
                  </div>
                  <div>
                    <h2 className="text-lg font-display font-extrabold tracking-tight text-white">Choose a new password</h2>
                    <div className="text-[10px] font-mono text-white/35 font-bold mt-0.5 uppercase tracking-[0.2em]">SECURE RECOVERY</div>
                  </div>
                </div>

                <p className="text-[13px] text-white/40 leading-relaxed mb-6">
                  For <span className="text-white/80 font-semibold">{email}</span>. Use at least 8 characters
                  with a mix of letters and numbers.
                </p>

                <form onSubmit={handleSubmit} noValidate className="space-y-4">
                  <div className="space-y-1.5">
                    <label htmlFor="rp-password" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                      New password
                    </label>
                    <div className="relative">
                      <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                      <input
                        id="rp-password"
                        name="new_password"
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="Enter a new password"
                        autoComplete="new-password"
                        className={`${inputClass} pr-11`}
                        autoFocus
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

                  <div className="space-y-1.5">
                    <label htmlFor="rp-confirm" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                      Confirm password
                    </label>
                    <div className="relative">
                      <Lock size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                      <input
                        id="rp-confirm"
                        name="confirm"
                        type={showPassword ? 'text' : 'password'}
                        value={confirm}
                        onChange={(e) => setConfirm(e.target.value)}
                        placeholder="Repeat the new password"
                        autoComplete="new-password"
                        className={inputClass}
                      />
                    </div>
                  </div>

                  {error && (
                    <div
                      key={error}
                      className="flex items-center gap-3 text-red-400/90 text-[12px] font-mono bg-red-500/[0.05] border border-red-500/15 rounded-xl px-4 py-3 animate-shake"
                      role="alert"
                    >
                      <span>{error}</span>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="group relative w-full py-3.5 rounded-xl text-[12px] font-bold uppercase tracking-[0.2em] font-mono bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-lg shadow-[#E91E8C]/20 hover:shadow-[#E91E8C]/35 hover:brightness-110 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98] overflow-hidden"
                  >
                    {loading ? 'Updating...' : 'Reset password & sign in'}
                  </button>
                </form>

                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 mt-5 py-1 text-[11px] font-mono font-bold uppercase tracking-wider text-white/30 hover:text-white/60 transition-colors"
                >
                  <ArrowLeft size={13} />
                  Back to sign in
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
