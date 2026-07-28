import { Device, Location, Command, MediaItem, MediaDetail, ErrorLogResponse } from '@/types';

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
    // Use auth mode from sessionStorage to determine header format
    const authMode = typeof window !== 'undefined' 
      ? sessionStorage.getItem('mt_auth_mode') 
      : null;
    
    if (authMode === 'user') {
      // User account login — JWT token goes in Authorization header
      headers['Authorization'] = `Bearer ${this.apiKey}`;
    } else {
      // API key login — goes in x-api-key header
      headers['x-api-key'] = this.apiKey;
    }
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
      throw new Error(error.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // ── Health ──────────────────────────────────────────────────────────────

  async healthCheck(): Promise<{ status: string; time: string }> {
    return this.request('/health');
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

  async markDeviceRecovered(deviceId: string): Promise<{ status: string }> {
    return this.request(`/api/dashboard/devices/${deviceId}/recover`, 'POST');
  }
}

// ─── Singleton ───────────────────────────────────────────────────────────────

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
