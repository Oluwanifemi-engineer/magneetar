'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useStore } from '@/store/useStore';

import { cn, openGoogleMapsDirections, formatDistance, formatDuration, isOnline, relativeTime, formatTimestamp, locationTimestamp } from '@/lib/utils';
import { getOSRMRoute, snapToRoad, NavigationRoute } from '@/services/navigation';
import type { Location } from '@/types';

// ─── Reverse Geocoding ─────────────────────────────────────────────────────
const geocodeCache = new Map<string, string>();
const GEOCODE_CACHE_MAX = 50;

const snapCache = new Map<string, [number, number]>();
const SNAP_CACHE_MAX = 100;
const SNAP_MIN_ACCURACY_M = 30;

function snapCacheKey(lat: number, lng: number): string {
  return `${lat.toFixed(4)},${lng.toFixed(4)}`;
}

async function reverseGeocode(lat: number, lng: number): Promise<string> {
  const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
  if (geocodeCache.has(key)) return geocodeCache.get(key)!;
  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`,
      { headers: { 'Accept-Language': 'en' } }
    );
    if (!resp.ok) throw new Error(`Geocoder ${resp.status}`);
    const data = await resp.json();
    const addr = data.display_name || `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
    const parts = addr.split(',').map((s: string) => s.trim());
    const short = parts.slice(0, Math.min(3, parts.length)).join(', ');
    if (geocodeCache.size >= GEOCODE_CACHE_MAX) {
      const firstKey = geocodeCache.keys().next().value;
      if (firstKey) geocodeCache.delete(firstKey);
    }
    geocodeCache.set(key, short);
    return short;
  } catch {
    return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  }
}

// ─── Map tiles ──────────────────────────────────────────────────────────────
const MAPTILER_KEY = process.env.NEXT_PUBLIC_MAPTILER_KEY || '';
const MAP_TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || '';
const MAP_TILE_URL_RESOLVED =
  MAP_TILE_URL ||
  (MAPTILER_KEY
    ? `https://api.maptiler.com/maps/dark-matter/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`
    : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
const MAP_TILE_ATTRIBUTION = MAP_TILE_URL
  ? ''
  : MAPTILER_KEY
    ? '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const SATELLITE_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const SATELLITE_ATTRIBUTION = '&copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics';

const USER_ACCURACY_DISTANCE_MAX = 1000;
const USER_ACCURACY_NAVIGATION_MAX = 300;
const USER_ACCURACY_IP_FALLBACK = 5000;
const PINNED_STORAGE_KEY = 'mt_pinned_position';

function loadPinnedPosition(): [number, number] | null {
  try {
    const raw = typeof window !== 'undefined' ? window.localStorage.getItem(PINNED_STORAGE_KEY) : null;
    if (!raw) return null;
    const [lat, lng] = JSON.parse(raw);
    if (typeof lat === 'number' && typeof lng === 'number') return [lat, lng];
    return null;
  } catch {
    return null;
  }
}

function savePinnedPosition(pos: [number, number] | null) {
  try {
    if (pos) window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(pos));
    else window.localStorage.removeItem(PINNED_STORAGE_KEY);
  } catch {
    // localStorage unavailable (private mode)
  }
}

