'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { cn } from '@/lib/utils';
import { MapPin, Clock, Download, Filter, Layers } from 'lucide-react';

// Dynamic imports for SSR safety
const MapContainer = dynamic(() => import('react-leaflet').then(m => m.MapContainer), { ssr: false });
const TileLayer = dynamic(() => import('react-leaflet').then(m => m.TileLayer), { ssr: false });
const CircleMarker = dynamic(() => import('react-leaflet').then(m => m.CircleMarker), { ssr: false });
const Polyline = dynamic(() => import('react-leaflet').then(m => m.Polyline), { ssr: false });
const Popup = dynamic(() => import('react-leaflet').then(m => m.Popup), { ssr: false });

interface LocationPoint {
  lat: number;
  lng: number;
  server_timestamp: string;
  battery_percent?: number;
  speed?: number;
  accuracy_horizontal?: number;
}

interface LocationHeatmapProps {
  deviceId: string;
  className?: string;
}

type TimeFilter = '24h' | '7d' | '30d' | 'all';

function getTimeFilterMs(filter: TimeFilter): number | null {
  switch (filter) {
    case '24h': return 24 * 60 * 60 * 1000;
    case '7d': return 7 * 24 * 60 * 60 * 1000;
    case '30d': return 30 * 24 * 60 * 60 * 1000;
    case 'all': return null;
  }
}

function getHeatColor(index: number, total: number): string {
  // Gradient from blue (old) → green → yellow → red (recent)
  const ratio = total > 1 ? index / (total - 1) : 0;
  if (ratio < 0.25) return '#3b82f6'; // blue
  if (ratio < 0.5) return '#22c55e';  // green
  if (ratio < 0.75) return '#eab308'; // yellow
  return '#ef4444'; // red
}

