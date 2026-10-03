import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { routesText } from '@/i18n/routes';
import type { FavoriteRoute, RouteQuality } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { healthLabel } from '@/lib/labels';

import { HealthDot } from './quality-bar';
import { loadRouteQuality } from './quality-cache';
import { describeRoute, routeIcon } from './route-geometry';

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
  const s = useText(routesText);
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
      accessibilityHint={s.cardHint}
      onPress={onPress}
      onLongPress={onDelete}
      style={({ pressed }) => [styles.card, { backgroundColor: theme.backgroundElement }, pressed && styles.pressed]}>
      <View style={styles.main}>
        <ThemedText type="smallBold" numberOfLines={1} style={styles.name}>
          {route.name}
        </ThemedText>
        <View style={styles.kind}>
          <Icon name={routeIcon(route)} size={14} color={theme.textSecondary} />
          <ThemedText type="small" themeColor="textSecondary" numberOfLines={1} style={styles.kindText}>
            {describeRoute(route)}
          </ThemedText>
        </View>
        <View style={styles.quality}>
          {!current ? (
            <>
              <ActivityIndicator size="small" color={theme.textSecondary} />
              <ThemedText type="small" themeColor="textSecondary">
                {s.computingShort}
              </ThemedText>
            </>
          ) : current.failed || !quality ? (
            <ThemedText type="small" themeColor="textSecondary">
              {s.qualityFailed}
            </ThemedText>
          ) : (
            <>
              <HealthDot cls={quality.summary.overall} />
              <ThemedText type="small">{healthLabel(quality.summary.overall)}</ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                ·
              </ThemedText>
              {warnings > 0 && <Icon name="warning" size={14} color={theme.danger} />}
              <ThemedText type="small" style={warnings > 0 ? { color: theme.danger } : undefined} themeColor="textSecondary">
                {warnings > 0 ? s.warningCount(warnings) : s.noWarningsShort}
              </ThemedText>
            </>
          )}
        </View>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={s.deleteA11y(route.name)}
        hitSlop={10}
        onPress={onDelete}
        style={({ pressed }) => [styles.trash, pressed && styles.pressed]}>
        <Icon name="trash" size={20} color={theme.danger} />
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
  kind: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
  kindText: { flexShrink: 1 },
  pressed: { opacity: 0.6 },
});