function formatAccuracyMeters(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`;
}

// Dynamic imports for SSR safety
const MapContainer = dynamic(() => import('react-leaflet').then(m => m.MapContainer), { ssr: false });
const TileLayer = dynamic(() => import('react-leaflet').then(m => m.TileLayer), { ssr: false });
const Marker = dynamic(() => import('react-leaflet').then(m => m.Marker), { ssr: false });
const Polyline = dynamic(() => import('react-leaflet').then(m => m.Polyline), { ssr: false });
const Popup = dynamic(() => import('react-leaflet').then(m => m.Popup), { ssr: false });
const Circle = dynamic(() => import('react-leaflet').then(m => m.Circle), { ssr: false });

import { useMap } from 'react-leaflet';
import { MapPin } from 'lucide-react';

// ─── Professional SVG Map Icons ──────────────────────────────────────────────

let deviceIcon: any = null;
let userIcon: any = null;
let waypointIcon: any = null;
let trailDotIcon: any = null;

async function initIcons() {
  if (deviceIcon) return;
  const L = await import('leaflet');

  deviceIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:44px;height:52px;filter:drop-shadow(0 4px 12px rgba(0,0,0,0.35));">
        <div style="position:absolute;top:6px;left:6px;width:32px;height:32px;border-radius:50%;border:2px solid rgba(255,255,255,0.3);animation:none;"></div>
        <svg width="44" height="52" viewBox="0 0 44 52" fill="none" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="22" cy="49" rx="10" ry="3" fill="rgba(0,0,0,0.2)"/>
          <path d="M22 2C12.06 2 4 10.06 4 20c0 12 18 28 18 28s18-16 18-28C40 10.06 31.94 2 22 2z" fill="url(#deviceGrad)"/>
          <circle cx="22" cy="20" r="10" fill="white" fill-opacity="0.95"/>
          <circle cx="22" cy="20" r="4" fill="#10B981">
            <animate attributeName="r" values="3;5;3" dur="2s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="1;0.6;1" dur="2s" repeatCount="indefinite"/>
          </circle>
          <defs>
            <linearGradient id="deviceGrad" x1="4" y1="2" x2="40" y2="48" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stop-color="#111827"/>
              <stop offset="100%" stop-color="#374151"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
    `,
    iconSize: [44, 52],
    iconAnchor: [22, 48],
  });

  userIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:28px;height:28px;filter:drop-shadow(0 2px 6px rgba(6,182,212,0.4));">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="14" cy="14" r="13" stroke="#06B6D4" stroke-width="2" fill="rgba(6,182,212,0.1)"/>
          <circle cx="14" cy="14" r="5" fill="#06B6D4"/>
          <line x1="14" y1="0" x2="14" y2="6" stroke="#06B6D4" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="14" y1="22" x2="14" y2="28" stroke="#06B6D4" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="0" y1="14" x2="6" y2="14" stroke="#06B6D4" stroke-width="1.5" stroke-linecap="round"/>
          <line x1="22" y1="14" x2="28" y2="14" stroke="#06B6D4" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

  waypointIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:28px;height:36px;filter:drop-shadow(0 2px 8px rgba(0,0,0,0.3));">
        <svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 0C6.268 0 0 6.268 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.268 21.732 0 14 0z" fill="url(#waypointGrad)"/>
          <circle cx="14" cy="14" r="5" fill="white" fill-opacity="0.9"/>
          <defs>
            <linearGradient id="waypointGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#F59E0B"/>
              <stop offset="100%" stop-color="#D97706"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
    `,
    iconSize: [28, 36],
    iconAnchor: [14, 36],
  });

  trailDotIcon = L.divIcon({
    className: '',
    html: `<div style="width:8px;height:8px;border-radius:50%;background:#FFFFFF;border:2px solid rgba(255,255,255,0.6);box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>`,
    iconSize: [8, 8],
    iconAnchor: [4, 4],
  });
}

// ─── Map Controller — smooth follow & recenter ────────────────────────────

function MapController({ pinning, onPin, replayActive }: {
  pinning: boolean;
  onPin: (pos: [number, number]) => void;
  replayActive: boolean;
}) {
  const map = useMap();
  const { followDevice, latestLocation, selectedDeviceId } = useStore();
  const prevCenter = useRef<string>('');
  const prevDevice = useRef<string | null>(null);
  const userInteracted = useRef(false);
  const interactionTimer = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!pinning) return;
    const handler = (e: any) => { onPin([e.latlng.lat, e.latlng.lng]); };
    map.on('click', handler);
    return () => { map.off('click', handler); };
  }, [map, pinning, onPin]);

  useEffect(() => {
    const handler = () => {
      userInteracted.current = true;
      if (interactionTimer.current) clearTimeout(interactionTimer.current);
      interactionTimer.current = setTimeout(() => { userInteracted.current = false; }, 5000);
    };
    map.on('dragstart', handler);
    map.on('zoomstart', handler);
    return () => {
      map.off('dragstart', handler);
      map.off('zoomstart', handler);
    };
  }, [map]);

  useEffect(() => {
    if (followDevice && latestLocation && !userInteracted.current && !replayActive) {
      const key = `${latestLocation.lat.toFixed(6)},${latestLocation.lng.toFixed(6)}`;
      if (key !== prevCenter.current) {
        map.setView([latestLocation.lat, latestLocation.lng], Math.max(map.getZoom(), 16), {
          animate: true,
          duration: 0.5,
        });
        prevCenter.current = key;
      }
    }
  }, [followDevice, latestLocation, map, replayActive]);

  useEffect(() => {
    if (selectedDeviceId && selectedDeviceId !== prevDevice.current && latestLocation) {
      prevDevice.current = selectedDeviceId;
      map.setView([latestLocation.lat, latestLocation.lng], 17, { animate: true, duration: 0.6 });
    }
  }, [selectedDeviceId, latestLocation, map]);

  return null;
}

