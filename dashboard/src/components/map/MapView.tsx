'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { useStore } from '@/store/useStore';
import { cn, openGoogleMapsDirections, formatDistance, formatDuration } from '@/lib/utils';
import { getOSRMRoute, NavigationRoute } from '@/services/navigation';
import type { Location } from '@/types';

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

function MapController() {
  const map = useMap();
  const { followDevice, latestLocation } = useStore();
  const prevCenter = useRef<string>('');
  const userInteracted = useRef(false);
  const interactionTimer = useRef<NodeJS.Timeout | null>(null);

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
    if (followDevice && latestLocation && !userInteracted.current) {
      const key = `${latestLocation.lat.toFixed(6)},${latestLocation.lng.toFixed(6)}`;
      if (key !== prevCenter.current) {
        map.setView([latestLocation.lat, latestLocation.lng], Math.max(map.getZoom(), 16), {
          animate: true,
          duration: 0.5,
        });
        prevCenter.current = key;
      }
    }
  }, [followDevice, latestLocation, map]);

  return null;
}

// ─── Distance Overlay Component ─────────────────────────────────────────────

function DistanceOverlay({ userPos, deviceLat, deviceLng }: {
  userPos: [number, number] | null;
  deviceLat: number;
  deviceLng: number;
}) {
  const [distance, setDistance] = useState<number | null>(null);

  useEffect(() => {
    if (!userPos) return;
    const R = 6371000;
    const dLat = (deviceLat - userPos[0]) * Math.PI / 180;
    const dLng = (deviceLng - userPos[1]) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
              Math.cos(userPos[0] * Math.PI / 180) * Math.cos(deviceLat * Math.PI / 180) *
              Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    setDistance(R * c);
  }, [userPos, deviceLat, deviceLng]);

  if (!distance) return null;

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[1000]">
      <div className="mag-panel px-4 py-2.5 flex items-center gap-4 animate-fade-in">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-mag-secondary shadow-[0_0_10px_rgba(6,182,212,0.6)]" />
          <span className="font-mono text-[11px] text-mag-text-dim font-bold">YOU</span>
        </div>
        <svg width="16" height="16" viewBox="0 0 16 16" className="text-mag-text-dim/50">
          <path d="M1 8h14M8 1l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-mag-primary shadow-[0_0_10px_rgba(233,30,140,0.6)]" />
          <span className="font-mono text-[11px] text-mag-text-dim font-bold">DEVICE</span>
        </div>
        <div className="h-4 w-px bg-mag-border/40" />
        <span className="font-mono text-sm font-bold text-mag-primary tabular-nums">
          {formatDistance(distance)}
        </span>
        <span className="font-mono text-[10px] text-mag-text-dim/60 font-bold">away</span>
      </div>
    </div>
  );
}

// ─── Path Animation Tracker ────────────────────────────────────────────────

interface PathTrackerProps {
  locations: Location[];
  isPlaying: boolean;
  playbackSpeed: number;
  onProgress: (index: number) => void;
}

