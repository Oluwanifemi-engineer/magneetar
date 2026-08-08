'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  ShieldCheck,
  Users,
  Radar,
  MapPin,
  Send,
  Bell,
  X,
  Heart,
} from 'lucide-react';
import {
  GuardianProfile,
  RecoveryRequest,
  NearbyRecoveryRequest,
} from '@/types';
import { GuardianSkeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

/**
 * Guardian Network panel — community recovery for stolen devices.
 *
 * Two faces of the same feature:
 *  - OWNER: launch a recovery request for a stolen device, watch guardian
 *    sightings stream in, and close the request when the device is recovered.
 *  - GUARDIAN: opt in to help, see blurred nearby recovery requests, and
 *    report sightings anonymously (by public handle).
 */
export function GuardianPanel() {
  const { devices, selectedDeviceId, latestLocation } = useStore();
  const { toast } = useToast();
  const device = devices.find(d => d.id === selectedDeviceId);
  const isStolen = device?.is_stolen === true;

  const [profile, setProfile] = useState<GuardianProfile | null>(null);
  const [requests, setRequests] = useState<RecoveryRequest[]>([]);
  const [nearby, setNearby] = useState<NearbyRecoveryRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // Guardian opt-in form
  const [optRadius, setOptRadius] = useState(20);
  const [optHandle, setOptHandle] = useState('');

  // Sighting form
  const [sightingNote, setSightingNote] = useState('');
  const [sightingLat, setSightingLat] = useState('');
  const [sightingLng, setSightingLng] = useState('');
  const [activeNearby, setActiveNearby] = useState<NearbyRecoveryRequest | null>(null);

  const load = useCallback(async () => {
    try {
      const api = getAPI();
      const [prof, reqs] = await Promise.all([
        api.getGuardianProfile(),
        api.getRecoveryRequests(),
      ]);
      setProfile(prof);
      setRequests(reqs.requests || []);
      setOptRadius(prof.radius_km || 20);
      setOptHandle(prof.handle || '');
    } catch (e: any) {
      setErr(e?.message || 'Failed to load guardian data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [load]);

  // Scope to the SELECTED device — with multiple devices, each may have its
  // own active recovery request, and the panel must only act on the one
  // belonging to the device currently being viewed.
  const activeRequest = requests.find(r => r.status === 'active' && r.device_id === device?.id);

  // ── Owner actions ───────────────────────────────────────────────────────

  const handleLaunch = async () => {
    if (!device) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const api = getAPI();
      const req = await api.launchRecovery(device.id, undefined);
      setRequests(prev => [req, ...prev.filter(r => r.id !== req.id)]);
      const msg = 'Recovery request launched — guardians near the last known location will see it.';
      setMsg(msg);
      toast(msg, 'success');
    } catch (e: any) {
      setErr(e?.message || 'Failed to launch recovery request');
    } finally {
      setBusy(false);
    }
  };

  const handleClose = async (requestId: string) => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const api = getAPI();
      const res = await api.closeRecovery(requestId);
      setRequests(prev =>
        prev.map(r => (r.id === requestId ? { ...r, status: 'closed' as const } : r))
      );
      const msg = res.message || 'Recovery request closed — device marked recovered.';
      setMsg(msg);
      toast(msg, 'success');
    } catch (e: any) {
      setErr(e?.message || 'Failed to close recovery request');
    } finally {
      setBusy(false);
    }
  };

  // ── Guardian actions ────────────────────────────────────────────────────

  const handleOptIn = async () => {
    setBusy(true);
    setErr(null);
    try {
      const api = getAPI();
      const prof = await api.setGuardianOptIn({
        opted_in: !profile?.opted_in,
        radius_km: optRadius,
        handle: optHandle,
      });
      setProfile(prof);
      const msg = prof.opted_in ? 'You are now a Guardian.' : 'Guardian mode off.';
      setMsg(msg);
      toast(msg, 'success');
    } catch (e: any) {
      setErr(e?.message || 'Failed to update guardian profile');
    } finally {
      setBusy(false);
    }
  };

  const loadNearby = async () => {
    setBusy(true);
    setErr(null);
    setNearby([]);
    setActiveNearby(null);
    try {
      // Use the selected device's latest location (or a default) as "where I am".
      const lat = latestLocation?.lat ?? 9.082;
      const lng = latestLocation?.lng ?? 8.6753;
      const api = getAPI();
      const res = await api.getNearbyRecovery(lat, lng, optRadius);
      setNearby(res.requests || []);
      if (res.requests?.length === 0) setMsg('No active recovery requests nearby.');
    } catch (e: any) {
      setErr(e?.message || 'Failed to load nearby requests');
    } finally {
      setBusy(false);
    }
  };

  const openSightingForm = (r: NearbyRecoveryRequest) => {
    setActiveNearby(r);
    setSightingLat('');
    setSightingLng('');
    setSightingNote('');
    setErr(null);
  };

  const handleReportSighting = async () => {
    if (!activeNearby) return;
    const lat = parseFloat(sightingLat);
    const lng = parseFloat(sightingLng);
    if (isNaN(lat) || isNaN(lng)) {
      setErr('Enter valid latitude and longitude for the sighting.');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const api = getAPI();
      const res = await api.reportSighting({
        request_id: activeNearby.id,
        lat,
        lng,
        note: sightingNote || undefined,
      });
      const msg = `Sighting reported as "${res.guardian_handle}". The owner will be notified.`;
      setMsg(msg);
      toast(msg, 'success');
      setActiveNearby(null);
    } catch (e: any) {
      setErr(e?.message || 'Failed to report sighting');
    } finally {
      setBusy(false);
    }
  };

  const isGuardian = profile?.opted_in === true;

  return (
    <div className="p-4 space-y-4">
      {/* ── Mode header ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
        <ShieldCheck size={12} className="text-mag-primary" />
        Guardian Network
      </div>

      {msg && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-mag-accent/[0.05] border border-mag-accent/20 text-[11px] text-mag-accent/90">
          <span className="flex-1">{msg}</span>
          <button onClick={() => setMsg(null)} aria-label="Dismiss message">
            <X size={12} />
          </button>
        </div>
      )}
      {err && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-mag-danger/[0.05] border border-mag-danger/20 text-[11px] text-mag-danger/90">
          <span className="flex-1">{err}</span>
          <button onClick={() => setErr(null)} aria-label="Dismiss error">
            <X size={12} />
          </button>
        </div>
      )}

      {loading ? (
        <GuardianSkeleton />
      ) : (
        <>
          {/* ── Owner: launch / track recovery ─────────────────────────── */}
          <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-3">
              <Radar size={11} className="text-mag-primary" />
              My Recovery Requests
            </div>

            {!device ? (
              <div className="text-center py-6">
                <div className="w-10 h-10 rounded-xl bg-mag-surface/40 border border-mag-border/30 flex items-center justify-center mx-auto mb-2">
                  <Radar size={16} className="text-mag-text-dim/25" />
                </div>
                <div className="text-mag-text-dim/50 text-xs font-bold">Select a device</div>
                <div className="text-mag-text-dim/30 text-[10px] font-mono mt-1">Choose a device from the sidebar to manage recovery.</div>
              </div>
            ) : isStolen && !activeRequest ? (
              <button
                onClick={handleLaunch}
                disabled={busy}
                className="w-full mag-btn-primary text-[11px]"
              >
                <Bell size={13} />
                {busy ? 'Launching…' : 'Launch Community Recovery'}
              </button>
            ) : isStolen && activeRequest ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-[11px] text-mag-warning font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-mag-warning animate-pulse-slow" />
                  ACTIVE — {activeRequest.sighting_count} sighting{activeRequest.sighting_count !== 1 ? 's' : ''}
                </div>
                <button
                  onClick={() => handleClose(activeRequest.id)}
                  disabled={busy}
                  className="w-full mag-btn-secondary text-[11px]"
                >
                  <ShieldCheck size={13} />
                  {busy ? 'Closing…' : 'Mark Recovered & Close'}
                </button>
              </div>
            ) : (
              <div className="text-center py-4">
                <Heart size={20} className="mx-auto text-mag-text-dim/15 mb-2" />
                <div className="text-mag-text-dim/50 text-[11px] font-bold">
                  {requests.length === 0 ? 'No recovery requests yet' : 'Device is secure'}
                </div>
                <div className="text-mag-text-dim/30 text-[10px] font-mono mt-1 leading-relaxed max-w-[220px] mx-auto">
                  {requests.length === 0
                    ? 'When a device is marked stolen, you can launch a community recovery request to get help from nearby guardians.'
                    : 'Your device is not currently stolen. No recovery action needed.'}
                </div>
              </div>
            )}

            {/* Sighting feed */}
            {activeRequest && activeRequest.sightings.length > 0 && (
              <div className="mt-3 space-y-2 max-h-44 overflow-y-auto">
                {activeRequest.sightings.map(s => (
                  <div key={s.id} className="px-3 py-2 rounded-lg bg-mag-bg/40 border border-mag-border/20">
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-primary font-bold">
                      <Users size={10} />
                      {s.guardian_handle}
                      <span className="ml-auto text-mag-text-dim/30 normal-case font-medium">
                        {s.created_at ? new Date(s.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-1 text-[10px] font-mono text-mag-text-dim/60">
                      <MapPin size={9} />
                      {s.lat.toFixed(4)}, {s.lng.toFixed(4)}
                    </div>
                    {s.note && <div className="mt-1 text-[11px] text-mag-text/80">{s.note}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Guardian: opt in & nearby ─────────────────────────────── */}
          <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-3">
              <Users size={11} className="text-mag-secondary" />
              Guardian Mode
            </div>

            <div className="flex items-center justify-between mb-3">
              <div className="text-[11px] text-mag-text/80">
                {isGuardian ? 'You are helping recover devices.' : 'Help recover stolen devices nearby.'}
              </div>
              <button
                onClick={handleOptIn}
                disabled={busy}
                className={cn(
                  'relative w-9 h-5 rounded-full transition-colors duration-200',
                  isGuardian ? 'bg-mag-accent' : 'bg-mag-bg/60 border border-mag-border/40'
                )}
                aria-label={isGuardian ? 'Turn guardian mode off' : 'Turn guardian mode on'}
              >
                <span
                  className={cn(
                    'absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all duration-200 shadow',
                    isGuardian ? 'left-[18px]' : 'left-0.5'
                  )}
                />
              </button>
            </div>

            {isGuardian && (
              <>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <label className="text-[10px] font-mono text-mag-text-dim/50">
                    Radius (km)
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={optRadius}
                      onChange={e => setOptRadius(parseInt(e.target.value) || 20)}
                      className="mag-input mt-1 text-xs py-1.5"
                    />
                  </label>
                  <label className="text-[10px] font-mono text-mag-text-dim/50">
                    Public handle
                    <input
                      type="text"
                      maxLength={40}
                      value={optHandle}
                      onChange={e => setOptHandle(e.target.value)}
                      placeholder="e.g. NightWatch"
                      className="mag-input mt-1 text-xs py-1.5"
                    />
                  </label>
                </div>

                <button
                  onClick={loadNearby}
                  disabled={busy}
                  className="w-full mag-btn-primary text-[11px] mb-2"
                >
                  <Radar size={13} />
                  {busy ? 'Scanning…' : 'Scan Nearby Requests'}
                </button>

                {nearby.length > 0 && (
                  <div className="space-y-2 max-h-52 overflow-y-auto">
                    {nearby.map(r => (
                      <div key={r.id} className="px-3 py-2 rounded-lg bg-mag-bg/40 border border-mag-border/20">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-bold text-mag-text truncate max-w-[60%]">
                            {r.device_model || 'Device'}
                          </span>
                          <span className="text-[10px] font-mono text-mag-warning font-bold">
                            ~{r.distance_km} km
                          </span>
                        </div>
                        {r.description && (
                          <div className="mt-0.5 text-[10px] text-mag-text-dim/60 truncate">{r.description}</div>
                        )}
                        <div className="mt-1 text-[9px] font-mono text-mag-text-dim/40">
                          Area ≈ {r.blurred_lat.toFixed(2)}, {r.blurred_lng.toFixed(2)} · {r.sighting_count} sightings
                        </div>
                        <button
                          onClick={() => openSightingForm(r)}
                          className="mt-2 w-full mag-btn-secondary text-[10px] py-1.5"
                        >
                          <MapPin size={11} />
                          Report Sighting
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {activeNearby && (
                  <div className="mt-3 space-y-2 p-3 rounded-lg bg-mag-bg/40 border border-mag-primary/25">
                    <div className="text-[10px] font-mono text-mag-text-dim/60">
                      Report sighting — {activeNearby.device_model || 'device'} (~{activeNearby.distance_km} km away)
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <input
                        type="number"
                        step="any"
                        value={sightingLat}
                        onChange={e => setSightingLat(e.target.value)}
                        placeholder="Latitude"
                        className="mag-input text-xs py-1.5"
                      />
                      <input
                        type="number"
                        step="any"
                        value={sightingLng}
                        onChange={e => setSightingLng(e.target.value)}
                        placeholder="Longitude"
                        className="mag-input text-xs py-1.5"
                      />
                    </div>
                    <input
                      type="text"
                      maxLength={300}
                      value={sightingNote}
                      onChange={e => setSightingNote(e.target.value)}
                      placeholder="Where did you see it? (optional)"
                      className="mag-input text-xs py-1.5"
                    />
                    <button
                      onClick={handleReportSighting}
                      disabled={busy}
                      className="w-full mag-btn-primary text-[10px] py-1.5"
                    >
                      <Send size={11} />
                      {busy ? 'Sending…' : 'Submit Sighting'}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