// ─── Distance Overlay Component ─────────────────────────────────────────────

function DistanceOverlay({ userPos, userAccuracy, userPinned, deviceLat, deviceLng, offline, lastSeen }: {
  userPos: [number, number] | null;
  userAccuracy: number | null;
  userPinned: boolean;
  deviceLat: number;
  deviceLng: number;
  offline: boolean;
  lastSeen: string | null;
}) {
  const [distance, setDistance] = useState<number | null>(null);
  const map = useMap();
  const { setFollowDevice } = useStore();

  const flyToYou = useCallback(() => {
    if (!userPos) return;
    setFollowDevice(false);
    map.flyTo(userPos, Math.max(map.getZoom(), 16), { animate: true, duration: 0.8 });
  }, [userPos, map, setFollowDevice]);

  const flyToDevice = useCallback(() => {
    setFollowDevice(true);
    map.flyTo([deviceLat, deviceLng], Math.max(map.getZoom(), 16), { animate: true, duration: 0.8 });
  }, [deviceLat, deviceLng, map, setFollowDevice]);

  useEffect(() => {
    if (!userPos || offline) {
      setDistance(null);
      return;
    }
    const R = 6371000;
    const dLat = (deviceLat - userPos[0]) * Math.PI / 180;
    const dLng = (deviceLng - userPos[1]) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(userPos[0] * Math.PI / 180) * Math.cos(deviceLat * Math.PI / 180) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    setDistance(R * c);
  }, [userPos, deviceLat, deviceLng, offline, userAccuracy]);

  if (offline) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
        <div className="bg-mag-surface-raised/95 backdrop-blur-xl border-mag-border px-4 py-2.5 flex items-center gap-2.5 animate-fade-in">
          <div className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="font-mono text-[10px] text-amber-400 font-bold uppercase tracking-wider">OFFLINE</span>
          <div className="h-4 w-px border-mag-border" />
          <span className="font-mono text-[10px] text-mag-text-dim font-bold">
            Last seen {relativeTime(lastSeen)}
          </span>
        </div>
      </div>
    );
  }

  if (!userPos) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
        <div className="bg-mag-surface-raised/95 backdrop-blur-xl border-mag-border px-4 py-2.5 flex items-center gap-2.5 animate-fade-in">
          <div className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="font-mono text-[10px] text-amber-400 font-bold uppercase tracking-wider">
            SET POSITION
          </span>
          <span className="font-mono text-[10px] text-mag-text-muted font-bold">
            tap pin, then tap map
          </span>
        </div>
      </div>
    );
  }

  if (!distance) return null;

  if (!userPinned && userAccuracy != null && userAccuracy > USER_ACCURACY_IP_FALLBACK) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] max-w-md">
        <div className="bg-mag-surface-raised/95 backdrop-blur-xl border-mag-border px-4 py-3 animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-500" />
              <span className="font-mono text-[10px] text-mag-text-dim font-bold uppercase tracking-wider">YOU</span>
            </div>
            <svg width="14" height="14" viewBox="0 0 16 16" className="text-mag-text-muted/50">
              <path d="M1 8h14M8 1l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="font-mono text-[10px] text-mag-text-dim font-bold uppercase tracking-wider">DEVICE</span>
            </div>
            <div className="h-3 w-px border-mag-border" />
            <span className="font-mono text-sm font-bold text-mag-text tabular-nums">{formatDistance(distance)}</span>
            <span className="font-mono text-[10px] text-mag-text-muted font-bold">away</span>
          </div>
          <div className="flex items-center gap-1.5 mt-2">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-amber-500 shrink-0">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <span className="font-mono text-[9px] text-amber-400/80 font-bold">
              IP-derived (±{formatAccuracyMeters(userAccuracy!)}). Pin your spot for accuracy.
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
      <div className="bg-mag-surface-raised/95 backdrop-blur-xl border-mag-border px-4 py-2.5 flex items-center gap-3 animate-fade-in">
        <button
          onClick={flyToYou}
          disabled={!userPos}
          title={userPos ? 'Fly to your location' : 'No position yet'}
          className="flex items-center gap-2 group/y disabled:opacity-50"
        >
          <div className="w-2 h-2 rounded-full bg-cyan-500 group-hover/y:scale-125 transition-transform" />
          <span className="font-mono text-[10px] text-mag-text-dim font-bold group-hover/y:text-mag-text transition-colors">YOU</span>
        </button>
        <svg width="14" height="14" viewBox="0 0 16 16" className="text-mag-text-muted/50">
          <path d="M1 8h14M8 1l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <button
          onClick={flyToDevice}
          title="Fly to device"
          className="flex items-center gap-2 group/d"
        >
          <div className="w-2 h-2 rounded-full bg-emerald-500 group-hover/d:scale-125 transition-transform" />
          <span className="font-mono text-[10px] text-mag-text-dim font-bold group-hover/d:text-mag-text transition-colors">DEVICE</span>
        </button>
        <div className="h-3 w-px border-mag-border" />
        <span className="font-mono text-sm font-bold text-mag-text tabular-nums">
          {formatDistance(distance)}
        </span>
        <span className="font-mono text-[10px] text-mag-text-muted font-bold">away</span>
        {!userPinned && userAccuracy != null && userAccuracy > USER_ACCURACY_DISTANCE_MAX && (
          <span className="font-mono text-[9px] text-amber-400/70 font-bold">
            ±{formatAccuracyMeters(userAccuracy)}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Path Animation Tracker ────────────────────────────────────────────────

function PathAnimationTracker({ trailLocations, isPlaying, playbackSpeed, index, onIndexChange }: {
  trailLocations: Location[];
  isPlaying: boolean;
  playbackSpeed: number;
  index: number;
  onIndexChange: (index: number) => void;
}) {
  const map = useMap();
  const [animatedPath, setAnimatedPath] = useState<[number, number][]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!isPlaying || trailLocations.length < 2) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    intervalRef.current = setInterval(() => {
      onIndexChange(Math.min(index + 1, trailLocations.length - 1));
    }, 1000 / playbackSpeed);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, playbackSpeed, trailLocations.length, index, onIndexChange]);

  useEffect(() => {
    setAnimatedPath(trailLocations.slice(0, index + 1).map((l) => [l.lat, l.lng] as [number, number]));
    const loc = trailLocations[index];
    if (loc) {
      map.panTo([loc.lat, loc.lng], { animate: true, duration: 0.25 });
    }
  }, [index, trailLocations, map]);

  useEffect(() => {
    onIndexChange(0);
    setAnimatedPath([]);
  }, [trailLocations, onIndexChange]);

  if (animatedPath.length < 2) return null;

  return (
    <>
      <Polyline
        positions={animatedPath}
        pathOptions={{
          color: '#FFFFFF',
          weight: 4,
          opacity: 0.9,
          lineCap: 'round',
          lineJoin: 'round',
        }}
      />
      <Polyline
        positions={animatedPath}
        pathOptions={{
          color: '#FFFFFF',
          weight: 10,
          opacity: 0.15,
          lineCap: 'round',
          lineJoin: 'round',
        }}
      />
      {animatedPath.length > 0 && trailDotIcon && (
        <Marker
          position={animatedPath[animatedPath.length - 1]}
          icon={trailDotIcon}
        />
      )}
    </>
  );
}

