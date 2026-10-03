/**
 * Loads what the map shows for the visible region: open incidents and measured segments
 * (as colour classes only). Debounced, padded by 20 %, stale responses are dropped.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import { getIncidents, getSegments, type MobileSegment, type PublicIncident } from '@/lib/api';
import { bboxOf, toLatLng, WARSAW_REGION, type Region } from '@/lib/geo';
import { healthColor } from '@/lib/labels';

import type { MapSegment } from './types';

const DEBOUNCE_MS = 400;
/** Above this latitudeDelta (~9 km tall) road colours are not loaded: too many lines. */
export const MAX_SEGMENT_DELTA = 0.08;
/** Fewer polylines than the API limit keeps the map smooth on mid-range phones. */
const SEGMENT_CAP = 3000;
const PAD = 0.2;

function toMapSegment(s: MobileSegment): MapSegment {
  return {
    key: `${s.mode}-${s.id}`,
    color: healthColor(s.health_class),
    width: s.mode === 'tram' ? 3 : 4,
    coords: s.path.map(toLatLng),
  };
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export type MapData = {
  region: Region;
  setRegion: (region: Region) => void;
  incidents: PublicIncident[];
  segments: MapSegment[];
  /** True when zoomed out too far for road colours. */
  zoomedOut: boolean;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useMapData(initialRegion: Region = WARSAW_REGION): MapData {
  const [region, setRegion] = useState<Region>(initialRegion);
  const [incidents, setIncidents] = useState<PublicIncident[]>([]);
  const [rawSegments, setRawSegments] = useState<MobileSegment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const zoomedOut = region.latitudeDelta > MAX_SEGMENT_DELTA;

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      const bbox = bboxOf(region, PAD);
      const [inc, seg] = await Promise.allSettled([
        getIncidents(bbox),
        zoomedOut ? Promise.resolve(null) : getSegments(bbox, undefined, SEGMENT_CAP),
      ]);
      if (cancelled) return;
      if (inc.status === 'fulfilled') setIncidents(inc.value);
      if (seg.status === 'fulfilled' && seg.value) setRawSegments(seg.value);
      const failed = [inc, seg].find((r) => r.status === 'rejected');
      setError(failed ? message((failed as PromiseRejectedResult).reason) : null);
      setLoading(false);
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [region, zoomedOut, reloadKey]);

  // Converted once per response, so the polyline layer only re-renders when data changes.
  const segments = useMemo(() => rawSegments.map(toMapSegment), [rawSegments]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);

  return { region, setRegion, incidents, segments, zoomedOut, loading, error, reload };
}
