import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';

type Variant = 'primary' | 'secondary' | 'danger';

type Props = {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  accessibilityHint?: string;
};

/** Full-width button used on the sign-in and profile screens. */
export function ActionButton({ label, onPress, variant = 'primary', disabled, loading, accessibilityHint }: Props) {
  const theme = useTheme();
  const filled = variant === 'primary';
  const color = variant === 'danger' ? theme.danger : theme.tint;
  const inactive = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      disabled={inactive}
      style={({ pressed }) => [
        styles.button,
        filled ? { backgroundColor: color } : { borderColor: color, borderWidth: 1 },
        inactive && styles.inactive,
        pressed && styles.pressed,
      ]}>
      {loading ? (
        <ActivityIndicator color={filled ? '#ffffff' : color} />
      ) : (
        <ThemedText type="smallBold" style={{ color: filled ? '#ffffff' : color }}>
          {label}
        </ThemedText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.three,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
  },
  inactive: {
    opacity: 0.5,
  },
  pressed: {
    opacity: 0.7,
  },
});