function formatTimeAgo(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diff = now - then;

  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

export function LocationHeatmap({ deviceId, className }: LocationHeatmapProps) {
  const [locations, setLocations] = useState<LocationPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeFilter, setTimeFilter] = useState<TimeFilter>('7d');
  const [showTrail, setShowTrail] = useState(true);
  const [showHeat, setShowHeat] = useState(true);

  useEffect(() => {
    async function fetchLocations() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/dashboard/locations/${deviceId}?limit=1000`);
        if (!res.ok) throw new Error('Failed to fetch locations');
        const data = await res.json();
        setLocations(data.locations || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load locations');
      } finally {
        setLoading(false);
      }
    }
    fetchLocations();
  }, [deviceId]);

  const filteredLocations = useMemo(() => {
    const filterMs = getTimeFilterMs(timeFilter);
    if (!filterMs) return locations;

    const cutoff = Date.now() - filterMs;
    return locations.filter(loc =>
      new Date(loc.server_timestamp).getTime() > cutoff
    );
  }, [locations, timeFilter]);

  const sortedLocations = useMemo(() =>
    [...filteredLocations].sort((a, b) =>
      new Date(a.server_timestamp).getTime() - new Date(b.server_timestamp).getTime()
    ),
    [filteredLocations]
  );

  const center = useMemo(() => {
    if (sortedLocations.length === 0) return [6.5244, 3.3792] as [number, number];
    const avgLat = sortedLocations.reduce((sum, loc) => sum + loc.lat, 0) / sortedLocations.length;
    const avgLng = sortedLocations.reduce((sum, loc) => sum + loc.lng, 0) / sortedLocations.length;
    return [avgLat, avgLng] as [number, number];
  }, [sortedLocations]);

  const stats = useMemo(() => {
    if (sortedLocations.length === 0) return null;
    const first = sortedLocations[0];
    const last = sortedLocations[sortedLocations.length - 1];
    const timeSpan = new Date(last.server_timestamp).getTime() - new Date(first.server_timestamp).getTime();

    return {
      count: sortedLocations.length,
      timeSpan: timeSpan < 3600000
        ? `${Math.round(timeSpan / 60000)} min`
        : timeSpan < 86400000
          ? `${Math.round(timeSpan / 3600000)} hours`
          : `${Math.round(timeSpan / 86400000)} days`,
      firstSeen: first.server_timestamp,
      lastSeen: last.server_timestamp,
    };
  }, [sortedLocations]);

  const handleExport = useCallback(() => {
    const csv = [
      'timestamp,lat,lng,battery,speed,accuracy',
      ...sortedLocations.map(loc =>
        `${loc.server_timestamp},${loc.lat},${loc.lng},${loc.battery_percent || ''},${loc.speed || ''},${loc.accuracy_horizontal || ''}`
      )
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `location-history-${deviceId}-${timeFilter}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [sortedLocations, deviceId, timeFilter]);

  if (loading) {
    return (
      <div className={cn('flex items-center justify-center h-64 bg-mag-surface rounded-lg', className)}>
        <div className="text-mag-text-muted animate-pulse">Loading location history...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={cn('flex items-center justify-center h-64 bg-mag-surface rounded-lg', className)}>
        <div className="text-red-400">{error}</div>
      </div>
    );
  }

  return (
    <div className={cn('relative', className)}>
      {/* Controls */}
      <div className="absolute top-2 left-2 z-[1000] flex flex-wrap gap-2">
        {/* Time Filter */}
        <div className="flex bg-mag-surface-raised/80 backdrop-blur rounded-lg p-1">
          {(['24h', '7d', '30d', 'all'] as TimeFilter[]).map(filter => (
            <button
              key={filter}
              onClick={() => setTimeFilter(filter)}
              className={cn(
                'px-2 py-1 text-xs font-medium rounded transition-colors',
                timeFilter === filter
                  ? 'bg-mag-primary text-white'
                  : 'text-mag-text-muted hover:text-white'
              )}
            >
              {filter === 'all' ? 'All' : filter}
            </button>
          ))}
        </div>

        {/* Display Options */}
        <div className="flex bg-mag-surface-raised/80 backdrop-blur rounded-lg p-1 gap-1">
          <button
            onClick={() => setShowTrail(!showTrail)}
            className={cn(
              'p-1.5 rounded transition-colors',
              showTrail ? 'bg-blue-600 text-white' : 'text-mag-text-muted hover:text-white'
            )}
            title="Show trail"
          >
            <MapPin className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setShowHeat(!showHeat)}
            className={cn(
              'p-1.5 rounded transition-colors',
              showHeat ? 'bg-orange-600 text-white' : 'text-mag-text-muted hover:text-white'
            )}
            title="Show heatmap"
          >
            <Layers className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleExport}
            className="p-1.5 text-mag-text-muted hover:text-white transition-colors"
            title="Export CSV"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Stats */}
      {stats && (
        <div className="absolute bottom-2 left-2 z-[1000] bg-mag-surface-raised/80 backdrop-blur rounded-lg p-2 text-xs">
          <div className="text-mag-text">
            <span className="font-medium text-white">{stats.count}</span> points
            <span className="text-mag-text-muted mx-1">·</span>
            <Clock className="w-3 h-3 inline mr-1 text-mag-text-muted" />
            {stats.timeSpan}
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-2 right-2 z-[1000] bg-mag-surface-raised/80 backdrop-blur rounded-lg p-2 text-xs">
        <div className="text-mag-text-muted mb-1">Timeline</div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span className="text-mag-text-muted">Oldest</span>
          <div className="flex-1 h-1 bg-gradient-to-r from-blue-500 via-green-500 via-yellow-500 to-red-500 rounded mx-1" />
          <span className="text-mag-text-muted">Newest</span>
          <div className="w-3 h-3 rounded-full bg-red-500" />
        </div>
      </div>

      {/* Map */}
      <MapContainer
        center={center}
        zoom={13}
        className="h-64 w-full rounded-lg"
        style={{ background: '#1a1a2e' }}
      >
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />

        {/* Trail */}
        {showTrail && sortedLocations.length > 1 && (
          <Polyline
            positions={sortedLocations.map(loc => [loc.lat, loc.lng])}
            pathOptions={{
              color: '#3b82f6',
              weight: 2,
              opacity: 0.6,
              dashArray: '5, 10',
            }}
          />
        )}

        {/* Heatmap points */}
        {showHeat && sortedLocations.map((loc, i) => (
          <CircleMarker
            key={`${loc.server_timestamp}-${i}`}
            center={[loc.lat, loc.lng]}
            radius={4}
            pathOptions={{
              color: getHeatColor(i, sortedLocations.length),
              fillColor: getHeatColor(i, sortedLocations.length),
              fillOpacity: 0.7,
              weight: 1,
            }}
          >
            <Popup>
              <div className="text-sm">
                <div className="font-medium">{formatTimeAgo(loc.server_timestamp)}</div>
                <div className="text-mag-text-muted text-xs">{loc.server_timestamp}</div>
                {loc.battery_percent && (
                  <div className="text-xs mt-1">Battery: {loc.battery_percent}%</div>
                )}
                {loc.speed && loc.speed > 0 && (
                  <div className="text-mag-text text-xs">Speed: {Math.round(loc.speed * 3.6)} km/h</div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
