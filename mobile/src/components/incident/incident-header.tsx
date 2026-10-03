import { StyleSheet, View } from 'react-native';

import { TypeIcon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import type { IssueType } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { typeLabel } from '@/lib/labels';

type Props = {
  type: IssueType;
  address: string | null;
  department: string | null;
};

/** Big type icon + label, address and the responsible department. */
export function IncidentHeader({ type, address, department }: Props) {
  const theme = useTheme();
  const c = useText(commonText);
  return (
    <View style={styles.row}>
      <View style={[styles.icon, { backgroundColor: theme.backgroundElement }]}>
        <TypeIcon type={type} size={32} color={theme.tint} />
      </View>
      <View style={styles.text}>
        <ThemedText style={styles.title} accessibilityRole="header">
          {typeLabel(type)}
        </ThemedText>
        <ThemedText themeColor={address ? 'text' : 'textSecondary'}>
          {address || c.unknownAddress}
        </ThemedText>
        {department ? (
          <ThemedText type="small" themeColor="textSecondary">
            {c.responsible(department)}
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
