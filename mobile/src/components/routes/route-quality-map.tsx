/**
 * Native map of a route's quality: the path in thin grey, measured segments in their colour class,
 * warnings as pins. Web uses route-quality-map.web.tsx.
 */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { StyleSheet } from 'react-native';

import {
  MapCanvas,
  type CanvasMarker,
  type CanvasPolyline,
  type MapCanvasHandle,
} from '@/components/map-canvas';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { routesText } from '@/i18n/routes';
import type { RouteQuality, RouteWarning } from '@/lib/api';
import { toLatLng, WARSAW_REGION, type LatLng } from '@/lib/geo';
import { useText } from '@/lib/i18n';
import { healthColor } from '@/lib/labels';

import { regionFor } from './route-geometry';

export const ROUTE_MAP_SUPPORTED = true;

type Props = {
  quality: RouteQuality;
  /** The warning the "Bad road ahead" banner points at (drawn larger). */
  highlighted?: RouteWarning | null;
  onWarningPress?: (warning: RouteWarning) => void;
  /** The user's position, drawn as a blue dot. */
  user?: LatLng | null;
  height?: number;
};

const EDGE = { top: 48, right: 48, bottom: 48, left: 48 };

export function RouteQualityMap({ quality, highlighted, onWarningPress, user, height = 320 }: Props) {
  const s = useText(routesText);
  const dark = useColorScheme() === 'dark';
  const ref = useRef<MapCanvasHandle>(null);
  const coords = useMemo(() => quality.path.map(toLatLng), [quality.path]);
  const initialRegion = useMemo(() => regionFor(quality.path) ?? WARSAW_REGION, [quality.path]);

  const fit = useCallback(() => {
    if (coords.length >= 2) ref.current?.fitTo(coords, EDGE);
  }, [coords]);

  // Re-fit after a refresh changed the path (the first fit happens in onReady).
  useEffect(() => {
    fit();
  }, [fit]);

  const polylines = useMemo<CanvasPolyline[]>(
    () => [
      ...(coords.length >= 2
        ? [{ id: 'path', coords, color: 'rgba(128,128,128,0.75)', width: 3, zIndex: 1 }]
        : []),
      ...quality.segments.map((seg) => ({
        id: `seg-${seg.id}`,
        coords: seg.path.map(toLatLng),
        color: healthColor(seg.health_class),
        width: 6,
        zIndex: 2,
      })),
    ],
    [coords, quality.segments],
  );

  const { route, warnings } = quality;
  const markers = useMemo<CanvasMarker[]>(() => {
    const out: CanvasMarker[] = [];
    if (route.kind === 'points' && route.start)
      out.push({ id: 'start', coord: toLatLng(route.start), title: s.start, color: '#1A73E8' });
    if (route.kind === 'points' && route.end)
      out.push({ id: 'end', coord: toLatLng(route.end), title: s.end, color: '#202124' });
    warnings.forEach((w, i) =>
      out.push({
        id: `warn-${i}`,
        coord: { latitude: w.lat, longitude: w.lon },
        title: w.kind === 'incident' ? s.reportedProblem : s.badRoad,
        description: w.kind === 'incident' ? s.tapForDetails(w.message) : w.message,
        color: w.kind === 'incident' ? '#D93025' : '#F29900',
        zIndex: highlighted === w ? 10 : 5,
      }),
    );
    if (user) out.push({ id: 'user', coord: user, color: '#1A73E8', kind: 'dot', zIndex: 200 });
    return out;
  }, [route, warnings, highlighted, user, s]);

  return (
    <MapCanvas
      ref={ref}
      style={[styles.map, { height }]}
      initialRegion={initialRegion}
      dark={dark}
      polylines={polylines}
      markers={markers}
      onReady={fit}
      onCalloutPress={(id) => {
        const w = id.startsWith('warn-') ? warnings[Number(id.slice(5))] : undefined;
        if (w) onWarningPress?.(w);
      }}
    />
  );
}

const styles = StyleSheet.create({
  map: { width: '100%', borderRadius: 16, overflow: 'hidden' },
});
