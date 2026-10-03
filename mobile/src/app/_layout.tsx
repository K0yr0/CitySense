import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useColorScheme } from 'react-native';

import { NearbyQuestion } from '@/components/question/nearby-question';
import { commonText } from '@/i18n/common';
import { I18nProvider, useText } from '@/lib/i18n';
import { SessionProvider } from '@/lib/session';

// Root: a Stack around the tab group; detail screens are pushed on top of the tabs.
// NearbyQuestion (M4) floats above every screen and asks about incidents within 25 m.
// I18nProvider is outermost: changing the language remounts everything below it.
export default function RootLayout() {
  return (
    <I18nProvider>
      <SessionProvider>
        <AppStack />
      </SessionProvider>
    </I18nProvider>
  );
}

function AppStack() {
  const colorScheme = useColorScheme();
  const s = useText(commonText);
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <Stack screenOptions={{ headerShown: false, headerBackTitle: s.back }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="incident/[id]" options={{ headerShown: true, title: s.titles.incident }} />
        <Stack.Screen name="route/new" options={{ headerShown: true, title: s.titles.newRoute }} />
        <Stack.Screen name="route/[id]" options={{ headerShown: true, title: s.titles.route }} />
        <Stack.Screen name="sign-in" options={{ presentation: 'modal', headerShown: true, title: s.titles.signIn }} />
      </Stack>
      <NearbyQuestion />
    </ThemeProvider>
  );
}
