import { StyleSheet, Text, View } from 'react-native';

import { Spacing } from '@/constants/theme';
import { incidentText } from '@/i18n/incident';
import { useText } from '@/lib/i18n';
import { WORK_STATUS_COLORS } from '@/lib/labels';

/** Shown when the city marked the incident done (work_status = done). Asks nothing. */
export function DoneBanner() {
  const s = useText(incidentText);
  return (
    <View style={[styles.banner, { backgroundColor: WORK_STATUS_COLORS.done }]} accessibilityRole="summary">
      <Text style={styles.title}>{s.doneTitle}</Text>
      <Text style={styles.body}>{s.doneBody}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
    gap: Spacing.one,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 18,
    lineHeight: 24,
    fontWeight: 700,
  },
  body: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: 500,
  },
});
