'use client';

import { create } from 'zustand';
import { Device, Location, Command, MediaItem, TabId, Alert } from '@/types';
import { isOnline, getSignalLevel, calculateDistance, calculateBearing, bearingToLabel } from '@/lib/utils';

// ─── Store Types ─────────────────────────────────────────────────────────────

interface MagneetarState {
  // Auth
  serverUrl: string;
  apiKey: string;
  isAuthenticated: boolean;
  isConnected: boolean;
  setCredentials: (serverUrl: string, apiKey: string) => void;
  setConnected: (connected: boolean) => void;
  logout: () => void;

  // Devices
  devices: Device[];
  selectedDeviceId: string | null;
  setDevices: (devices: Device[]) => void;
  selectDevice: (id: string | null) => void;

  // Locations
  locations: Location[];
  latestLocation: Location | null;
  setLocations: (locations: Location[]) => void;

  // Commands
  commands: Command[];
  setCommands: (commands: Command[]) => void;

  // Media
  media: MediaItem[];
  setMedia: (media: MediaItem[]) => void;

  // Map
  mapCenter: [number, number];
  mapZoom: number;
  followDevice: boolean;
  showTrail: boolean;
  setMapCenter: (center: [number, number]) => void;
  setMapZoom: (zoom: number) => void;
  setFollowDevice: (follow: boolean) => void;
  setShowTrail: (show: boolean) => void;

  // UI
  sidebarOpen: boolean;
  activeTab: TabId;
  setSidebarOpen: (open: boolean) => void;
  setActiveTab: (tab: TabId) => void;

  // Alerts
  alerts: Alert[];
  unreadAlertCount: number;
  addAlert: (alert: Alert) => void;
  markAlertRead: (id: string) => void;
  clearAlerts: () => void;

  // Computed helpers
  getSelectedDevice: () => Device | null;
  getDeviceStatus: (deviceId: string) => { isOnline: boolean; signal: string };
  getNavigationInfo: (userLat: number, userLng: number) => {
    distance: number;
    bearing: number;
    bearingLabel: string;
  } | null;
}

// ─── Store ───────────────────────────────────────────────────────────────────

export const useStore = create<MagneetarState>((set, get) => ({
  // Auth
  serverUrl: '',
  apiKey: '',
  isAuthenticated: false,
  isConnected: false,

  setCredentials: (serverUrl, apiKey) =>
    set({ serverUrl, apiKey, isAuthenticated: true }),

  setConnected: (connected) =>
    set({ isConnected: connected }),

  logout: () =>
    set({
      isAuthenticated: false,
      isConnected: false,
      serverUrl: '',
      apiKey: '',
      devices: [],
      selectedDeviceId: null,
      locations: [],
      latestLocation: null,
      commands: [],
      media: [],
      alerts: [],
    }),

  // Devices
  devices: [],
  selectedDeviceId: null,

  setDevices: (devices) => {
    const state = get();
    if (!state.selectedDeviceId && devices.length > 0) {
      set({ devices, selectedDeviceId: devices[0].id });
    } else {
      set({ devices });
    }
  },

  selectDevice: (id) => {
    set({ selectedDeviceId: id, locations: [], commands: [], media: [], latestLocation: null });
  },

  // Locations
  locations: [],
  latestLocation: null,

  setLocations: (locations) => {
    const latest = locations.length > 0 ? locations[0] : null;
    set({ locations, latestLocation: latest });
    if (latest && get().followDevice) {
      set({ mapCenter: [latest.lat, latest.lng] });
    }
  },

  // Commands
  commands: [],
  setCommands: (commands) => set({ commands }),

  // Media
  media: [],
  setMedia: (media) => set({ media }),

  // Map
  mapCenter: [9.0820, 8.6753],
  mapZoom: 6,
  followDevice: true,
  showTrail: true,

  setMapCenter: (center) => set({ mapCenter: center }),
  setMapZoom: (zoom) => set({ mapZoom: zoom }),
  setFollowDevice: (follow) => set({ followDevice: follow }),
  setShowTrail: (show) => set({ showTrail: show }),

  // UI
  sidebarOpen: true,
  activeTab: 'commands',

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Alerts
  alerts: [],
  unreadAlertCount: 0,

  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts].slice(0, 100),
      unreadAlertCount: state.unreadAlertCount + 1,
    })),

  markAlertRead: (id) =>
    set((state) => ({
      alerts: state.alerts.map((a) => (a.id === id ? { ...a, read: true } : a)),
      unreadAlertCount: Math.max(0, state.unreadAlertCount - 1),
    })),

  clearAlerts: () =>
    set({ alerts: [], unreadAlertCount: 0 }),

  // Computed helpers
  getSelectedDevice: () => {
    const state = get();
    return state.devices.find((d) => d.id === state.selectedDeviceId) || null;
  },

  getDeviceStatus: (deviceId) => {
    const device = get().devices.find((d) => d.id === deviceId);
    if (!device) return { isOnline: false, signal: 'none' };
    return {
      isOnline: isOnline(device.last_seen),
      signal: getSignalLevel(device.last_seen),
    };
  },

  getNavigationInfo: (userLat, userLng) => {
    const loc = get().latestLocation;
    if (!loc) return null;
    const distance = calculateDistance(userLat, userLng, loc.lat, loc.lng);
    const bearing = calculateBearing(userLat, userLng, loc.lat, loc.lng);
    return {
      distance,
      bearing,
      bearingLabel: bearingToLabel(bearing),
    };
  },
}));
