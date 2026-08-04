'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useStore } from '@/store/useStore';

type MessageType = 'location' | 'alert' | 'command_ack' | 'heartbeat' | 'sentinel' | 'ping' | 'pong';

interface WebSocketMessage {
  type: MessageType;
  data: any;
}

export function useWebSocket() {
  const {
    serverUrl,
    apiKey,
    isConnected,
    addAlert,
    setDevices,
    setLocations,
    setCommands,
    applyCommandAck,
    setConnected,
  } = useStore();

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const [wsConnected, setWsConnected] = useState(false);

  const connect = useCallback(() => {
    if (!isConnected || !serverUrl) return;

    try {
      // Convert HTTP URL to WebSocket URL. The JWT goes in the query string
      // because the WebSocket API has no headers — the server rejects
      // connections without a valid ?token= (previously it accepted everyone
      // and treated anonymous connections as admin, leaking every device's
      // live location).
      const baseWsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/dashboard';
      const wsUrl = apiKey
        ? `${baseWsUrl}?token=${encodeURIComponent(apiKey)}`
        : baseWsUrl;

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WebSocket] Connected');
        setWsConnected(true);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          handleMessage(message);
        } catch (e) {
          console.error('[WebSocket] Failed to parse message:', e);
        }
      };

      ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', event.code, event.reason);
        setWsConnected(false);
        wsRef.current = null;

        // Auto-reconnect with exponential backoff
        if (isConnected && reconnectAttemptsRef.current < 10) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
          reconnectAttemptsRef.current++;

          console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current})`);

          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        }
      };

      ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };
    } catch (e) {
      console.error('[WebSocket] Failed to connect:', e);
    }
  }, [isConnected, serverUrl, apiKey]);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    const { type, data } = message;

    switch (type) {
      case 'location': {
        // Immediately update device location in store for real-time map
        const { devices, selectedDeviceId } = useStore.getState();
        if (data.device_id === selectedDeviceId) {
          // Update latest location directly (partial — runtime data)
          useStore.setState({
            latestLocation: {
              id: Date.now(),
              device_id: data.device_id,
              lat: data.lat,
              lng: data.lng,
              // The server broadcasts accuracy_horizontal (the device's
              // Kalman-fused accuracy in meters) on every live location — map
              // it to the UI's `accuracy` field so the map circle and
              // "±Nm" readouts show the REAL fused accuracy in real time,
              // not a perpetual "±?m". Falls back to the legacy `accuracy`
              // key for older server builds.
              accuracy: data.accuracy_horizontal ?? data.accuracy ?? null,
              accuracy_horizontal: data.accuracy_horizontal ?? null,
              provider: data.provider || 'gps',
              speed: data.speed,
              bearing: data.bearing ?? null,
              battery_percent: data.battery,
              altitude: null,
              sentinel_score: data.sentinel_score,
              threat_level: data.threat_level,
              anomalies: data.anomalies || null,
              timestamp: data.timestamp || new Date().toISOString(),
              server_timestamp: data.timestamp || null,
              device_timestamp: data.timestamp || null,
              is_charging: null,
              network_type: null,
              sim_changed: null,
              is_airplane_mode: null,
              is_location_enabled: null,
              activity_type: null,
              // Honest confidence from the device's telemetry (HIGH/MEDIUM/
              // LOW) instead of a hardcoded 'high'.
              confidence_level: data.confidence_level || 'unknown',
            },
            // Also update map center if following
            mapCenter: useStore.getState().followDevice ? [data.lat, data.lng] : useStore.getState().mapCenter,
          });
        }
        // Update device in list
        const updatedDevices = devices.map(d =>
          d.id === data.device_id
            ? { ...d, lat: data.lat, lng: data.lng, battery_percent: data.battery, is_online: true, last_seen: data.timestamp }
            : d
        );
        useStore.setState({ devices: updatedDevices });

        // Also append to locations array for trail rendering
        const prevLocations = useStore.getState().locations;
        const newLoc: any = {
          lat: data.lat,
          lng: data.lng,
          battery_percent: data.battery,
          speed: data.speed,
          accuracy: data.accuracy_horizontal ?? data.accuracy ?? null,
          provider: data.provider || null,
          bearing: data.bearing ?? null,
          timestamp: data.timestamp,
          sentinel_score: data.sentinel_score,
          threat_level: data.threat_level,
          device_timestamp: data.timestamp,
          server_timestamp: data.timestamp,
        };
        useStore.setState({ locations: [newLoc, ...prevLocations].slice(0, 500) });
        break;
      }

      case 'alert':
        // Add new alert to store
        addAlert({
          id: String(Date.now()),
          device_id: data.device_id,
          type: data.alert_type || 'offline',
          message: data.message || 'New alert',
          timestamp: data.timestamp || new Date().toISOString(),
          severity: data.severity || 'info',
          read: false,
        });
        break;

      case 'command_ack':
        // Command acknowledgment received — flip the command row's status
        // IMMEDIATELY (executed/failed) instead of waiting up to 10s for the
        // next history poll. The server broadcasts this the moment the device
        // acks; the old empty handler is why a successful command kept showing
        // PENDING for seconds even when the device had already executed it.
        if (data && typeof data.command_id === 'number') {
          applyCommandAck(data.command_id, data.status || 'executed', data.failure_reason);
        }
        break;

      case 'heartbeat':
        // Device heartbeat — nothing to do, connection is alive
        break;

      case 'sentinel':
        // Sentinel score update received
        break;

      case 'ping':
        // Server keepalive heartbeat (every 30s). MUST reply with a pong —
        // the server prunes connections that don't pong within 90s. The old
        // client never responded, so every dashboard connection was
        // force-dropped and reconnect-looped forever (the real-time feed
        // churned every ~90s instead of staying live).
        // Send directly on the socket (not via the `send` helper) so this
        // handler needs no extra hook deps.
        wsRef.current?.send(JSON.stringify({ type: 'pong' }));
        break;

      case 'pong':
        // Connection alive
        break;

      default:
        console.log('[WebSocket] Unknown message type:', type);
    }
  }, [addAlert, applyCommandAck]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
  }, []);

  const send = useCallback((message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    if (isConnected) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [isConnected, connect, disconnect]);

  // Reconnect when connection state changes
  useEffect(() => {
    if (isConnected && !wsConnected) {
      connect();
    }
  }, [isConnected, wsConnected, connect]);

  return {
    connected: wsConnected,
    send,
    disconnect,
  };
}
