/**
 * M5 · Favourite routes: the list. Each card shows the route's overall road colour and its
 * number of warnings; tap opens /route/[id], long-press or the trash icon deletes, "Add route" → /route/new.
 */
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { confirmAction, showMessage } from '@/components/routes/confirm';
import { invalidateRouteQuality } from '@/components/routes/quality-cache';
import { RouteCard } from '@/components/routes/route-card';
import { RoutesSignInGate } from '@/components/routes/sign-in-prompt';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { routesText } from '@/i18n/routes';
import { ApiError, deleteRoute, getRoutes, type FavoriteRoute } from '@/lib/api';
import { text, useText } from '@/lib/i18n';
import { useSession } from '@/lib/session';

function errorText(e: unknown): string {
  if (e instanceof ApiError && e.status === 401) return text(routesText).sessionExpired;
  return e instanceof Error ? e.message : String(e);
}

export default function RoutesScreen() {
  const { status } = useSession();
  const theme = useTheme();
  const s = useText(routesText);
  const c = useText(commonText);
  const [routes, setRoutes] = useState<FavoriteRoute[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  // Reload whenever the tab comes into focus (e.g. back from adding or deleting a route).
  useFocusEffect(
    useCallback(() => {
      if (status !== 'signedIn') return;
      let cancelled = false;
      getRoutes().then(
        (list) => {
          if (cancelled) return;
          setRoutes(list);
          setError(null);
        },
        (e) => {
          if (!cancelled) setError(errorText(e));
        },
      );
      return () => {
        cancelled = true;
      };
    }, [status]),
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    invalidateRouteQuality();
    try {
      setRoutes(await getRoutes());
      setError(null);
      setRefreshToken((t) => t + 1);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  const onDelete = useCallback(async (route: FavoriteRoute) => {
    const t = text(routesText);
    const ok = await confirmAction(t.deleteRoute, t.deleteConfirm(route.name), text(commonText).delete);
    if (!ok) return;
    try {
      await deleteRoute(route.id);
      invalidateRouteQuality(route.id);
      setRoutes((list) => list?.filter((r) => r.id !== route.id) ?? list);
    } catch (e) {
      showMessage(t.deleteFailed, errorText(e));
    }
  }, []);

  if (status !== 'signedIn') return <RoutesSignInGate status={status} />;

  const addButton = (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push('/route/new')}
      style={({ pressed }) => [styles.addButton, { backgroundColor: theme.tint }, pressed && styles.pressed]}>
      <ThemedText type="smallBold" style={styles.addText}>
        {s.addRoute}
      </ThemedText>
    </Pressable>
  );

  return (
    <ThemedView style={styles.flex}>
      <FlatList
        data={routes ?? []}
        keyExtractor={(r) => String(r.id)}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.tint} />}
        ListHeaderComponent={
          <View style={styles.header}>
            {error && (
              <ThemedView type="backgroundElement" style={styles.errorBox}>
                <ThemedText type="small" style={{ color: theme.danger }}>
                  {s.loadFailed(error)}
                </ThemedText>
                <Pressable accessibilityRole="button" onPress={onRefresh}>
                  <ThemedText type="smallBold" style={{ color: theme.tint }}>
                    {c.retry}
                  </ThemedText>
                </Pressable>
              </ThemedView>
            )}
            {routes && routes.length > 0 && addButton}
          </View>
        }
        ListEmptyComponent={
          routes === null ? (
            error ? null : (
              <View style={styles.empty}>
                <ActivityIndicator color={theme.tint} />
              </View>
            )
          ) : (
            <View style={styles.empty}>
              <Icon name="route" size={48} color={theme.tint} />
              <ThemedText type="smallBold" style={styles.emptyTitle}>
                {s.emptyTitle}
              </ThemedText>
              <ThemedText themeColor="textSecondary" style={styles.center}>
                {s.emptyText}
              </ThemedText>
              {addButton}
            </View>
          )
        }
        ItemSeparatorComponent={() => <View style={styles.separator} />}
        renderItem={({ item }) => (
          <RouteCard
            route={item}
            refreshToken={refreshToken}
            onPress={() => router.push(`/route/${item.id}`)}
            onDelete={() => onDelete(item)}
          />
        )}
        ListFooterComponent={
          routes && routes.length > 0 ? (
            <ThemedText type="small" themeColor="textSecondary" style={[styles.center, styles.hint]}>
              {s.deleteHint}
            </ThemedText>
          ) : null
        }
      />
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    padding: Spacing.three,
    paddingBottom: Spacing.six,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    flexGrow: 1,
  },
  header: { gap: Spacing.three, marginBottom: Spacing.three },
  errorBox: { padding: Spacing.three, borderRadius: Spacing.three, gap: Spacing.two },
  addButton: {
    alignSelf: 'stretch',
    alignItems: 'center',
    paddingVertical: Spacing.two + 4,
    borderRadius: Spacing.three,
  },
  addText: { color: '#ffffff', fontSize: 16 },
  pressed: { opacity: 0.7 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.three, paddingVertical: Spacing.five },
  emptyTitle: { fontSize: 18 },
  center: { textAlign: 'center' },
  hint: { marginTop: Spacing.four },
  separator: { height: Spacing.two },
});
