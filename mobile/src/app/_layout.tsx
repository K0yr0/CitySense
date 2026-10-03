import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useColorScheme } from 'react-native';

import { NearbyQuestion } from '@/components/question/nearby-question';
import { SessionProvider } from '@/lib/session';

// Root: a Stack around the tab group; detail screens are pushed on top of the tabs.
// NearbyQuestion (M4) floats above every screen and asks about incidents within 25 m.
export default function RootLayout() {
  const colorScheme = useColorScheme();
  return (
    <SessionProvider>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <Stack screenOptions={{ headerShown: false }}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="incident/[id]" options={{ headerShown: true, title: 'Sorun' }} />
          <Stack.Screen name="route/new" options={{ headerShown: true, title: 'Rota ekle' }} />
          <Stack.Screen name="route/[id]" options={{ headerShown: true, title: 'Rota' }} />
          <Stack.Screen name="sign-in" options={{ presentation: 'modal', headerShown: true, title: 'Giriş yap' }} />
        </Stack>
        <NearbyQuestion />
      </ThemeProvider>
    </SessionProvider>
  );
}
