'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { cn, relativeTime, formatCoordinate, deviceDisplayName } from '@/lib/utils';
import { BellRing, MapPin, LocateFixed, Navigation, ExternalLink, Save, Check, Trash2, X } from 'lucide-react';
import { CoordDisplay } from '@/components/ui/CoordDisplay';
import { getAPI } from '@/lib/api';

export function DevicePanel() {
  const { devices, selectedDeviceId, latestLocation, setDevices, selectDevice } = useStore();
  const device = devices.find(d => d.id === selectedDeviceId);

  // Alert recipient settings state (per-device override of global defaults)
  const [alertPhone, setAlertPhone] = useState('');
  const [alertEmail, setAlertEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  // Sync form fields when the selected device changes
  const deviceKey = device?.id;
  const [lastDeviceKey, setLastDeviceKey] = useState<string | undefined>(undefined);
  if (deviceKey && deviceKey !== lastDeviceKey) {
    setLastDeviceKey(deviceKey);
    setAlertPhone(device?.alert_phone || '');
    setAlertEmail(device?.alert_email || '');
    setError('');
    setSaved(false);
  }

  const saveAlertSettings = async () => {
    if (!device) return;
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      await getAPI().updateDeviceAlertSettings(device.id, alertPhone.trim(), alertEmail.trim());
      setSaved(true);
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

  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <MapPin size={28} className="mx-auto text-mag-text-dim/20 mb-3" />
        <div className="text-mag-text-dim/50 text-sm font-bold">
          No device selected.
        </div>
        <div className="text-mag-text-dim/30 text-xs font-mono mt-1">
          Select a device from the sidebar.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Device Header */}
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4">
        <h3 className="text-base font-bold text-mag-text flex items-center gap-2 mb-3">
          <div className="w-2.5 h-2.5 rounded-full bg-mag-primary shadow-[0_0_10px_rgba(233,30,140,0.5)]" />
          {deviceDisplayName(device)}
        </h3>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Device ID</span>
            <span className="text-[11px] font-mono text-mag-text font-bold">{device.id}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Registered</span>
            <span className="text-[11px] font-mono text-mag-text-dim font-bold">{relativeTime(device.registered)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Last Seen</span>
            <span className="text-[11px] font-mono text-mag-text-dim font-bold">{relativeTime(device.last_seen)}</span>
          </div>
        </div>
      </div>

      {/* Coordinates */}
      {latestLocation && (
        <CoordDisplay lat={latestLocation.lat} lng={latestLocation.lng} />
      )}

      {/* Location Details */}
      {latestLocation && (
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2">
            <LocateFixed size={12} className="text-mag-accent" />
            Location Details
          </div>

          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Provider</span>
            <span className="text-[11px] font-mono text-mag-accent font-bold">{latestLocation.provider}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Accuracy</span>
            <span className="text-[11px] font-mono text-mag-text font-bold">±{latestLocation.accuracy?.toFixed(1) || '?'}m</span>
          </div>
          {latestLocation.speed != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Speed</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{(latestLocation.speed * 3.6).toFixed(1)} km/h</span>
            </div>
          )}
          {latestLocation.altitude != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Altitude</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{latestLocation.altitude.toFixed(0)}m</span>
            </div>
          )}
          {latestLocation.bearing != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Bearing</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{latestLocation.bearing.toFixed(0)}°</span>
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
          className="flex items-center justify-center gap-2 py-3 rounded-xl border border-mag-border/40 text-mag-text-dim hover:text-mag-text hover:border-mag-border transition-all text-xs font-bold"
        >
          <ExternalLink size={14} />
          Open in Google Maps
        </a>
      )}

      {/* Alert Settings (per-device recipients) */}
      <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-3">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="w-full flex items-center justify-between text-[11px] font-mono text-mag-text-dim/80 uppercase tracking-wider font-bold hover:text-mag-text transition-colors"
        >
          <span className="flex items-center gap-1.5">
            <BellRing size={12} className="text-mag-accent" />
            Alert Settings
          </span>
          <span className="text-mag-text-dim/50">{showSettings ? '−' : '+'}</span>
        </button>

        {showSettings && (
          <div className="space-y-2 pt-1">
            <div>
              <label className="text-[10px] font-mono text-mag-text-dim/60 font-bold mb-1 block">
                Alert Phone (E.164, e.g. +2348081234567)
              </label>
              <input
                value={alertPhone}
                onChange={e => setAlertPhone(e.target.value)}
                placeholder="Leave empty to use global default"
                className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-primary/60 transition-colors"
              />
            </div>
            <div>
              <label className="text-[10px] font-mono text-mag-text-dim/60 font-bold mb-1 block">
                Alert Email
              </label>
              <input
                value={alertEmail}
                onChange={e => setAlertEmail(e.target.value)}
                placeholder="Leave empty to use global default"
                className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-primary/60 transition-colors"
              />
            </div>

            {error && <div className="text-[10px] font-mono text-red-400">{error}</div>}

            <button
              onClick={saveAlertSettings}
              disabled={saving}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-mag-primary/90 hover:bg-mag-primary disabled:opacity-50 text-white text-xs font-bold transition-all"
            >
              {saved ? <Check size={13} /> : <Save size={13} />}
              {saving ? 'Saving...' : saved ? 'Saved' : 'Save Alert Settings'}
            </button>
            <p className="text-[10px] font-mono text-mag-text-dim/40">
              Per-device recipients override the global default for SMS, WhatsApp & email alerts.
            </p>
          </div>
        )}
      </div>

      {!latestLocation && (
        <div className="text-mag-text-dim/30 text-[10px] font-mono text-center py-4">
          No location data available yet.
        </div>
      )}

      {/* Permanent deletion (privacy policy promise) */}
      <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4">
        {!confirmDelete ? (
          <button
            onClick={() => { setConfirmDelete(true); setDeleteError(''); }}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-mag-danger/25 text-mag-danger/80 hover:text-mag-danger hover:border-mag-danger/50 hover:bg-mag-danger/[0.05] text-[11px] font-mono font-bold uppercase tracking-wider transition-all"
          >
            <Trash2 size={13} />
            Delete Device Permanently
          </button>
        ) : (
          <div className="space-y-2.5">
            <div className="text-[11px] font-mono text-mag-danger/90 leading-relaxed">
              Permanently delete <span className="font-bold">{device.alias || device.model || device.id}</span>? All
              locations, media, evidence, alerts & recovery requests are erased. This cannot be undone.
            </div>
            {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  setDeleting(true);
                  setDeleteError('');
                  try {
                    await getAPI().deleteDevice(device.id);
                    const { devices: freshDevices } = await getAPI().getDevices();
                    setDevices(freshDevices);
                    // If the deleted device was selected, move to the first
                    // remaining device so the panel doesn't go stale.
                    if (selectedDeviceId === device.id) {
                      selectDevice(freshDevices[0]?.id ?? null);
                    }
                    setConfirmDelete(false);
                  } catch (e: any) {
                    setDeleteError(e.message || 'Failed to delete device');
                    // Keep the confirm card open so the error stays visible.
                  } finally {
                    setDeleting(false);
                  }
                }}
                disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[11px] font-bold transition-all"
              >
                <Trash2 size={12} />
                {deleting ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                disabled={deleting}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[11px] font-bold transition-all"
              >
                <X size={12} />
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
