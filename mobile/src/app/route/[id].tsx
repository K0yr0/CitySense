/**
 * M5 · One favourite route: road quality along it as colours, warnings in order of distance,
 * and a "Bad road ahead" banner when the user is on the route and a warning is close ahead.
 * Citizens only ever see colour classes here: no health numbers, no sensor data.
 */
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/components/icon';
import { confirmAction, showMessage } from '@/components/routes/confirm';
import { HealthDot, QualityBar } from '@/components/routes/quality-bar';
import { invalidateRouteQuality, loadRouteQuality } from '@/components/routes/quality-cache';
import { aheadOfUser, AHEAD_ALERT_M, coverageNote, describeRoute, ON_ROUTE_M, routeIcon } from '@/components/routes/route-geometry';
import { ROUTE_MAP_SUPPORTED, RouteQualityMap } from '@/components/routes/route-quality-map';
import { RoutesSignInGate } from '@/components/routes/sign-in-prompt';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useLocation } from '@/hooks/use-location';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { routesText } from '@/i18n/routes';
import { ApiError, deleteRoute, type RouteQuality, type RouteWarning } from '@/lib/api';
import { formatDistance } from '@/lib/geo';
import { text, useText } from '@/lib/i18n';
import { healthLabel, healthColor } from '@/lib/labels';
import { useSession } from '@/lib/session';

type Loaded = { key: string; quality: RouteQuality | null; error: string | null };

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const t = text(routesText);
    if (e.status === 404) return t.notFound;
    if (e.status === 401) return t.sessionExpired;
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
  const s = useText(routesText);
  const c = useText(commonText);
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
        <Stack.Screen options={{ title: c.titles.route }} />
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
      if (quality) showMessage(s.refreshFailed, errorText(e));
    } finally {
      setRefreshing(false);
    }
  };

  const onDelete = async () => {
    if (!Number.isFinite(id)) return;
    const name = quality?.route.name;
    const ok = await confirmAction(s.deleteRoute, name ? s.deleteConfirm(name) : s.deleteConfirmUnnamed, c.delete);
    if (!ok) return;
    setDeleting(true);
    try {
      await deleteRoute(id);
      invalidateRouteQuality(id);
      if (router.canGoBack()) router.back();
      else router.replace('/routes');
    } catch (e) {
      setDeleting(false);
      showMessage(s.deleteFailed, errorText(e));
    }
  };

  if (!quality) {
    return (
      <ThemedView style={styles.center}>
        <Stack.Screen options={{ title: c.titles.route }} />
        {error && !refreshing ? (
          <>
            <ThemedText style={[styles.centerText, { color: theme.danger }]}>{error}</ThemedText>
            <Pressable accessibilityRole="button" onPress={reload}>
              <ThemedText type="smallBold" style={{ color: theme.tint }}>
                {c.retry}
              </ThemedText>
            </Pressable>
          </>
        ) : (
          <>
            <ActivityIndicator color={theme.tint} />
            <ThemedText type="small" themeColor="textSecondary">
              {s.computing}
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
            <View style={styles.kind}>
              <Icon name="warning" size={18} color="#ffffff" />
              <ThemedText type="smallBold" style={styles.bannerTitle}>
                {s.badRoadAhead}
              </ThemedText>
            </View>
            <ThemedText type="small" style={styles.bannerText}>
              {s.inDistance(formatDistance(alert.inM), alert.warning.message)}
            </ThemedText>
          </Pressable>
        )}
        {ahead && !alert && (
          <ThemedView type="backgroundElement" style={styles.note}>
            <ThemedText type="small" style={{ color: theme.success }}>
              {s.onRouteClear(formatDistance(AHEAD_ALERT_M))}
            </ThemedText>
          </ThemedView>
        )}

        {ROUTE_MAP_SUPPORTED && <RouteQualityMap quality={quality} highlighted={alert?.warning} onWarningPress={openWarning} user={coords} />}

        <ThemedView type="backgroundElement" style={styles.card}>
          <View style={styles.overall}>
            <HealthDot cls={summary.overall} size={16} />
            <ThemedText type="smallBold" style={styles.overallText}>
              {s.overall(healthLabel(summary.overall))}
            </ThemedText>
          </View>
          {(() => {
            const note = coverageNote(quality);
            if (!note) return null;
            let text: string;
            if (note.kind === 'partial') text = s.measuredShare(`${Math.max(1, Math.round(note.share * 100))}%`);
            else if (note.kind === 'outside') text = s.outsideAreaLong;
            else text = s.notMeasuredLong;
            return (
              <ThemedText type="small" themeColor="textSecondary">
                {text}
              </ThemedText>
            );
          })()}
          <View style={styles.kind}>
            <Icon name={routeIcon(route)} size={14} color={theme.textSecondary} />
            <ThemedText type="small" themeColor="textSecondary">
              {describeRoute(route)}
            </ThemedText>
          </View>
          <QualityBar summary={summary} />
        </ThemedView>

        <View style={styles.section}>
          <ThemedText type="smallBold" style={styles.sectionTitle}>
            {s.warnings}
          </ThemedText>
          {!ahead && coords && (
            <ThemedText type="small" themeColor="textSecondary">
              {s.offRoute(formatDistance(ON_ROUTE_M))}
            </ThemedText>
          )}
          {warnings.length === 0 ? (
            <ThemedView type="backgroundElement" style={styles.note}>
              <ThemedText type="small" style={{ color: theme.success }}>
                {s.noWarnings}
              </ThemedText>
            </ThemedView>
          ) : (
            [...warnings]
              .sort((a, b) => a.distance_along_m - b.distance_along_m)
              .map((w, i) => {
                const passed = ahead ? w.distance_along_m <= ahead.userAlongM : false;
                const dist = ahead ? w.distance_along_m - ahead.userAlongM : w.distance_along_m;
                const label = passed
                  ? s.warningPassed(w.message)
                  : dist < 1
                    ? s.warningAtStart(w.message)
                    : s.warningAhead(formatDistance(dist), w.message);
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
                      <ThemedText type="small">{label}</ThemedText>
                      {tappable && (
                        <ThemedText type="small" style={{ color: theme.tint }}>
                          {c.details} ›
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
            {s.mapMobileOnly}
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
            <View style={styles.kind}>
              <Icon name="trash" size={16} color={theme.danger} />
              <ThemedText type="smallBold" style={{ color: theme.danger }}>
                {s.deleteRoute}
              </ThemedText>
            </View>
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
  kind: { flexDirection: 'row', alignItems: 'center', gap: Spacing.one },
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
