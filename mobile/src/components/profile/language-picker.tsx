/**
 * Language picker: three chips (English / Polski / Українська), each in its own language.
 * Choosing one calls setLocale(), which remounts the app (navigation goes back to the first tab).
 */
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { LOCALES, useLocale, useText } from '@/lib/i18n';

export function LanguagePicker() {
  const theme = useTheme();
  const c = useText(commonText);
  const { locale, setLocale } = useLocale();

  return (
    <View style={styles.container}>
      <ThemedText type="smallBold">{c.language}</ThemedText>
      <View style={styles.row}>
        {LOCALES.map(({ code, name }) => {
          const selected = code === locale;
          return (
            <Pressable
              key={code}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLanguage={code}
              onPress={() => {
                if (!selected) setLocale(code);
              }}
              style={({ pressed }) => [
                styles.chip,
                selected
                  ? { backgroundColor: theme.tint, borderColor: theme.tint }
                  : { backgroundColor: theme.backgroundElement, borderColor: theme.backgroundSelected },
                pressed && styles.pressed,
              ]}>
              <ThemedText
                type="small"
                numberOfLines={1}
                style={[styles.label, { color: selected ? '#ffffff' : theme.text }]}>
                {name}
              </ThemedText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: Spacing.two,
  },
  row: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  chip: {
    flex: 1,
    minHeight: 40,
    borderWidth: 1,
    borderRadius: Spacing.three,
    paddingHorizontal: Spacing.two,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontWeight: '600',
  },
  pressed: {
    opacity: 0.7,
  },
});
