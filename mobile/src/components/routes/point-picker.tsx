/**
 * Native start/end picker: tap the map to place the start, then the end; both pins are draggable.
 * Web uses point-picker.web.tsx (coordinate fields instead of a map).
 */
import { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import MapView, { Marker, Polyline, type MapPressEvent, type MarkerDragStartEndEvent } from 'react-native-maps';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { routesText } from '@/i18n/routes';
import type { LonLat } from '@/lib/api';
import { toLatLng, toLonLat, WARSAW_REGION, type LatLng } from '@/lib/geo';
import { useText } from '@/lib/i18n';

export type PointPickerProps = {
  start: LonLat | null;
  end: LonLat | null;
  onChange: (start: LonLat | null, end: LonLat | null) => void;
  /** Takes a fresh GPS fix (asks for permission); null if unavailable. */
  locate: () => Promise<LatLng | null>;
};

type Which = 'start' | 'end';

export function PointPicker({ start, end, onChange, locate }: PointPickerProps) {
  const theme = useTheme();
  const s = useText(routesText);
  const ref = useRef<MapView>(null);
  const [which, setWhich] = useState<Which>(start ? 'end' : 'start');
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  const place = (point: LonLat, target: Which) => {
    if (target === 'start') {
      onChange(point, end);
      if (!end) setWhich('end');
    } else {
      onChange(start, point);
    }
  };

  const onMapPress = (e: MapPressEvent) => place(toLonLat(e.nativeEvent.coordinate), which);

  const onDragEnd = (target: Which) => (e: MarkerDragStartEndEvent) =>
    target === 'start' ? onChange(toLonLat(e.nativeEvent.coordinate), end) : onChange(start, toLonLat(e.nativeEvent.coordinate));

  const startFromMyLocation = async () => {
    setLocating(true);
    setLocError(null);
    try {
      const here = await locate();
      if (!here) {
        setLocError(s.locationFailed);
        return;
      }
      place(toLonLat(here), 'start');
      ref.current?.animateToRegion({ ...here, latitudeDelta: 0.02, longitudeDelta: 0.02 }, 400);
    } finally {
      setLocating(false);
    }
  };

  const initial = start
    ? { ...toLatLng(start), latitudeDelta: 0.03, longitudeDelta: 0.03 }
    : WARSAW_REGION;

  return (
    <View style={styles.wrap}>
      <View style={styles.chips}>
        {(['start', 'end'] as const).map((w) => {
          const active = which === w;
          const set = w === 'start' ? !!start : !!end;
          return (
            <Pressable
              key={w}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              onPress={() => setWhich(w)}
              style={[
                styles.chip,
                { borderColor: active ? theme.tint : theme.backgroundSelected },
                active && { backgroundColor: theme.backgroundSelected },
              ]}>
              <ThemedText type="small" style={active ? { color: theme.tint } : undefined}>
                {w === 'start' ? `🔵 ${s.start}` : `⚫ ${s.end}`}
                {set ? ' ✓' : ''}
              </ThemedText>
            </Pressable>
          );
        })}
      </View>
      <ThemedText type="small" themeColor="textSecondary">
        {which === 'start' ? s.tapForStart : s.tapForEnd} {s.dragHint}
      </ThemedText>

      <MapView
        ref={ref}
        style={styles.map}
        initialRegion={initial}
        onPress={onMapPress}
        showsUserLocation
        showsMyLocationButton={false}
        toolbarEnabled={false}
        pitchEnabled={false}>
        {start && end && (
          <Polyline
            coordinates={[toLatLng(start), toLatLng(end)]}
            strokeColor="rgba(128,128,128,0.8)"
            strokeWidth={2}
            lineDashPattern={[6, 6]}
          />
        )}
        {start && (
          <Marker
            coordinate={toLatLng(start)}
            title={s.start}
            pinColor="#1A73E8"
            draggable
            onDragEnd={onDragEnd('start')}
          />
        )}
        {end && (
          <Marker coordinate={toLatLng(end)} title={s.end} pinColor="#202124" draggable onDragEnd={onDragEnd('end')} />
        )}
      </MapView>

      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          onPress={startFromMyLocation}
          disabled={locating}
          style={({ pressed }) => [styles.outline, { borderColor: theme.tint }, pressed && styles.pressed]}>
          {locating ? (
            <ActivityIndicator size="small" color={theme.tint} />
          ) : (
            <ThemedText type="smallBold" style={{ color: theme.tint }}>
              {s.useMyLocation}
            </ThemedText>
          )}
        </Pressable>
        {(start || end) && (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              onChange(null, null);
              setWhich('start');
            }}
            style={({ pressed }) => [styles.outline, { borderColor: theme.backgroundSelected }, pressed && styles.pressed]}>
            <ThemedText type="small" themeColor="textSecondary">
              {s.reset}
            </ThemedText>
          </Pressable>
        )}
      </View>
      {locError && (
        <ThemedText type="small" style={{ color: theme.danger }}>
          {locError}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing.two },
  chips: { flexDirection: 'row', gap: Spacing.two },
  chip: { borderWidth: 1, borderRadius: Spacing.four, paddingVertical: Spacing.one, paddingHorizontal: Spacing.three },
  map: { width: '100%', height: 320, borderRadius: 16, overflow: 'hidden' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  outline: {
    borderWidth: 1,
    borderRadius: Spacing.three,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    minHeight: 40,
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
});
