import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { API_URL, getHealth, getLiveVehicles } from '@/lib/api';

type Status =
  | { state: 'loading' }
  | { state: 'ok'; trams: number | null }
  | { state: 'error'; message: string };

async function checkBackend(): Promise<Status> {
  try {
    const health = await getHealth();
    if (!health.ok) throw new Error('/health ok=false döndü');
  } catch (e) {
    return { state: 'error', message: e instanceof Error ? e.message : String(e) };
  }
  // The live feed may be down even when the backend is up; that is not a connection error.
  try {
    return { state: 'ok', trams: (await getLiveVehicles('tram')).length };
  } catch {
    return { state: 'ok', trams: null };
  }
}

/** Day-0 connection check: GET /health + live tram count from GET /vehicles/live?kind=tram. */
export function BackendStatus() {
  const theme = useTheme();
  const [status, setStatus] = useState<Status>({ state: 'loading' });

  useEffect(() => {
    let cancelled = false;
    checkBackend().then((s) => {
      if (!cancelled) setStatus(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const retry = useCallback(() => {
    setStatus({ state: 'loading' });
    checkBackend().then(setStatus);
  }, []);

  return (
    <ThemedView type="backgroundElement" style={styles.card}>
      <ThemedText type="smallBold">Backend bağlantısı</ThemedText>
      <ThemedText type="code" themeColor="textSecondary">
        {API_URL}
      </ThemedText>

      {status.state === 'loading' && <ActivityIndicator color={theme.tint} />}

      {status.state === 'ok' && (
        <>
          <ThemedText style={{ color: theme.success }}>● Bağlı</ThemedText>
          <ThemedText>
            {status.trams === null
              ? 'Canlı tramvay verisi şu an alınamıyor.'
              : `Şu an ${status.trams} tramvay canlı.`}
          </ThemedText>
        </>
      )}

      {status.state === 'error' && (
        <>
          <ThemedText style={{ color: theme.danger }}>● Backend&apos;e ulaşılamadı</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            Backend çalışıyor mu? Telefondaysan EXPO_PUBLIC_API_URL bilgisayarının LAN IP&apos;si
            olmalı (ör. http://192.168.1.20:8000) ve aynı Wi-Fi&apos;da olmalısın.
          </ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            ({status.message})
          </ThemedText>
        </>
      )}

      <Pressable
        onPress={retry}
        disabled={status.state === 'loading'}
        style={({ pressed }) => [styles.button, { borderColor: theme.tint }, pressed && styles.pressed]}>
        <ThemedText type="smallBold" style={{ color: theme.tint }}>
          Yeniden dene
        </ThemedText>
      </Pressable>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  card: {
    alignSelf: 'stretch',
    maxWidth: 420,
    width: '100%',
    marginHorizontal: 'auto',
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.two,
    alignItems: 'center',
  },
  button: {
    marginTop: Spacing.two,
    paddingVertical: Spacing.one,
    paddingHorizontal: Spacing.three,
    borderRadius: Spacing.three,
    borderWidth: 1,
  },
  pressed: {
    opacity: 0.6,
  },
});
