/**
 * Web start/end picker: react-native-maps has no web support, so points are typed as
 * "enlem, boylam" (the format Google Maps copies) or taken from the browser's location.
 */
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { LonLat } from '@/lib/api';
import { toLonLat, type LatLng } from '@/lib/geo';

export type PointPickerProps = {
  start: LonLat | null;
  end: LonLat | null;
  onChange: (start: LonLat | null, end: LonLat | null) => void;
  locate: () => Promise<LatLng | null>;
};

/** "52.2297, 21.0122" → [lon, lat] */
function parseLatLon(text: string): LonLat | null {
  const m = text.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return [lon, lat];
}

function format(p: LonLat | null): string {
  return p ? `${p[1].toFixed(5)}, ${p[0].toFixed(5)}` : '';
}

export function PointPicker({ start, end, onChange, locate }: PointPickerProps) {
  const theme = useTheme();
  const [startText, setStartText] = useState(format(start));
  const [endText, setEndText] = useState(format(end));
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  const inputStyle = [styles.input, { color: theme.text, borderColor: theme.backgroundSelected }];

  const startFromMyLocation = async () => {
    setLocating(true);
    setLocError(null);
    try {
      const here = await locate();
      if (!here) {
        setLocError('Konum alınamadı. Tarayıcının konum iznini kontrol et.');
        return;
      }
      const p = toLonLat(here);
      setStartText(format(p));
      onChange(p, end);
    } finally {
      setLocating(false);
    }
  };

  return (
    <View style={styles.wrap}>
      <ThemedText type="small" themeColor="textSecondary">
        Harita web&apos;de kullanılamıyor. Noktaları &quot;enlem, boylam&quot; olarak yaz (ör. 52.22970, 21.01220).
      </ThemedText>
      <ThemedText type="smallBold">Başlangıç</ThemedText>
      <TextInput
        value={startText}
        onChangeText={(t) => {
          setStartText(t);
          onChange(parseLatLon(t), end);
        }}
        placeholder="52.22970, 21.01220"
        placeholderTextColor={theme.textSecondary}
        style={inputStyle}
      />
      <ThemedText type="smallBold">Bitiş</ThemedText>
      <TextInput
        value={endText}
        onChangeText={(t) => {
          setEndText(t);
          onChange(start, parseLatLon(t));
        }}
        placeholder="52.24000, 21.00000"
        placeholderTextColor={theme.textSecondary}
        style={inputStyle}
      />
      <Pressable
        accessibilityRole="button"
        onPress={startFromMyLocation}
        disabled={locating}
        style={({ pressed }) => [styles.outline, { borderColor: theme.tint }, pressed && styles.pressed]}>
        {locating ? (
          <ActivityIndicator size="small" color={theme.tint} />
        ) : (
          <ThemedText type="smallBold" style={{ color: theme.tint }}>
            📍 Konumumu başlangıç yap
          </ThemedText>
        )}
      </Pressable>
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
  input: { borderWidth: 1, borderRadius: Spacing.two, paddingHorizontal: Spacing.three, paddingVertical: Spacing.two, fontSize: 16 },
  outline: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderRadius: Spacing.three,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    minHeight: 40,
    justifyContent: 'center',
  },
  pressed: { opacity: 0.6 },
});
