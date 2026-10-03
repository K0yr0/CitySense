import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { routesText } from '@/i18n/routes';
import type { HealthClass, RouteQuality } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { healthLabel, healthColor } from '@/lib/labels';

import { healthShares } from './route-geometry';

/** A coloured dot for a health class. */
export function HealthDot({ cls, size = 12 }: { cls: HealthClass; size?: number }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: healthColor(cls) }} />;
}

/** Proportions of good / fair / poor / unknown road along the route (by metres), plus a legend. */
export function QualityBar({ summary }: { summary: RouteQuality['summary'] }) {
  const s = useText(routesText);
  const { total, shares } = healthShares(summary);
  const visible = shares.filter((s) => s.fraction > 0);

  return (
    <View style={styles.wrap}>
      <View style={styles.bar} accessibilityLabel={s.qualityBarA11y}>
        {total > 0 ? (
          visible.map((share) => (
            <View key={share.cls} style={{ flex: share.fraction, backgroundColor: healthColor(share.cls) }} />
          ))
        ) : (
          <View style={{ flex: 1, backgroundColor: healthColor('unknown') }} />
        )}
      </View>
      <View style={styles.legend}>
        {total > 0 ? (
          visible.map((share) => (
            <View key={share.cls} style={styles.legendItem}>
              <HealthDot cls={share.cls} size={10} />
              <ThemedText type="small" themeColor="textSecondary">
                {healthLabel(share.cls)} {Math.round(100 * share.fraction)}%
              </ThemedText>
            </View>
          ))
        ) : (
          <ThemedText type="small" themeColor="textSecondary">
            {s.noMeasurements}
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
