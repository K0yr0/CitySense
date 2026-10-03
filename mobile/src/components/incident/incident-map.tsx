/** Small, non-interactive map with one marker (native). The web build uses incident-map.web.tsx. */
import { StyleSheet, View } from 'react-native';
import MapView, { Marker } from 'react-native-maps';

import { Spacing } from '@/constants/theme';

export type IncidentMiniMapProps = {
  lon: number;
  lat: number;
  color: string;
  title?: string;
  height?: number;
};

const DELTA = 0.004; // ~400 m across

export function IncidentMiniMap({ lon, lat, color, title, height = 160 }: IncidentMiniMapProps) {
  const coordinate = { latitude: lat, longitude: lon };
  return (
    <View style={[styles.frame, { height }]} pointerEvents="none" accessibilityElementsHidden>
      <MapView
        style={StyleSheet.absoluteFill}
        initialRegion={{ ...coordinate, latitudeDelta: DELTA, longitudeDelta: DELTA }}
        scrollEnabled={false}
        zoomEnabled={false}
        rotateEnabled={false}
        pitchEnabled={false}
        toolbarEnabled={false}
        liteMode
        showsPointsOfInterests={false}>
        <Marker coordinate={coordinate} pinColor={color} title={title} />
      </MapView>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: {
    borderRadius: Spacing.three,
    overflow: 'hidden',
  },
});
