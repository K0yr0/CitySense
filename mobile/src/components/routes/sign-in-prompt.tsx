import { router } from 'expo-router';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { SessionStatus } from '@/lib/session';

/** Shown instead of a routes screen while the session loads or when the user is signed out. */
export function RoutesSignInGate({ status }: { status: SessionStatus }) {
  const theme = useTheme();
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
        <ThemedText style={styles.icon}>🛣️</ThemedText>
        <ThemedText type="smallBold" style={styles.title}>
          Favori rotaların
        </ThemedText>
        <ThemedText themeColor="textSecondary" style={styles.text}>
          Evden işe giden yolunu ya da bindiğin otobüs/tramvay hattını kaydet. Rota boyunca yolun
          durumunu renklerle gösterir, ileride kötü yol ya da bildirilmiş bir sorun varsa seni uyarırız.
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary" style={styles.text}>
          Rotalar hesabına kaydedildiği için giriş yapman gerekiyor.
        </ThemedText>
        <Pressable
          accessibilityRole="button"
          onPress={() => router.push('/sign-in')}
          style={({ pressed }) => [styles.button, { backgroundColor: theme.tint }, pressed && styles.pressed]}>
          <ThemedText type="smallBold" style={styles.buttonText}>
            Giriş yap
          </ThemedText>
        </Pressable>
      </View>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: Spacing.four },
  box: { maxWidth: 420, width: '100%', alignItems: 'center', gap: Spacing.three },
  icon: { fontSize: 40, lineHeight: 48 },
  title: { fontSize: 18 },
  text: { textAlign: 'center' },
  button: { paddingVertical: Spacing.two + 2, paddingHorizontal: Spacing.five, borderRadius: Spacing.five },
  buttonText: { color: '#ffffff' },
  pressed: { opacity: 0.7 },
});
