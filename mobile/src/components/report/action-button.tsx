import { ActivityIndicator, Pressable, StyleSheet, Text, type StyleProp, type ViewStyle } from 'react-native';

import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Variant = 'primary' | 'secondary' | 'danger';

type Props = {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  compact?: boolean;
  style?: StyleProp<ViewStyle>;
  accessibilityHint?: string;
};

/** Small themed button used by the report screen. */
export function ActionButton({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  compact = false,
  style,
  accessibilityHint,
}: Props) {
  const theme = useTheme();
  const inactive = disabled || loading;
  const background =
    variant === 'primary' ? theme.tint : variant === 'danger' ? theme.danger : theme.backgroundElement;
  const foreground = variant === 'secondary' ? theme.text : '#ffffff';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      accessibilityHint={accessibilityHint}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.base,
        compact && styles.compact,
        { backgroundColor: background, opacity: inactive ? 0.5 : pressed ? 0.8 : 1 },
        style,
      ]}>
      {loading ? (
        <ActivityIndicator color={foreground} />
      ) : (
        <Text style={[styles.label, compact && styles.compactLabel, { color: foreground }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 48,
    borderRadius: 12,
    paddingHorizontal: Spacing.three,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compact: {
    minHeight: 36,
    paddingHorizontal: Spacing.two + Spacing.one,
    borderRadius: 10,
  },
  label: {
    fontSize: 16,
    fontWeight: '600',
  },
  compactLabel: {
    fontSize: 14,
  },
});