function PathAnimationTracker({ locations, isPlaying, playbackSpeed, onProgress }: PathTrackerProps) {
  const map = useMap();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [animatedPath, setAnimatedPath] = useState<[number, number][]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const trailLocations = locations.slice().reverse();

  useEffect(() => {
    if (!isPlaying || trailLocations.length < 2) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }

    intervalRef.current = setInterval(() => {
      setCurrentIndex(prev => {
        const next = prev + 1;
        if (next >= trailLocations.length) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return prev;
        }
        const loc = trailLocations[next];
        setAnimatedPath(p => [...p, [loc.lat, loc.lng]]);
        onProgress(next);

        // Smooth pan to current position
        map.panTo([loc.lat, loc.lng], { animate: true, duration: 0.3 });

        return next;
      });
    }, 1000 / playbackSpeed);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isPlaying, playbackSpeed, trailLocations.length]);

  // Reset when locations change
  useEffect(() => {
    setCurrentIndex(0);
    setAnimatedPath([]);
  }, [locations]);

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
  } = useStore();

  const [mapReady, setMapReady] = useState(false);
  const [iconsReady, setIconsReady] = useState(false);
  const [navigationRoute, setNavigationRoute] = useState<NavigationRoute | null>(null);
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);
  const [navigating, setNavigating] = useState(false);

  // Path tracker state
  const [pathPlaying, setPathPlaying] = useState(false);
  const [pathSpeed, setPathSpeed] = useState(2);
  const [pathProgress, setPathProgress] = useState(0);
  const [showPathTracker, setShowPathTracker] = useState(false);

  // Get user position
  useEffect(() => {
    if (!navigator.geolocation) return;
    const watchId = navigator.geolocation.watchPosition(
      (pos) => setUserPosition([pos.coords.latitude, pos.coords.longitude]),
      () => {},
      { enableHighAccuracy: true, maximumAge: 5000 }
    );
    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  // Initialize Leaflet icons and map
  useEffect(() => {
    setMapReady(true);
    initIcons().then(() => setIconsReady(true));
  }, []);

  // Navigation handler
  const handleNavigate = useCallback(async () => {
    if (!latestLocation || !userPosition) return;
    setNavigating(true);
    try {
      const route = await getOSRMRoute(
        userPosition[0], userPosition[1],
        latestLocation.lat, latestLocation.lng
      );
      setNavigationRoute(route);
    } catch (e) {
      console.warn('Navigation failed:', e);
    } finally {
      setNavigating(false);
    }
  }, [latestLocation, userPosition]);

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
  const trailPoints = locations
    .slice()
    .reverse()
    .map((l) => [l.lat, l.lng] as [number, number]);

  return (
    <div className="relative flex-1 h-full bg-mag-bg">
      {/* Map */}
      {mapReady && (
        <MapContainer
          center={mapCenter}
          zoom={mapZoom}
          className="w-full h-full"
          zoomControl={true}
          attributionControl={true}
          zoomSnap={0.5}
          zoomDelta={0.5}
          wheelPxPerZoomLevel={60}
        >
          {/* Dark map tiles — CartoDB Dark Matter */}
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            maxZoom={19}
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
          />

          <MapController />

          {/* Distance Overlay */}
          {latestLocation && userPosition && (
            <DistanceOverlay
              userPos={userPosition}
              deviceLat={latestLocation.lat}
              deviceLng={latestLocation.lng}
            />
          )}

          {/* Path Animation Tracker */}
          {showPathTracker && (
            <PathAnimationTracker
              locations={locations}
              isPlaying={pathPlaying}
              playbackSpeed={pathSpeed}
              onProgress={setPathProgress}
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

          {/* Device Marker */}
          {latestLocation && iconsReady && deviceIcon && (
            <Marker position={[latestLocation.lat, latestLocation.lng]} icon={deviceIcon}>
              <Popup>
                <div className="font-sans text-sm min-w-[180px]">
                  <div className="font-bold text-mag-primary mb-2 flex items-center gap-1.5">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/><path d="M2 12h20"/></svg>
                    DEVICE LOCATION
                  </div>
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
                    {latestLocation.timestamp}
                  </div>
                </div>
              </Popup>
            </Marker>
          )}

          {/* User Location Marker */}
          {userPosition && iconsReady && userIcon && (
            <Marker position={userPosition} icon={userIcon}>
              <Popup>
                <div className="font-sans text-sm min-w-[160px]">
                  <div className="font-bold text-mag-secondary mb-1 flex items-center gap-1.5">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="12" cy="12" r="10"/></svg>
                    YOUR LOCATION
                  </div>
                  <div className="text-mag-text-dim font-mono text-[11px] font-bold">
                    {userPosition[0].toFixed(6)}, {userPosition[1].toFixed(6)}
                  </div>
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

      {/* ── Bottom Controls ──────────────────────────────────────────────── */}
      <div className="absolute bottom-4 left-4 right-4 z-[1000] flex items-end gap-3 pointer-events-none">
        {/* Left: Follow/Trail/Path controls */}
        <div className="pointer-events-auto space-y-2">
          {latestLocation && (
            <div className="mag-panel px-3 py-2 flex items-center gap-2">
              <button
                onClick={() => setFollowDevice(!followDevice)}
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
            </div>
          )}

          {/* Path Animation Controls */}
          {latestLocation && locations.length > 2 && (
            <div className="mag-panel px-3 py-2 space-y-2">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => { setShowPathTracker(!showPathTracker); setPathPlaying(false); setPathProgress(0); }}
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold uppercase tracking-wider border transition-all',
                    showPathTracker
                      ? 'border-mag-primary/40 text-mag-primary bg-mag-primary/10'
                      : 'border-mag-border/60 text-mag-text-dim hover:border-mag-border'
                  )}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                  REPLAY
                </button>
                {showPathTracker && (
                  <>
                    <button
                      onClick={() => setPathPlaying(!pathPlaying)}
                      className={cn(
                        'flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold border transition-all',
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
                      className="bg-mag-surface/40 border border-mag-border/40 rounded-lg px-2 py-1 text-[10px] font-mono font-bold text-mag-text-dim focus:outline-none focus:border-mag-primary/40"
                    >
                      <option value={1}>1x</option>
                      <option value={2}>2x</option>
                      <option value={4}>4x</option>
                      <option value={8}>8x</option>
                    </select>
                  </>
                )}
              </div>
              {showPathTracker && locations.length > 0 && (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-mag-bg/50 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-mag-primary rounded-full transition-all duration-300"
                      style={{ width: `${(pathProgress / (locations.length - 1)) * 100}%` }}
                    />
                  </div>
                  <span className="text-[9px] font-mono text-mag-text-dim/50 font-bold tabular-nums">
                    {pathProgress}/{locations.length - 1}
                  </span>
                </div>
              )}
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
                    disabled={!userPosition || navigating}
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
                        GET ROUTE
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
