import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { profileText } from '@/i18n/profile';
import type { Me } from '@/lib/api';
import { useText } from '@/lib/i18n';

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <View style={styles.stat}>
      <ThemedText type="smallBold" style={styles.statValue}>
        {value}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary" style={styles.statLabel}>
        {label}
      </ThemedText>
    </View>
  );
}

/** Trust score (0–1 from the engine) as a percentage + bar, and activity counts. */
export function TrustCard({ me }: { me: Me }) {
  const theme = useTheme();
  const s = useText(profileText);
  const pct = Math.round(100 * Math.min(1, Math.max(0, me.trust || 0)));
  const barColor = pct >= 70 ? theme.success : pct >= 40 ? '#F2B300' : theme.danger;
  const pctText = `${pct}%`;

  return (
    <ThemedView type="backgroundElement" style={styles.card}>
      <View style={styles.header}>
        <ThemedText type="smallBold">{s.trustTitle}</ThemedText>
        <ThemedText type="smallBold" style={{ color: barColor }}>
          {pctText}
        </ThemedText>
      </View>
      <View
        style={[styles.track, { backgroundColor: theme.backgroundSelected }]}
        accessibilityRole="progressbar"
        accessibilityLabel={s.trustA11y(pctText)}
        accessibilityValue={{ min: 0, max: 100, now: pct }}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      <ThemedText type="small" themeColor="textSecondary">
        {s.trustHint}
      </ThemedText>
      <View style={styles.stats}>
        <Stat value={me.correct} label={s.stats.correct(me.correct)} />
        <Stat value={me.incorrect} label={s.stats.incorrect(me.incorrect)} />
        <Stat value={me.reports_count} label={s.stats.reports(me.reports_count)} />
        <Stat value={me.answers_count} label={s.stats.answers(me.answers_count)} />
      </View>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  card: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.two,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  track: {
    height: 10,
    borderRadius: 5,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 5,
  },
  stats: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: Spacing.one,
  },
  stat: {
    flex: 1,
    alignItems: 'center',
  },
  statValue: {
    fontSize: 20,
    lineHeight: 26,
  },
  statLabel: {
    textAlign: 'center',
    fontSize: 12,
    lineHeight: 16,
  },
});
