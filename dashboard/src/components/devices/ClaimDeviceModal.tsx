'use client';

import { useState, type FormEvent } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { Link2, X, Loader2, CheckCircle2, Smartphone } from 'lucide-react';

/**
 * "Link a device" modal — claims an ownerless device into the signed-in
 * account using the pairing code shown in the Magneetar app on the phone.
 *
 * The pairing code is the first 8 hex chars of SHA-256(device_key), displayed
 * on the phone's Home screen (tap to copy). Server-side this is rate-limited
 * per user (10/10 min) so the 32-bit code can't be brute-forced from the
 * dashboard. The device must be ownerless (or already owned by this account)
 * and the per-user device limit still applies.
 */
export function ClaimDeviceModal({ onClose }: { onClose: () => void }) {
  const { setDevices } = useStore();
  const [deviceId, setDeviceId] = useState('');
  const [pairingCode, setPairingCode] = useState('');
  const [error, setError] = useState('');
  const [claiming, setClaiming] = useState(false);
  const [successId, setSuccessId] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const id = deviceId.trim();
    const code = pairingCode.trim().toLowerCase();
    if (!id || !code) {
      setError('Enter both the device ID and the pairing code from the phone app.');
      return;
    }
    if (!/^[a-f0-9]{8}$/.test(code)) {
      setError('Pairing code must be 8 lowercase hex characters (from the Magneetar app).');
      return;
    }
    setClaiming(true);
    setError('');
    try {
      const api = getAPI();
      await api.claimDeviceByPairing(id, code);
      // Refresh the device list so the newly linked device appears.
      const { devices } = await api.getDevices();
      setDevices(devices);
      setSuccessId(id);
      setTimeout(onClose, 1200);
    } catch (err: any) {
      // Surface the server's reason verbatim — e.g. the device-limit message
      // ("delete a stale device or upgrade") so the user knows the fix.
      setError(err.message || 'Failed to link device.');
    } finally {
      setClaiming(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Link a device"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-md rounded-2xl border border-mag-border/50 bg-mag-panel/95 backdrop-blur-xl shadow-2xl shadow-black/60 overflow-hidden animate-fade-slide">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-mag-border/30">
          <div className="w-8 h-8 rounded-lg bg-mag-primary/15 border border-mag-primary/30 flex items-center justify-center shrink-0">
            <Link2 size={14} className="text-mag-accent" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-bold text-mag-text">Link a device</h3>
            <p className="text-[10px] font-mono text-mag-text-dim/50 mt-0.5">
              Claim an unlinked phone into this account
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-md text-mag-text-dim/50 hover:text-mag-text hover:bg-mag-surface/30 transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {successId ? (
          <div className="px-5 py-8 flex flex-col items-center gap-3 text-center">
            <CheckCircle2 size={28} className="text-mag-accent" />
            <div className="text-sm font-bold text-mag-text">Device linked</div>
            <div className="text-[11px] font-mono text-mag-text-dim/60 break-all">{successId}</div>
          </div>
        ) : (
          <form onSubmit={submit} className="p-5 space-y-4">
            {/* How-to hint */}
            <div className="flex items-start gap-2.5 rounded-xl border border-mag-border/30 bg-mag-bg/40 p-3">
              <Smartphone size={13} className="text-mag-primary/70 shrink-0 mt-0.5" />
              <p className="text-[10px] font-mono text-mag-text-dim/60 leading-relaxed">
                On the phone, open the Magneetar app → Home screen shows the
                <span className="text-mag-accent"> Device ID</span> and
                <span className="text-mag-accent"> Pairing code</span> (tap to copy).
                Enter them here to link this phone to your dashboard.
              </p>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="claim-device-id" className="text-[10px] font-mono text-mag-text-dim/60 font-bold uppercase tracking-wider">
                Device ID
              </label>
              <input
                id="claim-device-id"
                value={deviceId}
                onChange={e => setDeviceId(e.target.value)}
                placeholder="mt-1a2b3c4d"
                autoComplete="off"
                autoFocus
                className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2.5 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-primary/60 transition-colors"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="claim-pairing-code" className="text-[10px] font-mono text-mag-text-dim/60 font-bold uppercase tracking-wider">
                Pairing code
              </label>
              <input
                id="claim-pairing-code"
                value={pairingCode}
                onChange={e => setPairingCode(e.target.value)}
                placeholder="a1b2c3d4"
                autoComplete="off"
                maxLength={8}
                spellCheck={false}
                className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2.5 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-primary/60 transition-colors tracking-widest"
              />
            </div>

            {error && (
              <div className="text-[11px] font-mono text-red-400 bg-red-500/[0.06] border border-red-500/15 rounded-lg px-3 py-2.5 leading-relaxed">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={claiming}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-mag-primary/90 hover:bg-mag-primary disabled:opacity-50 text-white text-xs font-bold transition-all"
            >
              {claiming ? <Loader2 size={13} className="animate-spin" /> : <Link2 size={13} />}
              {claiming ? 'Linking…' : 'Link Device'}
            </button>
            <p className="text-[9px] font-mono text-mag-text-dim/35 text-center">
              Only ownerless phones can be linked. Attempts are rate-limited.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
