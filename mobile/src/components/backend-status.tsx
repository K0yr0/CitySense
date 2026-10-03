import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { useText } from '@/lib/i18n';
import { API_URL, getHealth, getLiveVehicles } from '@/lib/api';

type Status =
  | { state: 'loading' }
  | { state: 'ok'; trams: number | null }
  | { state: 'error'; message: string };

async function checkBackend(): Promise<Status> {
  try {
    const health = await getHealth();
    if (!health.ok) throw new Error('/health returned ok=false');
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

/** Connection check: GET /health + live tram count from GET /vehicles/live?kind=tram. */
export function BackendStatus() {
  const theme = useTheme();
  const s = useText(commonText).backend;
  const c = useText(commonText);
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
      <ThemedText type="smallBold">{s.title}</ThemedText>
      <ThemedText type="code" themeColor="textSecondary">
        {API_URL}
      </ThemedText>

      {status.state === 'loading' && <ActivityIndicator color={theme.tint} />}

      {status.state === 'ok' && (
        <>
          <ThemedText style={{ color: theme.success }}>{s.connected}</ThemedText>
          <ThemedText>
            {status.trams === null ? s.noLiveData : s.liveTrams(status.trams)}
          </ThemedText>
        </>
      )}

      {status.state === 'error' && (
        <>
          <ThemedText style={{ color: theme.danger }}>{s.unreachable}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {s.help}
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
          {c.retry}
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
