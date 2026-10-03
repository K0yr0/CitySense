import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { profileText } from '@/i18n/profile';
import type { MobileReport } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { TYPE_ICONS, timeAgo, typeLabel, WORK_STATUS_COLORS, workStatusLabel } from '@/lib/labels';

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <View style={[styles.chip, { borderColor: color }]}>
      <ThemedText type="small" style={[styles.chipText, { color }]}>
        {label}
      </ThemedText>
    </View>
  );
}

/** One row of "My reports": category, own text, backend message, time and the city's work status. */
export function ReportRow({ report, onPress }: { report: MobileReport; onPress?: () => void }) {
  const theme = useTheme();
  const s = useText(profileText);
  const c = useText(commonText);
  const category = report.category ?? 'other';
  const incident = report.incident;

  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: theme.backgroundElement },
        pressed && styles.pressed,
      ]}>
      <View style={styles.top}>
        <ThemedText type="smallBold" style={styles.category} numberOfLines={1}>
          {TYPE_ICONS[category] ?? TYPE_ICONS.other} {typeLabel(category)}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {timeAgo(report.created_at)}
        </ThemedText>
      </View>
      {!!report.text && (
        <ThemedText type="small" numberOfLines={2}>
          {report.text}
        </ThemedText>
      )}
      {!!report.message && (
        <ThemedText type="small" themeColor="textSecondary">
          {report.message}
        </ThemedText>
      )}
      <View style={styles.bottom}>
        {incident ? (
          <Chip label={workStatusLabel(incident.work_status)} color={WORK_STATUS_COLORS[incident.work_status]} />
        ) : (
          <Chip label={s.underReview} color={theme.textSecondary} />
        )}
        {onPress && (
          <ThemedText type="small" style={{ color: theme.tint }}>
            {c.details} ›
          </ThemedText>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.one,
  },
  pressed: {
    opacity: 0.7,
  },
  top: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: Spacing.two,
  },
  category: {
    flexShrink: 1,
  },
  bottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: Spacing.one,
  },
  chip: {
    borderWidth: 1,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.two,
    paddingVertical: Spacing.half,
  },
  chipText: {
    fontSize: 12,
    lineHeight: 16,
  },
});
