'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { useStore } from '@/store/useStore';
import { cn, openGoogleMapsDirections, formatDistance, formatDuration, isOnline, relativeTime, formatTimestamp, locationTimestamp } from '@/lib/utils';
import { getOSRMRoute, NavigationRoute } from '@/services/navigation';
import type { Location } from '@/types';

// ─── Reverse Geocoding ─────────────────────────────────────────────────────
// Converts lat/lng to a human-readable street address using Nominatim
// (OpenStreetMap's free geocoder). Caches results to avoid hammering the
// free API. This is what makes the map "real-world navigatable" — the
// operator sees "14 Broad St, Lagos" not just "6.5244, 3.3792".
const geocodeCache = new Map<string, string>();
const GEOCODE_CACHE_MAX = 50;

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
    // Shorten: take the first two comma-separated parts (street + city)
    const parts = addr.split(',').map((s: string) => s.trim());
    const short = parts.slice(0, Math.min(3, parts.length)).join(', ');
    // Evict oldest entry when cache is full
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
// MapTiler gives noticeably better Africa/Nigeria coverage than pure OSM
// (Carto's dark_all tiles — Nigerian building polygons show as black blocks).
// Falls back to Carto Dark Matter when no key is configured so the map never
// breaks. Set NEXT_PUBLIC_MAPTILER_KEY (or a full NEXT_PUBLIC_MAP_TILE_URL)
// in the dashboard build env to enable.
const MAPTILER_KEY = process.env.NEXT_PUBLIC_MAPTILER_KEY || '';
const MAP_TILE_URL = process.env.NEXT_PUBLIC_MAP_TILE_URL || '';
const MAP_TILE_URL_RESOLVED =
  MAP_TILE_URL ||
  (MAPTILER_KEY
    ? `https://api.maptiler.com/maps/dark-matter/{z}/{x}/{y}.png?key=${MAPTILER_KEY}`
    : 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png');
const MAP_TILE_ATTRIBUTION = MAP_TILE_URL
  ? ''
  : MAPTILER_KEY
    ? '&copy; <a href="https://www.maptiler.com/copyright/">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    : '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

// Satellite view tiles — Esri World Imagery (free, no key needed)
const SATELLITE_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const SATELLITE_ATTRIBUTION = '&copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics';

// ─── Operator position policy ────────────────────────────────────────────────
// The DEVICE marker comes from the tracked phone's GPS (server data). The
// operator's own "YOU" position comes from navigator.geolocation, which varies
// wildly by browser: mobile browsers use GPS (3-15m), desktop browsers fall
// back to WiFi (~20-100m) or IP geolocation (1-100+ km) and ignore
// enableHighAccuracy (no GPS hardware). In the REAL theft scenario the phone
// with GPS is the one that was stolen — telling the operator to "open the
// dashboard on your phone" is impossible — so the honest answer is a MANUAL
// PIN: the operator taps the map to say "I am here". The pinned position
// always beats the browser fix for distance and routing.
//   1. draws the browser-reported accuracy circle around the YOU marker
//   2. distance shows from the effective position (pin > browser), annotated
//      with fix quality when coarse
//   3. OSRM routing is allowed from a pin, or from a browser fix whose
//      reported accuracy is street-level
//   4. flags IP-derived fixes and offers the pin instead of "use your phone"
const USER_ACCURACY_DISTANCE_MAX = 1000; // metres — beyond this, annotate distance with fix quality
const USER_ACCURACY_NAVIGATION_MAX = 300; // metres — OSRM route from browser fix only when this good
const USER_ACCURACY_IP_FALLBACK = 5000; // metres — >= this is an IP-derived (desktop) fix
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
    // localStorage unavailable (private mode) — the pin just won't survive reloads
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

// ─── Refined Map Icons (magenta themed) ──────────────────────────────────────

let deviceIcon: any = null;
let userIcon: any = null;
let waypointIcon: any = null;
let trailDotIcon: any = null;

async function initIcons() {
  if (deviceIcon) return;
  const L = await import('leaflet');

  // Device marker — magenta dot with ring
  deviceIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:40px;height:40px;">
        <div style="position:absolute;top:4px;left:4px;width:32px;height:32px;border-radius:50%;background:rgba(233,30,140,0.2);animation:marker-pulse 2s infinite;"></div>
        <div style="position:absolute;top:8px;left:8px;width:24px;height:24px;border-radius:50%;background:linear-gradient(135deg,#E91E8C,#C4176E);border:3px solid #fff;box-shadow:0 2px 16px rgba(233,30,140,0.6);"></div>
        <div style="position:absolute;top:14px;left:14px;width:12px;height:12px;border-radius:50%;background:#fff;opacity:0.9;"></div>
      </div>
    `,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });

  // User location — cyan dot
  userIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:24px;height:24px;">
        <div style="position:absolute;top:2px;left:2px;width:20px;height:20px;border-radius:50%;background:rgba(6,182,212,0.3);animation:user-pulse 2s infinite;"></div>
        <div style="position:absolute;top:4px;left:4px;width:16px;height:16px;border-radius:50%;background:#06B6D4;border:3px solid #fff;box-shadow:0 0 10px rgba(6,182,212,0.8);"></div>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });

  // Waypoint flag
  waypointIcon = L.divIcon({
    className: '',
    html: `
      <div style="position:relative;width:28px;height:36px;">
        <svg width="28" height="36" viewBox="0 0 28 36" fill="none">
          <path d="M14 0C6.268 0 0 6.268 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.268 21.732 0 14 0z" fill="url(#pinGrad)" stroke="#fff" stroke-width="1.5"/>
          <circle cx="14" cy="14" r="6" fill="#fff" opacity="0.9"/>
          <defs><linearGradient id="pinGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#E91E8C"/><stop offset="100%" stop-color="#C4176E"/></linearGradient></defs>
        </svg>
      </div>
    `,
    iconSize: [28, 36],
    iconAnchor: [14, 36],
  });

  // Trail dot
  trailDotIcon = L.divIcon({
    className: '',
    html: `<div style="width:8px;height:8px;border-radius:50%;background:#E91E8C;border:2px solid #fff;box-shadow:0 0 6px rgba(233,30,140,0.5);"></div>`,
    iconSize: [8, 8],
    iconAnchor: [4, 4],
  });
}

// ─── Map Controller — smooth follow & recenter ────────────────────────────

function MapController({ pinning, onPin, replayActive }: {
  pinning: boolean;
  onPin: (pos: [number, number]) => void;
  // While the trail replay timeline is open the operator is scrubbing
  // history — the live follow re-centre must yield, or every poll tick
  // yanks the map away from the point being scrubbed.
  replayActive: boolean;
}) {
  const map = useMap();
  const { followDevice, latestLocation, selectedDeviceId } = useStore();
  const prevCenter = useRef<string>('');
  const prevDevice = useRef<string | null>(null);
  const userInteracted = useRef(false);
  const interactionTimer = useRef<NodeJS.Timeout | null>(null);

  // Pin mode: one map click places the operator's position.
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

  // When the operator (re)selects a device, jump to street level (z17) so the
  // exact building is visible — the persisted mapZoom is 6 (whole country) and
  // follow only pans at the current zoom, so a fresh selection used to land
  // nowhere near the device.
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

  // ── Interactive YOU / DEVICE navigation ──────────────────────────────
  // Clicking the chips flies the map to that position instead of waiting for
  // the next poll cycle. Flying to YOU turns follow OFF (so the per-second
  // device re-centre can't yank the map back); flying to DEVICE turns it ON.
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
    // A distance is always useful from ANY position we have (pin or browser
    // fix); a coarse fix is annotated, not hidden. Only a missing position
    // (nothing pinned AND no browser fix) blocks the readout.
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

  // Offline device — show when it was last seen and WHERE (last-known
  // coordinates) instead of hiding the overlay entirely.
  if (offline) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
        <div className="mag-panel px-4 py-2.5 flex items-center gap-2.5 animate-fade-in">
          <div className="w-2 h-2 rounded-full bg-mag-warning shadow-[0_0_10px_rgba(245,158,11,0.6)] animate-pulse-slow" />
          <span className="font-mono text-[10px] text-mag-warning font-bold uppercase tracking-wider">OFFLINE</span>
          <div className="h-4 w-px bg-mag-border/40" />
          <span className="font-mono text-[11px] text-mag-text-dim font-bold">
            Last seen {relativeTime(lastSeen)}
          </span>
          <span className="font-mono text-[10px] text-mag-text-dim/60 font-bold hidden sm:inline">
            · {deviceLat.toFixed(5)}, {deviceLng.toFixed(5)}
          </span>
        </div>
      </div>
    );
  }

  // No usable operator position (nothing pinned AND the browser has no fix):
  // tell the operator HOW to set one — pinning is the honest fallback when
  // the only "phone" with GPS is the one that was stolen.
  if (!userPos) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
        <div className="mag-panel px-4 py-2.5 flex items-center gap-2.5 animate-fade-in">
          <div className="w-2 h-2 rounded-full bg-mag-warning shadow-[0_0_10px_rgba(245,158,11,0.6)] animate-pulse-slow" />
          <span className="font-mono text-[10px] text-mag-warning font-bold uppercase tracking-wider">
            SET YOUR POSITION
          </span>
          <div className="h-4 w-px bg-mag-border/40" />
          <span className="font-mono text-[10px] text-mag-text-dim font-bold">
            tap PIN POSITION, then tap the map where you are
          </span>
        </div>
      </div>
    );
  }

  if (!distance) return null;

  // When the operator's position is IP-derived (desktop browser, no GPS),
  // the distance is meaningless — it's measuring from a random IP location,
  // not from where the operator actually is. Show a different overlay that
  // makes this clear and promotes PIN POSITION.
  if (!userPinned && userAccuracy != null && userAccuracy > USER_ACCURACY_IP_FALLBACK) {
    return (
      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000] max-w-lg">
        <div className="mag-panel px-4 py-3 animate-fade-in">
          <div className="flex items-center gap-2 mb-1.5">
            <div className="w-2 h-2 rounded-full bg-mag-primary shadow-[0_0_10px_rgba(233,30,140,0.6)]" />
            <span className="font-mono text-[10px] text-mag-primary font-bold uppercase tracking-wider">DEVICE TRACKED</span>
            <div className="h-3 w-px bg-mag-border/40" />
            <span className="font-mono text-[10px] text-mag-accent font-bold">{formatDistance(distance)} away (approx)</span>
          </div>
          <div className="flex items-start gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-warning shrink-0 mt-0.5">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/>
              <line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <div className="text-[10px] font-mono text-mag-text-dim leading-relaxed">
              <span className="text-mag-warning font-bold">Your browser position is IP-derived (±{formatAccuracyMeters(userAccuracy!)})</span>
              — desktop browsers have no GPS. The distance above is approximate.
              <span className="text-mag-text font-bold"> Tap PIN POSITION below, then tap the map where you actually are</span>
              for an accurate distance and turn-by-turn route to your device.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
      <div className="mag-panel px-4 py-2.5 flex items-center gap-4 animate-fade-in">
        <button
          onClick={flyToYou}
          disabled={!userPos}
          title={userPos ? 'Fly to your location (stops device follow)' : 'No position yet'}
          className="flex items-center gap-2 group/y disabled:opacity-50"
        >
          <div className="w-2 h-2 rounded-full bg-mag-secondary shadow-[0_0_10px_rgba(6,182,212,0.6)] group-hover/y:scale-125 transition-transform" />
          <span className="font-mono text-[11px] text-mag-text-dim font-bold group-hover/y:text-mag-secondary group-hover/y:underline underline-offset-2 transition-colors">YOU</span>
        </button>
        <svg width="16" height="16" viewBox="0 0 16 16" className="text-mag-text-dim/50">
          <path d="M1 8h14M8 1l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <button
          onClick={flyToDevice}
          title="Fly to the device (resumes follow)"
          className="flex items-center gap-2 group/d"
        >
          <div className="w-2 h-2 rounded-full bg-mag-primary shadow-[0_0_10px_rgba(233,30,140,0.6)] group-hover/d:scale-125 transition-transform" />
          <span className="font-mono text-[11px] text-mag-text-dim font-bold group-hover/d:text-mag-primary group-hover/d:underline underline-offset-2 transition-colors">DEVICE</span>
        </button>
        <div className="h-4 w-px bg-mag-border/40" />
        <span className="font-mono text-sm font-bold text-mag-primary tabular-nums">
          {formatDistance(distance)}
        </span>
        <span className="font-mono text-[10px] text-mag-text-dim/60 font-bold">away</span>
        {!userPinned && userAccuracy != null && userAccuracy > USER_ACCURACY_DISTANCE_MAX && (
          <span className="font-mono text-[9px] text-mag-warning font-bold">
            ±{formatAccuracyMeters(userAccuracy)} IP fix — pin your spot
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Path Animation Tracker ────────────────────────────────────────────────

function PathAnimationTracker({ trailLocations, isPlaying, playbackSpeed, index, onIndexChange }: {
  // Pre-reversed (oldest → newest) trail from the parent — already memoized
  // upstream so the path-rebuild effect never re-fires on every render.
  trailLocations: Location[];
  isPlaying: boolean;
  playbackSpeed: number;
  index: number;
  onIndexChange: (index: number) => void;
}) {
  const map = useMap();
  const [animatedPath, setAnimatedPath] = useState<[number, number][]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // Playback ticker — advances the SHARED index (the parent owns the state so
  // the timeline slider and the animation stay in sync).
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

  // Rebuild the drawn path whenever the index changes (playback OR scrubbing)
  // and keep the map panned onto the current point.
  useEffect(() => {
    setAnimatedPath(trailLocations.slice(0, index + 1).map((l) => [l.lat, l.lng] as [number, number]));
    const loc = trailLocations[index];
    if (loc) {
      map.panTo([loc.lat, loc.lng], { animate: true, duration: 0.25 });
    }
  }, [index, trailLocations, map]);

  // Reset when the device/selection changes
  useEffect(() => {
    onIndexChange(0);
    setAnimatedPath([]);
  }, [trailLocations, onIndexChange]);

  if (animatedPath.length < 2) return null;

  return (
    <>
      {/* Animated trail line */}
      <Polyline
        positions={animatedPath}
        pathOptions={{
          color: '#E91E8C',
          weight: 4,
          opacity: 0.9,
          lineCap: 'round',
          lineJoin: 'round',
        }}
      />
      {/* Glow layer */}
      <Polyline
        positions={animatedPath}
        pathOptions={{
          color: '#E91E8C',
          weight: 10,
          opacity: 0.15,
          lineCap: 'round',
          lineJoin: 'round',
        }}
      />
      {/* Current position dot */}
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

  // Leaflet map instance — lets marker clicks fly the map to their position
  // instantly instead of waiting for the next poll/follow cycle.
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
  // Pinned operator position — the operator taps the map to say "I am here".
  // This is the PRIMARY source for a theft trail run from a laptop (no GPS)
  // and always beats an IP-derived browser fix. Survives reloads.
  const [userPinned, setUserPinned] = useState<[number, number] | null>(loadPinnedPosition);
  const [pinning, setPinning] = useState(false);

  // Effective operator position: pin wins over the browser fix.
  const effectiveUserPos = userPinned ?? userPosition;
  // Routing is safe from a pinned position (the operator chose the exact
  // point), or from a browser fix whose reported accuracy is street-level.
  // Routing from an IP-derived fix would send the operator to the wrong city.
  const userNavigationUsable =
    !!userPinned || (!!userPosition && userAccuracy != null && userAccuracy <= USER_ACCURACY_NAVIGATION_MAX);
  const userFixIsIpDerived =
    !userPinned && !!userPosition && userAccuracy != null && userAccuracy >= USER_ACCURACY_IP_FALLBACK;

  // Path tracker state — the index is shared with the timeline slider so
  // scrubbing and playback stay in sync
  const [pathPlaying, setPathPlaying] = useState(false);
  const [pathSpeed, setPathSpeed] = useState(2);
  const [pathIndex, setPathIndex] = useState(0);
  const [showPathTracker, setShowPathTracker] = useState(false);
  // Remember whether follow was on before replay opened, so closing replay
  // restores it instead of leaving the map stranded or yanking it.
  const followBeforeReplay = useRef<boolean | null>(null);

  // Selected device + online state (drives the offline banner + zoom-on-select)
  const device = devices.find(d => d.id === selectedDeviceId);
  const deviceOnline = device ? isOnline(device.last_seen) : true;

  // Replay trail (oldest → newest) for the timeline scrubber — memoized so
  // the timeline and the animation tracker share one stable ordering.
  const trailLocations = useMemo(() => locations.slice().reverse(), [locations]);

  // Stop playback when the replay reaches the end of the trail
  useEffect(() => {
    if (pathPlaying && trailLocations.length > 0 && pathIndex >= trailLocations.length - 1) {
      setPathPlaying(false);
    }
  }, [pathPlaying, pathIndex, trailLocations.length]);

  // Get user position — captures coords.accuracy too, because the operator's
  // fix quality is browser-dependent (mobile GPS vs desktop WiFi/IP). Every
  // downstream feature (distance, routing) is gated on that accuracy; the
  // error handler flags permission denial so the UI can explain itself.
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

  // Reverse geocode device position when it changes — show a street address
  // instead of raw coordinates for real-world navigability.
  // Deps are the primitive coords on purpose: the location object identity
  // changes on EVERY ping (battery/timestamp/etc.) and re-geocoding then
  // would waste calls; re-run only when lat/lng actually move.
  useEffect(() => {
    if (!latestLocation) return;
    let cancelled = false;
    reverseGeocode(latestLocation.lat, latestLocation.lng).then((addr) => {
      if (!cancelled) setDeviceAddress(addr);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- coord deps are deliberate: re-geocode only when lat/lng actually move (see comment above the hook)
  }, [latestLocation?.lat, latestLocation?.lng]);

  // Initialize Leaflet icons and map
  useEffect(() => {
    setMapReady(true);
    initIcons().then(() => setIconsReady(true));
  }, []);

  // Place the operator's pinned position (from pin mode) and persist it.
  const handlePin = useCallback((pos: [number, number]) => {
    setUserPinned(pos);
    savePinnedPosition(pos);
    setPinning(false);
  }, []);

  // Navigation handler
  const handleNavigate = useCallback(async () => {
    if (!latestLocation || !effectiveUserPos || !userNavigationUsable) return;
    setNavigating(true);
    try {
      const route = await getOSRMRoute(
        effectiveUserPos[0], effectiveUserPos[1],
        latestLocation.lat, latestLocation.lng
      );
      setNavigationRoute(route);
    } catch (e) {
      console.warn('Navigation failed:', e);
    } finally {
      setNavigating(false);
    }
  }, [latestLocation, effectiveUserPos, userNavigationUsable]);

  // Clear route when device moves
  useEffect(() => {
    if (navigationRoute && latestLocation) {
      const lastCoord = navigationRoute.geometry[navigationRoute.geometry.length - 1];
      if (lastCoord) {
        const dist = Math.abs(latestLocation.lat - lastCoord[0]) + Math.abs(latestLocation.lng - lastCoord[1]);
        if (dist > 0.001) setNavigationRoute(null);
      }
    }
  }, [latestLocation, navigationRoute]);

  // Trail points (oldest to newest)
  const trailPoints = useMemo(
    () => locations.slice().reverse().map((l) => [l.lat, l.lng] as [number, number]),
    [locations]
  );

  return (
    <div className="relative flex-1 h-full bg-mag-bg">
      {/* Map */}
      {mapReady && (
        <MapContainer
          ref={mapRef}
          center={mapCenter}
          zoom={mapZoom}
          className="w-full h-full"
          zoomControl={true}
          attributionControl={true}
          zoomSnap={0.5}
          zoomDelta={0.5}
          wheelPxPerZoomLevel={60}
        >
          {/* Map tiles — dark (default) or satellite view */}
          {showSatellite ? (
            <>
              <TileLayer
                url={SATELLITE_TILE_URL}
                maxZoom={18}
                attribution={SATELLITE_ATTRIBUTION}
              />
              {/* Semi-transparent dark overlay for satellite so UI text is readable */}
              <TileLayer
                url={MAP_TILE_URL_RESOLVED}
                maxZoom={19}
                opacity={0.3}
              />
            </>
          ) : (
            <TileLayer
              url={MAP_TILE_URL_RESOLVED}
              maxZoom={19}
              attribution={MAP_TILE_ATTRIBUTION}
            />
          )}

          <MapController pinning={pinning} onPin={handlePin} replayActive={showPathTracker} />

          {/* Distance / offline overlay */}
          {latestLocation && (effectiveUserPos || !deviceOnline) && (
            <DistanceOverlay
              userPos={effectiveUserPos}
              userAccuracy={userAccuracy}
              userPinned={!!userPinned}
              deviceLat={latestLocation.lat}
              deviceLng={latestLocation.lng}
              offline={!deviceOnline}
              lastSeen={device?.last_seen ?? null}
            />
          )}

          {/* IP-derived warning is now shown in the DistanceOverlay component */}

          {/* Location permission denied — distance/routing can't work at all */}
          {userGeoDenied && (
            <div className="absolute top-3 right-3 z-[1000] max-w-xs">
              <div className="mag-panel px-3 py-2 flex items-start gap-2 animate-fade-in">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-warning shrink-0 mt-0.5">
                  <path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/>
                  <path d="M2 12h20"/>
                </svg>
                <div className="text-[10px] font-mono text-mag-text-dim font-bold leading-tight">
                  <span className="text-mag-warning">LOCATION PERMISSION DENIED</span>
                  <span className="block mt-0.5 text-mag-text-dim/70">
                    Distance and routing need browser location. Allow it in your
                    browser settings.
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Path Animation Tracker — receives the memoized trail (already
              oldest→newest) so it doesn't reverse the array a second time on
              every render. */}
          {showPathTracker && (
            <PathAnimationTracker
              trailLocations={trailLocations}
              isPlaying={pathPlaying}
              playbackSpeed={pathSpeed}
              index={pathIndex}
              onIndexChange={setPathIndex}
            />
          )}

          {/* OSRM Navigation Route */}
          {navigationRoute && navigationRoute.geometry.length > 1 && (
            <>
              <Polyline
                positions={navigationRoute.geometry}
                pathOptions={{
                  color: '#06B6D4',
                  weight: 5,
                  opacity: 0.85,
                }}
              />
              <Polyline
                positions={navigationRoute.geometry}
                pathOptions={{
                  color: '#0891B2',
                  weight: 3,
                  opacity: 0.5,
                  dashArray: '1, 8',
                }}
              />
            </>
          )}

          {/* Trail */}
          {showTrail && trailPoints.length > 1 && !navigationRoute && !showPathTracker && (
            <Polyline
              positions={trailPoints}
              pathOptions={{
                color: '#E91E8C',
                weight: 2.5,
                opacity: 0.4,
                dashArray: '8, 10',
              }}
            />
          )}

          {/* Prediction Line */}
          {latestLocation && latestLocation.speed && latestLocation.speed > 0.5 && (() => {
            const distM = latestLocation.speed * 60;
            const bearingRad = ((latestLocation.bearing || 0) * Math.PI) / 180;
            const R = 6371000;
            const dLat = distM * Math.cos(bearingRad) / R;
            const dLng = distM * Math.sin(bearingRad) / (R * Math.cos((latestLocation.lat * Math.PI) / 180));
            const predLat = latestLocation.lat + (dLat * 180) / Math.PI;
            const predLng = latestLocation.lng + (dLng * 180) / Math.PI;
            return (
              <Polyline
                positions={[[latestLocation.lat, latestLocation.lng], [predLat, predLng]]}
                pathOptions={{
                  color: '#F59E0B',
                  weight: 2,
                  opacity: 0.5,
                  dashArray: '6, 8',
                }}
              />
            );
          })()}

          {/* Accuracy Circle */}
          {latestLocation && latestLocation.accuracy && (
            <Circle
              center={[latestLocation.lat, latestLocation.lng]}
              radius={latestLocation.accuracy}
              pathOptions={{
                color: '#E91E8C',
                fillColor: '#E91E8C',
                fillOpacity: 0.06,
                weight: 1,
                opacity: 0.25,
              }}
            />
          )}

          {/* Device Marker — click flies to it (street level) and resumes
              follow, so the operator never fights the per-second re-centre */}
          {latestLocation && iconsReady && deviceIcon && (
            <Marker
              position={[latestLocation.lat, latestLocation.lng]}
              icon={deviceIcon}
              eventHandlers={{
                click: () => {
                  if (!mapRef.current) return;
                  setFollowDevice(true);
                  mapRef.current.flyTo(
                    [latestLocation.lat, latestLocation.lng],
                    Math.max(mapRef.current.getZoom(), 16),
                    { animate: true, duration: 0.8 }
                  );
                },
              }}
            >
              <Popup>
                <div className="font-sans text-sm min-w-[220px]">
                  <div className="font-bold text-mag-primary mb-2 flex items-center gap-1.5">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/><path d="M2 12h20"/></svg>
                    DEVICE LOCATION
                  </div>
                  {deviceAddress && (
                    <div className="text-mag-text text-xs font-bold mb-2 leading-tight">
                      📍 {deviceAddress}
                    </div>
                  )}
                  <div className="space-y-1 text-mag-text-dim">
                    <div className="flex justify-between">
                      <span className="font-mono text-[11px] font-bold">Latitude</span>
                      <span className="font-mono text-[11px] text-mag-text font-bold">{latestLocation.lat.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="font-mono text-[11px] font-bold">Longitude</span>
                      <span className="font-mono text-[11px] text-mag-text font-bold">{latestLocation.lng.toFixed(6)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="font-mono text-[11px] font-bold">Accuracy</span>
                      <span className="font-mono text-[11px] text-mag-text font-bold">±{latestLocation.accuracy?.toFixed(1) || '?'}m</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="font-mono text-[11px] font-bold">Provider</span>
                      <span className="font-mono text-[11px] text-mag-accent font-bold">{latestLocation.provider}</span>
                    </div>
                    {latestLocation.speed != null && (
                      <div className="flex justify-between">
                        <span className="font-mono text-[11px] font-bold">Speed</span>
                        <span className="font-mono text-[11px] text-mag-text font-bold">{(latestLocation.speed * 3.6).toFixed(1)} km/h</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-2 pt-2 border-t border-mag-border/50 text-mag-text-dim/50 font-mono text-[10px] font-bold">
                    {formatTimestamp(locationTimestamp(latestLocation))}
                  </div>
                </div>
              </Popup>
            </Marker>
          )}

          {/* User accuracy circle — honest visualization of the browser's own
              reported fix quality (tiny on mobile GPS, huge on desktop IP). */}
          {!userPinned && userPosition && userAccuracy != null && (
            <Circle
              center={userPosition}
              radius={userAccuracy}
              pathOptions={{
                color: '#06B6D4',
                fillColor: '#06B6D4',
                fillOpacity: 0.05,
                weight: 1,
                opacity: 0.25,
              }}
            />
          )}

          {/* Operator marker — click flies to YOU and pauses device follow */}
          {effectiveUserPos && iconsReady && userIcon && (
            <Marker
              position={effectiveUserPos}
              icon={userIcon}
              eventHandlers={{
                click: () => {
                  if (!mapRef.current) return;
                  setFollowDevice(false);
                  mapRef.current.flyTo(
                    effectiveUserPos,
                    Math.max(mapRef.current.getZoom(), 16),
                    { animate: true, duration: 0.8 }
                  );
                },
              }}
            >
              <Popup>
                <div className="font-sans text-sm min-w-[160px]">
                  <div className="font-bold text-mag-secondary mb-1 flex items-center gap-1.5">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
                    {userPinned ? 'PINNED POSITION' : 'YOUR LOCATION'}
                  </div>
                  <div className="text-mag-text-dim font-mono text-[11px] font-bold">
                    {effectiveUserPos[0].toFixed(6)}, {effectiveUserPos[1].toFixed(6)}
                  </div>
                  {userPinned ? (
                    <div className="text-mag-text-dim/70 font-mono text-[10px] font-bold mt-1">
                      Set by you on the map — used for distance & route
                    </div>
                  ) : (
                    userAccuracy != null && (
                      <div className="text-mag-text-dim/70 font-mono text-[10px] font-bold mt-1">
                        Accuracy ±{formatAccuracyMeters(userAccuracy)}
                        {userAccuracy > USER_ACCURACY_DISTANCE_MAX && (
                          <span className="text-mag-warning"> — IP-based, not GPS</span>
                        )}
                      </div>
                    )
                  )}
                </div>
              </Popup>
            </Marker>
          )}

          {/* Route Waypoints */}
          {iconsReady && waypointIcon && navigationRoute?.steps.map((step, idx) => {
            const coord = navigationRoute.geometry[Math.min(
              Math.floor((idx / navigationRoute.steps.length) * navigationRoute.geometry.length),
              navigationRoute.geometry.length - 1
            )];
            if (!coord || idx === 0) return null;
            return (
              <Marker key={idx} position={coord} icon={waypointIcon}>
                <Popup>
                  <div className="font-sans text-xs max-w-[200px]">
                    <div className="font-bold text-mag-primary mb-1">Step {idx}</div>
                    <div className="text-mag-text-dim font-bold">{step.instruction}</div>
                    <div className="text-mag-text-dim/60 mt-1 font-mono text-[10px] font-bold">
                      {formatDistance(step.distance)} • {formatDuration(Math.round(step.duration))}
                    </div>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      )}

      {/* ── Trail Replay Timeline (video-scrubber style) ────────────────── */}
      {showPathTracker && latestLocation && trailLocations.length > 2 && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-[1000] w-[min(520px,calc(100%-2rem))] mag-panel px-4 py-3 animate-fade-in">
          <div className="flex items-center justify-between gap-3 mb-2">
            <span className="text-[9px] font-mono font-bold uppercase tracking-widest text-mag-text-dim/60">
              Trail Replay
            </span>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPathPlaying(!pathPlaying)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-mono font-bold border transition-all',
                  pathPlaying
                    ? 'border-mag-accent/40 text-mag-accent bg-mag-accent/10'
                    : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
              >
                {pathPlaying ? (
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                ) : (
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                )}
                {pathPlaying ? 'PAUSE' : 'PLAY'}
              </button>
              <select
                value={pathSpeed}
                onChange={(e) => setPathSpeed(Number(e.target.value))}
                className="bg-mag-surface/40 border border-mag-border/40 rounded-lg px-1.5 py-1 text-[9px] font-mono font-bold text-mag-text-dim focus:outline-none focus:border-mag-primary/40"
              >
                <option value={1}>1x</option>
                <option value={2}>2x</option>
                <option value={4}>4x</option>
                <option value={8}>8x</option>
              </select>
            </div>
          </div>

          <input
            type="range"
            min={0}
            max={trailLocations.length - 1}
            step={1}
            value={pathIndex}
            onChange={(e) => { setPathPlaying(false); setPathIndex(Number(e.target.value)); }}
            aria-label="Trail replay timeline"
            className="w-full accent-[#E91E8C] cursor-pointer"
          />

          <div className="flex items-center justify-between mt-1 text-[8px] font-mono text-mag-text-dim/40 font-bold">
            <span>{formatTimestamp(locationTimestamp(trailLocations[0]))}</span>
            <span className="text-mag-primary">{formatTimestamp(locationTimestamp(trailLocations[pathIndex]))}</span>
            <span>{formatTimestamp(locationTimestamp(trailLocations[trailLocations.length - 1]))}</span>
          </div>
        </div>
      )}

      {/* ── Bottom Controls ──────────────────────────────────────────────── */}
      <div className="absolute bottom-4 left-4 right-4 z-[1000] flex items-end gap-3 pointer-events-none">
        {/* Left: Position / Follow / Trail controls */}
        <div className="pointer-events-auto space-y-2">
          {latestLocation && (
            <div className="mag-panel px-3 py-2 flex items-center gap-2">
              <button
                onClick={() => { setPinning(!pinning); }}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all',
                  pinning
                    ? 'border-mag-warning/60 text-mag-warning bg-mag-warning/10 animate-pulse'
                    : userPinned
                      ? 'border-mag-secondary/40 text-mag-secondary bg-mag-secondary/10'
                      : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
                title={
                  pinning
                    ? 'Tap the map to place your position'
                    : userPinned
                      ? 'Your position is pinned on the map'
                      : 'Tap the map to mark where you are (use this when the browser has no GPS)'
                }
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                {pinning ? 'TAP THE MAP…' : userPinned ? 'PINNED' : 'PIN POSITION'}
              </button>
              {userPinned && (
                <button
                  onClick={() => { setUserPinned(null); savePinnedPosition(null); }}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border border-mag-border/60 text-mag-text-dim hover:text-mag-danger hover:border-mag-danger/40 transition-all"
                  title="Clear the pin and fall back to the browser position"
                >
                  USE GPS
                </button>
              )}
              <button
                onClick={() => {
                  // Turning follow ON also flies straight to the device — the
                  // operator shouldn't have to wait for the next poll tick to
                  // be pulled back.
                  const next = !followDevice;
                  setFollowDevice(next);
                  if (next && latestLocation && mapRef.current) {
                    mapRef.current.flyTo(
                      [latestLocation.lat, latestLocation.lng],
                      Math.max(mapRef.current.getZoom(), 16),
                      { animate: true, duration: 0.8 }
                    );
                  }
                }}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all',
                  followDevice
                    ? 'border-mag-primary/40 text-mag-primary bg-mag-primary/10 shadow-mag-glow'
                    : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg>
                {followDevice ? 'FOLLOWING' : 'FOLLOW'}
              </button>
              <button
                onClick={() => setShowTrail(!showTrail)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all',
                  showTrail
                    ? 'border-mag-secondary/40 text-mag-secondary bg-mag-secondary/10'
                    : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 4-8"/></svg>
                TRAIL
              </button>
              {/* Satellite view toggle */}
              <button
                onClick={() => setShowSatellite(!showSatellite)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all',
                  showSatellite
                    ? 'border-mag-accent/40 text-mag-accent bg-mag-accent/10'
                    : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z"/></svg>
                {showSatellite ? 'MAP' : 'SAT'}
              </button>
            </div>
          )}

          {/* Path Animation toggle */}
          {latestLocation && locations.length > 2 && (
            <div className="mag-panel px-3 py-2">
              <button
                onClick={() => {
                  if (showPathTracker) {
                    // Closing replay — restore the follow state it paused.
                    if (followBeforeReplay.current != null) {
                      setFollowDevice(followBeforeReplay.current);
                      followBeforeReplay.current = null;
                    }
                  } else {
                    // Opening replay — pause follow so the live re-centre
                    // can't fight the scrubber; remember it to restore.
                    followBeforeReplay.current = followDevice;
                    setFollowDevice(false);
                  }
                  setShowPathTracker(!showPathTracker);
                  setPathPlaying(false);
                  setPathIndex(0);
                }}
                className={cn(
                  'flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all w-full',
                  showPathTracker
                    ? 'border-mag-primary/40 text-mag-primary bg-mag-primary/10 shadow-mag-glow'
                    : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                )}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                REPLAY TRAIL
              </button>
            </div>
          )}
        </div>

        {/* Right: Navigation Panel */}
        <div className="ml-auto pointer-events-auto max-w-sm">
          {latestLocation && (
            <div className="mag-panel px-4 py-3 space-y-2 animate-fade-in">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
                  {navigationRoute ? 'ROUTE ACTIVE' : 'NAVIGATE'}
                </span>
                {navigationRoute && (
                  <button
                    onClick={() => { setNavigationRoute(null); }}
                    className="text-mag-text-dim/50 hover:text-mag-danger transition-colors"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                )}
              </div>

              {navigationRoute ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 bg-mag-secondary/10 border border-mag-secondary/20 rounded-lg px-3 py-1.5">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-secondary"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>
                      <span className="font-mono text-xs text-mag-secondary font-bold">{formatDistance(navigationRoute.distance)}</span>
                    </div>
                    <div className="flex items-center gap-2 bg-mag-accent/10 border border-mag-accent/20 rounded-lg px-3 py-1.5">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-accent"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                      <span className="font-mono text-xs text-mag-accent font-bold">{formatDuration(navigationRoute.duration)}</span>
                    </div>
                  </div>

                  {navigationRoute.steps.length > 0 && (
                    <div className="max-h-28 overflow-y-auto space-y-1 bg-mag-bg/40 rounded-lg p-2">
                      {navigationRoute.steps.slice(0, 5).map((step, idx) => (
                        <div key={idx} className="flex items-start gap-2 py-1">
                          <span className="text-sm shrink-0 mt-0.5">{step.maneuverIcon}</span>
                          <div className="min-w-0">
                            <div className="text-[10px] font-mono text-mag-text leading-tight font-bold">{step.instruction}</div>
                            <div className="text-[9px] font-mono text-mag-text-dim/60 font-bold">{formatDistance(step.distance)}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={() => openGoogleMapsDirections(latestLocation.lat, latestLocation.lng)}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-mag-border/60 text-[10px] font-mono font-bold text-mag-text-dim hover:text-mag-text hover:border-mag-border transition-all"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>
                      Google Maps
                    </button>
                    <button
                      onClick={() => window.open(`https://waze.com/ul?ll=${latestLocation.lat},${latestLocation.lng}&navigate=yes`, '_blank')}
                      className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-mag-border/60 text-[10px] font-mono font-bold text-mag-text-dim hover:text-mag-text hover:border-mag-border transition-all"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                      Waze
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={handleNavigate}
                    disabled={!userPosition || !userNavigationUsable || navigating}
                    title={!userNavigationUsable ? 'No usable position to route from — tap PIN POSITION and tap the map where you are.' : undefined}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-mono font-bold border border-mag-primary/40 text-mag-primary bg-mag-primary/8 hover:bg-mag-primary/15 transition-all disabled:opacity-40"
                  >
                    {navigating ? (
                      <span className="flex items-center gap-2">
                        <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                        CALCULATING...
                      </span>
                    ) : (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
                        {userNavigationUsable ? 'GET ROUTE' : 'PIN YOUR POSITION'}
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => openGoogleMapsDirections(latestLocation.lat, latestLocation.lng)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-[10px] font-mono font-bold border border-mag-border/60 text-mag-text-dim hover:text-mag-text hover:border-mag-border transition-all"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/></svg>
                    EXT MAPS
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Scan Line Effect */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden z-[999] opacity-[0.03]">
        <div className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-mag-primary to-transparent animate-scan" />
      </div>
    </div>
  );
}
