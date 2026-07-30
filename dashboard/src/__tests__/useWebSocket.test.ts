/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach, afterEach } from '@jest/globals';
import { renderHook, act, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';

// ─── Fresh WebSocket mock per test (getter/setter pattern) ──────────────
let mockWsSend: jest.Mock;
let mockWsClose: jest.Mock;
let mockWsOnopen: ((event: any) => void) | null;
let mockWsOnclose: ((event: any) => void) | null;
let mockWsOnerror: ((event: any) => void) | null;
let mockWsOnmessage: ((event: any) => void) | null;
let mockWsReadyState: number;

function createMockWs() {
  mockWsSend = jest.fn();
  mockWsClose = jest.fn();
  mockWsOnopen = null;
  mockWsOnclose = null;
  mockWsOnerror = null;
  mockWsOnmessage = null;
  mockWsReadyState = 1; // WebSocket.OPEN
  return {
    get onopen() { return mockWsOnopen; },
    set onopen(fn) { mockWsOnopen = fn; },
    get onclose() { return mockWsOnclose; },
    set onclose(fn) { mockWsOnclose = fn; },
    get onerror() { return mockWsOnerror; },
    set onerror(fn) { mockWsOnerror = fn; },
    get onmessage() { return mockWsOnmessage; },
    set onmessage(fn) { mockWsOnmessage = fn; },
    send: mockWsSend,
    close: mockWsClose,
    get readyState() { return mockWsReadyState; },
    set readyState(v) { mockWsReadyState = v; },
  };
}

// ─── Mutable mock state for the store ───────────────────────────────────
// These are read at renderHook time (inside the jest.fn callback),
// NOT at jest.mock factory time — so no TDZ issue despite jest.mock hoisting.
let mockIsConnected = false;
let mockServerUrl = 'https://api.magneetar.me';
let mockApiKey = 'test-api-key';

const mockAddAlert = jest.fn();
const mockSetDevices = jest.fn();
const mockSetLocations = jest.fn();
const mockSetCommands = jest.fn();
const mockSetConnected = jest.fn();

// useStore.getState() and useStore.setState() must be static properties
// on the function itself (matching zustand's API), NOT inside the selector
// return value. The inner function CAN access outer variables because it
// runs at render time, not at module-init time.
jest.mock('@/store/useStore', () => {
  const storeFn = jest.fn((selector: any) => {
    // These are evaluated at renderHook time — safely past TDZ
    const state: any = {
      serverUrl: mockServerUrl,
      apiKey: mockApiKey,
      isConnected: mockIsConnected,
      isAuthenticated: true,
      devices: [],
      selectedDeviceId: null,
      locations: [],
      latestLocation: null,
      followDevice: true,
      mapCenter: [9.0820, 8.6753],
      addAlert: mockAddAlert,
      setDevices: mockSetDevices,
      setLocations: mockSetLocations,
      setCommands: mockSetCommands,
      setConnected: mockSetConnected,
    };
    return selector ? selector(state) : state;
  });
  // Static methods on the function itself (zustand pattern)
  storeFn.getState = jest.fn().mockReturnValue({
    devices: [],
    selectedDeviceId: null,
    followDevice: true,
    mapCenter: [9.0820, 8.6753] as [number, number],
    locations: [],
  });
  storeFn.setState = jest.fn();
  return { useStore: storeFn };
});

import { useWebSocket } from '@/hooks/useWebSocket';

describe('useWebSocket Hook', () => {
  let mockWebSocket: jest.Mock;

  beforeEach(() => {
    jest.clearAllMocks();
    mockIsConnected = false;
    mockServerUrl = 'https://api.magneetar.me';
    mockApiKey = 'test-api-key';

    // Create fresh WebSocket mock
    const wsInstance = createMockWs();
    mockWebSocket = jest.fn(() => wsInstance);
    (globalThis as any).WebSocket = mockWebSocket;

    // Reset getState/setState to default values
    const useStoreModule = jest.requireMock('@/store/useStore');
    useStoreModule.useStore.getState.mockReturnValue({
      devices: [],
      selectedDeviceId: null,
      followDevice: true,
      mapCenter: [9.0820, 8.6753] as [number, number],
      locations: [],
    });
    useStoreModule.useStore.setState.mockClear();
  });

  afterEach(() => {
    cleanup();
  });

  it('does not connect when store isConnected is false', () => {
    mockIsConnected = false;
    renderHook(() => useWebSocket());
    expect(mockWebSocket).not.toHaveBeenCalled();
  });

  it('connects when store isConnected becomes true', () => {
    mockIsConnected = true;
    renderHook(() => useWebSocket());

    // The hook has two useEffects that both call connect() on mount
    expect(mockWebSocket).toHaveBeenCalledTimes(2);
    // Server URL gets converted from https → wss
    const expectedWsUrl = 'wss://api.magneetar.me/ws/dashboard';
    expect(mockWebSocket).toHaveBeenCalledWith(expectedWsUrl);
  });

  it('sends auth message on open', () => {
    mockIsConnected = true;
    renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    expect(mockWsSend).toHaveBeenCalledWith(
      JSON.stringify({ type: 'auth', token: mockApiKey })
    );
  });

  it('handles location messages from WebSocket', () => {
    const useStoreModule = jest.requireMock('@/store/useStore');
    const testDevice = {
      id: 'device-001', lat: null, lng: null,
      battery_percent: null, is_online: false, last_seen: '',
    };
    useStoreModule.useStore.getState.mockReturnValue({
      devices: [testDevice],
      selectedDeviceId: 'device-001',
      followDevice: true,
      mapCenter: [9.0820, 8.6753] as [number, number],
      locations: [],
    });

    mockIsConnected = true;
    renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    const locationData = {
      type: 'location',
      data: {
        device_id: 'device-001',
        lat: 9.0820,
        lng: 8.6753,
        speed: 0,
        battery: 85,
        timestamp: '2024-01-01T12:00:00Z',
        provider: 'gps',
        sentinel_score: 12,
        threat_level: 'safe',
      },
    };

    act(() => {
      mockWsOnmessage?.({ data: JSON.stringify(locationData) });
    });

    // The location handler calls useStore.setState internally
    expect(useStoreModule.useStore.setState).toHaveBeenCalled();
    // location !== alert
    expect(mockAddAlert).not.toHaveBeenCalled();
  });

  it('handles alert messages from WebSocket', () => {
    mockIsConnected = true;
    renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    const alertData = {
      type: 'alert',
      data: {
        device_id: 'device-001',
        alert_type: 'offline',
        message: 'Device went offline',
        timestamp: '2024-01-01T12:00:00Z',
        severity: 'warning',
      },
    };

    act(() => {
      mockWsOnmessage?.({ data: JSON.stringify(alertData) });
    });

    expect(mockAddAlert).toHaveBeenCalledWith(
      expect.objectContaining({
        device_id: 'device-001',
        type: 'offline',
        message: 'Device went offline',
      })
    );
  });

  it('handles pong messages without errors', () => {
    mockIsConnected = true;
    renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    expect(() => {
      act(() => {
        mockWsOnmessage?.({ data: JSON.stringify({ type: 'pong' }) });
      });
    }).not.toThrow();
  });

  it('disconnect closes WebSocket and clears state', () => {
    mockIsConnected = true;
    const { result } = renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    act(() => {
      result.current.disconnect();
    });

    expect(mockWsClose).toHaveBeenCalled();
    expect(result.current.connected).toBe(false);
  });

  it('attempts reconnect on close when store is still connected', () => {
    jest.useFakeTimers();
    mockIsConnected = true;
    renderHook(() => useWebSocket());

    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    // Simulate close — triggers:
    //   1. setWsConnected(false) + reconnect timer
    //   2. Second useEffect fires during act flush, calling connect() again
    act(() => {
      mockWsOnclose?.(new CloseEvent('close', { code: 1006, reason: 'Abnormal' }));
    });

    // Advance the reconnect timer
    act(() => {
      jest.advanceTimersByTime(1500);
    });

    // 2 (mount: two effects) + 1 (effect after close) + 1 (timer) = 4
    expect(mockWebSocket).toHaveBeenCalledTimes(4);

    jest.useRealTimers();
  });

  it('send method is exposed and queues auth on open', () => {
    mockIsConnected = true;
    const { result } = renderHook(() => useWebSocket());

    // send should be a function
    expect(typeof result.current.send).toBe('function');

    // Trigger onopen to send auth
    act(() => {
      mockWsOnopen?.(new Event('open'));
    });

    // Auth message should have been sent
    expect(mockWsSend).toHaveBeenCalledWith(
      JSON.stringify({ type: 'auth', token: mockApiKey })
    );

    // Call send — it should not throw (wsRef state handled internally)
    expect(() => {
      act(() => {
        result.current.send({ type: 'ping', data: {} });
      });
    }).not.toThrow();
  });

  it('exposes connected state as false when not connected', () => {
    mockIsConnected = false;
    const { result } = renderHook(() => useWebSocket());
    expect(result.current.connected).toBe(false);
  });
});
