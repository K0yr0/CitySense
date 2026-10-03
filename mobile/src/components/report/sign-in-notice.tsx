import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { reportText } from '@/i18n/report';
import { useText } from '@/lib/i18n';

/** Shown above the form when the user is signed out: reading is free, sending needs an account. */
export function SignInNotice({ message }: { message?: string }) {
  const theme = useTheme();
  const s = useText(reportText);
  const c = useText(commonText);
  return (
    <View style={[styles.card, { backgroundColor: theme.backgroundElement, borderColor: theme.tint }]}>
      <ThemedText type="smallBold">{s.signInTitle}</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {message ?? s.signInBody}
      </ThemedText>
      <ActionButton label={c.signIn} compact onPress={() => router.push('/sign-in')} style={styles.button} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    borderWidth: 1,
    padding: Spacing.three,
    gap: Spacing.two,
  },
  button: {
    alignSelf: 'flex-start',
  },
});
