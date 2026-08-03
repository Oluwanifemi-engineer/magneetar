import { Device, Location, Command, MediaItem, MediaDetail, ErrorLogResponse, GuardianProfile, RecoveryRequest, NearbyRecoveryRequest, UserProfile } from '@/types';

// ─── Configuration ───────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── API Client ──────────────────────────────────────────────────────────────

class MagneetarAPI {
  private serverUrl: string;
  private apiKey: string;

  constructor(serverUrl: string = API_BASE, apiKey: string = '') {
    this.serverUrl = serverUrl.replace(/\/+$/, '');
    this.apiKey = apiKey;
  }

  setCredentials(serverUrl: string, apiKey: string) {
    this.serverUrl = serverUrl.replace(/\/+$/, '');
    this.apiKey = apiKey;
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    // Fall back to the session's stored token when the shared singleton hasn't
    // been configured yet — e.g. the Sidebar's stats fetch can fire before
    // useDevices() sets credentials on the instance, which used to send an
    // empty Bearer token and 401 on first load after login.
    const sessionKey = typeof window !== 'undefined'
      ? sessionStorage.getItem('mt_api_key')
      : null;
    const key = this.apiKey || sessionKey || '';

    // Both login modes (account and API-key) store a JWT in mt_api_key — the
    // API-key login exchanges the key for a dashboard JWT. The raw key is
    // NEVER sent as a header: the master key ships inside the public APK, so
    // an x-api-key header fallback made anyone with the APK a platform admin
    // (removed server-side). Always authenticate with Bearer.
    headers['Authorization'] = `Bearer ${key}`;
    return headers;
  }

