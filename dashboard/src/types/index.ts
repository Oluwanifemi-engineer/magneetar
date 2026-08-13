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
  capture_armed: boolean | null;
  alert_phone: string | null;
  alert_email: string | null;
  alert_channels: string[] | null;
  enabled_types: string[] | null;
  quiet_hours_start: number | null;
  quiet_hours_end: number | null;
  // Set when a device has been silent beyond the archive threshold (30 days
  // by default) — the server soft-archives it and any fresh telemetry clears
  // the flag. Archived devices are dimmed in the sidebar with a review &
  // purge flow (password-gated permanent deletion).
  archived_at: string | null;
  // Offline Command Relay (SMS): when a device is offline (no data), commands
  // are SMSed to sms_phone (E.164, the phone's SIM number) and executed
  // locally. Owner opt-in only — sms_commands_enabled defaults to false.
  sms_phone: string | null;
  sms_commands_enabled: boolean;
  // Milestone 2 P1 RBAC: the caller's effective role on this device.
  // 'owner' = the linked account; admin/viewer/device_only = shared grants
  // (family sharing). The UI hides write/delete controls below admin, and
  // coordinates/PII for device_only (the server strips them too).
  access_role: 'owner' | ShareRole;
  is_owner: boolean;
}

// ─── Device Sharing (Milestone 2 P1) ──────────────────────────────────────

// Roles granted via device sharing, least → most privileged:
// device_only — status glance only (online, battery, last seen). No location,
//               evidence, or command access (privacy tier).
// viewer      — full read access (locations, media, evidence, history).
// admin       — viewer + full control (commands, geofences, settings).
// Only the device OWNER can grant, change, or revoke shares (server-enforced).
export type ShareRole = 'admin' | 'viewer' | 'device_only';

export interface DeviceShare {
  id: string;
  device_id: string;
  grantee_user_id: string;
  role: ShareRole;
  email: string;
  display_name: string | null;
  created_at: string;
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

// NOTE: keep this in sync with the SERVER's valid command set
// (server/models.py CommandRequest.validate_command) AND the Android app
// (TrackingService.handleCommand). Commands the device cannot execute were
// removed (phantom_on/off, fake_shutdown, location_burst_stop,
// capture_photo_rear, display_message, get_sim_info, get_battery, reboot) —
// the old list advertised commands that would 422 on the server or always
// ack 'failed', i.e. buttons that could never work.
export type CommandType =
  | 'ping'
  | 'capture_photo'
  | 'capture_photo_front'
  | 'capture_audio'
  | 'location_burst'
  | 'lock'
  | 'wipe'
  // Wire command for the siren — the server (models.CommandRequest) and the
  // Android app (TrackingService.handleCommand) only accept 'alarm'.
  | 'alarm'
  // Lost Mode (v1.5) — locks the device to a full-screen recovery message
  // (Android LostModeActivity + LostModeManager). Implemented end-to-end on
  // all three sides: server validate_command, this type, TrackingService.
  | 'lost_mode';

export interface Command {
  id: number;
  device_id: string;
  command: string;
  params: string;
  // 'expired' = never acknowledged within its expiry window (server marks it
  // when listing history; the device poll skips it via the same check).
  status: 'pending' | 'executed' | 'failed' | 'expired';
  issued_at: string;
  executed_at: string | null;
  // Human-readable reason a FAILED ack failed (e.g. "Microphone muted — set
  // Microphone to Allow all the time"). Sent by the Android app, shown on
  // the command row so a red FAILED explains itself.
  failure_reason?: string | null;
  // How the command reached the device: 'poll' (normal network poll) or
  // 'sms' (offline command relay — delivered over SMS because the device had
  // no data). Surfaced so the operator knows the delivery path.
  delivery_channel?: 'poll' | 'sms' | null;
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

// User account profile from GET /api/auth/me — carries the plan tier and the
// device allowance the server enforces (free=1 / personal=3 / guardian=10 /
// enterprise=unlimited).
export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  tier: 'free' | 'personal' | 'guardian' | 'enterprise' | 'admin' | string;
  is_active: boolean;
  created_at: string | null;
  device_count: number;
  max_devices: number;
  // v1.4 account security: email verification + TOTP 2FA state.
  email_verified: boolean;
  totp_enabled: boolean;
}

// ─── Developer API Keys (docs/developer-api.md) ─────────────────────────────

// Scope set a developer key may carry. The key's effective rights are ALWAYS
// intersected with the owning account's own RBAC rights server-side — a
// viewer-shared device stays read-only even through a devices:write key.
export type ApiKeyScope =
  | 'devices:read'
  | 'devices:write'
  | 'alerts:read'
  | 'media:read';

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  scopes: ApiKeyScope[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

// Full key returned EXACTLY ONCE at creation — the server stores only the
// 12-char prefix + SHA-256 hash, so a lost response can't be recovered.
export interface ApiKeyCreated extends ApiKey {
  key: string;
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

// ─── Geofences ────────────────────────────────────────────────────────────────

// Per-zone automated reaction fired exactly once on an EXIT transition
// (server models.GeofenceRequest.validate_auto_action). 'alert' / null →
// geofence_exit alert only; 'capture' → front-camera photo + audio capture;
// 'siren' → the max-volume alarm. Mirror of the server's valid set.
export type GeofenceAutoAction = 'capture' | 'siren' | 'alert' | null;

export interface Geofence {
  id: number;
  device_id: string;
  name: string | null;
  center_lat: number;
  center_lng: number;
  radius_meters: number;
  is_safe_zone: boolean;
  active: boolean;
  // NULL = not yet observed inside (or legacy row) — no exit event fires.
  last_inside: boolean | null;
  auto_action: GeofenceAutoAction;
  created_at: string;
}

// ─── UI State ────────────────────────────────────────────────────────────────

export type TabId = 'sentinel' | 'commands' | 'location' | 'zones' | 'media' | 'evidence' | 'guardian' | 'alerts' | 'errors';

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

// ─── Guardian Network (community recovery) ───────────────────────────────────

export interface GuardianProfile {
  user_id: string;
  opted_in: boolean;
  radius_km: number;
  handle: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RecoverySighting {
  id: number;
  guardian_handle: string | null;
  lat: number;
  lng: number;
  note: string | null;
  created_at: string | null;
}

export interface RecoveryRequest {
  id: string;
  device_id: string;
  status: 'active' | 'closed';
  description: string | null;
  created_at: string | null;
  closed_at: string | null;
  closed_reason: string | null;
  sighting_count: number;
  sightings: RecoverySighting[];
}

export interface NearbyRecoveryRequest {
  id: string;
  device_model: string | null;
  description: string | null;
  distance_km: number;
  blurred_lat: number;
  blurred_lng: number;
  sighting_count: number;
  created_at: string | null;
}
