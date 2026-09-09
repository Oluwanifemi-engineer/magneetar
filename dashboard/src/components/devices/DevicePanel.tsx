'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useStore } from '@/store/useStore';
import { cn, relativeTime, formatCoordinate, deviceDisplayName, stepUpPasswordHint } from '@/lib/utils';
import { BellRing, MapPin, LocateFixed, Navigation, ExternalLink, Download, Save, Check, Trash2, X, Pencil, MessageSquareText, Users, UserPlus, UserMinus, ShieldCheck } from 'lucide-react';
import { MagInput, MagButton, MagStatusPill, MagPanel, MagRow, MagEmpty } from '@/components/ui/MagPrimitives';
import { CoordDisplay } from '@/components/ui/CoordDisplay';
import { getAPI } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import type { DeviceShare, ShareRole } from '@/types';

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  viewer: 'Viewer',
  device_only: 'Device-only',
};

const LOCATION_MODE_LABEL: Record<string, string> = {
  battery_saving: 'Battery-saving',
  gps_only: 'GPS only',
  off: 'Location off',
};
const LOCATION_MODE_HINT: Record<string, string> = {
  battery_saving: 'Battery-saving mode disables GPS — fixes are network-only (100-500m), even outdoors.',
  gps_only: 'GPS-only mode turns off Wi-Fi/cell scanning — the device cannot be located indoors.',
  off: 'Location services are OFF on the device — no fixes at all until re-enabled.',
};

const ALL_ALERT_TYPES = [
  'theft_detected', 'sim_changed', 'factory_reset', 'battery_low',
  'device_offline', 'device_recovered', 'geofence_exit',
];

const ALL_CHANNELS = ['email', 'whatsapp', 'sms', 'push'];

