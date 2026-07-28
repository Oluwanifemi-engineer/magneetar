'use client';

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';

const POLL_INTERVAL = 3000; // 3 seconds — WebSocket handles real-time location updates

export function useDevices() {
  const {
    serverUrl,
    apiKey,
    isConnected,
    selectedDeviceId,
    setDevices,
    setLocations,
    setCommands,
    setMedia,
    setConnected,
  } = useStore();

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const mountedRef = useRef(true);

  const fetchDevices = useCallback(async () => {
    if (!isConnected) return;
    try {
      const api = getAPI(serverUrl, apiKey);
      const data = await api.getDevices();
      if (mountedRef.current) {
        setDevices(data.devices || []);
      }
    } catch (e) {
      console.warn('Failed to fetch devices:', e);
      if (mountedRef.current) {
        setConnected(false);
      }
    }
  }, [isConnected, serverUrl, apiKey, setDevices, setConnected]);

  const fetchLocations = useCallback(async () => {
    if (!isConnected || !selectedDeviceId) return;
    try {
      const api = getAPI(serverUrl, apiKey);
      const data = await api.getLocations(selectedDeviceId, 200);
      if (mountedRef.current) {
        setLocations(data.locations || []);
      }
    } catch (e) {
      console.warn('Failed to fetch locations:', e);
    }
  }, [isConnected, serverUrl, apiKey, selectedDeviceId, setLocations]);

  const fetchCommands = useCallback(async () => {
    if (!isConnected || !selectedDeviceId) return;
    try {
      const api = getAPI(serverUrl, apiKey);
      const data = await api.getCommands(selectedDeviceId);
      if (mountedRef.current) {
        setCommands(data.commands || []);
      }
    } catch (e) {
      console.warn('Failed to fetch commands:', e);
    }
  }, [isConnected, serverUrl, apiKey, selectedDeviceId, setCommands]);

  const fetchMedia = useCallback(async () => {
    if (!isConnected || !selectedDeviceId) return;
    try {
      const api = getAPI(serverUrl, apiKey);
      const data = await api.getMedia(selectedDeviceId);
      if (mountedRef.current) {
        setMedia(data.media || []);
      }
    } catch (e) {
      console.warn('Failed to fetch media:', e);
    }
  }, [isConnected, serverUrl, apiKey, selectedDeviceId, setMedia]);

  const refresh = useCallback(async () => {
    await Promise.all([
      fetchDevices(),
      fetchLocations(),
      fetchCommands(),
      fetchMedia(),
    ]);
  }, [fetchDevices, fetchLocations, fetchCommands, fetchMedia]);

  // Start polling when connected
  useEffect(() => {
    mountedRef.current = true;

    if (isConnected) {
      // Initial fetch
      refresh();

      // Set up polling
      intervalRef.current = setInterval(refresh, POLL_INTERVAL);
    }

    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isConnected, refresh]);

  // Re-fetch device-specific data when selection changes
  useEffect(() => {
    if (isConnected && selectedDeviceId) {
      fetchLocations();
      fetchCommands();
      fetchMedia();
    }
  }, [isConnected, selectedDeviceId, fetchLocations, fetchCommands, fetchMedia]);

  return { refresh };
}
