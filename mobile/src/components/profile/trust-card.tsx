import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { Me } from '@/lib/api';

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
  const pct = Math.round(100 * Math.min(1, Math.max(0, me.trust || 0)));
  const barColor = pct >= 70 ? theme.success : pct >= 40 ? '#F2B300' : theme.danger;

  return (
    <ThemedView type="backgroundElement" style={styles.card}>
      <View style={styles.header}>
        <ThemedText type="smallBold">Güven puanın</ThemedText>
        <ThemedText type="smallBold" style={{ color: barColor }}>
          %{pct}
        </ThemedText>
      </View>
      <View
        style={[styles.track, { backgroundColor: theme.backgroundSelected }]}
        accessibilityRole="progressbar"
        accessibilityLabel={`Güven puanı yüzde ${pct}`}
        accessibilityValue={{ min: 0, max: 100, now: pct }}>
        <View style={[styles.fill, { width: `${pct}%`, backgroundColor: barColor }]} />
      </View>
      <ThemedText type="small" themeColor="textSecondary">
        Cevapların doğru çıktıkça puanın artar; puanın yükseldikçe cevapların daha çok sayılır.
      </ThemedText>
      <View style={styles.stats}>
        <Stat value={me.correct} label="Doğru cevap" />
        <Stat value={me.incorrect} label="Yanlış cevap" />
        <Stat value={me.reports_count} label="Bildirim" />
        <Stat value={me.answers_count} label="Cevap" />
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