export function DevicePanel() {
  const { devices, selectedDeviceId, latestLocation, setDevices, selectDevice } = useStore();
  const { toast } = useToast();
  const device = devices.find(d => d.id === selectedDeviceId);

  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = device?.access_role ?? 'owner';
  const canManage = accessRole === 'owner' || accessRole === 'admin';
  const canReadLocation = canManage || accessRole === 'viewer';
  const isOwner = accessRole === 'owner';

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
  const [smsPhone, setSmsPhone] = useState('');
  const [smsEnabled, setSmsEnabled] = useState(false);
  const [smsSaving, setSmsSaving] = useState(false);
  const [smsSaved, setSmsSaved] = useState(false);
  const [smsError, setSmsError] = useState('');
  const [showSmsSettings, setShowSmsSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [deletePassword, setDeletePassword] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [nameSaving, setNameSaving] = useState(false);
  const [nameError, setNameError] = useState('');
  const [exporting, setExporting] = useState(false);
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
    } catch { setShares([]); }
  }, []);

  const inviteShare = async (e: FormEvent) => {
    e.preventDefault();
    if (!device || shareSaving) return;
    const email = inviteEmail.trim();
    if (!email) { setShareError("Enter the recipient's email address."); return; }
    setShareSaving(true); setShareError(''); setShareMsg('');
    try {
      await getAPI().addShare(device.id, email, inviteRole);
      setInviteEmail('');
      setShareMsg(`Access granted (${inviteRole}) — they'll see this device when they sign in.`);
      await fetchShares(device.id);
    } catch (err: any) { setShareError(err?.message || 'Failed to share device'); }
    finally { setShareSaving(false); }
  };

  const revokeShare = async (shareId: string) => {
    if (!device) return;
    try { await getAPI().revokeShare(device.id, shareId); await fetchShares(device.id); toast('Access revoked', 'success'); }
    catch (err: any) { toast(err?.message || 'Failed to revoke access', 'error'); }
  };

  const exportCsv = async () => {
    if (!device || exporting) return;
    setExporting(true);
    try {
      const blob = await getAPI().exportLocationsCSV(device.id);
      if (blob.size === 0) toast('No location history to export yet', 'error');
      else toast('Location history exported', 'success');
    } catch (e: any) { toast(e?.message || 'Failed to export location history', 'error'); }
    finally { setExporting(false); }
  };

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
    setError(''); setSaved(false); setSmsError(''); setSmsSaved(false);
    setEditingName(false); setNameError(''); setDeletePassword(''); setDeleteError('');
    setShares([]); setShowShares(false); setShareError(''); setShareMsg(''); setInviteEmail('');
  }

  useEffect(() => { if (deviceKey) fetchShares(deviceKey); }, [deviceKey, fetchShares]);

  const confirmDeleteDevice = async () => {
    if (!device || deleting) return;
    if (!deletePassword.trim()) { setDeleteError('Enter your password to confirm.'); return; }
    setDeleting(true); setDeleteError('');
    try {
      await getAPI().deleteDevice(device.id, deletePassword);
      const { devices: freshDevices } = await getAPI().getDevices();
      setDevices(freshDevices);
      if (selectedDeviceId === device.id) selectDevice(freshDevices[0]?.id ?? null);
      setConfirmDelete(false); setDeletePassword('');
    } catch (e: any) { setDeleteError(e.message || 'Failed to delete device'); }
    finally { setDeleting(false); }
  };

  const saveDeviceName = async (e: FormEvent) => {
    e.preventDefault();
    if (!device) return;
    const alias = nameDraft.trim();
    if (!alias) { setNameError('Name cannot be empty'); return; }
    setEditingName(false); setSaving(true); setNameError('');
    try {
      await getAPI().updateDeviceAlias(device.id, alias);
      toast('Device renamed', 'success');
      const { devices: freshDevices } = await getAPI().getDevices(); setDevices(freshDevices);
    } catch (err: any) { setNameError(err.message || 'Failed to rename device'); setEditingName(true); }
    finally { setSaving(false); }
  };

  const saveSmsSettings = async () => {
    if (!device || smsSaving) return;
    setSmsSaving(true); setSmsError(''); setSmsSaved(false);
    try {
      const res = await getAPI().updateSmsSettings(device.id, smsPhone.trim(), smsEnabled);
      setSmsPhone(res.sms_phone || ''); setSmsEnabled(res.sms_commands_enabled);
      setSmsSaved(true); toast('SMS relay settings saved', 'success');
      try { const { devices: freshDevices } = await getAPI().getDevices(); setDevices(freshDevices); } catch {}
      setTimeout(() => setSmsSaved(false), 2000);
    } catch (e: any) { setSmsError(e.message || 'Failed to save SMS settings'); }
    finally { setSmsSaving(false); }
  };

  const saveAlertSettings = async () => {
    if (!device) return;
    setSaving(true); setError(''); setSaved(false);
    try {
      await getAPI().updateDeviceAlertSettings(device.id, alertPhone.trim(), alertEmail.trim(), {
        alert_channels: alertChannels && alertChannels.length ? alertChannels : null,
        enabled_types: enabledTypes && enabledTypes.length ? enabledTypes : null,
        quiet_hours_start: quietStart, quiet_hours_end: quietEnd,
      });
      setSaved(true); toast('Alert settings saved', 'success');
      try { const { devices: freshDevices } = await getAPI().getDevices(); setDevices(freshDevices); } catch {}
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) { setError(e.message || 'Failed to save alert settings'); }
    finally { setSaving(false); }
  };

  const toggleChannel = (ch: string) => {
    setAlertChannels(prev => { const base = prev ?? ALL_CHANNELS; return base.includes(ch) ? base.filter(c => c !== ch) : [...base, ch]; });
  };
  const toggleType = (t: string) => {
    setEnabledTypes(prev => { const base = prev ?? ALL_ALERT_TYPES; return base.includes(t) ? base.filter(x => x !== t) : [...base, t]; });
  };

  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <MagEmpty aria-hidden="true">
          <MapPin size={24} className="text-white/15" />
        </MagEmpty>
        <div className="text-mag-text-muted text-sm font-bold mb-1">No device selected</div>
        <div className="text-mag-text-2 text-xs font-mono leading-relaxed max-w-[200px]">
          Select a device from the sidebar to view its details, location, alert settings, and capture status.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Device Header */}
      <MagPanel>
        <div className="flex items-center gap-2 mb-3">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)] shrink-0" />
          {device.archived_at && (
            <MagStatusPill variant="elevated">Archived</MagStatusPill>
          )}
          {!isOwner && (
            <MagStatusPill
              variant={accessRole === 'admin' ? 'secure' : 'muted'}
            >
              {ROLE_LABEL[accessRole] ?? accessRole}
            </MagStatusPill>
          )}
          {device.location_mode && LOCATION_MODE_LABEL[device.location_mode] && (
            <MagStatusPill
              variant={device.location_mode === 'off' ? 'danger' : 'elevated'}
              title={LOCATION_MODE_HINT[device.location_mode]}
            >
              {LOCATION_MODE_LABEL[device.location_mode]}
            </MagStatusPill>
          )}
          {editingName ? (
            <form onSubmit={saveDeviceName} className="flex items-center gap-1.5 flex-1 min-w-0">
              <MagInput
                value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                autoFocus
                maxLength={60}
                className="flex-1 min-w-0 text-sm font-bold"
              />
              <MagButton
                variant="subtle"
                size="sm"
                disabled={nameSaving}
                type="submit"
              >
                <Check size={13} />
              </MagButton>
              <MagButton
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => setEditingName(false)}
              >
                <X size={13} />
              </MagButton>
            </form>
          ) : (
            <>
              <h3 className="text-base font-bold text-mag-text-1 truncate flex-1 min-w-0">{deviceDisplayName(device)}</h3>
              {canManage && (
                <MagButton
                  variant="ghost"
                  size="sm"
                  onClick={() => { setNameDraft(deviceDisplayName(device)); setNameError(''); setEditingName(true); }}
                >
                  <Pencil size={12} />
                </MagButton>
              )}
            </>
          )}
        </div>
        {nameError && <div className="text-xs font-mono text-red-400 mb-2">{nameError}</div>}

        <div className="space-y-2">
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Device ID</span>
            <span className="text-xs font-mono text-mag-text-1 font-bold">{device.id}</span>
          </MagRow>
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Registered</span>
            <span className="text-xs font-mono text-mag-text-3 font-bold">{relativeTime(device.registered)}</span>
          </MagRow>
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Last Seen</span>
            <span className="text-xs font-mono text-mag-text-3 font-bold">{relativeTime(device.last_seen)}</span>
          </MagRow>
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Capture</span>
            {device.capture_armed == null ? (
              <span className="text-xs font-mono text-mag-text-4 font-bold">Unknown</span>
            ) : device.capture_armed ? (
              <span className="text-xs font-mono text-emerald-400 font-bold">Armed</span>
            ) : (
              <span className="text-xs font-mono text-amber-400 font-bold">Unarmed</span>
            )}
          </MagRow>
        </div>
      </MagPanel>

      {/* Coordinates */}
      {latestLocation && <CoordDisplay lat={latestLocation.lat} lng={latestLocation.lng} />}

      {/* Location Details */}
      {latestLocation && (
        <MagPanel>
          <div className="flex items-center gap-1.5 text-xs font-mono text-mag-text-2 uppercase tracking-wider font-bold mb-2">
            <LocateFixed size={12} className="text-mag-text-4" />
            Location Details
          </div>
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Provider</span>
            <span className="text-xs font-mono text-mag-text-1 font-bold">{latestLocation.provider}</span>
          </MagRow>
          <MagRow align="between">
            <span className="text-xs font-mono text-mag-text-2 font-bold">Accuracy</span>
            <span className="text-xs font-mono text-mag-text-1 font-bold">±{latestLocation.accuracy?.toFixed(1) || '?'}m</span>
          </MagRow>
          {latestLocation.speed != null && (
            <MagRow align="between">
              <span className="text-xs font-mono text-mag-text-2 font-bold">Speed</span>
              <span className="text-xs font-mono text-mag-text-1 font-bold">{(latestLocation.speed * 3.6).toFixed(1)} km/h</span>
            </MagRow>
          )}
          {latestLocation.altitude != null && (
            <MagRow align="between">
              <span className="text-xs font-mono text-mag-text-2 font-bold">Altitude</span>
              <span className="text-xs font-mono text-mag-text-1 font-bold">{latestLocation.altitude.toFixed(0)}m</span>
            </MagRow>
          )}
          {latestLocation.bearing != null && (
            <MagRow align="between">
              <span className="text-xs font-mono text-mag-text-2 font-bold">Bearing</span>
              <span className="text-xs font-mono text-mag-text-1 font-bold">{latestLocation.bearing.toFixed(0)}°</span>
            </MagRow>
          )}
        </MagPanel>
      )}

      {/* Open in Maps */}
      {latestLocation && (          <a
          href={`https://www.google.com/maps?q=${latestLocation.lat},${latestLocation.lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-mag-border text-mag-text-muted hover:bg-mag-surface-raised hover:border-mag-border/50 hover:text-mag-text transition-all text-xs font-bold"
        >
          <ExternalLink size={14} />
          Open in Google Maps
        </a>
      )}

      {/* Export CSV */}
      {canReadLocation && (
        <MagButton
          variant="ghost"
          onClick={exportCsv}
          disabled={exporting}
          startIcon={<Download size={14} />}
        >
          {exporting ? 'Exporting…' : 'Export Location History (CSV)'}
        </MagButton>
      )}

      {/* Sharing */}
      {canManage && (
        <MagPanel>
          <button
            type="button"
            onClick={() => setShowShares(!showShares)}
            className="w-full flex items-center justify-between text-xs font-mono text-mag-text-2 uppercase tracking-wider font-bold hover:text-mag-text-1 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <Users size={12} className="text-mag-text-4" />
              Sharing
              {shares.length > 0 && (
                <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-mag-surface-raised text-mag-text-2 border border-mag-border">{shares.length}</span>
              )}
            </span>
            <span className="text-mag-text-4">{showShares ? '−' : '+'}</span>
          </button>
          {showShares && (
            <div className="space-y-2.5 pt-1">
              {isOwner ? (
                <form onSubmit={inviteShare} className="space-y-2">
                  <div>
                    <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Share with (account email)</label>
                    <MagInput
                      value={inviteEmail}
                      onChange={e => setInviteEmail(e.target.value)}
                      placeholder="family@example.com"
                      type="email"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Role</label>
                    <select
                      value={inviteRole}
                      onChange={e => setInviteRole(e.target.value as ShareRole)}
                      className="w-full bg-mag-surface border-mag-border text-mag-text-1 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-mag-primary/20"
                    >
                      <option value="viewer">Viewer — read only</option>
                      <option value="admin">Admin — full control</option>
                      <option value="device_only">Device-only — status glance</option>
                    </select>
                  </div>
                  <MagButton
                    variant="primary"
                    type="submit"
                    disabled={shareSaving}
                    startIcon={<UserPlus size={13} />}
                  >
                    {shareSaving ? 'Sharing...' : 'Share device'}
                  </MagButton>
                  {shareError && <div className="text-[10px] font-mono text-red-400">{shareError}</div>}
                  {shareMsg && (
                    <div className="flex items-start gap-1.5 text-[10px] font-mono text-emerald-400/70 leading-relaxed">
                      <ShieldCheck size={11} className="shrink-0 mt-0.5" />
                      {shareMsg}
                    </div>
                  )}
                </form>
              ) : (
                <p className="text-[10px] font-mono text-mag-text-3 leading-relaxed">
                  Only the device owner can manage sharing. You have{' '}
                  <span className="font-bold text-mag-text-2">{ROLE_LABEL[accessRole] ?? accessRole}</span> access.
                </p>
              )}
              {shares.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  {shares.map(s => (
                    <div key={s.id} className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-mag-surface border-mag-border">
                      <div className="flex-1 min-w-0">
                        <div className="text-[10px] font-mono text-mag-text-1 font-bold truncate">{s.display_name || s.email}</div>
                        <div className="text-[9px] font-mono text-mag-text-3 truncate">{s.email}</div>
                      </div>
                      <MagStatusPill
                        variant={s.role === 'admin' ? 'secure' : 'muted'}
                      >
                        {ROLE_LABEL[s.role] ?? s.role}
                      </MagStatusPill>
                      {isOwner && (
                        <MagButton
                          variant="ghost"
                          size="sm"
                          onClick={() => revokeShare(s.id)}
                        >
                          <UserMinus size={12} />
                        </MagButton>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </MagPanel>
      )}

      {/* Alert Settings */}
      {canManage && (
        <MagPanel>
          <button
            type="button"
            onClick={() => setShowSettings(!showSettings)}
            className="w-full flex items-center justify-between text-xs font-mono text-mag-text-2 uppercase tracking-wider font-bold hover:text-mag-text-1 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <BellRing size={12} className="text-mag-text-4" />
              Alert Settings
            </span>
            <span className="text-mag-text-4">{showSettings ? '−' : '+'}</span>
          </button>
          {showSettings && (
            <div className="space-y-2 pt-1">
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Alert Phone (E.164)</label>
                <MagInput
                  value={alertPhone}
                  onChange={e => setAlertPhone(e.target.value)}
                  placeholder="Leave empty for global default"
                />
              </div>
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Alert Email</label>
                <MagInput
                  value={alertEmail}
                  onChange={e => setAlertEmail(e.target.value)}
                  placeholder="Leave empty for global default"
                />
              </div>
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Channels</label>
                <div className="flex flex-wrap gap-1.5">
                  {ALL_CHANNELS.map(ch => {
                    const active = (alertChannels ?? ALL_CHANNELS).includes(ch);
                    return (
                      <MagStatusPill
                        key={ch}
                        variant={active ? 'secure' : 'muted'}
                        label={ch}
                        ariaLabel={`Toggle ${ch} channel`}
                        ariaPressed={active}
                        onClick={() => toggleChannel(ch)}
                      />
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Alert types</label>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    ['theft_detected', 'Theft'], ['sim_changed', 'SIM change'], ['factory_reset', 'Factory reset'],
                    ['battery_low', 'Battery low'], ['device_offline', 'Offline'], ['device_recovered', 'Recovered'], ['geofence_exit', 'Geofence'],
                  ].map(([type, label]) => {
                    const base = enabledTypes ?? ALL_ALERT_TYPES;
                    const active = base.includes(type);
                    const locked = type === 'theft_detected' || type === 'sim_changed' || type === 'factory_reset';
                    return (
                      <MagStatusPill
                        key={type}
                        variant={active ? 'secure' : 'muted'}
                        label={label}
                        ariaLabel={`Toggle ${label} alert type`}
                        ariaPressed={active}
                        onClick={() => !locked && toggleType(type)}
                        disabled={locked}
                      />
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">Quiet hours</label>
                <div className="flex items-center gap-2">
                  <select
                    value={quietStart ?? ''}
                    onChange={e => setQuietStart(e.target.value === '' ? null : Number(e.target.value))}
                    aria-label="Quiet hours start"
                    className="flex-1 bg-mag-surface border-mag-border text-mag-text-1 rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-mag-primary/20"
                  >
                    <option value="">Off</option>
                    {Array.from({ length: 24 }, (_, h) => (<option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>))}
                  </select>
                  <span className="text-mag-text-4 text-[10px] font-mono">to</span>
                  <select
                    value={quietEnd ?? ''}
                    onChange={e => setQuietEnd(e.target.value === '' ? null : Number(e.target.value))}
                    aria-label="Quiet hours end"
                    className="flex-1 bg-mag-surface border-mag-border text-mag-text-1 rounded-lg px-2 py-1.5 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-mag-primary/20"
                  >
                    <option value="">Off</option>
                    {Array.from({ length: 24 }, (_, h) => (<option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>))}
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <MagButton
                  variant="primary"
                  onClick={saveAlertSettings}
                  disabled={saving}
                  startIcon={<Save size={11} />}
                >
                  {saving ? 'SAVING...' : saved ? 'SAVED ✓' : 'Save Alert Settings'}
                </MagButton>
                {error && <div className="text-[10px] font-mono text-red-400">{error}</div>}
              </div>
            </div>
          )}
        </MagPanel>
      )}

      {/* Offline SMS Commands */}
      {canManage && (
        <MagPanel>
          <button
            type="button"
            onClick={() => setShowSmsSettings(!showSmsSettings)}
            className="w-full flex items-center justify-between text-xs font-mono text-mag-text-2 uppercase tracking-wider font-bold hover:text-mag-text-1 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <MessageSquareText size={12} className="text-mag-text-4" />
              Offline SMS Commands
            </span>
            <span className="flex items-center gap-2">
              {smsEnabled && <MagStatusPill variant="secure" label="On" />}
              <span className="text-mag-text-4">{showSmsSettings ? '−' : '+'}</span>
            </span>
          </button>
          {showSmsSettings && (
            <div className="space-y-2 pt-1">
              <div>
                <label className="text-[10px] font-mono text-mag-text-2 font-bold mb-1 block">SMS phone number</label>
                <MagInput
                  value={smsPhone}
                  onChange={e => setSmsPhone(e.target.value)}
                  placeholder="+234..."
                  aria-label="Offline SMS phone number"
                />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={smsEnabled}
                  onChange={e => setSmsEnabled(e.target.checked)}
                  className="mag-check"
                  aria-label="Enable offline SMS commands"
                />
                <span className="text-[10px] font-mono text-mag-text-2 font-bold">Enable offline SMS relay</span>
              </label>
              <MagButton
                variant="primary"
                onClick={saveSmsSettings}
                disabled={smsSaving}
                startIcon={<Save size={11} />}
              >
                {smsSaving ? 'SAVING...' : smsSaved ? 'SAVED ✓' : 'Save SMS Settings'}
              </MagButton>
              {smsError && <div className="text-[10px] font-mono text-red-400">{smsError}</div>}
            </div>
          )}
        </MagPanel>
      )}

      {/* Delete Device */}
      {isOwner && (
        <MagPanel>
          {!confirmDelete ? (
            <MagButton
              variant="danger"
              onClick={() => setConfirmDelete(true)}
              startIcon={<Trash2 size={14} />}
            >
              Delete Device Permanently
            </MagButton>
          ) : (
            <div className="space-y-3">
              <div className="text-xs font-mono text-red-400 font-bold">Confirm device deletion — this is irreversible.</div>
              <MagInput
                type="password"
                value={deletePassword}
                onChange={e => setDeletePassword(e.target.value)}
                placeholder={stepUpPasswordHint()}
                autoFocus
                aria-label="Confirm deletion password"
                variant="danger"
              />
              {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
              <div className="flex gap-2">
                <MagButton
                  variant="danger"
                  onClick={confirmDeleteDevice}
                  disabled={deleting}
                >
                  {deleting ? 'Deleting...' : 'Yes, Delete'}
                </MagButton>
                <MagButton
                  variant="ghost"
                  size="sm"
                  onClick={() => { setConfirmDelete(false); setDeletePassword(''); setDeleteError(''); }}
                >
                  Cancel
                </MagButton>
              </div>
            </div>
          )}
        </MagPanel>
      )}
    </div>
  );
}
