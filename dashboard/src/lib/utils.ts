import { clsx, type ClassValue } from 'clsx';

// ─── External URLs ───────────────────────────────────────────────────────────

// The release APK is served from the API host — see /apk/download in
// server/main.py (same host the footer's API docs link to).
export const APK_DOWNLOAD_URL = 'https://api.magneetar.me/apk/download';

// SHA-256 checksum metadata for the exact APK /apk/download serves — see
// /apk/checksum in server/main.py. Used by the /download page so users can
// verify a sideloaded file byte-for-byte before installing.
export const APK_CHECKSUM_URL = 'https://api.magneetar.me/apk/checksum';

// ─── Math Helpers ───────────────────────────────────────────────────────────
function toRad(deg: number): number {
  return deg * (Math.PI / 180);
}

function toDeg(rad: number): number {
  return rad * (180 / Math.PI);
}

// ─── Class Name Utility ──────────────────────────────────────────────────────

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

// ─── Device Display Name ─────────────────────────────────────────────────────

/**
 * Best display name for a device. Devices register with a hardware model
 * (e.g. "Samsung SM-A037F") but no alias, so the old `alias || 'Device'`
 * rendered every un-renamed device as a useless "Device" — ambiguous once an
 * account owns several phones. Prefer the owner's alias, then the registered
 * model, and only fall back to a generic label.
 */
export function deviceDisplayName(
  device: { alias?: string | null; model?: string | null } | null | undefined
): string {
  if (!device) return 'Device';
  if (device.alias && device.alias.trim()) return device.alias;
  if (device.model && device.model.trim()) return device.model;
  return 'Device';
}

// ─── Time Utilities ──────────────────────────────────────────────────────────

/**
 * Parse a server timestamp robustly. The DB stores two formats:
 * - ISO-8601 with offset: "2026-08-02T10:00:00.123456+00:00" (server writes)
 * - SQLite CURRENT_TIMESTAMP: "2026-08-01 20:34:00" (legacy rows, UTC)
 * `new Date()` fails on the space-separated format in some engines (e.g.
 * Safari) and `new Date(undefined)` yields Invalid Date — both produced the
 * "Invalid Date" text seen in Trail Replay. Returns null when unparseable.
 */
export function parseTimestamp(ts: string | null | undefined): Date | null {
  if (!ts) return null;
  let value = ts;
  // Normalize SQLite "YYYY-MM-DD HH:MM:SS" (UTC) into ISO with a UTC marker.
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(value)) {
    value = value.replace(' ', 'T') + 'Z';
  }
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Best display timestamp for a location row. The server's location rows carry
 * server_timestamp / device_timestamp but no `timestamp` field — reading
 * `loc.timestamp` directly was undefined → "Invalid Date".
 */
export function locationTimestamp(
  loc: {
    timestamp?: string | null;
    server_timestamp?: string | null;
    device_timestamp?: string | null;
  } | null | undefined
): string | null {
  if (!loc) return null;
  return loc.server_timestamp || loc.device_timestamp || loc.timestamp || null;
}

export function relativeTime(ts: string | null | undefined): string {
  if (!ts) return 'Never';
  const d = parseTimestamp(ts);
  if (!d) return 'Never';
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 5) return 'Just now';
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function formatTimestamp(ts: string | null | undefined): string {
  const d = parseTimestamp(ts);
  if (!d) return '—';
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * True when lastSeen falls inside the freshness window.
 *
 * Default (5 min) mirrors the server's definition of online — the dashboard
 * API computes is_online at <300s (server/routes/dashboard.py), the active-
 * device count uses '-5 minutes', and devices heartbeat every 60s. A 60s
 * threshold (the old default) flipped devices to offline on a single missed
 * heartbeat even though the server still considered them online.
 */
export function isOnline(lastSeen: string | null, thresholdMs = 300000): boolean {
  if (!lastSeen) return false;
  const d = parseTimestamp(lastSeen);
  if (!d) return false;
  return Date.now() - d.getTime() < thresholdMs;
}

// ─── Distance Utilities ──────────────────────────────────────────────────────

export function calculateDistance(
  lat1: number, lng1: number,
  lat2: number, lng2: number
): number {
  const R = 6371000; // Earth's radius in meters
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLng / 2) * Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export function calculateBearing(
  lat1: number, lng1: number,
  lat2: number, lng2: number
): number {
  const dLng = toRad(lng2 - lng1);
  const y = Math.sin(dLng) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLng);
  let bearing = toDeg(Math.atan2(y, x));
  return (bearing + 360) % 360;
}

export function bearingToLabel(bearing: number): string {
  const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const index = Math.round(bearing / 45) % 8;
  return directions[index];
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters)}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.round((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

// ─── Coordinate Utilities ────────────────────────────────────────────────────

export function formatCoordinate(value: number, type: 'lat' | 'lng'): string {
  const abs = Math.abs(value);
  const deg = Math.floor(abs);
  const min = Math.floor((abs - deg) * 60);
  const sec = ((abs - deg - min / 60) * 3600).toFixed(1);
  const dir = type === 'lat'
    ? (value >= 0 ? 'N' : 'S')
    : (value >= 0 ? 'E' : 'W');
  return `${deg}°${min}'${sec}"${dir}`;
}

export function formatDecimal(value: number, decimals = 6): string {
  return value.toFixed(decimals);
}

// ─── Navigation Utilities ────────────────────────────────────────────────────

export function openGoogleMapsDirections(
  destLat: number,
  destLng: number,
  originLat?: number,
  originLng?: number
): void {
  let url: string;
  if (originLat !== undefined && originLng !== undefined) {
    url = `https://www.google.com/maps/dir/${originLat},${originLng}/${destLat},${destLng}`;
  } else {
    url = `https://www.google.com/maps/dir/?api=1&destination=${destLat},${destLng}`;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function openWazeDirections(destLat: number, destLng: number): void {
  const url = `https://www.waze.com/ul?ll=${destLat},${destLng}&navigate=yes`;
  window.open(url, '_blank', 'noopener,noreferrer');
}

// ─── Command Utilities ───────────────────────────────────────────────────────

export function getCommandLabel(command: string): string {
  const labels: Record<string, string> = {
    ping: 'PING',
    capture_photo: 'PHOTO',
    capture_audio: 'AUDIO',
    lock: 'LOCK',
    wipe: 'WIPE',
    alarm: 'SIREN',
    display_message: 'MESSAGE',
    get_sim_info: 'SIM INFO',
    get_battery: 'BATTERY',
    reboot: 'REBOOT',
  };
  return labels[command] || command.toUpperCase();
}

export function isDestructiveCommand(command: string): boolean {
  return ['wipe', 'reboot'].includes(command);
}

// ─── Signal Strength ─────────────────────────────────────────────────────────

export type SignalLevel = 'strong' | 'medium' | 'weak' | 'none';

export function getSignalLevel(lastSeen: string | null): SignalLevel {
  if (!lastSeen) return 'none';
  const d = parseTimestamp(lastSeen);
  if (!d) return 'none';
  const diff = Date.now() - d.getTime();
  // Buckets mirror the online window: devices heartbeat every 60s and the
  // server keeps a device 'online' for 5 minutes, so anything within that
  // window is a live signal — only past it do we drop to 'none'.
  if (diff < 60000) return 'strong';
  if (diff < 180000) return 'medium';
  if (diff < 300000) return 'weak';
  return 'none';
}
