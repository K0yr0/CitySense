/** Small, non-interactive map with one marker (native). The web build uses incident-map.web.tsx. */
import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import { MapCanvas, type CanvasMarker } from '@/components/map-canvas';
import { Spacing } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';

export type IncidentMiniMapProps = {
  lon: number;
  lat: number;
  color: string;
  title?: string;
  height?: number;
};

const DELTA = 0.004; // ~400 m across

export function IncidentMiniMap({ lon, lat, color, title, height = 160 }: IncidentMiniMapProps) {
  const dark = useColorScheme() === 'dark';
  const coordinate = useMemo(() => ({ latitude: lat, longitude: lon }), [lat, lon]);
  const markers = useMemo<CanvasMarker[]>(
    () => [{ id: 'incident', coord: coordinate, color, title }],
    [coordinate, color, title],
  );
  return (
    <View style={[styles.frame, { height }]} pointerEvents="none" accessibilityElementsHidden>
      <MapCanvas
        style={StyleSheet.absoluteFill}
        initialRegion={{ ...coordinate, latitudeDelta: DELTA, longitudeDelta: DELTA }}
        interactive={false}
        dark={dark}
        markers={markers}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: Spacing.three,
    overflow: 'hidden',
  },
});
