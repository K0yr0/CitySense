import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import { MapCanvas, type CanvasCircle, type CanvasMarker } from '@/components/map-canvas';
import { useColorScheme } from '@/hooks/use-color-scheme';
import type { LatLng } from '@/lib/geo';

type Props = { coords: LatLng; accuracy: number | null };

const DELTA = 0.003;

/** Small, non-interactive map with the report's pin (iOS / Android). */
export function LocationPreview({ coords, accuracy }: Props) {
  const dark = useColorScheme() === 'dark';
  const markers = useMemo<CanvasMarker[]>(() => [{ id: 'report', coord: coords, color: '#D93025' }], [coords]);
  const circles = useMemo<CanvasCircle[]>(
    () =>
      accuracy != null && accuracy > 0
        ? [
            {
              id: 'accuracy',
              center: coords,
              radius: accuracy,
              strokeColor: 'rgba(32, 138, 239, 0.6)',
              fillColor: 'rgba(32, 138, 239, 0.15)',
            },
          ]
        : [],
    [coords, accuracy],
  );
  return (
    <View style={styles.frame} pointerEvents="none">
      <MapCanvas
        // A new position re-centres the still map.
        key={`${coords.latitude.toFixed(5)},${coords.longitude.toFixed(5)}`}
        style={StyleSheet.absoluteFill}
        initialRegion={{ ...coords, latitudeDelta: DELTA, longitudeDelta: DELTA }}
        interactive={false}
        dark={dark}
        markers={markers}
        circles={circles}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    height: 140,
    borderRadius: 12,
    overflow: 'hidden',
  },
});