  private async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    const opts: RequestInit = {
      method,
      headers: this.headers(),
    };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${this.serverUrl}${path}`, opts);
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(extractErrorMessage(error) || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // ── Health ──────────────────────────────────────────────────────────────

  async healthCheck(): Promise<{ status: string; time: string }> {
    return this.request('/health');
  }

  // ── Account / plan ──────────────────────────────────────────────────────

  /** Current user profile — plan tier + enforced device allowance. */
  async fetchMe(): Promise<UserProfile> {
    return this.request('/api/auth/me');
  }

  // ── Devices ─────────────────────────────────────────────────────────────

  async getDevices(): Promise<{ devices: Device[] }> {
    return this.request('/api/dashboard/devices');
  }

  // ── Locations ───────────────────────────────────────────────────────────

  async getLocations(deviceId: string, limit = 200): Promise<{ locations: Location[] }> {
    return this.request(`/api/dashboard/locations/${deviceId}?limit=${limit}`);
  }

  // ── Commands ────────────────────────────────────────────────────────────

  async getCommands(deviceId: string): Promise<{ commands: Command[] }> {
    return this.request(`/api/dashboard/commands/${deviceId}`);
  }

  async issueCommand(deviceId: string, command: string, params = ''): Promise<{ status: string; command_id: number }> {
    return this.request('/api/dashboard/command', 'POST', {
      device_id: deviceId,
      command,
      params,
    });
  }

  // ── Media ───────────────────────────────────────────────────────────────

  async getMedia(deviceId: string): Promise<{ media: MediaItem[] }> {
    return this.request(`/api/dashboard/media/${deviceId}`);
  }

  async getMediaFile(mediaId: number): Promise<MediaDetail> {
    return this.request(`/api/dashboard/media/file/${mediaId}`);
  }

  /**
   * Delete a media item. Step-up auth: requires the account password (user
   * mode) or the master API key (admin mode) — a dashboard session alone is
   * not enough to destroy evidence.
   */
  async deleteMedia(mediaId: number, password: string): Promise<{ status: string; deleted_id: number }> {
    return this.request(`/api/dashboard/media/${mediaId}/delete`, 'POST', { password });
  }

  // ── Generic Request ────────────────────────────────────────────────────────

  async fetch<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
    return this.request<T>(path, method, body);
  }

  // ── Evidence ────────────────────────────────────────────────────────────

  async getEvidence(deviceId: string): Promise<any> {
    return this.request(`/api/dashboard/evidence/${deviceId}`);
  }

  async generateEvidencePDF(deviceId: string): Promise<any> {
    return this.request(`/api/dashboard/evidence/${deviceId}/generate-pdf`, 'POST');
  }

  // ── Alerts ──────────────────────────────────────────────────────────────

  async getAlerts(deviceId: string): Promise<{ alerts: any[] }> {
    return this.request(`/api/dashboard/alerts/${deviceId}`);
  }

  // ── Stats ───────────────────────────────────────────────────────────────

  async getStats(): Promise<{
    total_devices: number;
    active_devices: number;
    stolen_devices: number;
    total_locations: number;
    total_media: number;
    alerts_today: number;
  }> {
    return this.request('/api/dashboard/stats');
  }

  // ── Geofences ───────────────────────────────────────────────────────────

  async getGeofences(deviceId: string): Promise<{ geofences: any[] }> {
    return this.request(`/api/dashboard/geofences/${deviceId}`);
  }

  async createGeofence(data: {
    device_id: string;
    name?: string;
    center_lat: number;
    center_lng: number;
    radius_meters: number;
    is_safe_zone?: boolean;
  }): Promise<{ status: string; geofence_id: number }> {
    return this.request('/api/dashboard/geofence', 'POST', data);
  }

  async deleteGeofence(geofenceId: number): Promise<{ status: string }> {
    return this.request(`/api/dashboard/geofence/${geofenceId}`, 'DELETE');
  }

  // ── Error Log ──────────────────────────────────────────────────────────

  async getErrors(unresolvedOnly = false): Promise<ErrorLogResponse> {
    const params = unresolvedOnly ? '?unresolved_only=true' : '';
    return this.request(`/api/dashboard/errors${params}`);
  }

  async resolveError(errorId: number, notes = ''): Promise<{ status: string }> {
    return this.request(`/api/dashboard/errors/${errorId}/resolve`, 'PATCH', { notes });
  }

  // ── Device Management ───────────────────────────────────────────────────

  async updateDeviceAlias(deviceId: string, alias: string): Promise<{ status: string }> {
    return this.request(`/api/dashboard/devices/${deviceId}/alias`, 'PATCH', { alias });
  }

  async updateDeviceAlertSettings(
    deviceId: string,
    alertPhone: string,
    alertEmail: string,
    opts: {
      alert_channels?: string[] | null;
      enabled_types?: string[] | null;
      quiet_hours_start?: number | null;
      quiet_hours_end?: number | null;
    } = {},
  ): Promise<{
    status: string;
    alert_phone: string;
    alert_email: string;
    alert_channels: string[] | null;
    enabled_types: string[] | null;
    quiet_hours_start: number | null;
    quiet_hours_end: number | null;
  }> {
    return this.request(`/api/dashboard/devices/${deviceId}/alert-settings`, 'PATCH', {
      alert_phone: alertPhone,
      alert_email: alertEmail,
      ...opts,
    });
  }

  async markDeviceRecovered(deviceId: string): Promise<{ status: string }> {
    return this.request(`/api/dashboard/devices/${deviceId}/recover`, 'POST');
  }

  async deleteDevice(deviceId: string, password: string): Promise<{ status: string; message: string }> {
    // Step-up password: deletion is destructive, so the server re-authenticates
    // with the account password (users) or the master API key (admin).
    return this.request(`/api/dashboard/devices/${deviceId}`, 'DELETE', { password });
  }

  async deleteAccount(): Promise<{ status: string; message: string; devices_removed: number }> {
    return this.request('/api/auth/user/account', 'DELETE');
  }

  // ── Guardian Network (community recovery) ────────────────────────────────

  async getGuardianProfile(): Promise<GuardianProfile> {
    return this.request('/api/guardian/profile');
  }

  async setGuardianOptIn(data: {
    opted_in: boolean;
    radius_km?: number;
    handle?: string;
  }): Promise<GuardianProfile> {
    return this.request('/api/guardian/opt-in', 'POST', data);
  }

  async launchRecovery(deviceId: string, description?: string): Promise<RecoveryRequest> {
    return this.request('/api/recovery/requests', 'POST', { device_id: deviceId, description });
  }

  async getRecoveryRequests(): Promise<{ requests: RecoveryRequest[] }> {
    return this.request('/api/recovery/requests');
  }

  async closeRecovery(requestId: string): Promise<{ status: string; message: string; request_id: string }> {
    return this.request(`/api/recovery/requests/${requestId}/close`, 'POST');
  }

  async getNearbyRecovery(lat: number, lng: number, radiusKm = 20): Promise<{ requests: NearbyRecoveryRequest[] }> {
    return this.request(`/api/recovery/nearby?lat=${lat}&lng=${lng}&radius_km=${radiusKm}`);
  }

  async reportSighting(data: {
    request_id: string;
    lat: number;
    lng: number;
    note?: string;
  }): Promise<{ status: string; sighting_id: number; guardian_handle: string }> {
    return this.request('/api/recovery/sightings', 'POST', data);
  }
}

// ─── Singleton ───────────────────────────────────────────────────────────────

/**
 * Convert a FastAPI error body into a readable string.
 * 422 validation errors put an array of `{loc, msg}` objects in `detail`;
 * stringifying that directly yields "[object Object]".
 * Returns the fallback when nothing readable is found.
 */
export function extractErrorMessage(body: any, fallback = ''): string {
  const detail = body?.detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) => (typeof d?.msg === 'string' ? d.msg : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  if (typeof detail === 'string' && detail.trim()) return detail;
  return fallback;
}

let apiInstance: MagneetarAPI | null = null;

export function getAPI(serverUrl?: string, apiKey?: string): MagneetarAPI {
  if (!apiInstance) {
    apiInstance = new MagneetarAPI(serverUrl, apiKey);
  } else if (serverUrl && apiKey) {
    apiInstance.setCredentials(serverUrl, apiKey);
  }
  return apiInstance;
}

export default MagneetarAPI;
