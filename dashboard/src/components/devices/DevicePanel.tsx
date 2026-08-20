'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useStore } from '@/store/useStore';
import { cn, relativeTime, formatCoordinate, deviceDisplayName, stepUpPasswordHint } from '@/lib/utils';
import { BellRing, MapPin, LocateFixed, Navigation, ExternalLink, Download, Save, Check, Trash2, X, Pencil, MessageSquareText, Users, UserPlus, UserMinus, ShieldCheck } from 'lucide-react';
import { CoordDisplay } from '@/components/ui/CoordDisplay';
import { getAPI } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import type { DeviceShare, ShareRole } from '@/types';

// Role labels for the access badge (Milestone 2 P1 family sharing).
const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  viewer: 'Viewer',
  device_only: 'Device-only',
};

// G1-17: system location MODE labels + explanations. The badge only renders
// for DEGRADED modes — high_accuracy is the healthy state and stays silent.
const LOCATION_MODE_LABEL: Record<string, string> = {
  battery_saving: 'Battery-saving',
  gps_only: 'GPS only',
  off: 'Location off',
};
const LOCATION_MODE_HINT: Record<string, string> = {
  battery_saving:
    'Battery-saving mode disables GPS — fixes are network-only (100-500m), even outdoors. Switch the phone to High accuracy for precise tracking.',
  gps_only:
    'GPS-only mode turns off Wi-Fi/cell scanning — the device cannot be located indoors. Switch to High accuracy for precise tracking.',
  off: 'Location services are OFF on the device — no fixes at all until re-enabled.',
};

// All toggleable alert types, mirroring server alerts.ALL_ALERT_TYPES. The
// emergency types (theft, SIM change, factory reset) always deliver and are
// locked in the UI; the rest can be silenced per-device. Keeping the list in
// sync here matters because toggling ANY type sends this exact set to the
// server as the stored enabled_types override.
const ALL_ALERT_TYPES = [
  'theft_detected',
  'sim_changed',
  'factory_reset',
  'battery_low',
  'device_offline',
  'device_recovered',
  'geofence_exit',
];

// All alert channels, mirroring server alerts.ALL_CHANNELS. An empty selection
// means "use the global defaults" (all four fire).
const ALL_CHANNELS = ['email', 'whatsapp', 'sms', 'push'];

