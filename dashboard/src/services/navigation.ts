/**
 * Magneetar Navigation Service
 * OSRM-based turn-by-turn navigation.
 */

export interface RouteStep {
  instruction: string;
  distance: number;
  duration: number;
  maneuver: {
    type: string;
    modifier?: string;
  };
  maneuverIcon: string;
}

export interface NavigationRoute {
  distance: number;       // meters
  duration: number;       // seconds
  steps: RouteStep[];
  geometry: [number, number][];  // [lat, lng] pairs
}

/**
 * Get driving route between two points using public OSRM API.
 * Falls back to straight line if OSRM fails.
 */
export async function getOSRMRoute(
  originLat: number,
  originLng: number,
  destLat: number,
  destLng: number
): Promise<NavigationRoute | null> {
  try {
    // Public OSRM demo server (free, no key needed)
    const url = `https://router.project-osrm.org/route/v1/driving/${originLng},${originLat};${destLng},${destLat}?overview=full&steps=true&geometries=geojson`;

    const response = await fetch(url);
    if (!response.ok) throw new Error('OSRM request failed');

    const data = await response.json();
    if (!data.routes || data.routes.length === 0) return null;

    const route = data.routes[0];
    const leg = route.legs[0];

    // Parse steps
    const steps: RouteStep[] = leg.steps.map((step: any) => ({
      instruction: step.maneuver?.type === 'arrive'
        ? 'Arrive at destination'
        : `${capitalize(step.maneuver?.modifier || '')} onto ${step.name || 'road'}`,
      distance: step.distance,
      duration: step.duration,
      maneuver: step.maneuver,
      maneuverIcon: getManeuverIcon(step.maneuver?.type, step.maneuver?.modifier),
    }));

    // Parse geometry (GeoJSON coordinates are [lng, lat])
    const geometry: [number, number][] = (route.geometry?.coordinates || []).map(
      (coord: number[]) => [coord[1], coord[0]]
    );

    return {
      distance: route.distance,
      duration: route.duration,
      steps,
      geometry,
    };
  } catch (e) {
    console.warn('[Navigation] OSRM failed, using straight line:', e);

    // Fallback: straight line
    return null;
  }
}

/**
 * Snap a coarse fix to the nearest drivable road — DISPLAY-ONLY (G1-17).
 * Uses OSRM's /nearest service (same free stack as getOSRMRoute) so a 30-80m
 * fix reads as street truth on the map. Returns the snapped [lat, lng], or
 * null when the fix is more than ~500m from any road (the snap would be a
 * lie) or OSRM fails — callers MUST fall back to the raw fix. NEVER used for
 * the trail/history/evidence and never persisted: this is a presentation
 * transform; the accuracy circle and server data stay raw.
 */
export async function snapToRoad(lat: number, lng: number): Promise<[number, number] | null> {
  try {
    const url = `https://router.project-osrm.org/nearest/v1/driving/${lng},${lat}?number=1`;
    const response = await fetch(url);
    if (!response.ok) throw new Error('OSRM nearest request failed');
    const data = await response.json();
    if (data.code !== 'Ok' || !data.waypoints || data.waypoints.length === 0) return null;
    const waypoint = data.waypoints[0];
    const snapDistanceM = typeof waypoint.distance === 'number' ? waypoint.distance : Infinity;
    // OSRM always returns a waypoint; reject snaps that moved the fix a long
    // way (middle of a field / bad geocoding) — beyond ~500m it's a lie.
    if (snapDistanceM > 500) return null;
    const location: number[] = waypoint.location; // [lng, lat]
    if (!Array.isArray(location) || location.length < 2) return null;
    return [location[1], location[0]];
  } catch (e) {
    console.warn('[Navigation] snapToRoad failed:', e);
    return null;
  }
}

function capitalize(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1).replace(/-/g, ' ');
}

function getManeuverIcon(type: string, modifier?: string): string {
  if (type === 'arrive') return '🏁';
  if (type === 'depart') return '🚀';

  const modifierIcons: Record<string, string> = {
    'uturn': '🔄',
    'sharp right': '↗️',
    'right': '➡️',
    'slight right': '↗',
    'straight': '⬆️',
    'slight left': '↖',
    'left': '⬅️',
    'sharp left': '↖️',
  };

  return modifierIcons[modifier || ''] || '➡️';
}
