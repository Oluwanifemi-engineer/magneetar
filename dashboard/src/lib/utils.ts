import { clsx, type ClassValue } from 'clsx';

// ─── External URLs ───────────────────────────────────────────────────────────

// The release APK is served from the API host — see /apk/download in
// server/main.py (same host the footer's API docs link to).
export const APK_DOWNLOAD_URL = 'https://api.magneetar.me/apk/download';

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

// ─── Time Utilities ──────────────────────────────────────────────────────────

export function relativeTime(ts: string | null | undefined): string {
  if (!ts) return 'Never';
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 5) return 'Just now';
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

export function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function isOnline(lastSeen: string | null, thresholdMs = 60000): boolean {
  if (!lastSeen) return false;
  return Date.now() - new Date(lastSeen).getTime() < thresholdMs;
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
  const diff = Date.now() - new Date(lastSeen).getTime();
  if (diff < 15000) return 'strong';
  if (diff < 30000) return 'medium';
  if (diff < 60000) return 'weak';
  return 'none';
}