// ─── Main Map Component ──────────────────────────────────────────────────────

export function MapView() {
  const {
    locations, latestLocation, mapCenter, mapZoom,
    followDevice, setFollowDevice, showTrail, setShowTrail,
    devices, selectedDeviceId,
  } = useStore();

  const mapRef = useRef<any>(null);

  const [mapReady, setMapReady] = useState(false);
  const [iconsReady, setIconsReady] = useState(false);
  const [navigationRoute, setNavigationRoute] = useState<NavigationRoute | null>(null);
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);
  const [userAccuracy, setUserAccuracy] = useState<number | null>(null);
  const [userGeoDenied, setUserGeoDenied] = useState(false);
  const [navigating, setNavigating] = useState(false);
  const [showSatellite, setShowSatellite] = useState(false);

  const [deviceAddress, setDeviceAddress] = useState<string | null>(null);
  const [userPinned, setUserPinned] = useState<[number, number] | null>(loadPinnedPosition);
  const [pinning, setPinning] = useState(false);
  const [snappedDevicePos, setSnappedDevicePos] = useState<[number, number] | null>(null);
  const [showMapControls, setShowMapControls] = useState(false);

  const effectiveUserPos = userPinned ?? userPosition;
  const deviceMarkerPos: [number, number] | null = snappedDevicePos ?? (latestLocation ? [latestLocation.lat, latestLocation.lng] : null);
  const isDeviceSnapped = snappedDevicePos != null;
  const userNavigationUsable =
    !!userPinned || (!!userPosition && userAccuracy != null && userAccuracy <= USER_ACCURACY_NAVIGATION_MAX);
  const userFixIsIpDerived =
    !userPinned && !!userPosition && userAccuracy != null && userAccuracy >= USER_ACCURACY_IP_FALLBACK;

  const [pathPlaying, setPathPlaying] = useState(false);
  const [pathSpeed, setPathSpeed] = useState(2);
  const [pathIndex, setPathIndex] = useState(0);
  const [showPathTracker, setShowPathTracker] = useState(false);
  const followBeforeReplay = useRef<boolean | null>(null);

  const device = devices.find(d => d.id === selectedDeviceId);
  const deviceOnline = device ? isOnline(device.last_seen) : true;

  const trailLocations = useMemo(() => locations.slice().reverse(), [locations]);

  useEffect(() => {
    if (pathPlaying && trailLocations.length > 0 && pathIndex >= trailLocations.length - 1) {
      setPathPlaying(false);
    }
  }, [pathPlaying, pathIndex, trailLocations.length]);

  useEffect(() => {
    if (!navigator.geolocation) return;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setUserPosition([pos.coords.latitude, pos.coords.longitude]);
        setUserAccuracy(pos.coords.accuracy);
      },
      (err) => {
        if (err && err.code === err.PERMISSION_DENIED) setUserGeoDenied(true);
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 15000 }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  useEffect(() => {
    if (!latestLocation) return;
    let cancelled = false;
    reverseGeocode(latestLocation.lat, latestLocation.lng).then((addr) => {
      if (!cancelled) setDeviceAddress(addr);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestLocation?.lat, latestLocation?.lng]);

  useEffect(() => {
    if (!latestLocation || latestLocation.accuracy == null || latestLocation.accuracy < SNAP_MIN_ACCURACY_M) {
      setSnappedDevicePos(null);
      return;
    }
    const { lat, lng } = latestLocation;
    const key = snapCacheKey(lat, lng);
    const cached = snapCache.get(key);
    if (cached) {
      setSnappedDevicePos(cached);
      return;
    }
    let cancelled = false;
    snapToRoad(lat, lng).then((pos) => {
      if (cancelled) return;
      if (pos) {
        if (snapCache.size >= SNAP_CACHE_MAX) {
          const firstKey = snapCache.keys().next().value;
          if (firstKey) snapCache.delete(firstKey);
        }
        snapCache.set(key, pos);
      }
      setSnappedDevicePos(pos);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestLocation?.lat, latestLocation?.lng, latestLocation?.accuracy]);

  // Initialize Leaflet icons
  useEffect(() => {
    setMapReady(true);
    initIcons().then(() => setIconsReady(true));
  }, []);

  // ROBUST map size invalidation: run on mount, after delay, and on window resize
  useEffect(() => {
    if (!mapReady) return;

    const invalidateMapSize = () => {
      if (mapRef.current && mapRef.current.invalidateSize) {
        mapRef.current.invalidateSize();
      }
    };

    // Immediate invalidation
    invalidateMapSize();

    // Delayed invalidation (for flex layout settling)
    const timers = [
      setTimeout(invalidateMapSize, 100),
      setTimeout(invalidateMapSize, 300),
      setTimeout(invalidateMapSize, 500),
      setTimeout(invalidateMapSize, 1000),
    ];

    // Also invalidate on window resize
    window.addEventListener('resize', invalidateMapSize);

    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener('resize', invalidateMapSize);
    };
  }, [mapReady]);

  const handlePin = useCallback((pos: [number, number]) => {
    setUserPinned(pos);
    savePinnedPosition(pos);
    setPinning(false);
  }, []);

  const handleNavigate = useCallback(async () => {
    if (!latestLocation || !effectiveUserPos || !userNavigationUsable) return;
    setNavigating(true);
    setNavigationRoute(null);
    try {
      const route = await getOSRMRoute(
        effectiveUserPos[0], effectiveUserPos[1],
        latestLocation.lat, latestLocation.lng
      );
      if (route) {
        setNavigationRoute(route);
        setFollowDevice(false);
      } else {
        openGoogleMapsDirections(effectiveUserPos[0], effectiveUserPos[1], latestLocation.lat, latestLocation.lng);
      }
    } catch {
      openGoogleMapsDirections(effectiveUserPos[0], effectiveUserPos[1], latestLocation.lat, latestLocation.lng);
    } finally {
      setNavigating(false);
    }
  }, [latestLocation, effectiveUserPos, userNavigationUsable, setFollowDevice]);

  const trailPoints = useMemo(() => {
    return trailLocations.map(l => ({ lat: l.lat, lng: l.lng, ts: l.timestamp }));
  }, [trailLocations]);

  if (!mapReady) return <div className="w-full h-full bg-mag-bg" />;

  return (
    <div className="w-full h-full relative bg-mag-bg">
      {mapReady && iconsReady && (
        <MapContainer
          ref={mapRef}
          center={mapCenter || (latestLocation ? [latestLocation.lat, latestLocation.lng] : [6.5244, 3.3792])}
          zoom={mapZoom || 17}
          className="w-full h-full"
          zoomControl={false}
          attributionControl={false}
        >
          <MapController pinning={pinning} onPin={handlePin} replayActive={showPathTracker} />

          <TileLayer
            key={showSatellite ? 'satellite' : 'street'}
            url={showSatellite ? SATELLITE_TILE_URL : MAP_TILE_URL_RESOLVED}
            attribution={showSatellite ? SATELLITE_ATTRIBUTION : MAP_TILE_ATTRIBUTION}
            maxNativeZoom={19}
            maxZoom={21}
          />

          {/* User marker */}
          {effectiveUserPos && userIcon && (
            <Marker position={effectiveUserPos} icon={userIcon}>
              <Popup>
                <div className="text-center">
                  <div className="font-bold">Your Position</div>
                  {userPinned && <div className="text-xs text-mag-text-muted">Pinned manually</div>}
                  {!userPinned && userAccuracy != null && (
                    <div className="text-xs text-mag-text-muted">Accuracy: ±{formatAccuracyMeters(userAccuracy)}</div>
                  )}
                </div>
              </Popup>
            </Marker>
          )}

          {/* User accuracy circle */}
          {effectiveUserPos && userAccuracy && !userPinned && userAccuracy < 1000 && (
            <Circle
              center={effectiveUserPos}
              radius={userAccuracy}
              pathOptions={{
                color: '#06B6D4',
                fillColor: '#06B6D4',
                fillOpacity: 0.08,
                weight: 1,
              }}
            />
          )}

          {/* Device marker */}
          {deviceMarkerPos && deviceIcon && (
            <Marker position={deviceMarkerPos} icon={deviceIcon}>
              <Popup>
                <div className="text-center">
                  <div className="font-bold">{device?.id || 'Device'}</div>
                  {deviceAddress && <div className="text-xs text-mag-text-muted">{deviceAddress}</div>}
                  {latestLocation && (
                    <div className="text-xs text-mag-text-muted mt-1">
                      Accuracy: ±{latestLocation.accuracy ? formatAccuracyMeters(latestLocation.accuracy) : 'Unknown'}
                    </div>
                  )}
                </div>
              </Popup>
            </Marker>
          )}

          {/* Device accuracy circle */}
          {deviceMarkerPos && latestLocation?.accuracy && latestLocation.accuracy < 50 && (
            <Circle
              center={deviceMarkerPos}
              radius={latestLocation.accuracy}
              pathOptions={{
                color: '#10B981',
                fillColor: '#10B981',
                fillOpacity: 0.08,
                weight: 1,
              }}
            />
          )}

          {/* Navigation route */}
          {navigationRoute && (
            <Polyline
              positions={navigationRoute.geometry.map((p: [number, number]) => [p[0], p[1]])}
              pathOptions={{
                color: '#3B82F6',
                weight: 4,
                opacity: 0.8,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          )}

          {/* Trail */}
          {showTrail && trailPoints.length > 1 && !navigationRoute && !showPathTracker && (
            <Polyline
              positions={trailPoints.map(p => [p.lat, p.lng])}
              pathOptions={{
                color: '#FFFFFF',
                weight: 3,
                opacity: 0.6,
                lineCap: 'round',
                lineJoin: 'round',
              }}
            />
          )}

          {/* Path replay */}
          {showPathTracker && trailLocations.length > 1 && (
            <PathAnimationTracker
              trailLocations={trailLocations}
              isPlaying={pathPlaying}
              playbackSpeed={pathSpeed}
              index={pathIndex}
              onIndexChange={setPathIndex}
            />
          )}

          {/* Community Heatmap */}


          {/* Waypoints */}
          {navigationRoute && navigationRoute.steps.map((step: any, i: number) => (
            waypointIcon && step.maneuver && (
              <Marker key={`wp-${i}`} position={[step.maneuver.location[1], step.maneuver.location[0]]} icon={waypointIcon}>
                <Popup>
                  <div className="text-center">
                    <div className="font-bold">{i === 0 ? 'Start' : i === navigationRoute.steps.length - 1 ? 'End' : `Step ${i}`}</div>
                    <div className="text-xs text-mag-text-muted">{step.name || 'Continue'}</div>
                  </div>
                </Popup>
              </Marker>
            )
          ))}

          {/* Distance Overlay — must be inside MapContainer for useMap() context */}
          {latestLocation && deviceOnline && (
            <DistanceOverlay
              userPos={effectiveUserPos}
              userAccuracy={userAccuracy}
              userPinned={!!userPinned}
              deviceLat={latestLocation.lat}
              deviceLng={latestLocation.lng}
              offline={false}
              lastSeen={null}
            />
          )}

        </MapContainer>
      )}

      {/* Unified map controls — bottom-right, premium dark glass panel */}
      <div className="absolute bottom-4 right-3 z-[1000] flex flex-col items-end gap-1.5 md:bottom-4 bottom-20">
        <div className="bg-mag-surface-raised/90 backdrop-blur-xl border-mag-border rounded-2xl shadow-2xl p-1.5">
          <div className="grid grid-cols-2 gap-1">
          {/* Pin position */}
          <button
            onClick={() => setPinning(!pinning)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
              pinning
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : 'bg-mag-surface-raised backdrop-blur text-mag-text-muted border-mag-border hover:bg-mag-surface hover:text-mag-text-dim'
            }`}
            title="Pin your position"
          >
            <MapPin size={10} />
            {pinning ? 'Tap...' : 'Pin'}
          </button>

          {/* Follow */}
          <button
            onClick={() => setFollowDevice(!followDevice)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
              followDevice
                ? 'bg-emerald-500/15 text-emerald-400/80 border border-emerald-500/20'
                : 'bg-mag-surface-raised backdrop-blur text-mag-text-muted border-mag-border hover:bg-mag-surface hover:text-mag-text-dim'
            }`}
            title={followDevice ? 'Stop following' : 'Follow device'}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r={followDevice ? '3' : '1'} />
            </svg>
            {followDevice ? 'Track' : 'Follow'}
          </button>

          {/* Trail */}
          <button
            onClick={() => setShowTrail(!showTrail)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
              showTrail
                ? 'bg-mag-surface-raised/80 text-mag-text-dim border-mag-border/50'
                : 'bg-mag-surface-raised backdrop-blur text-mag-text-muted border-mag-border hover:bg-mag-surface hover:text-mag-text-dim'
            }`}
            title={showTrail ? 'Hide trail' : 'Show trail'}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 17l4-4 4 4 4-4 4 4"/>
            </svg>
            Trail
          </button>

          {/* Satellite */}
          <button
            onClick={() => setShowSatellite(!showSatellite)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
              showSatellite
                ? 'bg-blue-500/15 text-blue-400/80 border border-blue-500/20'
                : 'bg-mag-surface-raised backdrop-blur text-mag-text-muted border-mag-border hover:bg-mag-surface hover:text-mag-text-dim'
            }`}
            title={showSatellite ? 'Map view' : 'Satellite view'}
          >
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {showSatellite ? (
                <><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></>
              ) : (
                <><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/></>
              )}
            </svg>
            {showSatellite ? 'Map' : 'Sat'}
          </button>



          {/* Nav */}
          {effectiveUserPos && latestLocation && userNavigationUsable && (
            <button
              onClick={handleNavigate}
              disabled={navigating}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all bg-emerald-500/15 text-emerald-400/80 border border-emerald-500/20 hover:bg-emerald-500/25 disabled:opacity-50"
              title="Navigate to device"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 11l19-9-9 19-2-8-8-2z"/>
              </svg>
              {navigating ? '...' : 'Nav'}
            </button>
          )}

          {/* Replay */}
          {locations.length > 2 && (
            <button
              onClick={() => {
                if (showPathTracker) {
                  setShowPathTracker(false);
                  setPathPlaying(false);
                  if (followBeforeReplay.current !== null) {
                    setFollowDevice(followBeforeReplay.current);
                    followBeforeReplay.current = null;
                  }
                } else {
                  followBeforeReplay.current = followDevice;
                  setFollowDevice(false);
                  setShowPathTracker(true);
                  setPathIndex(0);
                }
              }}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[9px] font-mono font-bold uppercase tracking-wider transition-all ${
                showPathTracker
                  ? 'bg-blue-500/15 text-blue-400/80 border border-blue-500/20'
                  : 'bg-mag-surface-raised backdrop-blur text-mag-text-muted border-mag-border hover:bg-mag-surface hover:text-mag-text-dim'
              }`}
              title={showPathTracker ? 'Close replay' : 'Replay trail'}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="5 3 19 12 5 21 5 3"/>
              </svg>
              {showPathTracker ? 'Close' : 'Replay'}
            </button>
          )}
        </div>
        </div>
      </div>

      {/* Path replay timeline — premium dark */}
      {showPathTracker && trailLocations.length > 1 && (
        <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-[1000] md:bottom-4 bottom-28">
          <div className="bg-mag-surface-raised/95 backdrop-blur-xl border-mag-border rounded-xl shadow-xl px-4 py-3 flex items-center gap-3">
            <button
              onClick={() => setPathPlaying(!pathPlaying)}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-mag-surface-raised text-mag-text-dim hover:bg-mag-surface hover:text-mag-text transition-colors"
            >
              {pathPlaying ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
                </svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
              )}
            </button>

            <input
              type="range"
              min={0}
              max={trailLocations.length - 1}
              value={pathIndex}
              onChange={(e) => { setPathIndex(Number(e.target.value)); setPathPlaying(false); }}
              className="w-32 sm:w-48 h-1.5 bg-mag-border rounded-full appearance-none cursor-pointer"
            />

            <span className="font-mono text-[10px] text-white/50 font-bold tabular-nums min-w-[40px]">
              {pathIndex + 1}/{trailLocations.length}
            </span>

            <select
              value={pathSpeed}
              onChange={(e) => setPathSpeed(Number(e.target.value))}
              className="font-mono text-[10px] font-bold text-mag-text-dim bg-mag-surface-raised border-mag-border rounded-md px-2 py-1"
            >
              <option value={1}>1×</option>
              <option value={2}>2×</option>
              <option value={4}>4×</option>
              <option value={8}>8×</option>
            </select>

            {pathIndex > 0 && trailLocations[pathIndex] && (
              <span className="font-mono text-[10px] text-mag-text-muted font-bold hidden sm:inline">
                {formatTimestamp(locationTimestamp(trailLocations[pathIndex]))}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
