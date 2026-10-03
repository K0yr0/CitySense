import { router } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

/** Shown above the form when the user is signed out: reading is free, sending needs an account. */
export function SignInNotice({ message }: { message?: string }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.backgroundElement, borderColor: theme.tint }]}>
      <ThemedText type="smallBold">Bildirim göndermek için giriş yapmalısın</ThemedText>
      <ThemedText type="small" themeColor="textSecondary">
        {message ??
          'Haritaya bakmak serbest. Bildirimlerin hesabına bağlanır; böylece güven puanın birikir ve sahte bildirimler ayıklanır.'}
      </ThemedText>
      <ActionButton label="Giriş yap" compact onPress={() => router.push('/sign-in')} style={styles.button} />
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
