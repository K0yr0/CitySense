import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { IssueType } from '@/lib/api';
import { TYPE_ICONS, typeLabel } from '@/lib/labels';

type Props = {
  type: IssueType;
  address: string | null;
  department: string | null;
};

/** Big type icon + label, address and the responsible department. */
export function IncidentHeader({ type, address, department }: Props) {
  const theme = useTheme();
  return (
    <View style={styles.row}>
      <View style={[styles.icon, { backgroundColor: theme.backgroundElement }]}>
        <ThemedText style={styles.emoji}>{TYPE_ICONS[type] ?? TYPE_ICONS.other}</ThemedText>
      </View>
      <View style={styles.text}>
        <ThemedText style={styles.title} accessibilityRole="header">
          {typeLabel(type)}
        </ThemedText>
        <ThemedText themeColor={address ? 'text' : 'textSecondary'}>
          {address || 'Adres bilinmiyor'}
        </ThemedText>
        {department ? (
          <ThemedText type="small" themeColor="textSecondary">
            Sorumlu: {department}
          </ThemedText>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
  },
  icon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emoji: {
    fontSize: 32,
    lineHeight: 40,
  },
  text: {
    flex: 1,
    gap: Spacing.half,
  },
  title: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: 700,
  },
});
