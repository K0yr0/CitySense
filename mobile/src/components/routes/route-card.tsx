import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { FavoriteRoute, RouteQuality } from '@/lib/api';
import { HEALTH_LABELS } from '@/lib/labels';

import { HealthDot } from './quality-bar';
import { loadRouteQuality } from './quality-cache';
import { describeRoute } from './route-geometry';

type Loaded = { key: string; quality: RouteQuality | null; failed: boolean };

type Props = {
  route: FavoriteRoute;
  /** Changes on pull-to-refresh so the card reloads its quality. */
  refreshToken: number;
  onPress: () => void;
  onDelete: () => void;
};

/** One saved route: name, kind, and (loaded lazily) the overall colour and number of warnings. */
export function RouteCard({ route, refreshToken, onPress, onDelete }: Props) {
  const theme = useTheme();
  const key = `${route.id}:${refreshToken}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadRouteQuality(route.id).then(
      (quality) => {
        if (!cancelled) setLoaded({ key, quality, failed: false });
      },
      () => {
        if (!cancelled) setLoaded({ key, quality: null, failed: true });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [route.id, key]);

  const current = loaded?.key === key ? loaded : null;
  const quality = current?.quality ?? null;
  const warnings = quality?.warnings.length ?? 0;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityHint="Rotayı açar. Silmek için basılı tut."
      onPress={onPress}
      onLongPress={onDelete}
      style={({ pressed }) => [styles.card, { backgroundColor: theme.backgroundElement }, pressed && styles.pressed]}>
      <View style={styles.main}>
        <ThemedText type="smallBold" numberOfLines={1} style={styles.name}>
          {route.name}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
          {route.kind === 'line' ? (route.mode === 'tram' ? '🚋 ' : '🚌 ') : '📍 '}
          {describeRoute(route)}
        </ThemedText>
        <View style={styles.quality}>
          {!current ? (
            <>
              <ActivityIndicator size="small" color={theme.textSecondary} />
              <ThemedText type="small" themeColor="textSecondary">
                Yol durumu hesaplanıyor…
              </ThemedText>
            </>
          ) : current.failed || !quality ? (
            <ThemedText type="small" themeColor="textSecondary">
              Yol durumu alınamadı
            </ThemedText>
          ) : (
            <>
              <HealthDot cls={quality.summary.overall} />
              <ThemedText type="small">{HEALTH_LABELS[quality.summary.overall]}</ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                ·
              </ThemedText>
              <ThemedText type="small" style={warnings > 0 ? { color: theme.danger } : undefined} themeColor="textSecondary">
                {warnings > 0 ? `⚠️ ${warnings} uyarı` : 'Uyarı yok'}
              </ThemedText>
            </>
          )}
        </View>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${route.name} rotasını sil`}
        hitSlop={10}
        onPress={onDelete}
        style={({ pressed }) => [styles.trash, pressed && styles.pressed]}>
        <ThemedText style={styles.trashIcon}>🗑️</ThemedText>
      </Pressable>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.two,
  },
  main: { flex: 1, gap: Spacing.half },
  name: { fontSize: 16 },
  quality: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two, marginTop: Spacing.one },
  trash: { padding: Spacing.two },
  trashIcon: { fontSize: 20, lineHeight: 26 },
  pressed: { opacity: 0.6 },
});
