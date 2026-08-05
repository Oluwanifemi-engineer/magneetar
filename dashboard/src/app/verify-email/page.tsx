'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { BadgeCheck, ShieldCheck, KeyRound, ArrowLeft, Loader2 } from 'lucide-react';

function VerifyEmailForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token') || '';

  type State = 'verifying' | 'verified' | 'broken' | 'expired' | 'error';
  const [state, setState] = useState<State>('verifying');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState('broken');
      return;
    }

    const baseUrl = (typeof window !== 'undefined' && sessionStorage.getItem('mt_server_url')) || 'https://api.magneetar.me';
    (async () => {
      try {
        const res = await fetch(`${baseUrl.replace(/\/+$/, '')}/api/auth/verify-email`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token }),
        });
        if (cancelled) return;
        if (res.ok) {
          setState('verified');
        } else if (res.status === 401) {
          setState('expired');
        } else {
          const body = await res.json().catch(() => null);
          setErrorMsg(body?.detail || `Verification failed (HTTP ${res.status})`);
          setState('error');
        }
      } catch (err: any) {
        if (cancelled) return;
        setErrorMsg(err?.message || 'Connection failed. Check your connection and try again.');
        setState('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  const header = (icon: React.ReactNode, title: string, subtitle: string) => (
    <div className="flex items-center gap-3 mb-4">
      {icon}
      <div>
        <h2 className="text-lg font-display font-extrabold tracking-tight text-white">{title}</h2>
        <div className="text-[10px] font-mono text-white/35 font-bold mt-0.5 uppercase tracking-[0.2em]">{subtitle}</div>
      </div>
    </div>
  );

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
                <path d="M27 88L27 38L60 82L93 38L93 88" stroke="url(#ve-grad)" strokeWidth="17" strokeLinecap="round" strokeLinejoin="round" />
                <defs>
                  <linearGradient id="ve-grad" x1="27" y1="38" x2="93" y2="88">
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
            {state === 'verifying' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-[#06B6D4]/10 border border-[#06B6D4]/25 flex items-center justify-center">
                    <Loader2 size={17} className="text-[#06B6D4] animate-spin" />
                  </div>,
                  'Verifying your email',
                  'ACCOUNT SECURITY'
                )}
                <p className="text-[13px] text-white/45 leading-relaxed">
                  Confirming your verification link with the Magneetar server…
                </p>
              </div>
            )}

            {state === 'verified' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center">
                    <BadgeCheck size={18} className="text-emerald-400" />
                  </div>,
                  'Email verified',
                  'SECURE ACCOUNT'
                )}
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  Your email is confirmed. This strengthens account recovery and unlocks
                  password-reset links — your Magneetar account is now fully secured.
                </p>
                <a
                  href="/dashboard"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  Go to dashboard
                </a>
              </div>
            )}

            {state === 'broken' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/25 flex items-center justify-center">
                    <KeyRound size={17} className="text-red-400" />
                  </div>,
                  'Broken verification link',
                  'INVALID LINK'
                )}
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  This link is missing its verification token. Sign in and request a fresh
                  verification email from Settings → Security.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  <ArrowLeft size={13} />
                  Back to sign in
                </Link>
              </div>
            )}

            {state === 'expired' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-center">
                    <KeyRound size={17} className="text-amber-400" />
                  </div>,
                  'Link expired',
                  'REQUEST A NEW ONE'
                )}
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  Verification links are single-use and expire after 24 hours. Sign in and
                  resend a fresh verification email from Settings → Security.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  <ArrowLeft size={13} />
                  Back to sign in
                </Link>
              </div>
            )}

            {state === 'error' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/25 flex items-center justify-center">
                    <ShieldCheck size={17} className="text-red-400" />
                  </div>,
                  'Could not verify',
                  'TRY AGAIN'
                )}
                <p className="text-[13px] text-white/45 leading-relaxed mb-6">
                  {errorMsg || 'Something went wrong while verifying your email.'}
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-[#06B6D4] hover:text-[#22D3EE] transition-colors"
                >
                  <ArrowLeft size={13} />
                  Back to sign in
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailForm />
    </Suspense>
  );
}
