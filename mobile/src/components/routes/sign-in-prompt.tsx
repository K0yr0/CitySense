import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { routesText } from '@/i18n/routes';
import { useText } from '@/lib/i18n';
import type { SessionStatus } from '@/lib/session';

/** Shown instead of a routes screen while the session loads or when the user is signed out. */
export function RoutesSignInGate({ status }: { status: SessionStatus }) {
  const theme = useTheme();
  const s = useText(routesText);
  const c = useText(commonText);
  if (status === 'loading') {
    return (
      <ThemedView style={styles.center}>
        <ActivityIndicator color={theme.tint} />
      </ThemedView>
    );
  }
  return (
    <ThemedView style={styles.center}>
      <View style={styles.box}>
        <Icon name="route" size={44} color={theme.tint} />
        <ThemedText type="smallBold" style={styles.title}>
          {s.gateTitle}
        </ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.text}>
          {s.gateText}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" style={styles.text}>
          {s.gateNeedSignIn}
        </ThemedText>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push('/sign-in')}
          style={({ pressed }) => [styles.button, { backgroundColor: theme.tint }, pressed && styles.pressed]}>
          <ThemedText type="smallBold" style={styles.buttonText}>
            {c.signIn}
          </ThemedText>
        </Pressable>
      </View>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.four },
  box: { maxWidth: 420, width: '100%', alignItems: 'center', gap: Spacing.three },
  title: { fontSize: 18 },
  text: { textAlign: 'center' },
  button: { paddingVertical: Spacing.two + 2, paddingHorizontal: Spacing.five, borderRadius: Spacing.five },
  buttonText: { color: '#ffffff' },
  pressed: { opacity: 0.7 },
});
