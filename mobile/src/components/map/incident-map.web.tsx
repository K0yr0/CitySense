/**
 * Web fallback for the map: react-native-maps does not run on web, so `expo start --web`
 * shows the open incidents around central Warsaw as a simple list instead.
 */
import { useImperativeHandle } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useText } from '@/lib/i18n';
import { commonText } from '@/i18n/common';
import { mapText } from '@/i18n/map';
import { confidencePct, incidentColor, statusLabel, TYPE_ICONS, typeLabel } from '@/lib/labels';

import type { IncidentMapProps } from './types';

export function IncidentMap({ ref, incidents, selectedId, topInset, bottomInset, onSelectIncident }: IncidentMapProps) {
  const theme = useTheme();
  const s = useText(mapText);
  const c = useText(commonText);

  useImperativeHandle(ref, () => ({ animateTo: () => {} }));

  return (
    <ThemedView style={StyleSheet.absoluteFill}>
      <ScrollView
        contentContainerStyle={[styles.content, { paddingTop: topInset, paddingBottom: bottomInset }]}>
        <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
          {s.web.note}
        </ThemedText>
        {incidents.length === 0 && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.note}>
            {s.web.empty}
          </ThemedText>
        )}
        {incidents.map((i) => (
          <Pressable
            key={i.id}
            onPress={() => onSelectIncident(i)}
            style={({ pressed }) => [
              styles.row,
              { backgroundColor: i.id === selectedId ? theme.backgroundSelected : theme.backgroundElement },
              pressed && styles.pressed,
            ]}>
            <View style={[styles.dot, { backgroundColor: incidentColor(i) }]} />
            <View style={styles.rowText}>
              <ThemedText type="smallBold">
                {TYPE_ICONS[i.type] ?? TYPE_ICONS.other} {typeLabel(i.type)}
              </ThemedText>
              <ThemedText type="small" themeColor="textSecondary" numberOfLines={1}>
                {i.address ?? c.unknownAddress} · {statusLabel(i.status)} {confidencePct(i.confidence)}
              </ThemedText>
            </View>
          </Pressable>
        ))}
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: Spacing.three,
    gap: Spacing.two,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  note: {
    textAlign: 'center',
    marginVertical: Spacing.two,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  rowText: {
    flex: 1,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  pressed: {
    opacity: 0.6,
  },
});
