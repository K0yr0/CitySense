/**
 * "Confidence": the confidence engine's status (candidate → likely → verified). Never mixed with the
 * city's work status (see work-status-steps.tsx).
 */
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { incidentText } from '@/i18n/incident';
import type { IncidentStatus } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { STATUS_COLORS, confidencePct, statusHint, statusLabel } from '@/lib/labels';

type Props = {
  status: IncidentStatus;
  confidence: number;
  /** Compact = just the coloured pill (for lists / map callouts). */
  compact?: boolean;
};

/** Coloured pill "Likely · 72%", optionally with the one-line explanation under it. */
export function ConfidenceChip({ status, confidence, compact = false }: Props) {
  const s = useText(incidentText);
  const color = STATUS_COLORS[status] ?? STATUS_COLORS.candidate;
  const pill = (
    <View
      style={[styles.pill, { backgroundColor: `${color}22`, borderColor: color }]}
      accessibilityLabel={s.confidenceA11y(statusLabel(status), confidencePct(confidence))}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <ThemedText type="smallBold" style={{ color }}>
        {statusLabel(status)} · {confidencePct(confidence)}
      </ThemedText>
    </View>
  );
  if (compact) return pill;
  return (
    <View style={styles.block}>
      {pill}
      <ThemedText type="small" themeColor="textSecondary">
        {statusHint(status)}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: Spacing.two,
    alignItems: 'flex-start',
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingVertical: Spacing.one,
    paddingHorizontal: Spacing.three,
    borderRadius: 999,
    borderWidth: 1,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
});
