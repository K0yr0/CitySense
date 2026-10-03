import { StyleSheet, View } from 'react-native';
import MapView, { Circle, Marker } from 'react-native-maps';

import type { LatLng } from '@/lib/geo';

type Props = { coords: LatLng; accuracy: number | null };

/** Small, non-interactive map with the report's pin (iOS / Android). */
export function LocationPreview({ coords, accuracy }: Props) {
  const delta = 0.003;
  return (
    <View style={styles.frame} pointerEvents="none">
      <MapView
        style={StyleSheet.absoluteFill}
        region={{ ...coords, latitudeDelta: delta, longitudeDelta: delta }}
        scrollEnabled={false}
        zoomEnabled={false}
        rotateEnabled={false}
        pitchEnabled={false}
        toolbarEnabled={false}
        liteMode
        showsPointsOfInterests={false}>
        {accuracy != null && accuracy > 0 ? (
          <Circle
            center={coords}
            radius={accuracy}
            strokeColor="rgba(32, 138, 239, 0.6)"
            fillColor="rgba(32, 138, 239, 0.15)"
          />
        ) : null}
        <Marker coordinate={coords} />
      </MapView>
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
