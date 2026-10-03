/**
 * Native start/end picker (MapCanvas): tap the map to place the start, then the end; both pins are draggable.
 * Web uses point-picker.web.tsx (coordinate fields instead of a map).
 */
import { useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { MapCanvas, type CanvasMarker, type CanvasPolyline, type MapCanvasHandle } from '@/components/map-canvas';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
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
  const dark = useColorScheme() === 'dark';
  const ref = useRef<MapCanvasHandle>(null);
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

  const onMapPress = (coord: LatLng) => place(toLonLat(coord), which);

  const onDragEnd = (id: string, coord: LatLng) =>
    id === 'start' ? onChange(toLonLat(coord), end) : onChange(start, toLonLat(coord));

  const polylines = useMemo<CanvasPolyline[]>(
    () =>
      start && end
        ? [{ id: 'line', coords: [toLatLng(start), toLatLng(end)], color: 'rgba(128,128,128,0.8)', width: 2, dash: [6, 6] }]
        : [],
    [start, end],
  );
  const markers = useMemo<CanvasMarker[]>(() => {
    const out: CanvasMarker[] = [];
    if (start) out.push({ id: 'start', coord: toLatLng(start), title: s.start, color: '#1A73E8', draggable: true });
    if (end) out.push({ id: 'end', coord: toLatLng(end), title: s.end, color: '#202124', draggable: true });
    return out;
  }, [start, end, s]);

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
      ref.current?.animateTo({ ...here, latitudeDelta: 0.02, longitudeDelta: 0.02 });
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
              <View style={styles.chipInner}>
                <View style={[styles.chipDot, { backgroundColor: w === 'start' ? '#1A73E8' : '#202124' }]} />
                <ThemedText type="small" style={active ? { color: theme.tint } : undefined}>
                  {w === 'start' ? s.start : s.end}
                  {set ? ' ✓' : ''}
                </ThemedText>
              </View>
            </Pressable>
          );
        })}
      </View>
      <ThemedText type="small" themeColor="textSecondary">
        {which === 'start' ? s.tapForStart : s.tapForEnd} {s.dragHint}
      </ThemedText>

      <MapCanvas
        ref={ref}
        style={styles.map}
        initialRegion={initial}
        dark={dark}
        polylines={polylines}
        markers={markers}
        onPress={onMapPress}
        onMarkerDragEnd={onDragEnd}
      />

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
  chipInner: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
  chipDot: { width: 10, height: 10, borderRadius: 5, borderWidth: 1, borderColor: '#ffffff' },
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
