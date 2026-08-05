'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { UserProfile } from '@/types';
import { X, Trash2, ShieldAlert, ShieldCheck, Crown, ArrowUpRight, Smartphone, Mail, RefreshCw } from 'lucide-react';

const PLAN_LABELS: Record<string, string> = {
  free: 'FREE',
  personal: 'PERSONAL',
  guardian: 'GUARDIAN',
  enterprise: 'ENTERPRISE',
  admin: 'ADMIN',
};

/**
 * Settings modal (opened from the header gear). Account info + plan status +
 * the Danger Zone. Account deletion lives HERE — deliberately NOT in the main
 * header, where a stressed user could hit it by accident.
 */
export function SettingsModal({ onClose }: { onClose: () => void }) {
  const { serverUrl, logout } = useStore();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileUnavailable, setProfileUnavailable] = useState(false);

  // ── Security panel state (2FA + email verification) ─────────────────────
  const [twoFaStep, setTwoFaStep] = useState<'idle' | 'setup'>('idle');
  const [totpSecret, setTotpSecret] = useState('');
  const [qrDataUri, setQrDataUri] = useState('');
  const [stepupPassword, setStepupPassword] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [securityMsg, setSecurityMsg] = useState('');
  const [securityError, setSecurityError] = useState('');
  const [securityBusy, setSecurityBusy] = useState(false);

  const authMode =
    typeof window !== 'undefined' ? sessionStorage.getItem('mt_auth_mode') : null;

  // Plan status is only meaningful for user accounts (API-key admins have no
  // /api/auth/me row). Load it quietly — a slow/failed fetch must never block
  // the settings panel.
  useEffect(() => {
    if (authMode !== 'user') return;
    let cancelled = false;
    getAPI()
      .fetchMe()
      .then((me) => {
        if (!cancelled) setProfile(me);
      })
      .catch(() => {
        if (!cancelled) setProfileUnavailable(true);
      });
    return () => {
      cancelled = true;
    };
  }, [authMode]);

  const usagePct = profile && profile.max_devices > 0
    ? Math.min(100, Math.round((profile.device_count / profile.max_devices) * 100))
    : 0;
  const atLimit = profile ? profile.device_count >= profile.max_devices : false;

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await getAPI().deleteAccount();
      logout();
      window.location.href = '/login';
    } catch (e: any) {
      setError(e.message || 'Account deletion failed');
      setDeleting(false);
    }
  };

  // ── Security handlers ────────────────────────────────────────────────────
  const startTwoFactorSetup = async () => {
    setSecurityBusy(true);
    setSecurityError('');
    setSecurityMsg('');
    try {
      const res = await getAPI().setupTwoFactor();
      setTotpSecret(res.secret);
      setQrDataUri(res.qr_svg_data_uri);
      setTwoFaStep('setup');
    } catch (e: any) {
      setSecurityError(e.message || 'Could not start 2FA setup');
    } finally {
      setSecurityBusy(false);
    }
  };

  const confirmTwoFactorEnable = async () => {
    setSecurityBusy(true);
    setSecurityError('');
    setSecurityMsg('');
    try {
      const res = await getAPI().enableTwoFactor(stepupPassword, totpCode);
      if (res.totp_enabled) {
        setProfile((p) => (p ? { ...p, totp_enabled: true } : p));
        setTwoFaStep('idle');
        setTotpSecret('');
        setQrDataUri('');
        setStepupPassword('');
        setTotpCode('');
        setSecurityMsg('Two-factor authentication is now ON — your account is protected by a second factor.');
      }
    } catch (e: any) {
      setSecurityError(e.message || 'Could not enable 2FA — check your password and code');
    } finally {
      setSecurityBusy(false);
    }
  };

  const disableTwoFactor = async () => {
    setSecurityBusy(true);
    setSecurityError('');
    setSecurityMsg('');
    try {
      const res = await getAPI().disableTwoFactor(stepupPassword);
      if (!res.totp_enabled) {
        setProfile((p) => (p ? { ...p, totp_enabled: false } : p));
        setStepupPassword('');
        setSecurityMsg('Two-factor authentication is now OFF.');
      }
    } catch (e: any) {
      setSecurityError(e.message || 'Could not disable 2FA — check your password');
    } finally {
      setSecurityBusy(false);
    }
  };

  const resendVerification = async () => {
    setSecurityBusy(true);
    setSecurityError('');
    setSecurityMsg('');
    try {
      const res = await getAPI().resendVerificationEmail();
      setSecurityMsg(res.message);
    } catch (e: any) {
      setSecurityError(e.message || 'Could not send the verification email');
    } finally {
      setSecurityBusy(false);
    }
  };

  const stepupInputClass =
    'w-full px-3 py-2 bg-mag-bg/60 border border-mag-border/40 rounded-lg text-[11px] font-mono text-mag-text ' +
    'placeholder:text-mag-text-dim/40 focus:outline-none focus:border-mag-accent/50 focus:ring-1 focus:ring-mag-accent/20 transition-all';

  // Rendered through a portal into document.body. The modal used to live
  // inside the <header>, whose backdrop-blur (backdrop-filter) establishes a
  // containing block for fixed-position descendants — the "fixed" modal was
  // contained by the 56px header and clipped by its overflow-hidden, so
  // clicking SETTINGS appeared to do nothing.
  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative mag-panel w-full max-w-md p-6 space-y-6 animate-fade-in shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-mag-text tracking-wide">SETTINGS</h2>
            <div className="text-[9px] font-mono text-mag-text-dim/50 uppercase tracking-[0.2em] font-bold mt-0.5">
              Account &amp; security
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="w-8 h-8 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text hover:border-mag-border flex items-center justify-center transition-all"
          >
            <X size={14} />
          </button>
        </div>

        {/* Account */}
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-2">
          <div className="text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-1">
            Account
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Auth Mode</span>
            <span className="text-[11px] font-mono text-mag-accent font-bold">
              {authMode === 'user' ? 'USER ACCOUNT' : 'API KEY'}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Server</span>
            <span className="text-[11px] font-mono text-mag-text font-bold truncate max-w-[220px]">
              {serverUrl}
            </span>
          </div>
          <div className="text-[10px] font-mono text-mag-text-dim/40 leading-relaxed pt-2 border-t border-mag-border/20">
            Alert recipients (SMS / WhatsApp / email) are set per device under Location →
            Alert Settings.
          </div>
        </div>

        {/* Plan */}
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4">
          <div className="text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2">
            Plan
          </div>
          {authMode === 'user' && profile ? (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Current plan</span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-mag-accent/10 border border-mag-accent/30 text-[10px] font-mono font-bold text-mag-accent uppercase tracking-wider">
                  <Crown size={10} />
                  {PLAN_LABELS[profile.tier] || profile.tier.toUpperCase()}
                </span>
              </div>
              <div>
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-mag-text-dim/60 font-bold">Devices</span>
                  <span className={atLimit ? 'text-amber-400 font-bold' : 'text-mag-text font-bold'}>
                    {profile.device_count} / {profile.max_devices >= 999 ? '∞' : profile.max_devices}
                  </span>
                </div>
                <div className="mt-1.5 h-1 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      atLimit
                        ? 'bg-amber-400'
                        : 'bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]'
                    }`}
                    style={{ width: `${usagePct}%` }}
                  />
                </div>
              </div>
              {atLimit ? (
                <div className="text-[10px] font-mono text-amber-300/80 leading-relaxed">
                  Device limit reached — upgrade your plan to protect more devices.
                </div>
              ) : (
                <div className="text-[10px] font-mono text-mag-text-dim/50 leading-relaxed">
                  Free plans protect 1 device. Upgrade for up to 3 (₦500/mo) or 10 (₦1500/mo).
                </div>
              )}
              <a
                href="/#pricing"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-mag-accent hover:text-emerald-300 transition-colors"
              >
                See plans &amp; pricing
                <ArrowUpRight size={11} />
              </a>
            </div>
          ) : authMode === 'user' && profileUnavailable ? (
            <div className="text-[10px] font-mono text-mag-text-dim/50">
              Plan info unavailable — check your connection.
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Access</span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-[10px] font-mono font-bold text-emerald-300 uppercase tracking-wider">
                <Crown size={10} />
                ADMIN · UNLIMITED
              </span>
            </div>
          )}
        </div>

        {/* Security (user accounts only — API-key admins have no account row) */}
        {authMode === 'user' && (
          <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
              <ShieldCheck size={12} />
              Security
            </div>

            {securityMsg && (
              <div className="text-[10px] font-mono text-emerald-300/90 bg-emerald-500/[0.06] border border-emerald-500/20 rounded-lg px-3 py-2 leading-relaxed">
                {securityMsg}
              </div>
            )}
            {securityError && (
              <div className="text-[10px] font-mono text-red-400/90 bg-red-500/[0.06] border border-red-500/20 rounded-lg px-3 py-2 leading-relaxed" role="alert">
                {securityError}
              </div>
            )}

            {/* Email verification */}
            <div className="rounded-lg border border-mag-border/20 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[11px] font-mono text-mag-text font-bold">
                  <Mail size={12} className="text-mag-text-dim/60" />
                  Email verified
                </div>
                {profile?.email_verified ? (
                  <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-[9px] font-mono font-bold text-emerald-300 uppercase tracking-wider">
                    VERIFIED
                  </span>
                ) : (
                  <button
                    onClick={resendVerification}
                    disabled={securityBusy}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-mag-border/40 text-[9px] font-mono font-bold text-mag-accent hover:text-emerald-300 hover:border-mag-accent/40 transition-all disabled:opacity-50"
                  >
                    <RefreshCw size={9} />
                    {securityBusy ? 'SENDING...' : 'RESEND EMAIL'}
                  </button>
                )}
              </div>
              {!profile?.email_verified && (
                <div className="text-[9px] font-mono text-mag-text-dim/50 leading-relaxed">
                  Verifying your email unlocks account recovery — a reset link can only be sent to a
                  verified address.
                </div>
              )}
            </div>

            {/* Two-factor authentication */}
            <div className="rounded-lg border border-mag-border/20 p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[11px] font-mono text-mag-text font-bold">
                  <Smartphone size={12} className="text-mag-text-dim/60" />
                  Two-factor auth
                </div>
                {profile?.totp_enabled ? (
                  <span className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-[9px] font-mono font-bold text-emerald-300 uppercase tracking-wider">
                    ENABLED
                  </span>
                ) : (
                  <button
                    onClick={startTwoFactorSetup}
                    disabled={securityBusy}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-mag-border/40 text-[9px] font-mono font-bold text-mag-accent hover:text-emerald-300 hover:border-mag-accent/40 transition-all disabled:opacity-50"
                  >
                    <ShieldCheck size={9} />
                    {securityBusy ? 'STARTING...' : 'ENABLE'}
                  </button>
                )}
              </div>

              {twoFaStep === 'setup' && (
                <div className="space-y-3 animate-fade-in">
                  <div className="text-[9px] font-mono text-mag-text-dim/50 leading-relaxed">
                    Scan the QR code with Google Authenticator (or any TOTP app), then confirm with your
                    password + a fresh code.
                  </div>
                  <div className="flex items-center gap-3">
                    {qrDataUri && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={qrDataUri}
                        alt="TOTP setup QR code"
                        className="w-28 h-28 rounded-lg border border-mag-border/40 bg-white p-1"
                      />
                    )}
                    <div className="text-[9px] font-mono text-mag-text-dim/50 leading-relaxed">
                      Can&apos;t scan? Manual secret:
                      <div className="mt-1 font-mono text-[10px] text-mag-text font-bold break-all select-all">
                        {totpSecret}
                      </div>
                    </div>
                  </div>
                  <input
                    type="password"
                    value={stepupPassword}
                    onChange={(e) => setStepupPassword(e.target.value)}
                    placeholder="Account password"
                    autoComplete="current-password"
                    className={stepupInputClass}
                  />
                  <input
                    inputMode="numeric"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    placeholder="6-digit code"
                    autoComplete="one-time-code"
                    className={`${stepupInputClass} tracking-[0.3em]`}
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={confirmTwoFactorEnable}
                      disabled={securityBusy}
                      className="flex-1 py-2 rounded-lg bg-mag-accent/90 hover:bg-mag-accent disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
                    >
                      {securityBusy ? 'CONFIRMING...' : 'Confirm & Enable'}
                    </button>
                    <button
                      onClick={() => { setTwoFaStep('idle'); setTotpSecret(''); setQrDataUri(''); setSecurityError(''); }}
                      className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {profile?.totp_enabled && (
                <div className="space-y-2 animate-fade-in">
                  <div className="text-[9px] font-mono text-mag-text-dim/50 leading-relaxed">
                    Sign-in now requires a code from your authenticator app. Disabling requires your
                    account password.
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={stepupPassword}
                      onChange={(e) => setStepupPassword(e.target.value)}
                      placeholder="Account password"
                      autoComplete="current-password"
                      className={stepupInputClass}
                    />
                    <button
                      onClick={disableTwoFactor}
                      disabled={securityBusy}
                      className="px-4 py-2 rounded-lg border border-mag-danger/30 text-mag-danger/90 hover:text-mag-danger hover:border-mag-danger/60 text-[10px] font-mono font-bold uppercase tracking-wider transition-all whitespace-nowrap"
                    >
                      {securityBusy ? 'DISABLING...' : 'Disable'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Danger Zone */}
        <div className="bg-mag-danger/[0.03] border border-mag-danger/20 rounded-xl p-4">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-danger uppercase tracking-wider font-bold mb-2">
            <ShieldAlert size={12} />
            Danger Zone
          </div>
          {!confirmDelete ? (
            <button
              onClick={() => { setConfirmDelete(true); setError(''); }}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-mag-danger/30 text-mag-danger/90 hover:text-mag-danger hover:border-mag-danger/60 hover:bg-mag-danger/[0.05] text-[11px] font-mono font-bold uppercase tracking-wider transition-all"
            >
              <Trash2 size={13} />
              Delete Account Permanently
            </button>
          ) : (
            <div className="space-y-2.5">
              <div className="text-[11px] font-mono text-mag-danger/90 leading-relaxed">
                Permanently delete this account and ALL linked devices? Every location,
                media file, evidence case, alert and recovery request is erased. This
                cannot be undone.
              </div>
              {error && <div className="text-[10px] font-mono text-red-400">{error}</div>}
              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[11px] font-bold transition-all"
                >
                  <Trash2 size={12} />
                  {deleting ? 'DELETING...' : 'Yes, Delete Everything'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleting}
                  className="px-4 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[11px] font-bold transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
