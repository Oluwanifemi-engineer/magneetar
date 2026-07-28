// ─── Device ──────────────────────────────────────────────────────────────────

export interface Device {
  id: string;
  alias: string | null;
  model: string | null;
  os_version: string | null;
  app_version: string | null;
  last_seen: string;
  registered: string;
  is_stolen: boolean;
  operating_mode: string;
  sentinel_score: number;
  lat: number | null;
  lng: number | null;
  battery_percent: number | null;
  is_online: boolean;
}

export interface DeviceWithStatus extends Device {
  is_online: boolean;
  signal_strength: 'strong' | 'medium' | 'weak' | 'none';
  battery_level?: number;
  sim_info?: string;
}

// ─── Location ────────────────────────────────────────────────────────────────

export interface Location {
  id: number;
  device_id: string;
  lat: number;
  lng: number;
  accuracy: number | null;
  accuracy_horizontal: number | null;
  provider: string;
  speed: number | null;
  bearing: number | null;
  battery_percent: number | null;
  altitude: number | null;
  sentinel_score: number | null;
  threat_level: string | null;
  anomalies: string[] | null;
  timestamp: string;
  server_timestamp: string | null;
  device_timestamp: string | null;
  is_charging: boolean | null;
  network_type: string | null;
  sim_changed: boolean | null;
  is_airplane_mode: boolean | null;
  is_location_enabled: boolean | null;
  activity_type: string | null;
  confidence_level: string;
}

export interface LocationWithMeta extends Location {
  distance_from_user?: number;
  bearing_from_user?: number;
  address?: string;
}

// ─── Commands ────────────────────────────────────────────────────────────────

export type CommandType =
  | 'ping'
  | 'capture_photo'
  | 'capture_audio'
  | 'lock'
  | 'wipe'
  | 'siren'
  | 'display_message'
  | 'get_sim_info'
  | 'get_battery'
  | 'reboot';

export interface Command {
  id: number;
  device_id: string;
  command: string;
  params: string;
  status: 'pending' | 'executed' | 'failed';
  issued_at: string;
  executed_at: string | null;
}

// ─── Media ───────────────────────────────────────────────────────────────────

export type MediaType = 'photo' | 'audio';

export interface MediaItem {
  id: number;
  device_id: string;
  type: MediaType;
  timestamp: string;
}

export interface MediaDetail extends MediaItem {
  data_b64: string;
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface AuthState {
  server_url: string;
  api_key: string;
  isAuthenticated: boolean;
  isConnected: boolean;
}

// ─── Map ─────────────────────────────────────────────────────────────────────

export interface MapState {
  center: [number, number];
  zoom: number;
  selectedDeviceId: string | null;
  followDevice: boolean;
  showTrail: boolean;
  showGeofence: boolean;
}

// ─── UI State ────────────────────────────────────────────────────────────────

export type TabId = 'sentinel' | 'commands' | 'location' | 'media' | 'evidence' | 'alerts' | 'errors';

export interface UIState {
  sidebarOpen: boolean;
  activeTab: TabId;
  commandLogOpen: boolean;
}

// ─── Navigation ──────────────────────────────────────────────────────────────

export interface NavigationInfo {
  distance: number;        // meters
  bearing: number;         // degrees (0-360)
  bearingLabel: string;    // N, NE, E, SE, S, SW, W, NW
  estimatedTime: string;   // formatted time string
  speed: number;           // assumed km/h
}

// ─── Alert ───────────────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  device_id: string;
  type: 'sim_change' | 'offline' | 'geofence_breach' | 'low_battery' | 'command_failed' | 'intruder_detected';
  message: string;
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  read: boolean;
}

// ─── Evidence ────────────────────────────────────────────────────────────────

export interface EvidenceCase {
  case_id: string | null;
  status: string;
  item_counts: {
    locations: number;
    photos: number;
    audio: number;
  };
  sha256_chain: string | null;
  created_at: string | null;
  theft_time: string | null;
}

// ─── Error Log ────────────────────────────────────────────────────────────────

export interface ErrorLogEntry {
  id: number;
  timestamp: string;
  level: 'ERROR' | 'CRITICAL';
  source: string | null;
  message: string;
  traceback: string | null;
  request_method: string | null;
  request_path: string | null;
  request_ip: string | null;
  user_agent: string | null;
  device_id: string | null;
  resolved: boolean;
  resolved_at: string | null;
  resolved_by: string | null;
  notes: string | null;
}

export interface ErrorLogResponse {
  errors: ErrorLogEntry[];
  unresolved_count: number;
  total_count: number;
}

// ─── Geofence ────────────────────────────────────────────────────────────────

export interface Geofence {
  id: number;
  device_id: string;
  name: string | null;
  center_lat: number;
  center_lng: number;
  radius_meters: number;
  is_safe_zone: boolean;
  active: boolean;
}
