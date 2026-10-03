/**
 * Native map of a route's quality: the path in thin grey, measured segments in their colour class,
 * warnings as pins. Web uses route-quality-map.web.tsx (react-native-maps has no web support).
 */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { StyleSheet } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';

import type { RouteQuality, RouteWarning } from '@/lib/api';
import { toLatLng, WARSAW_REGION } from '@/lib/geo';
import { healthColor } from '@/lib/labels';

import { regionFor } from './route-geometry';

export const ROUTE_MAP_SUPPORTED = true;

type Props = {
  quality: RouteQuality;
  /** The warning the "İleride kötü yol" banner points at (drawn larger). */
  highlighted?: RouteWarning | null;
  onWarningPress?: (warning: RouteWarning) => void;
  height?: number;
};

const EDGE = { top: 48, right: 48, bottom: 48, left: 48 };

export function RouteQualityMap({ quality, highlighted, onWarningPress, height = 320 }: Props) {
  const ref = useRef<MapView>(null);
  const coords = useMemo(() => quality.path.map(toLatLng), [quality.path]);
  const initialRegion = useMemo(() => regionFor(quality.path) ?? WARSAW_REGION, [quality.path]);

  const fit = useCallback(() => {
    if (coords.length >= 2) ref.current?.fitToCoordinates(coords, { edgePadding: EDGE, animated: false });
  }, [coords]);

  // Re-fit after a refresh changed the path (the first fit happens in onMapReady).
  useEffect(() => {
    fit();
  }, [fit]);

  const { route } = quality;

  return (
    <MapView
      ref={ref}
      style={[styles.map, { height }]}
      initialRegion={initialRegion}
      onMapReady={fit}
      showsUserLocation
      showsMyLocationButton={false}
      toolbarEnabled={false}
      pitchEnabled={false}>
      {coords.length >= 2 && (
        <Polyline coordinates={coords} strokeColor="rgba(128,128,128,0.75)" strokeWidth={3} zIndex={1} />
      )}
      {quality.segments.map((s) => (
        <Polyline
          key={`seg-${s.id}`}
          coordinates={s.path.map(toLatLng)}
          strokeColor={healthColor(s.health_class)}
          strokeWidth={6}
          zIndex={2}
        />
      ))}
      {route.kind === 'points' && route.start && (
        <Marker coordinate={toLatLng(route.start)} title="Başlangıç" pinColor="#1A73E8" />
      )}
      {route.kind === 'points' && route.end && (
        <Marker coordinate={toLatLng(route.end)} title="Bitiş" pinColor="#202124" />
      )}
      {quality.warnings.map((w, i) => {
        const isHighlighted = highlighted === w;
        return (
          <Marker
            key={`warn-${w.kind}-${w.incident_id ?? 'p'}-${i}`}
            coordinate={{ latitude: w.lat, longitude: w.lon }}
            title={w.kind === 'incident' ? '⚠️ Bildirilmiş sorun' : '⚠️ Kötü yol'}
            description={w.kind === 'incident' ? `${w.message} · Ayrıntı için dokun` : w.message}
            pinColor={w.kind === 'incident' ? '#D93025' : '#F29900'}
            zIndex={isHighlighted ? 10 : 5}
            onCalloutPress={() => onWarningPress?.(w)}
          />
        );
      })}
    </MapView>
  );
}

const styles = StyleSheet.create({
  map: { width: '100%', borderRadius: 16, overflow: 'hidden' },
});
