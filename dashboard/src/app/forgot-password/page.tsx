'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { extractErrorMessage } from '@/lib/api';
import { Mail, ArrowRight, ArrowLeft, ShieldCheck, CheckCircle2 } from 'lucide-react';

/**
 * Password reset request. The server deliberately returns the SAME response
 * for known and unknown addresses — this page never reveals whether an email
 * is registered.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email) {
      setError('Please enter your email address.');
      return;
    }
    setLoading(true);
    setError('');
    const baseUrl = (typeof window !== 'undefined' && sessionStorage.getItem('mt_server_url')) || 'https://api.magneetar.me';
    try {
      const res = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        throw new Error(extractErrorMessage(await res.json().catch(() => null), 'Could not request a reset link'));
      }
      await res.json();
      setSent(true);
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
          {/* Brand */}
          <Link href="/" className="inline-flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center overflow-hidden">
              <svg viewBox="0 0 120 120" className="w-5 h-5" fill="none" aria-label="Magneetar logo">
                <path d="M27 88L27 38L60 82L93 38L93 88" stroke="url(#fp-grad)" strokeWidth="17" strokeLinecap="round" strokeLinejoin="round" />
                <defs>
                  <linearGradient id="fp-grad" x1="27" y1="38" x2="93" y2="88">
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
            {sent ? (
              <div className="animate-fade-in">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center">
                    <CheckCircle2 size={18} className="text-emerald-400" />
                  </div>
                  <h2 className="text-lg font-display font-extrabold tracking-tight text-white">Check your inbox</h2>
                </div>
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  If <span className="text-white/80 font-semibold">{email}</span> is registered to an account,
                  a password reset link is on its way. The link expires within 30 minutes — and each
                  reset invalidates any previous link.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  <ArrowLeft size={13} />
                  Back to sign in
                </Link>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-[#06B6D4]/10 border border-[#06B6D4]/25 flex items-center justify-center">
                    <ShieldCheck size={17} className="text-[#06B6D4]" />
                  </div>
                  <div>
                    <h2 className="text-lg font-display font-extrabold tracking-tight text-white">Reset your password</h2>
                    <div className="text-[10px] font-mono text-white/35 font-bold mt-0.5 uppercase tracking-[0.2em]">ACCOUNT RECOVERY</div>
                  </div>
                </div>

                <p className="text-[13px] text-white/40 leading-relaxed mb-6">
                  Enter the email on your account and we&apos;ll send a secure, single-use reset link.
                </p>

                <form onSubmit={handleSubmit} noValidate className="space-y-4">
                  <div className="space-y-1.5">
                    <label htmlFor="fp-email" className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                      Email
                    </label>
                    <div className="relative">
                      <Mail size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/20 pointer-events-none" />
                      <input
                        id="fp-email"
                        name="email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="you@example.com"
                        autoComplete="email"
                        className={inputClass}
                        autoFocus
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
                    {loading ? (
                      <span className="flex items-center justify-center gap-2.5">
                        <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
                        Sending...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center gap-2.5">
                        Send reset link
                        <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
                      </span>
                    )}
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
