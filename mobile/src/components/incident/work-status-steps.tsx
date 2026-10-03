/**
 * "Belediye": the city's work on the incident as a 3-step progress
 * (Yapılmadı → Belediye ilgileniyor → Yapıldı). Independent of the confidence status.
 */
import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import type { WorkStatus } from '@/lib/api';
import { WORK_STATUS_COLORS, workStatusLabel } from '@/lib/labels';

export const WORK_STEPS: WorkStatus[] = ['todo', 'in_progress', 'done'];

const DOT = 14;
const DOT_CURRENT = 22;
const COLUMN = 100 / WORK_STEPS.length; // % width of one step column

export function WorkStatusSteps({ workStatus }: { workStatus: WorkStatus }) {
  const theme = useTheme();
  const current = Math.max(0, WORK_STEPS.indexOf(workStatus));
  const active = WORK_STATUS_COLORS[WORK_STEPS[current]];
  const inactive = theme.backgroundSelected;

  return (
    <View
      style={styles.container}
      accessible
      accessibilityLabel={`Belediye durumu: ${workStatusLabel(WORK_STEPS[current])}`}>
      {/* Connector lines between the dot centres, drawn behind the dots. */}
      {WORK_STEPS.slice(1).map((step, k) => (
        <View
          key={`line-${step}`}
          style={[
            styles.line,
            {
              left: `${COLUMN * (k + 0.5)}%`,
              width: `${COLUMN}%`,
              backgroundColor: k + 1 <= current ? active : inactive,
            },
          ]}
        />
      ))}
      {WORK_STEPS.map((step, i) => {
        const reached = i <= current;
        const isCurrent = i === current;
        return (
          <View key={step} style={styles.column}>
            <View style={styles.dotBox}>
              <View
                style={[
                  styles.dot,
                  isCurrent && styles.dotCurrent,
                  {
                    borderColor: reached ? active : inactive,
                    backgroundColor: reached ? active : theme.background,
                  },
                ]}>
                {isCurrent && <View style={[styles.dotInner, { backgroundColor: theme.background }]} />}
              </View>
            </View>
            <ThemedText
              type={isCurrent ? 'smallBold' : 'small'}
              themeColor={isCurrent ? undefined : 'textSecondary'}
              style={[styles.label, isCurrent && { color: active }]}>
              {workStatusLabel(step)}
            </ThemedText>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
  },
  line: {
    position: 'absolute',
    top: DOT_CURRENT / 2 - 1.5,
    height: 3,
    borderRadius: 2,
  },
  column: {
    flex: 1,
    alignItems: 'center',
    gap: Spacing.two,
  },
  dotBox: {
    height: DOT_CURRENT,
    justifyContent: 'center',
    alignItems: 'center',
  },
  dot: {
    width: DOT,
    height: DOT,
    borderRadius: DOT / 2,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dotCurrent: {
    width: DOT_CURRENT,
    height: DOT_CURRENT,
    borderRadius: DOT_CURRENT / 2,
  },
  dotInner: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  label: {
    textAlign: 'center',
    paddingHorizontal: Spacing.one,
  },
});
