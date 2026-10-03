/** Compact card for the tapped incident: public fields, the Yes/No poll, a link to details. No sensor data. */
import { router, type Href } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { TypeIcon } from '@/components/icon';
import { IncidentPoll } from '@/components/map/incident-poll';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { PublicIncident } from '@/lib/api';
import {
  confidencePct,
  incidentColor,
  STATUS_COLORS,
  statusLabel,
  typeLabel,
  WORK_STATUS_COLORS,
  workStatusLabel,
} from '@/lib/labels';
import { useText } from '@/lib/i18n';
import { commonText } from '@/i18n/common';
import { mapText } from '@/i18n/map';

export function IncidentCard({ incident, onClose }: { incident: PublicIncident; onClose: () => void }) {
  const theme = useTheme();
  const s = useText(mapText);
  const c = useText(commonText);

  return (
    <View style={[styles.card, { backgroundColor: theme.background }]}>
      <View style={styles.header}>
        <TypeIcon type={incident.type} size={26} color={incidentColor(incident)} />
        <View style={styles.headerText}>
          <ThemedText type="smallBold">{typeLabel(incident.type)}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary" numberOfLines={2}>
            {incident.address ?? c.unknownAddress}
          </ThemedText>
        </View>
        <Pressable
          onPress={onClose}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel={c.close}
          style={({ pressed }) => [styles.close, { backgroundColor: theme.backgroundElement }, pressed && styles.pressed]}>
          <ThemedText type="smallBold" themeColor="textSecondary">
            ✕
          </ThemedText>
        </Pressable>
      </View>

      <View style={styles.facts}>
        <View style={styles.fact}>
          <View style={[styles.dot, { backgroundColor: STATUS_COLORS[incident.status] }]} />
          <ThemedText type="small">
            {s.card.status(statusLabel(incident.status), confidencePct(incident.confidence))}
          </ThemedText>
        </View>
        <View style={styles.fact}>
          <View style={[styles.dot, { backgroundColor: WORK_STATUS_COLORS[incident.work_status] }]} />
          <ThemedText type="small">{s.card.repair(workStatusLabel(incident.work_status))}</ThemedText>
        </View>
        <ThemedText type="small" themeColor="textSecondary">
          {incident.report_count > 0 ? s.card.reportedBy(incident.report_count) : s.card.noReports}
        </ThemedText>
      </View>

      <IncidentPoll key={incident.id} incident={incident} />

      <Pressable
        onPress={() => router.push(`/incident/${incident.id}` as Href)}
        accessibilityRole="button"
        accessibilityLabel={s.card.openDetails}
        style={({ pressed }) => [styles.button, { backgroundColor: theme.tint }, pressed && styles.pressed]}>
        <ThemedText type="smallBold" style={styles.buttonText}>
          {c.details}
        </ThemedText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
    gap: Spacing.two,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 6,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.two,
  },
  headerText: {
    flex: 1,
  },
  close: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  facts: {
    gap: Spacing.one,
  },
  fact: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  button: {
    marginTop: Spacing.one,
    paddingVertical: Spacing.two,
    borderRadius: Spacing.three,
    alignItems: 'center',
  },
  buttonText: {
    color: 'white',
  },
  pressed: {
    opacity: 0.6,
  },
});
