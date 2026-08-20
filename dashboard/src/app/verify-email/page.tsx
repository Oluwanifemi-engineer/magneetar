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
        <h2 className="text-lg font-display font-extrabold tracking-tight text-gray-900">{title}</h2>
        <div className="text-[10px] font-mono text-gray-900/35 font-bold mt-0.5 uppercase tracking-[0.2em]">{subtitle}</div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-white text-gray-900 relative overflow-hidden">
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-mag-primary/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />

      <div className="relative min-h-screen flex items-center justify-center px-5 sm:px-8 py-14">
        <div className="w-full max-w-md">
          <Link href="/" className="inline-flex items-center gap-2.5 mb-8">
            <div className="w-9 h-9 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center overflow-hidden">
              <svg viewBox="0 0 120 120" className="w-5 h-5" fill="none" aria-label="Magneetar logo">
                <path
                  d="M 29,90 V 43 C 29,25 68,25 68,43 V 90 L 91,29 V 90"
                  fill="white"
                />
              </svg>
            </div>
            <div className="leading-none">
              <div className="text-gray-900 text-[15px] font-bold tracking-[0.25em]">MAGNEETAR</div>
              <div className="text-[8px] font-mono text-gray-900/30 tracking-[0.3em] mt-1">COMMAND CENTER</div>
            </div>
          </Link>

          <div className="relative rounded-2xl border border-white/[0.08] bg-mag-panel/85 backdrop-blur-xl p-7 sm:p-8 shadow-2xl shadow-black/50 spotlight-card">
            {state === 'verifying' && (
              <div className="animate-fade-in">
                {header(
                  <div className="w-10 h-10 rounded-xl bg-mag-primary/10 border border-mag-primary/25 flex items-center justify-center">
                    <Loader2 size={17} className="text-mag-primary animate-spin" />
                  </div>,
                  'Verifying your email',
                  'ACCOUNT SECURITY'
                )}
                <p className="text-[13px] text-gray-500 leading-relaxed">
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
                <p className="text-[13px] text-gray-500 leading-relaxed mb-6">
                  Your email is confirmed. This strengthens account recovery and unlocks
                  password-reset links — your Magneetar account is now fully secured.
                </p>
                <a
                  href="/dashboard"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-mag-primary hover:text-mag-primary-bright transition-colors"
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
                <p className="text-[13px] text-gray-500 leading-relaxed mb-6">
                  This link is missing its verification token. Sign in and request a fresh
                  verification email from Settings → Security.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-mag-primary hover:text-mag-primary-bright transition-colors"
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
                <p className="text-[13px] text-gray-500 leading-relaxed mb-6">
                  Verification links are single-use and expire after 24 hours. Sign in and
                  resend a fresh verification email from Settings → Security.
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-mag-primary hover:text-mag-primary-bright transition-colors"
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
                <p className="text-[13px] text-gray-500 leading-relaxed mb-6">
                  {errorMsg || 'Something went wrong while verifying your email.'}
                </p>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 py-2 text-[11px] font-mono font-bold uppercase tracking-wider text-mag-primary hover:text-mag-primary-bright transition-colors"
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
