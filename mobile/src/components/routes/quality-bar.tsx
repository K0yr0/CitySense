import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import type { HealthClass, RouteQuality } from '@/lib/api';
import { HEALTH_LABELS, healthColor } from '@/lib/labels';

import { healthShares } from './route-geometry';

/** A coloured dot for a health class. */
export function HealthDot({ cls, size = 12 }: { cls: HealthClass; size?: number }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: healthColor(cls) }} />;
}

/** Proportions of good / fair / poor / unknown road along the route (by metres), plus a legend. */
export function QualityBar({ summary }: { summary: RouteQuality['summary'] }) {
  const { total, shares } = healthShares(summary);
  const visible = shares.filter((s) => s.fraction > 0);

  return (
    <View style={styles.wrap}>
      <View style={styles.bar} accessibilityLabel="Rota boyunca yol durumu">
        {total > 0 ? (
          visible.map((s) => (
            <View key={s.cls} style={{ flex: s.fraction, backgroundColor: healthColor(s.cls) }} />
          ))
        ) : (
          <View style={{ flex: 1, backgroundColor: healthColor('unknown') }} />
        )}
      </View>
      <View style={styles.legend}>
        {total > 0 ? (
          visible.map((s) => (
            <View key={s.cls} style={styles.legendItem}>
              <HealthDot cls={s.cls} size={10} />
              <ThemedText type="small" themeColor="textSecondary">
                {HEALTH_LABELS[s.cls]} %{Math.round(100 * s.fraction)}
              </ThemedText>
            </View>
          ))
        ) : (
          <ThemedText type="small" themeColor="textSecondary">
            Bu rota boyunca henüz ölçüm yok.
          </ThemedText>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: Spacing.two },
  bar: { flexDirection: 'row', height: 14, borderRadius: 7, overflow: 'hidden' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', columnGap: Spacing.three, rowGap: Spacing.one },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
});
