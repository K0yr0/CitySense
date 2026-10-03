/**
 * Pure helpers for favourite routes (M5): where the user is along a route path,
 * which warnings are still ahead, and the colour proportions of the summary bar.
 * Only colour classes are used; no raw health numbers ever reach the UI.
 */
import type { IconName } from '@/components/icon';
import type { FavoriteRoute, HealthClass, LonLat, Mode, RouteQuality, RouteWarning } from '@/lib/api';
import { routesText } from '@/i18n/routes';
import type { LatLng } from '@/lib/geo';
import { text } from '@/lib/i18n';
import { HEALTH_CLASSES } from '@/lib/labels';

/** The user counts as "on the route" within this distance of the path. */
export const ON_ROUTE_M = 50;

/** "Bad road ahead" banner for the nearest warning ahead within this distance. */
export const AHEAD_ALERT_M = 500;

const M_PER_DEG_LAT = 110_574;

function metresPerDegLon(lat: number): number {
  return 111_320 * Math.cos((lat * Math.PI) / 180);
}

/** Local planar coordinates in metres around `lat0` (good enough within a city). */
function toXY([lon, lat]: LonLat, lat0: number): [number, number] {
  return [lon * metresPerDegLon(lat0), lat * M_PER_DEG_LAT];
}

/** Cumulative distance (m) at every vertex of the path; [0, d1, d1+d2, ...]. */
export function cumulativeDistances(path: LonLat[]): number[] {
  if (path.length === 0) return [];
  const lat0 = path[0][1];
  const out = [0];
  for (let i = 1; i < path.length; i++) {
    const [x1, y1] = toXY(path[i - 1], lat0);
    const [x2, y2] = toXY(path[i], lat0);
    out.push(out[i - 1] + Math.hypot(x2 - x1, y2 - y1));
  }
  return out;
}

export type PathPosition = {
  /** Distance from the path (m). */
  offsetM: number;
  /** Distance along the path from its start (m) of the closest point. */
  alongM: number;
};

/** Project a point onto the path: closest point on any path piece and its distance along. */
export function projectOnPath(path: LonLat[], point: LatLng, cum = cumulativeDistances(path)): PathPosition | null {
  if (path.length === 0) return null;
  const lat0 = path[0][1];
  const [px, py] = toXY([point.longitude, point.latitude], lat0);
  if (path.length === 1) {
    const [x, y] = toXY(path[0], lat0);
    return { offsetM: Math.hypot(px - x, py - y), alongM: 0 };
  }
  let best: PathPosition | null = null;
  for (let i = 1; i < path.length; i++) {
    const [ax, ay] = toXY(path[i - 1], lat0);
    const [bx, by] = toXY(path[i], lat0);
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;
    const t = len2 === 0 ? 0 : Math.min(1, Math.max(0, ((px - ax) * dx + (py - ay) * dy) / len2));
    const cx = ax + t * dx;
    const cy = ay + t * dy;
    const offset = Math.hypot(px - cx, py - cy);
    if (!best || offset < best.offsetM) {
      best = { offsetM: offset, alongM: cum[i - 1] + t * Math.sqrt(len2) };
    }
  }
  return best;
}

export type AheadInfo = {
  /** The user's position along the path (m from the start). */
  userAlongM: number;
  /** Warnings with distance_along_m greater than the user's position. */
  ahead: RouteWarning[];
  /** The nearest warning ahead if it is within AHEAD_ALERT_M. */
  alert: { warning: RouteWarning; inM: number } | null;
};

/**
 * If the user is within ON_ROUTE_M of the path, which warnings are still ahead of them
 * (assuming they travel in the path's direction, start → end). Null when off the route.
 */
export function aheadOfUser(path: LonLat[], warnings: RouteWarning[], user: LatLng | null): AheadInfo | null {
  if (!user || path.length < 2) return null;
  const pos = projectOnPath(path, user);
  if (!pos || pos.offsetM > ON_ROUTE_M) return null;
  const ahead = warnings
    .filter((w) => w.distance_along_m > pos.alongM)
    .sort((a, b) => a.distance_along_m - b.distance_along_m);
  const first = ahead[0];
  const inM = first ? first.distance_along_m - pos.alongM : Infinity;
  return {
    userAlongM: pos.alongM,
    ahead,
    alert: first && inM <= AHEAD_ALERT_M ? { warning: first, inM } : null,
  };
}

export type HealthShare = { cls: HealthClass; metres: number; fraction: number };

/** Metres per colour class as fractions of the total (in HEALTH_CLASSES order). */
export function healthShares(summary: RouteQuality['summary']): { total: number; shares: HealthShare[] } {
  const metres: Record<HealthClass, number> = {
    good: Math.max(0, summary.good_m || 0),
    fair: Math.max(0, summary.fair_m || 0),
    poor: Math.max(0, summary.poor_m || 0),
    unknown: Math.max(0, summary.unknown_m || 0),
  };
  const total = HEALTH_CLASSES.reduce((sum, cls) => sum + metres[cls], 0);
  return {
    total,
    shares: HEALTH_CLASSES.map((cls) => ({ cls, metres: metres[cls], fraction: total > 0 ? metres[cls] / total : 0 })),
  };
}

/** "Tram 17" / "Bus 175" for a line number, or "Tram line" / "Bus line" without one. */
export function lineLabel(mode: Mode | null | undefined, line?: string | null): string {
  const t = text(routesText);
  if (line) return mode === 'tram' ? t.tramLine(line) : t.busLine(line);
  return mode === 'tram' ? t.tramLineGeneric : t.busLineGeneric;
}

/** Short description of a route: "Tram 17", "Bus 175", "Start → end". */
export function describeRoute(route: FavoriteRoute): string {
  const t = text(routesText);
  if (route.kind === 'line') return route.line ? lineLabel(route.mode, route.line) : t.lineGeneric;
  return t.startToEnd;
}

/** Icon for a route: tram / bus for a line, a pin for start → end. */
export function routeIcon(route: FavoriteRoute): IconName {
  if (route.kind === 'line') return route.mode === 'tram' ? 'tram' : 'bus';
  return 'pin';
}

/** Region that contains every point, with a margin. */
export function regionFor(points: LonLat[]): {
  latitude: number;
  longitude: number;
  latitudeDelta: number;
  longitudeDelta: number;
} | null {
  if (points.length === 0) return null;
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  for (const [lon, lat] of points) {
    minLon = Math.min(minLon, lon);
    maxLon = Math.max(maxLon, lon);
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
  }
  return {
    latitude: (minLat + maxLat) / 2,
    longitude: (minLon + maxLon) / 2,
    latitudeDelta: Math.max(0.005, (maxLat - minLat) * 1.4),
    longitudeDelta: Math.max(0.005, (maxLon - minLon) * 1.4),
  };
}