export function DevicePanel() {
  const { devices, selectedDeviceId, latestLocation, setDevices, selectDevice } = useStore();
  const { toast } = useToast();
  const device = devices.find(d => d.id === selectedDeviceId);

  // ── Access role (Milestone 2 P1 RBAC) ───────────────────────────────────
  // owner (implicit) > admin > viewer > device_only. The SERVER enforces every
  // rule; these flags only hide controls a granted user cannot use anyway.
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = device?.access_role ?? 'owner';
  const canManage = accessRole === 'owner' || accessRole === 'admin'; // rename, settings, commands
  const canReadLocation = canManage || accessRole === 'viewer'; // coords, history, evidence
  const isOwner = accessRole === 'owner'; // delete, share grant/revoke

  // Alert recipient settings state (per-device override of global defaults)
  const [alertPhone, setAlertPhone] = useState('');
  const [alertEmail, setAlertEmail] = useState('');
  const [alertChannels, setAlertChannels] = useState<string[] | null>(null);
  const [enabledTypes, setEnabledTypes] = useState<string[] | null>(null);
  const [quietStart, setQuietStart] = useState<number | null>(null);
  const [quietEnd, setQuietEnd] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  // Offline Command Relay (SMS): when the device is offline (no data), the
  // dashboard can still reach it over SMS. Owner opt-in only — the toggle
  // defaults to OFF (SMS costs money + is a real attack surface).
  const [smsPhone, setSmsPhone] = useState('');
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [smsSaving, setSmsSaving] = useState(false);
  const [smsSaved, setSmsSaved] = useState(false);
  const [smsError, setSmsError] = useState('');
  const [showSmsSettings, setShowSmsSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  // Step-up password: permanent deletion re-authenticates (account password
  // for users, master API key for the admin dashboard) — a stolen session
  // alone must not destroy a device's history.
  const [deletePassword, setDeletePassword] = useState('');

  // Device rename state (uses the existing PATCH /alias endpoint)
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [nameSaving, setNameSaving] = useState(false);
  const [nameError, setNameError] = useState('');
  // Location-history CSV export (v1.5 — Prey-parity portable history)
  const [exporting, setExporting] = useState(false);
  // Device sharing (Milestone 2 P1) — invite by email, role picker, revoke.
  const [shares, setShares] = useState<DeviceShare[]>([]);
  const [showShares, setShowShares] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<ShareRole>('viewer');
  const [shareSaving, setShareSaving] = useState(false);
  const [shareError, setShareError] = useState('');
  const [shareMsg, setShareMsg] = useState('');

  const fetchShares = useCallback(async (deviceId: string) => {
    try {
      const res = await getAPI().getShares(deviceId);
      setShares(res.shares ?? []);
    } catch {
      setShares([]); // non-fatal — the sharing card simply stays empty
    }
  }, []);

  const inviteShare = async (e: FormEvent) => {
    e.preventDefault();
    if (!device || shareSaving) return;
    const email = inviteEmail.trim();
    if (!email) {
      setShareError("Enter the recipient's email address.");
      return;
    }
    setShareSaving(true);
    setShareError('');
    setShareMsg('');
    try {
      await getAPI().addShare(device.id, email, inviteRole);
      setInviteEmail('');
      setShareMsg(`Access granted (${inviteRole}) — they'll see this device when they sign in.`);
      await fetchShares(device.id);
    } catch (err: any) {
      setShareError(err?.message || 'Failed to share device');
    } finally {
      setShareSaving(false);
    }
  };

  const revokeShare = async (shareId: string) => {
    if (!device) return;
    try {
      await getAPI().revokeShare(device.id, shareId);
      await fetchShares(device.id);
      toast('Access revoked', 'success');
    } catch (err: any) {
      toast(err?.message || 'Failed to revoke access', 'error');
    }
  };

  const exportCsv = async () => {
    if (!device || exporting) return;
    setExporting(true);
    try {
      const blob = await getAPI().exportLocationsCSV(device.id);
      // (up to 10k rows) — a 0-byte file means no history recorded yet
      if (blob.size === 0) {
        toast('No location history to export yet', 'error');
      } else {
        toast('Location history exported', 'success');
      }
    } catch (e: any) {
      toast(e?.message || 'Failed to export location history', 'error');
    } finally {
      setExporting(false);
    }
  };

  // Sync form fields when the selected device changes
  const deviceKey = device?.id;
  const [lastDeviceKey, setLastDeviceKey] = useState<string | undefined>(undefined);
  if (deviceKey && deviceKey !== lastDeviceKey) {
    setLastDeviceKey(deviceKey);
    setAlertPhone(device?.alert_phone || '');
    setAlertEmail(device?.alert_email || '');
    setAlertChannels(device?.alert_channels ?? null);
    setEnabledTypes(device?.enabled_types ?? null);
    setQuietStart(device?.quiet_hours_start ?? null);
    setQuietEnd(device?.quiet_hours_end ?? null);
    setSmsPhone(device?.sms_phone || '');
    setSmsEnabled(device?.sms_commands_enabled ?? false);
    setError('');
    setSaved(false);
    setSmsError('');
    setSmsSaved(false);
    setEditingName(false);
    setNameError('');
    setDeletePassword('');
    setDeleteError('');
    setShares([]);
    setShowShares(false);
    setShareError('');
    setShareMsg('');
    setInviteEmail('');
  }

  // Load the share list whenever the selected device changes.
  useEffect(() => {
    if (deviceKey) fetchShares(deviceKey);
  }, [deviceKey, fetchShares]);

  const confirmDeleteDevice = async () => {
    if (!device || deleting) return;
    if (!deletePassword.trim()) {
      setDeleteError('Enter your password to confirm.');
      return;
    }
    setDeleting(true);
    setDeleteError('');
    try {
      await getAPI().deleteDevice(device.id, deletePassword);
      const { devices: freshDevices } = await getAPI().getDevices();
      setDevices(freshDevices);
      // If the deleted device was selected, move to the first remaining
      // device so the panel doesn't go stale.
      if (selectedDeviceId === device.id) {
        selectDevice(freshDevices[0]?.id ?? null);
      }
      setConfirmDelete(false);
      setDeletePassword('');
    } catch (e: any) {
      setDeleteError(e.message || 'Failed to delete device');
      // Keep the confirm card open so the error stays visible.
    } finally {
      setDeleting(false);
    }
  };

  const saveDeviceName = async (e: FormEvent) => {
    e.preventDefault();
    if (!device) return;
    const alias = nameDraft.trim();
    if (!alias) {
      setNameError('Name cannot be empty');
      return;
    }
    setEditingName(false);
    setNameSaving(true);
    setNameError('');
    try {
      await getAPI().updateDeviceAlias(device.id, alias);
      toast('Device renamed', 'success');
      // Refresh the device list so the sidebar + header pick up the new name
      const { devices: freshDevices } = await getAPI().getDevices();
      setDevices(freshDevices);
    } catch (err: any) {
      setNameError(err.message || 'Failed to rename device');
      setEditingName(true);
    } finally {
      setNameSaving(false);
    }
  };

  const saveSmsSettings = async () => {
    if (!device || smsSaving) return;
    setSmsSaving(true);
    setSmsError('');
    setSmsSaved(false);
    try {
      const res = await getAPI().updateSmsSettings(device.id, smsPhone.trim(), smsEnabled);
      setSmsPhone(res.sms_phone || '');
      setSmsEnabled(res.sms_commands_enabled);
      setSmsSaved(true);
      toast('SMS relay settings saved', 'success');
      // Refresh the device list so the stored relay settings stay in sync
      try {
        const { devices: freshDevices } = await getAPI().getDevices();
        setDevices(freshDevices);
      } catch {
        /* non-fatal — UI already reflects the saved values */
      }
      setTimeout(() => setSmsSaved(false), 2000);
    } catch (e: any) {
      setSmsError(e.message || 'Failed to save SMS settings');
    } finally {
      setSmsSaving(false);
    }
  };

  const saveAlertSettings = async () => {
    if (!device) return;
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await getAPI().updateDeviceAlertSettings(device.id, alertPhone.trim(), alertEmail.trim(), {
        alert_channels: alertChannels && alertChannels.length ? alertChannels : null,
        enabled_types: enabledTypes && enabledTypes.length ? enabledTypes : null,
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
      });
      setSaved(true);
      toast('Alert settings saved', 'success');
      // Refresh the device list so the stored recipients stay in sync
      try {
        const { devices: freshDevices } = await getAPI().getDevices();
        setDevices(freshDevices);
      } catch {
        /* non-fatal — UI already reflects the saved values */
      }
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setError(e.message || 'Failed to save alert settings');
    } finally {
      setSaving(false);
    }
  };

  // Toggle helpers for channel/type chip sets (null = use global defaults)
  const toggleChannel = (ch: string) => {
    setAlertChannels(prev => {
      const base = prev ?? ALL_CHANNELS;
      return base.includes(ch) ? base.filter(c => c !== ch) : [...base, ch];
    });
  };

  const toggleType = (t: string) => {
    setEnabledTypes(prev => {
      const base = prev ?? ALL_ALERT_TYPES;
      return base.includes(t) ? base.filter(x => x !== t) : [...base, t];
    });
  };

  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-14 h-14 rounded-2xl bg-gray-50/40 border border-gray-200/30 flex items-center justify-center mb-4">
          <MapPin size={24} className="text-gray-600/25" />
        </div>
        <div className="text-gray-600/60 text-sm font-bold mb-1">
          No device selected
        </div>
        <div className="text-gray-600/35 text-xs font-mono leading-relaxed max-w-[200px]">
          Select a device from the sidebar to view its details, location, alert settings, and capture status.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Device Header (with inline rename) */}
      <div className="bg-gray-50/40 border border-gray-200/40 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2.5 h-2.5 rounded-full bg-gray-100 shadow-[0_0_10px_rgba(233,30,140,0.5)] shrink-0" />
          {device.archived_at && (
            <span
              className="text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border border-amber-500/30 text-amber-400 bg-amber-500/10 shrink-0"
              title={`Archived ${relativeTime(device.archived_at)} — the device has been silent for a long time. Delete it here (password-gated) or wait for it to report again.`}
            >
              Archived
            </span>
          )}
          {/* Shared-access badge — shown only when this account does NOT own
              the device (Milestone 2 P1 family sharing). The server enforces
              the role; this is the user-facing label. */}
          {!isOwner && (
            <span
              className={cn(
                'text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0',
                accessRole === 'admin'
                  ? 'border-gray-900/40 text-gray-900 bg-gray-100/10'
                  : accessRole === 'viewer'
                    ? 'border-gray-900/40 text-gray-900 bg-gray-100/10'
                    : 'border-mag-text-dim/40 text-gray-600/80 bg-mag-text-dim/10'
              )}
              title={`Shared access — ${accessRole} role. ${
                accessRole === 'admin' ? 'Full control.' : accessRole === 'viewer' ? 'Read-only.' : 'Status only (no location).'
              }`}
            >
              {ROLE_LABEL[accessRole] ?? accessRole}
            </span>
          )}
          {/* G1-17 location MODE badge — only when accuracy is silently
              degraded (Battery-saving = no GPS, GPS-only = no WiFi/cell,
              off = nothing). high_accuracy/unknown stay silent; the phone's
              own 24h nudge covers the fix, this badge explains it. */}
          {device.location_mode && LOCATION_MODE_LABEL[device.location_mode] && (
            <span
              className={cn(
                'text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0',
                device.location_mode === 'off'
                  ? 'border-red-500/40 text-red-400 bg-red-500/10'
                  : 'border-amber-500/40 text-amber-400 bg-amber-500/10'
              )}
              title={LOCATION_MODE_HINT[device.location_mode]}
            >
              {LOCATION_MODE_LABEL[device.location_mode]}
            </span>
          )}
          {editingName ? (
            <form onSubmit={saveDeviceName} className="flex items-center gap-1.5 flex-1 min-w-0">
              <input
                value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                autoFocus
                maxLength={60}
                aria-label="Device name"
                className="flex-1 min-w-0 bg-white/60 border border-gray-900/40 rounded-lg px-2 py-1 text-sm font-bold text-gray-900 focus:outline-none focus:border-gray-900/70 transition-colors"
              />
              <button
                type="submit"
                disabled={nameSaving}
                aria-label="Save device name"
                className="p-1.5 rounded-md bg-gray-100/90 hover:bg-gray-100 disabled:opacity-50 text-white transition-colors"
              >
                <Check size={13} />
              </button>
              <button
                type="button"
                onClick={() => setEditingName(false)}
                aria-label="Cancel rename"
                className="p-1.5 rounded-md border border-gray-200/40 text-gray-600/60 hover:text-gray-900 transition-colors"
              >
                <X size={13} />
              </button>
            </form>
          ) : (
            <>
              <h3 className="text-base font-bold text-gray-900 truncate flex-1 min-w-0">
                {deviceDisplayName(device)}
              </h3>
              {canManage && (
                <button
                  onClick={() => {
                    setNameDraft(deviceDisplayName(device));
                    setNameError('');
                    setEditingName(true);
                  }}
                  aria-label="Rename device"
                  title="Rename device"
                  className="p-1.5 rounded-md border border-gray-200/40 text-gray-600/50 hover:text-gray-900 hover:border-gray-900/40 transition-colors"
                >
                  <Pencil size={12} />
                </button>
              )}
            </>
          )}
        </div>
        {nameError && <div className="text-[10px] font-mono text-red-400 mb-2">{nameError}</div>}

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Device ID</span>
            <span className="text-[11px] font-mono text-gray-900 font-bold">{device.id}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Registered</span>
            <span className="text-[11px] font-mono text-gray-600 font-bold">{relativeTime(device.registered)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Last Seen</span>
            <span className="text-[11px] font-mono text-gray-600 font-bold">{relativeTime(device.last_seen)}</span>
          </div>
          {/* Armed Watch state — the honest "capture posture": remote photo &
              audio capture only works while the device's capture service is
              armed (Android 14+ can't background-start a camera/mic service). */}
          <div className="flex justify-between items-center" title={
            device.capture_armed == null
              ? 'Capture state not reported yet (update the app).'
              : device.capture_armed
                ? 'Armed — remote photo & audio capture ready.'
                : 'Unarmed — open the app or tap “Re-arm” on the phone to re-enable capture.'
          }>
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Capture</span>
            {device.capture_armed == null ? (
              <span className="text-[11px] font-mono text-gray-600/40 font-bold">Unknown</span>
            ) : device.capture_armed ? (
              <span className="text-[11px] font-mono text-emerald-400 font-bold">Armed</span>
            ) : (
              <span className="text-[11px] font-mono text-amber-400 font-bold">Unarmed</span>
            )}
          </div>
        </div>
      </div>

      {/* Coordinates */}
      {latestLocation && (
        <CoordDisplay lat={latestLocation.lat} lng={latestLocation.lng} />
      )}

      {/* Location Details */}
      {latestLocation && (
        <div className="bg-gray-50/30 border border-gray-200/30 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-gray-600/70 uppercase tracking-wider font-bold mb-2">
            <LocateFixed size={12} className="text-gray-900" />
            Location Details
          </div>

          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Provider</span>
            <span className="text-[11px] font-mono text-gray-900 font-bold">{latestLocation.provider}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-gray-600/60 font-bold">Accuracy</span>
            <span className="text-[11px] font-mono text-gray-900 font-bold">±{latestLocation.accuracy?.toFixed(1) || '?'}m</span>
          </div>
          {latestLocation.speed != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-gray-600/60 font-bold">Speed</span>
              <span className="text-[11px] font-mono text-gray-900 font-bold">{(latestLocation.speed * 3.6).toFixed(1)} km/h</span>
            </div>
          )}
          {latestLocation.altitude != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-gray-600/60 font-bold">Altitude</span>
              <span className="text-[11px] font-mono text-gray-900 font-bold">{latestLocation.altitude.toFixed(0)}m</span>
            </div>
          )}
          {latestLocation.bearing != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-gray-600/60 font-bold">Bearing</span>
              <span className="text-[11px] font-mono text-gray-900 font-bold">{latestLocation.bearing.toFixed(0)}°</span>
            </div>
          )}
        </div>
      )}

      {/* Open in Maps */}
      {latestLocation && (
        <a
          href={`https://www.google.com/maps?q=${latestLocation.lat},${latestLocation.lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 py-3 rounded-xl border border-gray-200/40 text-gray-600 hover:text-gray-900 hover:border-gray-200 transition-all text-xs font-bold"
        >
          <ExternalLink size={14} />
          Open in Google Maps
        </a>
      )}

      {/* Export location history (CSV) — viewer+ only (device_only has no
          location access at all) */}
      {canReadLocation && (
        <button
          onClick={exportCsv}
          disabled={exporting}
          title="Download the full location history as CSV (law-enforcement handover, insurance claims, local analysis)"
          className="flex items-center justify-center gap-2 py-3 rounded-xl border border-gray-200/40 text-gray-600 hover:text-gray-900 hover:border-gray-900/50 hover:bg-gray-100/[0.04] transition-all text-xs font-bold disabled:opacity-50"
        >
          <Download size={14} />
          {exporting ? 'Exporting…' : 'Export Location History (CSV)'}
        </button>
      )}

      {/* Device Sharing (Milestone 2 P1) — invite family by email, pick a
          role, revoke. Owner manages grants; admins see the list read-only. */}
      {canManage && (
        <div className="bg-gray-50/30 border border-gray-200/30 rounded-xl p-4 space-y-3">
          <button
            onClick={() => setShowShares(!showShares)}
            className="w-full flex items-center justify-between text-[11px] font-mono text-gray-600/80 uppercase tracking-wider font-bold hover:text-gray-900 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <Users size={12} className="text-gray-900" />
              Sharing
              {shares.length > 0 && (
                <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-gray-100/15 text-gray-900 border border-gray-900/25">
                  {shares.length}
                </span>
              )}
            </span>
            <span className="text-gray-600/50">{showShares ? '−' : '+'}</span>
          </button>

          {showShares && (
            <div className="space-y-2.5 pt-1">
              {isOwner ? (
                <form onSubmit={inviteShare} className="space-y-2">
                  <div>
                    <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                      Share with (account email)
                    </label>
                    <input
                      value={inviteEmail}
                      onChange={e => setInviteEmail(e.target.value)}
                      placeholder="family@example.com"
                      type="email"
                      aria-label="Recipient email"
                      className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-600/30 focus:outline-none focus:border-gray-900/60 transition-colors"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                      Role
                    </label>
                    <select
                      value={inviteRole}
                      onChange={e => setInviteRole(e.target.value as ShareRole)}
                      aria-label="Share role"
                      className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 focus:outline-none focus:border-gray-900/60 transition-colors"
                    >
                      <option value="viewer">Viewer — read only</option>
                      <option value="admin">Admin — full control</option>
                      <option value="device_only">Device-only — status glance, no location</option>
                    </select>
                  </div>
                  <button
                    type="submit"
                    disabled={shareSaving}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-gray-100/90 hover:bg-gray-100 disabled:opacity-50 text-white text-xs font-bold transition-all"
                  >
                    <UserPlus size={13} />
                    {shareSaving ? 'Sharing...' : 'Share device'}
                  </button>
                  {shareError && <div className="text-[10px] font-mono text-red-400">{shareError}</div>}
                  {shareMsg && (
                    <div className="flex items-start gap-1.5 text-[10px] font-mono text-gray-900 leading-relaxed">
                      <ShieldCheck size={11} className="shrink-0 mt-0.5" />
                      {shareMsg}
                    </div>
                  )}
                </form>
              ) : (
                <p className="text-[10px] font-mono text-gray-600/50 leading-relaxed">
                  Only the device owner can manage sharing. You have{' '}
                  <span className="font-bold text-gray-600/80">{ROLE_LABEL[accessRole] ?? accessRole}</span>{' '}
                  access to this device.
                </p>
              )}

              {shares.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  {shares.map(s => (
                    <div
                      key={s.id}
                      className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-white/40 border border-gray-200/25"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] font-mono text-gray-900 font-bold truncate">
                          {s.display_name || s.email}
                        </div>
                        <div className="text-[9px] font-mono text-gray-600/45 truncate">
                          {s.email}
                        </div>
                      </div>
                      <span
                        className={cn(
                          'text-[9px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border shrink-0',
                          s.role === 'admin'
                            ? 'border-gray-900/40 text-gray-900 bg-gray-100/10'
                            : s.role === 'viewer'
                              ? 'border-gray-900/40 text-gray-900 bg-gray-100/10'
                              : 'border-mag-text-dim/40 text-gray-600/80 bg-mag-text-dim/10'
                        )}
                      >
                        {ROLE_LABEL[s.role] ?? s.role}
                      </span>
                      {isOwner && (
                        <button
                          onClick={() => revokeShare(s.id)}
                          aria-label={`Revoke access for ${s.email}`}
                          title="Revoke access"
                          className="p-1 rounded-md text-gray-600/40 hover:text-red-600 hover:bg-red-50/10 transition-colors"
                        >
                          <UserMinus size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Alert Settings (per-device recipients) — admin+ only */}
      {canManage && (
      <div className="bg-gray-50/30 border border-gray-200/30 rounded-xl p-4 space-y-3">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="w-full flex items-center justify-between text-[11px] font-mono text-gray-600/80 uppercase tracking-wider font-bold hover:text-gray-900 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <BellRing size={12} className="text-gray-900" />
            Alert Settings
          </span>
          <span className="text-gray-600/50">{showSettings ? '−' : '+'}</span>
        </button>

        {showSettings && (
          <div className="space-y-2 pt-1">
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Alert Phone (E.164, e.g. +2348081234567)
              </label>
              <input
                value={alertPhone}
                onChange={e => setAlertPhone(e.target.value)}
                placeholder="Leave empty to use global default"
                className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-600/30 focus:outline-none focus:border-gray-900/60 transition-colors"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Alert Email
              </label>
              <input
                value={alertEmail}
                onChange={e => setAlertEmail(e.target.value)}
                placeholder="Leave empty to use global default"
                className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-600/30 focus:outline-none focus:border-gray-900/60 transition-colors"
              />
            </div>

            {/* Channels — empty selection = all (global default) */}
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Channels (uncheck to disable a channel)
              </label>
              <div className="flex flex-wrap gap-1.5">
                {ALL_CHANNELS.map(ch => {
                  const active = (alertChannels ?? ALL_CHANNELS).includes(ch);
                  return (
                    <button
                      key={ch}
                      type="button"
                      onClick={() => toggleChannel(ch)}
                      aria-pressed={active}
                      aria-label={`Toggle ${ch} channel`}
                      className={`px-2.5 py-1 rounded-md text-[10px] font-mono font-bold uppercase tracking-wide transition-all ${
                        active
                          ? 'bg-gray-100/25 text-gray-900 border border-gray-900/40'
                          : 'bg-white/40 text-gray-600/40 border border-gray-200/30 hover:text-gray-600/70'
                      }`}
                    >
                      {ch}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Alert types — empty selection = all types enabled */}
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Alert types (theft / SIM / factory-reset always deliver)
              </label>
              <div className="flex flex-wrap gap-1.5">
                {[
                  ['theft_detected', 'Theft'],
                  ['sim_changed', 'SIM change'],
                  ['factory_reset', 'Factory reset'],
                  ['battery_low', 'Battery low'],
                  ['device_offline', 'Offline'],
                  ['device_recovered', 'Recovered'],
                  ['geofence_exit', 'Geofence exit'],
                ].map(([type, label]) => {
                  const base = enabledTypes ?? ALL_ALERT_TYPES;
                  const active = base.includes(type);
                  const locked = type === 'theft_detected' || type === 'sim_changed' || type === 'factory_reset';
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() => !locked && toggleType(type)}
                      disabled={locked}
                      aria-pressed={active}
                      aria-label={`Toggle ${label} alert type`}
                      title={locked ? 'Emergency alerts always deliver' : undefined}
                      className={`px-2.5 py-1 rounded-md text-[10px] font-mono font-bold uppercase tracking-wide transition-all ${
                        active
                          ? 'bg-gray-100/20 text-gray-900 border border-gray-900/40'
                          : 'bg-white/40 text-gray-600/40 border border-gray-200/30 hover:text-gray-600/70'
                      } disabled:cursor-not-allowed disabled:opacity-80`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Quiet hours — suppress non-emergency alerts overnight */}
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Quiet hours (suppress non-emergency alerts)
              </label>
              <div className="flex items-center gap-2">
                <select
                  value={quietStart ?? ''}
                  onChange={e => setQuietStart(e.target.value === '' ? null : Number(e.target.value))}
                  aria-label="Quiet hours start"
                  className="flex-1 bg-white/60 border border-gray-200/40 rounded-lg px-2 py-1.5 text-xs font-mono text-gray-900 focus:outline-none focus:border-gray-900/60 transition-colors"
                >
                  <option value="">Off</option>
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, '0')}:00
                    </option>
                  ))}
                </select>
                <span className="text-gray-600/50 text-[10px] font-mono">to</span>
                <select
                  value={quietEnd ?? ''}
                  onChange={e => setQuietEnd(e.target.value === '' ? null : Number(e.target.value))}
                  aria-label="Quiet hours end"
                  className="flex-1 bg-white/60 border border-gray-200/40 rounded-lg px-2 py-1.5 text-xs font-mono text-gray-900 focus:outline-none focus:border-gray-900/60 transition-colors"
                >
                  <option value="">Off</option>
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, '0')}:00
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {error && <div className="text-[10px] font-mono text-red-400">{error}</div>}

            <button
              onClick={saveAlertSettings}
              disabled={saving}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-gray-100/90 hover:bg-gray-100 disabled:opacity-50 text-white text-xs font-bold transition-all"
            >
              {saved ? <Check size={13} /> : <Save size={13} />}
              {saving ? 'Saving...' : saved ? 'Saved' : 'Save Alert Settings'}
            </button>
            <p className="text-[10px] font-mono text-gray-600/40">
              Per-device recipients & preferences override the global defaults. Emergency alerts
              (theft, SIM change, factory reset) always deliver.
            </p>
          </div>
        )}
      </div>
      )}

      {!latestLocation && (
        <div className="text-center py-6">
          <div className="w-10 h-10 rounded-xl bg-gray-50/30 border border-gray-200/20 flex items-center justify-center mx-auto mb-2">
            <MapPin size={16} className="text-gray-600/20" />
          </div>
          <div className="text-gray-600/40 text-[11px] font-bold">No location data yet</div>
          <div className="text-gray-600/25 text-[10px] font-mono mt-1">
            Location will appear once the device reports its first GPS fix.
          </div>
        </div>
      )}

      {/* Offline Command Relay (SMS) — commands that reach the phone even with no data. Admin+ only (it is a security surface + costs money). */}
      {canManage && (
      <div className="bg-gray-50/30 border border-gray-200/30 rounded-xl p-4 space-y-3">
        <button
          onClick={() => setShowSmsSettings(!showSmsSettings)}
          className="w-full flex items-center justify-between text-[11px] font-mono text-gray-600/80 uppercase tracking-wider font-bold hover:text-gray-900 transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <MessageSquareText size={12} className="text-gray-900" />
            Offline SMS Commands
            {device.sms_commands_enabled && (
              <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/25">
                On
              </span>
            )}
          </span>
          <span className="text-gray-600/50">{showSmsSettings ? '−' : '+'}</span>
        </button>

        {showSmsSettings && (
          <div className="space-y-2.5 pt-1">
            <p className="text-[10px] font-mono text-gray-600/50 leading-relaxed">
              When this device is <span className="text-gray-600/80 font-bold">offline (no data)</span>,
              the dashboard can still command it over the cellular SMS channel — every phone
              receives SMS even with zero data plan. Commands are texted to the SIM number
              below and executed on the phone locally. Location comes back as a coarse
              cell-tower fix + the exact GPS fix when the phone regains any internet.
            </p>
            <div>
              <label className="text-[10px] font-mono text-gray-600/60 font-bold mb-1 block">
                Device SIM number (E.164, e.g. +2348081234567)
              </label>
              <input
                value={smsPhone}
                onChange={e => setSmsPhone(e.target.value)}
                placeholder="+234..."
                aria-label="Offline SMS phone number"
                className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-600/30 focus:outline-none focus:border-gray-900/60 transition-colors"
              />
            </div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={smsEnabled}
                onChange={e => setSmsEnabled(e.target.checked)}
                aria-label="Enable offline SMS commands"
                className="accent-mag-accent w-4 h-4"
              />
              <span className="text-[10px] font-mono text-gray-600/70 font-bold">
                Enable SMS commands for this device
              </span>
            </label>
            {smsError && <div className="text-[10px] font-mono text-red-400">{smsError}</div>}
            <button
              onClick={saveSmsSettings}
              disabled={smsSaving}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-gray-100/90 hover:bg-gray-100 disabled:opacity-50 text-white text-xs font-bold transition-all"
            >
              {smsSaved ? <Check size={13} /> : <Save size={13} />}
              {smsSaving ? 'Saving...' : smsSaved ? 'Saved' : 'Save SMS Settings'}
            </button>
            <p className="text-[10px] font-mono text-gray-600/40 leading-relaxed">
              SMS messages cost money and an SMS command is a security surface — that's why this
              is opt-in. Commands only SMS when the device is offline; online devices use the
              normal poll. The phone verifies a per-device secret code and only accepts commands
              from the server's own number.
            </p>
            <p className="text-[10px] font-mono text-amber-400/70 leading-relaxed">
              ⚠ Also enable <span className="font-bold">Offline SMS Commands</span> in the Magneetar
              app on the phone (Home → Offline SMS) — the phone only accepts command SMS while its
              own toggle is on, and it must have the SMS permission (granted in the app's
              Permissions screen). Both sides must be enabled for the relay to work.
            </p>
          </div>
        )}
      </div>
      )}

      {/* Permanent deletion (privacy policy promise) — owner only */}
      {isOwner && (
      <div className="bg-gray-50/30 border border-gray-200/30 rounded-xl p-4">
        {!confirmDelete ? (
          <button
            onClick={() => { setConfirmDelete(true); setDeleteError(''); }}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-red-300/25 text-red-600/80 hover:text-red-600 hover:border-red-300/50 hover:bg-red-50/[0.05] text-[11px] font-mono font-bold uppercase tracking-wider transition-all"
          >
            <Trash2 size={13} />
            Delete Device Permanently
          </button>
        ) : (
          <div className="space-y-2.5">
            <div className="text-[11px] font-mono text-red-600/90 leading-relaxed">
              Permanently delete <span className="font-bold">{device.alias?.trim() || device.model || device.id}</span>? All
              locations, media, evidence, alerts & recovery requests are erased. This cannot be undone.
            </div>
            <input
              type="password"
              value={deletePassword}
              onChange={e => setDeletePassword(e.target.value)}
              placeholder={stepUpPasswordHint()}
              autoFocus
              aria-label="Confirm deletion password"
              onKeyDown={e => {
                if (e.key === 'Enter' && !deleting) {
                  e.preventDefault();
                  confirmDeleteDevice();
                }
              }}
              className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-600/30 focus:outline-none focus:border-red-300/60 transition-colors"
            />
            {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
            <div className="text-[10px] font-mono text-gray-600/50 leading-relaxed">
              This session verifies with <span className="font-bold text-gray-600/70">{stepUpPasswordHint()}</span> —
              the server re-checks it before anything is deleted.
            </div>
            <div className="flex gap-2">
              <button
                onClick={confirmDeleteDevice}
                disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-red-50/90 hover:bg-red-50 disabled:opacity-50 text-white text-[11px] font-bold transition-all"
              >
                <Trash2 size={12} />
                {deleting ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button
                onClick={() => {
                  setConfirmDelete(false);
                  setDeletePassword('');
                  setDeleteError('');
                }}
                disabled={deleting}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-gray-200/40 text-gray-600/70 hover:text-gray-900 text-[11px] font-bold transition-all"
              >
                <X size={12} />
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
