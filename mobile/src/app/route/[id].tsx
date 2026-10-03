/**
 * M5 · One favourite route: road quality along it as colours, warnings in order of distance,
 * and an "İleride kötü yol" banner when the user is on the route and a warning is close ahead.
 * Citizens only ever see colour classes here: no health numbers, no sensor data.
 */
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { confirmAction, showMessage } from '@/components/routes/confirm';
import { HealthDot, QualityBar } from '@/components/routes/quality-bar';
import { invalidateRouteQuality, loadRouteQuality } from '@/components/routes/quality-cache';
import { aheadOfUser, AHEAD_ALERT_M, describeRoute, ON_ROUTE_M } from '@/components/routes/route-geometry';
import { ROUTE_MAP_SUPPORTED, RouteQualityMap } from '@/components/routes/route-quality-map';
import { RoutesSignInGate } from '@/components/routes/sign-in-prompt';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useLocation } from '@/hooks/use-location';
import { useTheme } from '@/hooks/use-theme';
import { ApiError, deleteRoute, type RouteQuality, type RouteWarning } from '@/lib/api';
import { formatDistance } from '@/lib/geo';
import { HEALTH_LABELS, healthColor } from '@/lib/labels';
import { useSession } from '@/lib/session';

type Loaded = { key: string; quality: RouteQuality | null; error: string | null };

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return 'Bu rota bulunamadı. Silinmiş olabilir.';
    if (e.status === 401) return 'Oturumun sona ermiş. Lütfen yeniden giriş yap.';
  }
  return e instanceof Error ? e.message : String(e);
}

function openWarning(w: RouteWarning) {
  if (w.kind === 'incident' && w.incident_id != null) router.push(`/incident/${w.incident_id}`);
}

