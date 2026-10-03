import type { ReactNode } from 'react';
import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useLocale } from '@/lib/i18n';

/** A titled card; used to keep "Confidence" and "City" visibly separate. */
export function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  const { locale } = useLocale();
  return (
    <ThemedView type="backgroundElement" style={styles.card}>
      <ThemedText type="smallBold" themeColor="textSecondary" style={styles.title}>
        {title.toLocaleUpperCase(locale)}
      </ThemedText>
      {children}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: Spacing.three,
    padding: Spacing.three,
    gap: Spacing.three,
  },
  title: {
    letterSpacing: 0.8,
    fontSize: 12,
  },
});
