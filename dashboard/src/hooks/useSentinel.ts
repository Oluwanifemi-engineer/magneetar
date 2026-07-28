'use client';

import { useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';

export function useSentinel() {
  const {
    serverUrl,
    apiKey,
    selectedDeviceId,
    devices,
  } = useStore();

  const getDeviceScore = useCallback((deviceId: string) => {
    const device = devices.find(d => d.id === deviceId);
    return device?.sentinel_score || 0;
  }, [devices]);

  const getThreatLevel = useCallback((deviceId: string) => {
    const device = devices.find(d => d.id === deviceId);
    if (!device) return 'SAFE';
    if (device.sentinel_score >= 80) return 'CRITICAL';
    if (device.sentinel_score >= 60) return 'HIGH';
    if (device.sentinel_score >= 30) return 'ELEVATED';
    return 'SAFE';
  }, [devices]);

  const isStolen = useCallback((deviceId: string) => {
    const device = devices.find(d => d.id === deviceId);
    return device?.is_stolen || false;
  }, [devices]);

  const getStolenDevices = useCallback(() => {
    return devices.filter(d => d.is_stolen);
  }, [devices]);

  return {
    getDeviceScore,
    getThreatLevel,
    isStolen,
    getStolenDevices,
  };
}
