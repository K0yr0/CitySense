/** Small floating controls on the map: health legend, layer chips, locate button, banners. */
import { SymbolView } from 'expo-symbols';
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { HEALTH_CLASSES, HEALTH_COLORS, HEALTH_LABELS } from '@/lib/labels';

/** Road health legend: only colour classes, never numbers. */
export function HealthLegend() {
  const theme = useTheme();
  return (
    <View style={[styles.pill, styles.legend, { backgroundColor: theme.background }]}>
      {HEALTH_CLASSES.map((h) => (
        <View key={h} style={styles.legendItem}>
          <View style={[styles.swatch, { backgroundColor: HEALTH_COLORS[h] }]} />
          <ThemedText type="small">{HEALTH_LABELS[h]}</ThemedText>
        </View>
      ))}
    </View>
  );
}

export function Chip({ children, onPress, active = true }: { children: ReactNode; onPress?: () => void; active?: boolean }) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      accessibilityRole={onPress ? 'switch' : undefined}
      accessibilityState={onPress ? { checked: active } : undefined}
      style={({ pressed }) => [
        styles.pill,
        styles.chip,
        { backgroundColor: active ? theme.background : theme.backgroundElement },
        pressed && styles.pressed,
      ]}>
      <ThemedText type="small" themeColor={active ? 'text' : 'textSecondary'}>
        {children}
      </ThemedText>
    </Pressable>
  );
}

export function LocateButton({ onPress, busy, active }: { onPress: () => void; busy: boolean; active: boolean }) {
  const theme = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel="Anlık konum"
      style={({ pressed }) => [styles.locate, { backgroundColor: theme.background }, pressed && styles.pressed]}>
      {busy ? (
        <ActivityIndicator color={theme.tint} />
      ) : (
        <SymbolView
          name={{ ios: active ? 'location.fill' : 'location', android: 'my_location', web: 'my_location' }}
          tintColor={theme.tint}
          size={24}
        />
      )}
    </Pressable>
  );
}

/** Thin banner under the legend: hints, errors (with retry), loading. */
export function Banner({
  children,
  tone = 'info',
  actionLabel,
  onAction,
}: {
  children: ReactNode;
  tone?: 'info' | 'error';
  actionLabel?: string;
  onAction?: () => void;
}) {
  const theme = useTheme();
  return (
    <View style={[styles.pill, styles.banner, { backgroundColor: theme.background }]}>
      <ThemedText
        type="small"
        style={[styles.bannerText, tone === 'error' && { color: theme.danger }]}
        themeColor={tone === 'info' ? 'textSecondary' : undefined}>
        {children}
      </ThemedText>
      {actionLabel && onAction && (
        <Pressable onPress={onAction} hitSlop={8} style={({ pressed }) => pressed && styles.pressed}>
          <ThemedText type="smallBold" style={{ color: theme.tint }}>
            {actionLabel}
          </ThemedText>
        </Pressable>
      )}
    </View>
  );
}

const shadow = {
  shadowColor: '#000',
  shadowOpacity: 0.15,
  shadowRadius: 4,
  shadowOffset: { width: 0, height: 1 },
  elevation: 3,
} as const;

const styles = StyleSheet.create({
  pill: {
    borderRadius: 999,
    ...shadow,
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    alignSelf: 'center',
    columnGap: Spacing.three,
    rowGap: Spacing.one,
    paddingVertical: Spacing.one + Spacing.half,
    paddingHorizontal: Spacing.three,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one + Spacing.half,
  },
  swatch: {
    width: 14,
    height: 5,
    borderRadius: 3,
  },
  chip: {
    paddingVertical: Spacing.one + Spacing.half,
    paddingHorizontal: Spacing.three,
  },
  locate: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    ...shadow,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'center',
    gap: Spacing.two,
    paddingVertical: Spacing.one + Spacing.half,
    paddingHorizontal: Spacing.three,
    maxWidth: '100%',
  },
  bannerText: {
    flexShrink: 1,
  },
  pressed: {
    opacity: 0.6,
  },
});
