/**
 * MapCanvas on iOS (and the default build): react-native-maps with Apple Maps, no API key.
 * Android uses map-canvas.android.tsx (Leaflet). Web never imports this (screens have .web.tsx).
 */
import { memo, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import MapView, { Circle, Marker, Polyline } from 'react-native-maps';

import type { CanvasCircle, CanvasMarker, CanvasPolyline, MapCanvasProps } from './types';
import { NO_PADDING } from './types';

const DEFAULT_FIT_PADDING = { top: 60, bottom: 60, left: 40, right: 40 };

const Lines = memo(function Lines({ polylines }: { polylines: CanvasPolyline[] }) {
  return polylines.map((p) => (
    <Polyline
      key={p.id}
      coordinates={p.coords}
      strokeColor={p.color}
      strokeWidth={p.width}
      lineCap="round"
      lineDashPattern={p.dash}
      zIndex={p.zIndex ?? 1}
    />
  ));
});

const Circles = memo(function Circles({ circles }: { circles: CanvasCircle[] }) {
  return circles.map((c) => (
    <Circle
      key={c.id}
      center={c.center}
      radius={c.radius}
      fillColor={c.fillColor}
      strokeColor={c.strokeColor}
      strokeWidth={c.strokeWidth ?? 1}
      zIndex={50}
    />
  ));
});

/** The user's position: a blue dot with a white ring. */
function Dot({ marker }: { marker: CanvasMarker }) {
  // Custom marker views need a few frames to render before tracking can be turned off.
  const [tracking, setTracking] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setTracking(false), 1000);
    return () => clearTimeout(t);
  }, []);
  return (
    <Marker
      coordinate={marker.coord}
      anchor={{ x: 0.5, y: 0.5 }}
      tracksViewChanges={tracking}
      zIndex={marker.zIndex ?? 200}
      tappable={false}>
      <View style={styles.dotHalo}>
        <View style={[styles.dot, { backgroundColor: marker.color }]} />
      </View>
    </Marker>
  );
}

export function MapCanvas({
  ref,
  style,
  initialRegion,
  interactive = true,
  dark = false,
  padding = NO_PADDING,
  polylines = [],
  circles = [],
  markers = [],
  onPress,
  onMarkerPress,
  onCalloutPress,
  onMarkerDragEnd,
  onRegionChangeComplete,
  onReady,
}: MapCanvasProps) {
  const mapRef = useRef<MapView>(null);

  useImperativeHandle(ref, () => ({
    animateTo: (region) => mapRef.current?.animateToRegion(region, 600),
    fitTo: (coords, pad) => {
      if (coords.length) mapRef.current?.fitToCoordinates(coords, { edgePadding: pad ?? DEFAULT_FIT_PADDING, animated: false });
    },
  }));

  return (
    <MapView
      ref={mapRef}
      style={style}
      initialRegion={initialRegion}
      onRegionChangeComplete={(region) => onRegionChangeComplete?.(region)}
      onPress={(e) => onPress?.(e.nativeEvent.coordinate)}
      onMapReady={onReady}
      userInterfaceStyle={dark ? 'dark' : 'light'}
      mapPadding={padding}
      scrollEnabled={interactive}
      zoomEnabled={interactive}
      pitchEnabled={false}
      rotateEnabled={false}
      showsCompass={false}
      showsPointsOfInterests={false}
      toolbarEnabled={false}>
      <Lines polylines={polylines} />
      <Circles circles={circles} />
      {markers.map((m) =>
        m.kind === 'dot' ? (
          <Dot key={m.id} marker={m} />
        ) : (
          <Marker
            // pinColor is applied at creation on some platforms, so a colour change re-creates the pin.
            key={`${m.id}-${m.color}`}
            identifier={m.id}
            coordinate={m.coord}
            pinColor={m.color}
            title={m.title}
            description={m.description}
            draggable={m.draggable}
            tracksViewChanges={false}
            stopPropagation
            zIndex={m.zIndex ?? 10}
            onPress={() => onMarkerPress?.(m.id)}
            onCalloutPress={() => onCalloutPress?.(m.id)}
            onDragEnd={(e) => onMarkerDragEnd?.(m.id, e.nativeEvent.coordinate)}
          />
        ),
      )}
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
  dot: { width: 14, height: 14, borderRadius: 7 },
});
