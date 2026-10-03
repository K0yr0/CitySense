/**
 * Native map (iOS: Apple Maps, Android: Leaflet/OpenStreetMap; both via MapCanvas, no API key).
 * Road health is drawn only as colours; incidents are coloured pins; no sensor data.
 * Web uses incident-map.web.tsx instead.
 */
import { useImperativeHandle, useMemo, useRef } from 'react';
import { StyleSheet } from 'react-native';

import {
  MapCanvas,
  type CanvasCircle,
  type CanvasMarker,
  type CanvasPolyline,
  type MapCanvasHandle,
} from '@/components/map-canvas';
import { incidentColor } from '@/lib/labels';

import type { IncidentMapProps } from './types';

const USER_BLUE = '#1A73E8';
const USER_ID = 'user';

export function IncidentMap({
  ref,
  initialRegion,
  segments,
  incidents,
  showSegments,
  showIncidents,
  selectedId,
  user,
  dark,
  topInset,
  bottomInset,
  onRegionChangeComplete,
  onSelectIncident,
}: IncidentMapProps) {
  const mapRef = useRef<MapCanvasHandle>(null);

  useImperativeHandle(ref, () => ({
    animateTo: (region) => mapRef.current?.animateTo(region),
  }));

  const polylines = useMemo<CanvasPolyline[]>(
    () => (showSegments ? segments.map((s) => ({ id: s.key, coords: s.coords, color: s.color, width: s.width })) : []),
    [segments, showSegments],
  );

  const markers = useMemo<CanvasMarker[]>(() => {
    const pins: CanvasMarker[] = showIncidents
      ? incidents.map((i) => ({
          id: String(i.id),
          coord: { latitude: i.lat, longitude: i.lon },
          color: incidentColor(i),
          zIndex: i.id === selectedId ? 100 : 10,
        }))
      : [];
    if (user) pins.push({ id: USER_ID, coord: user.coords, color: USER_BLUE, kind: 'dot', zIndex: 200 });
    return pins;
  }, [incidents, showIncidents, selectedId, user]);

  const circles = useMemo<CanvasCircle[]>(
    () =>
      user?.accuracy != null && user.accuracy > 0
        ? [
            {
              id: 'accuracy',
              center: user.coords,
              radius: user.accuracy,
              fillColor: 'rgba(26,115,232,0.15)',
              strokeColor: 'rgba(26,115,232,0.45)',
            },
          ]
        : [],
    [user],
  );

  return (
    <MapCanvas
      ref={mapRef}
      style={StyleSheet.absoluteFill}
      initialRegion={initialRegion}
      dark={dark}
      padding={{ top: topInset, bottom: bottomInset, left: 0, right: 0 }}
      polylines={polylines}
      markers={markers}
      circles={circles}
      onRegionChangeComplete={onRegionChangeComplete}
      onPress={() => onSelectIncident(null)}
      onMarkerPress={(id) => {
        const incident = incidents.find((i) => String(i.id) === id);
        if (incident) onSelectIncident(incident);
      }}
    />
  );
}
