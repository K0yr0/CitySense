import type { ReactNode } from 'react';
import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';

/** Temporary screen body: says which roadmap task (docs/ROADMAP.md) fills this tab. */
export function Placeholder({ task, children }: { task: string; children?: ReactNode }) {
  return (
    <ThemedView style={styles.container}>
      <ThemedText themeColor="textSecondary" style={styles.task}>
        {task}
      </ThemedText>
      {children}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.four,
    gap: Spacing.four,
  },
  task: {
    textAlign: 'center',
  },
});
