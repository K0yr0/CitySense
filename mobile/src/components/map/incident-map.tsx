/**
 * Native map (iOS / Android, works in Expo Go: default provider, no API key).
 * Road health is drawn only as colours; incidents are coloured pins; no sensor data.
 * Web uses incident-map.web.tsx instead (react-native-maps has no web support).
 */
import { memo, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Circle, Marker, Polyline } from 'react-native-maps';

import type { PublicIncident } from '@/lib/api';
import { incidentColor } from '@/lib/labels';

import type { IncidentMapProps, MapSegment, UserPosition } from './types';

const USER_BLUE = '#1A73E8';

const SegmentLayer = memo(function SegmentLayer({ segments }: { segments: MapSegment[] }) {
  return segments.map((s) => (
    <Polyline
      key={s.key}
      coordinates={s.coords}
      strokeColor={s.color}
      strokeWidth={s.width}
      lineCap="round"
      zIndex={1}
    />
  ));
});

const IncidentLayer = memo(function IncidentLayer({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: PublicIncident[];
  selectedId: number | null;
  onSelect: (incident: PublicIncident) => void;
}) {
  return incidents.map((i) => {
    const color = incidentColor(i);
    return (
      <Marker
        // pinColor is applied at creation on some platforms, so a colour change re-creates the pin.
        key={`${i.id}-${color}`}
        identifier={String(i.id)}
        coordinate={{ latitude: i.lat, longitude: i.lon }}
        pinColor={color}
        tracksViewChanges={false}
        stopPropagation
        zIndex={i.id === selectedId ? 100 : 10}
        onPress={() => onSelect(i)}
      />
    );
  });
});

function UserLayer({ user }: { user: UserPosition }) {
  // Custom marker views need a few frames to render before tracking can be turned off
  // (otherwise Android may show an empty marker).
  const [tracking, setTracking] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setTracking(false), 1000);
    return () => clearTimeout(t);
  }, []);

  return (
    <>
      {user.accuracy != null && user.accuracy > 0 && (
        <Circle
          center={user.coords}
          radius={user.accuracy}
          fillColor="rgba(26,115,232,0.15)"
          strokeColor="rgba(26,115,232,0.45)"
          strokeWidth={1}
          zIndex={50}
        />
      )}
      <Marker
        coordinate={user.coords}
        anchor={{ x: 0.5, y: 0.5 }}
        tracksViewChanges={tracking}
        zIndex={200}
        tappable={false}>
        <View style={styles.dotHalo}>
          <View style={styles.dot} />
        </View>
      </Marker>
    </>
  );
}

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
  const mapRef = useRef<MapView>(null);

  useImperativeHandle(ref, () => ({
    animateTo: (region) => mapRef.current?.animateToRegion(region, 600),
  }));

  return (
    <MapView
      ref={mapRef}
      style={StyleSheet.absoluteFill}
      initialRegion={initialRegion}
      onRegionChangeComplete={(region) => onRegionChangeComplete(region)}
      onPress={() => onSelectIncident(null)}
      userInterfaceStyle={dark ? 'dark' : 'light'}
      mapPadding={{ top: topInset, bottom: bottomInset, left: 0, right: 0 }}
      showsCompass={false}
      showsPointsOfInterests={false}
      toolbarEnabled={false}
      pitchEnabled={false}
      rotateEnabled={false}>
      {showSegments && <SegmentLayer segments={segments} />}
      {showIncidents && (
        <IncidentLayer incidents={incidents} selectedId={selectedId} onSelect={onSelectIncident} />
      )}
      {user && <UserLayer user={user} />}
    </MapView>
  );
}

const styles = StyleSheet.create({
  dotHalo: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'white',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 3,
  },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: USER_BLUE,
  },
});
