'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, formatCoordinate } from '@/lib/utils';
import { MagInput, MagButton, MagStatusPill } from '@/components/ui/MagPrimitives';
import { Fence, MapPin, Plus, Trash2, ShieldAlert, Camera, Volume2, Loader, Check } from 'lucide-react';
import { useToast } from '@/components/ui/Toast';
import type { Geofence, GeofenceAutoAction } from '@/types';

const POLICY_OPTIONS: { value: GeofenceAutoAction; label: string; hint: string }[] = [
  { value: null, label: 'Alert only', hint: 'Send the geofence-exit alert, no on-device reaction' },
  { value: 'capture', label: 'Capture', hint: 'Front-camera photo + audio capture' },
  { value: 'siren', label: 'Siren', hint: 'Max-volume alarm + exit alert' },
];

function policyLabel(action: GeofenceAutoAction): string {
  if (action === 'capture') return 'CAPTURE';
  if (action === 'siren') return 'SIREN';
  return 'ALERT';
}

export function GeofencePanel() {
  const { selectedDeviceId, latestLocation, devices } = useStore();
  const { toast } = useToast();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const canManage = accessRole === 'owner' || accessRole === 'admin';

  const [zones, setZones] = useState<Geofence[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [name, setName] = useState('');
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [radius, setRadius] = useState('200');
  const [isSafeZone, setIsSafeZone] = useState(true);
  const [autoAction, setAutoAction] = useState<GeofenceAutoAction>(null);
  const [nameError, setNameError] = useState('');
  const formRef = useRef<HTMLFormElement>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const fetchZones = useCallback(async () => {
    if (!selectedDeviceId) return;
    setLoading(true);
    try {
      const res = await getAPI().getGeofences(selectedDeviceId);
      setZones(res.geofences ?? []);
    } catch (e) {
      console.error('Failed to fetch geofences:', e);
    } finally {
      setLoading(false);
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    fetchZones();
  }, [fetchZones]);

  const deviceKey = selectedDeviceId;
  const [lastDeviceKey, setLastDeviceKey] = useState<string | null>(null);
  if (deviceKey && deviceKey !== lastDeviceKey) {
    setLastDeviceKey(deviceKey);
    if (latestLocation && latestLocation.lat != null && latestLocation.lng != null) {
      setLat(String(latestLocation.lat));
      setLng(String(latestLocation.lng));
    }
    setFormOpen(false);
    setError('');
  }

  const createZone = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedDeviceId || creating) return;      const centerLat = Number(lat);
      const centerLng = Number(lng);
      const radiusMeters = Number(radius);
      if (!Number.isFinite(centerLat) || centerLat < -90 || centerLat > 90) {
        // The latitude input already shows the inline message via its error prop.
        const latField = formRef.current?.querySelector<HTMLInputElement>('#zone-lat');
        latField?.focus();
        return;
      }
      if (!Number.isFinite(centerLng) || centerLng < -180 || centerLng > 180) {
        setError('Enter a valid longitude (-180 to 180).');
        return;
      }
      if (!Number.isFinite(radiusMeters) || radiusMeters <= 0 || radiusMeters > 50000) {
        setError('Enter a radius between 1 and 50,000 meters.');
        return;
      }
      setCreating(true);
      setError('');
      setNameError('');
      try {
        await getAPI().createGeofence({
          device_id: selectedDeviceId,
          name: name.trim() || undefined,
          center_lat: centerLat,
          center_lng: centerLng,
          radius_meters: radiusMeters,
          is_safe_zone: isSafeZone,
          auto_action: autoAction,
        });
        toast('Geofence zone created', 'success');
        setName('');
        setFormOpen(false);
        await fetchZones();
      } catch (err: any) {
        setError(err?.message || 'Failed to create geofence');
      } finally {
        setCreating(false);
      }
    };

  const deleteZone = async (zone: Geofence) => {
    if (deletingId !== null) return;
    setDeletingId(zone.id);
    try {
      await getAPI().deleteGeofence(zone.id);
      toast('Zone deleted', 'success');
      await fetchZones();
    } catch (err: any) {
      toast(err?.message || 'Failed to delete zone', 'error');
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const armDelete = (zone: Geofence) => {
    if (confirmDeleteId === zone.id) {
      setConfirmDeleteId(null);
      deleteZone(zone);
    } else {
      setConfirmDeleteId(zone.id);
      setTimeout(() => {
        setConfirmDeleteId(cur => (cur === zone.id ? null : cur));
      }, 2500);
    }
  };

  if (!selectedDeviceId) {
    return (
      <div className="p-4 space-y-4">
        <div className="mag-panel-header">
          <Fence size={12} className="text-mag-text-muted" />
          <span className="mag-panel-label">Geofence Zones</span>
        </div>
        <div className="mag-empty">
          <div className="mag-empty-icon">
            <MapPin size={16} className="text-mag-text-muted" />
          </div>
          <div className="mag-empty-head">No device selected</div>
          <div className="mag-empty-sub">
            Select a device from the sidebar to manage its geofence zones.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="mag-panel-header">
        <Fence size={12} className="text-mag-text-muted" />
        <span className="mag-panel-label">Geofence Zones</span>
        <div className="ml-auto flex items-center gap-2">
          {canManage && (
            <span className="text-[9px] font-mono text-mag-text-muted/60">
              {zones && zones.length ? `${zones.length} zone${zones.length === 1 ? '' : 's'}` : 'No zones'}
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {loading && !zones ? (
          <div className="text-center py-8">
            <Loader size={18} className="animate-spin mx-auto text-emerald-500/40" />
            <div className="text-mag-text-muted text-[10px] font-mono mt-2">Loading zones...</div>
          </div>
        ) : !zones || zones.length === 0 ? (
          <div className="mag-empty">
            <div className="mag-empty-icon">
              <MapPin size={16} className="text-mag-text-muted" />
            </div>
            <div className="mag-empty-head">No zones yet</div>
            <div className="mag-empty-sub">
              Create a safe zone to get an alert the moment the device leaves it.
            </div>
          </div>
        ) : (
          zones.map(zone => (
            <div
              key={zone.id}
              className="mag-row"
            >
              <div className="flex items-center gap-2">
                <div className={cn(
                  'w-1.5 h-1.5 rounded-full shrink-0',
                  zone.is_safe_zone ? 'bg-emerald-500' : 'bg-amber-500'
                )} />
                <div className="text-[11px] font-bold text-mag-text truncate flex-1 min-w-0">
                  {zone.name || `Zone #${zone.id}`}
                </div>
                <MagStatusPill
                  variant={zone.is_safe_zone ? 'secure' : 'elevated'}
                  className="shrink-0"
                >
                  {zone.is_safe_zone ? 'Safe' : 'Restricted'}
                </MagStatusPill>
              </div>

              <div className="text-[9px] font-mono text-mag-text-muted leading-relaxed">
                {formatCoordinate(zone.center_lat, 'lat')}, {formatCoordinate(zone.center_lng, 'lng')}
                <span className="text-mag-text-muted/60"> · {Math.round(zone.radius_meters)}m</span>
              </div>

              <div className="flex items-center justify-between gap-2">
                <span
                  title={
                    zone.auto_action === 'capture'
                      ? 'On exit: front-camera photo + audio capture'
                      : zone.auto_action === 'siren'
                        ? 'On exit: max-volume alarm'
                        : 'On exit: alert only'
                  }
                  className="mag-chip border-mag-border bg-mag-surface/40 text-mag-text-muted"
                >
                  {zone.auto_action === 'capture' ? (
                    <Camera size={8} className="text-mag-text-muted" />
                  ) : zone.auto_action === 'siren' ? (
                    <Volume2 size={8} className="text-mag-text-muted" />
                  ) : (
                    <ShieldAlert size={8} className="text-mag-text-muted" />
                  )}
                  {policyLabel(zone.auto_action)}
                </span>
                {canManage && (
                  <button
                    onClick={() => armDelete(zone)}
                    disabled={deletingId !== null}
                    aria-label={`Delete zone ${zone.name || zone.id}`}
                    title={confirmDeleteId === zone.id ? 'Click again to confirm' : 'Delete zone'}
                    className={cn(
                      'mag-chip border transition-colors disabled:opacity-40 shrink-0',
                      confirmDeleteId === zone.id
                        ? 'border-red-500/30 bg-red-500/10 text-red-400'
                        : 'border-mag-border text-mag-text-muted hover:text-red-400 hover:border-red-500/20'
                    )}
                  >
                    {deletingId === zone.id ? (
                      <Loader size={10} className="animate-spin" />
                    ) : confirmDeleteId === zone.id ? (
                      'Confirm?'
                    ) : (
                      <Trash2 size={10} />
                    )}
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {!canManage ? (
        <p className="text-center text-[9px] font-mono text-mag-text-muted py-2">
          Read-only access — owner or admin can change zones.
        </p>
      ) : !formOpen ? (
        <MagButton
          variant="ghost"
          fullWidth
          onClick={() => { setFormOpen(true); setError(''); setNameError(''); }}
          icon={<Plus size={14} />}
        >
          Add Zone
        </MagButton>
      ) : (
        <form onSubmit={createZone} className="mag-panel-elevated p-4 space-y-3">
          <div className="mag-panel-header border-b border-mag-border/50">
            <span className="mag-panel-label">New Zone</span>
          </div>

          <MagInput
            label="Name (optional)"
            value={name}
            onChange={e => { setName(e.target.value); setNameError(''); }}
            maxLength={60}
            placeholder="e.g. Home, School, Office"
            aria-label="Zone name"
            error={!!nameError}
          />

          <div className="grid grid-cols-2 gap-2">
            <MagInput
              label="Latitude"
              value={lat}
              onChange={e => setLat(e.target.value)}
              inputMode="decimal"
              aria-label="Zone latitude"
              id="zone-lat"
              error={lat ? (Number(lat) < -90 || Number(lat) > 90 ? 'Enter a valid latitude (-90 to 90).' : false) : false}
            />
            <MagInput
              label="Longitude"
              value={lng}
              onChange={e => setLng(e.target.value)}
              inputMode="decimal"
              aria-label="Zone longitude"
              error={lat && lng ? (Number(lng) < -180 || Number(lng) > 180 ? 'Enter a valid longitude (-180 to 180).' : false) : false}
            />
          </div>

          <MagInput
            label="Radius (meters)"
            value={radius}
            onChange={e => setRadius(e.target.value)}
            inputMode="numeric"
            aria-label="Zone radius meters"
            type="number"
            error={radius ? (Number(radius) <= 0 || Number(radius) > 50000 ? 'Enter a radius between 1 and 50,000 meters.' : false) : false}
          />

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={isSafeZone}
              onChange={e => setIsSafeZone(e.target.checked)}
              aria-label="Safe zone"
              className="accent-emerald-500 w-4 h-4"
            />
            <span className="text-[9px] font-mono text-mag-text-dim font-bold">
              Safe zone (alert when device LEAVES it)
            </span>
          </label>

          <div>
            <div className="mag-field-label mb-1.5">Auto-action on exit</div>
            <div className="space-y-1.5">
              {POLICY_OPTIONS.map(opt => (
                <label
                  key={opt.label}
                  className={cn(
                    'flex items-start gap-2 p-2 rounded-lg border cursor-pointer transition-all select-none',
                    autoAction === opt.value
                      ? 'border-emerald-500/20 bg-emerald-500/5'
                      : 'border-mag-border bg-mag-surface/30 hover:border-mag-border/80'
                  )}
                >
                  <input
                    type="radio"
                    name="auto-action"
                    checked={autoAction === opt.value}
                    onChange={() => setAutoAction(opt.value)}
                    aria-label={`Auto action ${opt.label}`}
                    className="accent-emerald-500 mt-0.5"
                  />
                  <div className="flex flex-col">
                    <span className="block text-[9px] font-mono font-bold text-mag-text-dim">{opt.label}</span>
                    <span className="block text-[8px] font-mono text-mag-text-muted/70 leading-relaxed">{opt.hint}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {error && (
            <div className="text-[10px] font-mono text-red-400">{error}</div>
          )}

          <div className="mag-actions">
            <MagButton
              variant="primary"
              type="submit"
              loading={creating}
              icon={creating ? undefined : <Check size={12} />}
            >
              {creating ? 'Creating...' : 'Create Zone'}
            </MagButton>
            <MagButton
              variant="ghost"
              type="button"
              onClick={() => { setFormOpen(false); setError(''); setNameError(''); }}
              disabled={creating}
            >
              Cancel
            </MagButton>
          </div>
        </form>
      )}
    </div>
  );
}
