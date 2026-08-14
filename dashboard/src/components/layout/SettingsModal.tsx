'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { UserProfile } from '@/types';
import { X, Trash2, ShieldAlert, ShieldCheck, Crown, ArrowUpRight, Smartphone, Mail, RefreshCw, KeyRound, Plus, Copy, Check, Ban, RotateCcw } from 'lucide-react';
import { ApiKey, ApiKeyCreated, ApiKeyScope, ApiKeyType } from '@/types';

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

  // ── Developer API keys panel state ──────────────────────────────────────
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [showCreateKey, setShowCreateKey] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyScopes, setNewKeyScopes] = useState<ApiKeyScope[]>(['devices:read']);
  // 'live' (default) or 'readonly' — readonly keys can never carry
  // devices:write; switching to readonly strips it client-side (the server
  // enforces this too, at creation AND at every request).
  const [newKeyType, setNewKeyType] = useState<ApiKeyType>('live');
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const [keyPassword, setKeyPassword] = useState('');
  const [keyMsg, setKeyMsg] = useState('');
  const [keyError, setKeyError] = useState('');
  const [keyBusy, setKeyBusy] = useState(false);
  const [copiedKey, setCopiedKey] = useState(false);

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

  // ── Developer API keys handlers ─────────────────────────────────────────
  const ALL_SCOPES: { value: ApiKeyScope; label: string }[] = [
    { value: 'devices:read', label: 'devices:read — view devices & locations' },
    { value: 'devices:write', label: 'devices:write — issue commands' },
    { value: 'alerts:read', label: 'alerts:read — alert history' },
    { value: 'media:read', label: 'media:read — evidence media (owner)' },
  ];

  const loadApiKeys = async () => {
    setApiKeysLoading(true);
    setKeyError('');
    try {
      const res = await getAPI().getApiKeys();
      setApiKeys(res.api_keys.filter((k) => !k.revoked_at));
    } catch (e: any) {
      setKeyError(e.message || 'Could not load API keys');
    } finally {
      setApiKeysLoading(false);
    }
  };

  const toggleScope = (scope: ApiKeyScope) => {
    if (newKeyType === 'readonly' && scope === 'devices:write') return; // structurally impossible
    setNewKeyScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]
    );
  };

  const setKeyType = (t: ApiKeyType) => {
    setNewKeyType(t);
    if (t === 'readonly') {
      setNewKeyScopes((prev) => prev.filter((s) => s !== 'devices:write'));
    }
  };

  const createApiKey = async () => {
    setKeyBusy(true);
    setKeyError('');
    setKeyMsg('');
    try {
      if (!newKeyName.trim()) throw new Error('Give the key a name');
      if (!keyPassword) throw new Error('Enter your account password to confirm');
      if (newKeyScopes.length === 0) throw new Error('Select at least one scope');
      const res = await getAPI().createApiKey({
        name: newKeyName.trim(),
        scopes: newKeyScopes,
        key_type: newKeyType,
        password: keyPassword,
      });
      setCreatedKey(res);
      setApiKeys((prev) => [res, ...prev]);
      setKeyPassword('');
    } catch (e: any) {
      setKeyError(e.message || 'Could not create the key');
    } finally {
      setKeyBusy(false);
    }
  };

  const revokeApiKey = async (keyId: string) => {
    setKeyBusy(true);
    setKeyError('');
    setKeyMsg('');
    try {
      if (!keyPassword) throw new Error('Enter your account password to confirm');
      if (!window.confirm('Revoke this API key immediately? Every request using it will stop working.')) return;
      await getAPI().revokeApiKey(keyId, keyPassword);
      setApiKeys((prev) => prev.filter((k) => k.id !== keyId));
      setKeyPassword('');
      setKeyMsg('API key revoked.');
    } catch (e: any) {
      setKeyError(e.message || 'Could not revoke the key');
    } finally {
      setKeyBusy(false);
    }
  };

  const rotateApiKey = async (keyId: string) => {
    setKeyBusy(true);
    setKeyError('');
    setKeyMsg('');
    try {
      if (!keyPassword) throw new Error('Enter your account password to confirm');
      const res = await getAPI().rotateApiKey(keyId, keyPassword);
      setCreatedKey(res);
      setApiKeys((prev) => prev.filter((k) => k.id !== keyId).concat(res));
      setKeyPassword('');
    } catch (e: any) {
      setKeyError(e.message || 'Could not rotate the key');
    } finally {
      setKeyBusy(false);
    }
  };

  const copyFullKey = async () => {
    if (!createdKey) return;
    try {
      await navigator.clipboard.writeText(createdKey.key);
      setCopiedKey(true);
      setTimeout(() => setCopiedKey(false), 2000);
    } catch {
      // Clipboard unavailable — the key stays visible for manual copy.
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

        {/* Developer API keys (user accounts only — for third-party integrations) */}
        {authMode === 'user' && (
          <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
                <KeyRound size={12} />
                Developer API Keys
              </div>
              <button
                onClick={() => {
                  setShowCreateKey((v) => !v);
                  setCreatedKey(null);
                  setKeyError('');
                  setKeyMsg('');
                  if (!apiKeys.length && !apiKeysLoading) loadApiKeys();
                }}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-mag-border/40 text-[9px] font-mono font-bold text-mag-accent hover:text-emerald-300 hover:border-mag-accent/40 transition-all"
              >
                <Plus size={9} />
                {apiKeys.length ? 'MANAGE' : 'CREATE KEY'}
              </button>
            </div>

            <div className="text-[9px] font-mono text-mag-text-dim/50 leading-relaxed">
              Scoped keys for external integrations (scripts, resellers, custom dashboards). Keys
              can never exceed your account&apos;s own access — a viewer-shared device stays read-only
              through a key too.
            </div>

            {keyMsg && (
              <div className="text-[10px] font-mono text-emerald-300/90 bg-emerald-500/[0.06] border border-emerald-500/20 rounded-lg px-3 py-2 leading-relaxed">
                {keyMsg}
              </div>
            )}
            {keyError && (
              <div className="text-[10px] font-mono text-red-400/90 bg-red-500/[0.06] border border-red-500/20 rounded-lg px-3 py-2 leading-relaxed" role="alert">
                {keyError}
              </div>
            )}

            {showCreateKey && (
              <div className="space-y-3 animate-fade-in rounded-lg border border-mag-border/20 p-3">
                {/* Full key — shown exactly once */}
                {createdKey && (
                  <div className="space-y-2 bg-mag-bg/60 border border-emerald-500/30 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[9px] font-mono text-emerald-300 font-bold uppercase tracking-wider">
                        New key — copy it now, it won&apos;t be shown again
                      </span>
                      <button
                        onClick={copyFullKey}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-emerald-500/40 text-[9px] font-mono font-bold text-emerald-300 hover:bg-emerald-500/10 transition-all"
                      >
                        {copiedKey ? <Check size={9} /> : <Copy size={9} />}
                        {copiedKey ? 'COPIED' : 'COPY'}
                      </button>
                    </div>
                    <div className="text-[10px] font-mono text-mag-text font-bold break-all select-all leading-relaxed">
                      {createdKey.key}
                    </div>
                    <div className="text-[9px] font-mono text-mag-text-dim/50">
                      Prefix <span className="text-mag-text-dim/80">{createdKey.key_prefix}…</span> ·
                      {createdKey.key_type === 'readonly' ? ' read-only · ' : ' live · '}
                      scopes {createdKey.scopes.join(', ')}
                    </div>
                  </div>
                )}

                <input
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="Key name (e.g. reseller-sync)"
                  className={stepupInputClass}
                />

                <div className="flex gap-1.5">
                  {(['live', 'readonly'] as ApiKeyType[]).map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setKeyType(t)}
                      className={`flex-1 py-1.5 rounded-md border text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
                        newKeyType === t
                          ? t === 'readonly'
                            ? 'border-mag-accent/60 bg-mag-accent/10 text-mag-accent'
                            : 'border-mag-accent/60 bg-mag-accent/10 text-mag-accent'
                          : 'border-mag-border/30 text-mag-text-dim/50 hover:text-mag-text-dim/80'
                      }`}
                    >
                      {t === 'readonly' ? 'Read-only' : 'Live'}
                    </button>
                  ))}
                </div>
                <div className="text-[9px] font-mono text-mag-text-dim/50 -mt-1">
                  {newKeyType === 'readonly'
                    ? 'Read-only keys can never issue wipe/lock commands — enforced by the server even if leaked.'
                    : 'Live keys may carry write scopes (issue commands).'}
                </div>

                <div className="space-y-1.5">
                  {ALL_SCOPES.map((s) => {
                    const writeLocked = newKeyType === 'readonly' && s.value === 'devices:write';
                    return (
                      <label
                        key={s.value}
                        className={`flex items-center gap-2 text-[10px] font-mono transition-colors ${
                          writeLocked
                            ? 'cursor-not-allowed text-mag-text-dim/30'
                            : 'cursor-pointer text-mag-text-dim/70 hover:text-mag-text'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={newKeyScopes.includes(s.value)}
                          disabled={writeLocked}
                          onChange={() => toggleScope(s.value)}
                          className="accent-[#06B6D4]"
                        />
                        {s.label}
                        {writeLocked && ' (unavailable for read-only)'}
                      </label>
                    );
                  })}
                </div>

                <input
                  type="password"
                  value={keyPassword}
                  onChange={(e) => setKeyPassword(e.target.value)}
                  placeholder="Account password (confirm action)"
                  autoComplete="current-password"
                  className={stepupInputClass}
                />
                <button
                  onClick={createApiKey}
                  disabled={keyBusy}
                  className="w-full py-2 rounded-lg bg-mag-accent/90 hover:bg-mag-accent disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
                >
                  {keyBusy ? 'CREATING...' : 'Create Key'}
                </button>
              </div>
            )}

            {apiKeysLoading && (
              <div className="text-[9px] font-mono text-mag-text-dim/50 animate-pulse">Loading keys…</div>
            )}

            {apiKeys.length > 0 && (
              <div className="space-y-2">
                {apiKeys.map((k) => (
                  <div
                    key={k.id}
                    className="rounded-lg border border-mag-border/20 p-3 space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[11px] font-mono text-mag-text font-bold truncate">
                        {k.name}
                      </div>
                      <div className="text-[9px] font-mono text-mag-text-dim/50">
                        {k.key_prefix}…
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[8px] font-mono font-bold uppercase tracking-wider ${
                          k.key_type === 'readonly'
                            ? 'bg-mag-accent/10 text-mag-accent'
                            : 'bg-mag-border/20 text-mag-text-dim/60'
                        }`}
                      >
                        {k.key_type === 'readonly' ? 'read-only' : 'live'}
                      </span>
                      <span className="text-[9px] font-mono text-mag-text-dim/50">
                        {k.request_count} req
                      </span>
                    </div>
                    <div className="text-[9px] font-mono text-mag-text-dim/50 break-all">
                      {k.scopes.join(' · ')}
                      {k.expires_at && ` · expires ${new Date(k.expires_at).toLocaleDateString()}`}
                      {k.last_used_at && ` · used ${new Date(k.last_used_at).toLocaleDateString()}`}
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => rotateApiKey(k.id)}
                        disabled={keyBusy}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-mag-border/40 text-[9px] font-mono font-bold text-mag-text-dim/70 hover:text-mag-accent transition-all disabled:opacity-50"
                      >
                        <RotateCcw size={9} />
                        Rotate
                      </button>
                      <button
                        onClick={() => revokeApiKey(k.id)}
                        disabled={keyBusy}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-mag-danger/30 text-[9px] font-mono font-bold text-mag-danger/80 hover:text-mag-danger transition-all disabled:opacity-50"
                      >
                        <Ban size={9} />
                        Revoke
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
