import { Image } from 'expo-image';
import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { reportText } from '@/i18n/report';
import { absoluteUrl, type MobileReport } from '@/lib/api';
import { useText } from '@/lib/i18n';
import {
  confidencePct,
  STATUS_COLORS,
  statusLabel,
  TYPE_ICONS,
  typeLabel,
  WORK_STATUS_COLORS,
  workStatusLabel,
} from '@/lib/labels';

type Props = {
  report: MobileReport;
  onNew: () => void;
};

/**
 * Short status after sending (ROADMAP M3): category, department, the backend's message and,
 * when the report joined an incident, its confidence state, the city's work state and how many
 * others reported it. No sensor data, no evidence, no other people's texts.
 */
export function ReportResult({ report, onNew }: Props) {
  const theme = useTheme();
  const s = useText(reportText);
  const c = useText(commonText);
  const { incident } = report;
  const photo = absoluteUrl(report.photo_url);
  const category = report.category ?? incident?.type ?? null;

  return (
    <View style={styles.container}>
      <View style={[styles.banner, { backgroundColor: theme.backgroundElement }]}>
        <ThemedText type="subtitle" style={styles.bannerTitle}>
          {s.thanks}
        </ThemedText>
        <ThemedText themeColor="textSecondary">{s.received}</ThemedText>
      </View>

      <View style={[styles.card, { backgroundColor: theme.backgroundElement }]}>
        <View style={styles.categoryRow}>
          <ThemedText style={styles.icon}>{TYPE_ICONS[category ?? 'other']}</ThemedText>
          <View style={styles.flex}>
            <ThemedText type="smallBold">{typeLabel(category)}</ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {report.department ? c.responsible(report.department) : s.departmentPending}
            </ThemedText>
          </View>
          {photo ? (
            <Image source={{ uri: photo }} style={styles.thumbnail} contentFit="cover" accessibilityLabel={s.yourPhoto} />
          ) : null}
        </View>

        {report.message ? <ThemedText>{report.message}</ThemedText> : null}

        {incident ? (
          <View style={styles.facts}>
            <Fact
              label={s.factConfidence}
              value={`${statusLabel(incident.status)} · ${confidencePct(incident.confidence)}`}
              color={STATUS_COLORS[incident.status]}
            />
            <Fact
              label={s.factCity}
              value={workStatusLabel(incident.work_status)}
              color={WORK_STATUS_COLORS[incident.work_status]}
            />
            <Fact
              label={s.factReporters}
              value={
                report.others_count > 0 ? s.othersReported(report.others_count) : s.firstReporter
              }
            />
            {incident.address ? <Fact label={s.factAddress} value={incident.address} /> : null}
          </View>
        ) : (
          <ThemedText type="small" themeColor="textSecondary">
            {s.notMatched}
          </ThemedText>
        )}
      </View>

      {incident ? (
        <ActionButton label={s.viewProblem} onPress={() => router.push(`/incident/${incident.id}`)} />
      ) : null}
      <ActionButton label={s.newReport} variant="secondary" onPress={onNew} />
    </View>
  );
}

function Fact({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.factRow}>
      <ThemedText type="small" themeColor="textSecondary" style={styles.factLabel}>
        {label}
      </ThemedText>
      <View style={styles.factValue}>
        {color ? <View style={[styles.dot, { backgroundColor: color }]} /> : null}
        <ThemedText type="smallBold" style={styles.flex}>
          {value}
        </ThemedText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.three,
  },
  banner: {
    borderRadius: 16,
    padding: Spacing.four,
    alignItems: 'center',
    gap: Spacing.one,
  },
  bannerTitle: {
    textAlign: 'center',
  },
  card: {
    borderRadius: 16,
    padding: Spacing.three,
    gap: Spacing.three,
  },
  categoryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  icon: {
    fontSize: 28,
    lineHeight: 34,
  },
  thumbnail: {
    width: 56,
    height: 56,
    borderRadius: 10,
  },
  facts: {
    gap: Spacing.two,
  },
  factRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  factLabel: {
    width: 92,
  },
  factValue: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  flex: {
    flex: 1,
  },
});