export default function RouteScreen() {
  const params = useLocalSearchParams<{ id: string }>();
  const id = Number(params.id);
  const { status } = useSession();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { coords } = useLocation({ watch: status === 'signedIn', requestOnMount: status === 'signedIn', distanceIntervalM: 10 });

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const key = String(id);

  useEffect(() => {
    if (status !== 'signedIn' || !Number.isFinite(id)) return;
    let cancelled = false;
    loadRouteQuality(id).then(
      (quality) => {
        if (!cancelled) setLoaded({ key, quality, error: null });
      },
      (e) => {
        if (!cancelled) setLoaded({ key, quality: null, error: errorText(e) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id, key, status]);

  if (status !== 'signedIn') {
    return (
      <>
        <Stack.Screen options={{ title: 'Rota' }} />
        <RoutesSignInGate status={status} />
      </>
    );
  }

  const current = loaded?.key === key ? loaded : null;
  const quality = current?.quality ?? null;
  const error = current?.error ?? null;

  // Pull to refresh / retry: keeps showing the previous result until the new one arrives.
  const reload = async () => {
    setRefreshing(true);
    try {
      setLoaded({ key, quality: await loadRouteQuality(id, true), error: null });
    } catch (e) {
      setLoaded((prev) => (prev?.key === key && prev.quality ? prev : { key, quality: null, error: errorText(e) }));
      if (quality) showMessage('Yenilenemedi', errorText(e));
    } finally {
      setRefreshing(false);
    }
  };

  const onDelete = async () => {
    if (!Number.isFinite(id)) return;
    const ok = await confirmAction('Rotayı sil', `"${quality?.route.name ?? 'Bu rota'}" silinsin mi?`, 'Sil');
    if (!ok) return;
    setDeleting(true);
    try {
      await deleteRoute(id);
      invalidateRouteQuality(id);
      if (router.canGoBack()) router.back();
      else router.replace('/routes');
    } catch (e) {
      setDeleting(false);
      showMessage('Silinemedi', errorText(e));
    }
  };

  if (!quality) {
    return (
      <ThemedView style={styles.center}>
        <Stack.Screen options={{ title: 'Rota' }} />
        {error && !refreshing ? (
          <>
            <ThemedText style={[styles.centerText, { color: theme.danger }]}>{error}</ThemedText>
            <Pressable accessibilityRole="button" onPress={reload}>
              <ThemedText type="smallBold" style={{ color: theme.tint }}>
                Yeniden dene
              </ThemedText>
            </Pressable>
          </>
        ) : (
          <>
            <ActivityIndicator color={theme.tint} />
            <ThemedText type="small" themeColor="textSecondary">
              Rota boyunca yol durumu hesaplanıyor…
            </ThemedText>
          </>
        )}
      </ThemedView>
    );
  }

  const { route, summary, warnings, path } = quality;
  const ahead = aheadOfUser(path, warnings, coords);
  const alert = ahead?.alert ?? null;

  return (
    <ThemedView style={styles.flex}>
      <Stack.Screen options={{ title: route.name }} />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.five }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={reload} tintColor={theme.tint} />}>
        {alert && (
          <Pressable
            accessibilityRole={alert.warning.kind === 'incident' ? 'button' : undefined}
            onPress={() => openWarning(alert.warning)}
            style={[styles.banner, { backgroundColor: theme.danger }]}>
            <ThemedText type="smallBold" style={styles.bannerTitle}>
              ⚠️ İleride kötü yol
            </ThemedText>
            <ThemedText type="small" style={styles.bannerText}>
              {formatDistance(alert.inM)} sonra: {alert.warning.message}
            </ThemedText>
          </Pressable>
        )}
        {ahead && !alert && (
          <ThemedView type="backgroundElement" style={styles.note}>
            <ThemedText type="small" style={{ color: theme.success }}>
              ✓ Rotadasın. Önündeki {formatDistance(AHEAD_ALERT_M)} içinde uyarı yok.
            </ThemedText>
          </ThemedView>
        )}

        {ROUTE_MAP_SUPPORTED && <RouteQualityMap quality={quality} highlighted={alert?.warning} onWarningPress={openWarning} />}

        <ThemedView type="backgroundElement" style={styles.card}>
          <View style={styles.overall}>
            <HealthDot cls={summary.overall} size={16} />
            <ThemedText type="smallBold" style={styles.overallText}>
              Genel durum: {HEALTH_LABELS[summary.overall]}
            </ThemedText>
          </View>
          <ThemedText type="small" themeColor="textSecondary">
            {route.kind === 'line' ? (route.mode === 'tram' ? '🚋 ' : '🚌 ') : '📍 '}
            {describeRoute(route)}
          </ThemedText>
          <QualityBar summary={summary} />
        </ThemedView>

        <View style={styles.section}>
          <ThemedText type="smallBold" style={styles.sectionTitle}>
            Uyarılar
          </ThemedText>
          {!ahead && coords && (
            <ThemedText type="small" themeColor="textSecondary">
              Rotada değilsin ({formatDistance(ON_ROUTE_M)} dışında); mesafeler rotanın başından ölçülüyor.
            </ThemedText>
          )}
          {warnings.length === 0 ? (
            <ThemedView type="backgroundElement" style={styles.note}>
              <ThemedText type="small" style={{ color: theme.success }}>
                ✓ Bu rota boyunca bilinen bir sorun ya da kötü yol yok.
              </ThemedText>
            </ThemedView>
          ) : (
            [...warnings]
              .sort((a, b) => a.distance_along_m - b.distance_along_m)
              .map((w, i) => {
                const passed = ahead ? w.distance_along_m <= ahead.userAlongM : false;
                const dist = ahead ? w.distance_along_m - ahead.userAlongM : w.distance_along_m;
                const where = passed ? 'Geride kaldı' : dist < 1 ? 'Başlangıçta' : `${formatDistance(dist)} ileride`;
                const tappable = w.kind === 'incident' && w.incident_id != null;
                const isAlert = alert?.warning === w;
                return (
                  <Pressable
                    key={`${w.kind}-${w.incident_id ?? 'p'}-${i}`}
                    disabled={!tappable}
                    accessibilityRole={tappable ? 'button' : undefined}
                    onPress={() => openWarning(w)}
                    style={({ pressed }) => [
                      styles.warning,
                      { backgroundColor: theme.backgroundElement },
                      isAlert && { borderColor: theme.danger, borderWidth: 1 },
                      passed && styles.passed,
                      pressed && styles.pressed,
                    ]}>
                    <View
                      style={[
                        styles.warningMark,
                        { backgroundColor: w.kind === 'incident' ? healthColor('poor') : '#F29900' },
                      ]}
                    />
                    <View style={styles.flex}>
                      <ThemedText type="small">
                        ⚠️ {where}: {w.message}
                      </ThemedText>
                      {tappable && (
                        <ThemedText type="small" style={{ color: theme.tint }}>
                          Ayrıntılar ›
                        </ThemedText>
                      )}
                    </View>
                  </Pressable>
                );
              })
          )}
        </View>

        {!ROUTE_MAP_SUPPORTED && (
          <ThemedText type="small" themeColor="textSecondary" style={styles.centerText}>
            Rota haritası yalnızca mobil uygulamada gösterilir.
          </ThemedText>
        )}

        <Pressable
          accessibilityRole="button"
          onPress={onDelete}
          disabled={deleting}
          style={({ pressed }) => [styles.delete, { borderColor: theme.danger }, pressed && styles.pressed]}>
          {deleting ? (
            <ActivityIndicator color={theme.danger} />
          ) : (
            <ThemedText type="smallBold" style={{ color: theme.danger }}>
              🗑️ Rotayı sil
            </ThemedText>
          )}
        </Pressable>
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: Spacing.three, padding: Spacing.four },
  centerText: { textAlign: 'center' },
  content: {
    padding: Spacing.three,
    gap: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  banner: { padding: Spacing.three, borderRadius: Spacing.three, gap: Spacing.half },
  bannerTitle: { color: '#ffffff', fontSize: 16 },
  bannerText: { color: '#ffffff' },
  note: { padding: Spacing.three, borderRadius: Spacing.three },
  card: { padding: Spacing.three, borderRadius: Spacing.three, gap: Spacing.two },
  overall: { flexDirection: 'row', alignItems: 'center', gap: Spacing.two },
  overallText: { fontSize: 16 },
  section: { gap: Spacing.two },
  sectionTitle: { fontSize: 16 },
  warning: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Spacing.three,
  },
  warningMark: { width: 6, alignSelf: 'stretch', borderRadius: 3 },
  passed: { opacity: 0.5 },
  pressed: { opacity: 0.6 },
  delete: {
    marginTop: Spacing.three,
    alignItems: 'center',
    paddingVertical: Spacing.three,
    borderRadius: Spacing.three,
    borderWidth: 1,
  },
});
