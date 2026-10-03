/**
 * M6: short incident view for citizens (docs/ROADMAP.md, ARCHITECTURE.md §8.4).
 * Type, address, confidence label and the city's work status. No sensor data, evidence,
 * timeline or raw report texts: GET /mobile/incidents/{id} does not return them.
 */
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  ConfidenceChip,
  DoneBanner,
  IncidentHeader,
  IncidentMiniMap,
  openInMaps,
  SectionCard,
  WorkStatusSteps,
} from '@/components/incident';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { ApiError, getIncident, type IncidentDetail } from '@/lib/api';
import { incidentColor, timeAgo, typeLabel } from '@/lib/labels';
import { useSession } from '@/lib/session';

function parseId(raw: string | string[] | undefined): number | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : null;
}

type FetchResult =
  | { kind: 'ok'; incident: IncidentDetail }
  | { kind: 'notFound' }
  | { kind: 'error'; message: string };

async function fetchIncident(id: number): Promise<FetchResult> {
  try {
    return { kind: 'ok', incident: await getIncident(id) };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return { kind: 'notFound' };
    return { kind: 'error', message: e instanceof Error ? e.message : String(e) };
  }
}

export default function IncidentScreen() {
  const params = useLocalSearchParams<{ id: string }>();
  const id = parseId(params.id);
  const { user } = useSession();
  const userId = user?.id ?? null;

  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const requestSeq = useRef(0);

  const apply = useCallback((seq: number, result: FetchResult) => {
    if (seq !== requestSeq.current) return; // a newer request is in flight
    if (result.kind === 'ok') {
      setIncident(result.incident);
      setNotFound(false);
      setError(null);
    } else if (result.kind === 'notFound') {
      setIncident(null);
      setNotFound(true);
      setError(null);
    } else {
      setError(result.message);
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  const load = useCallback(() => {
    if (id === null) return;
    const seq = ++requestSeq.current;
    fetchIncident(id).then((result) => apply(seq, result));
  }, [id, apply]);

  // Reload when the signed-in user changes: my_answer / i_reported depend on the token.
  useEffect(() => {
    if (id === null) return;
    const seq = ++requestSeq.current;
    fetchIncident(id).then((result) => apply(seq, result));
  }, [id, userId, apply]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    load();
  }, [load]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    load();
  }, [load]);

  if (id === null || notFound) {
    return (
      <CenteredMessage
        icon="🔍"
        title="Bu sorun bulunamadı"
        body="Sorun kaldırılmış ya da bağlantı hatalı olabilir."
        action={{ label: 'Geri dön', onPress: goBack }}
      />
    );
  }

  if (!incident) {
    if (loading) {
      return <LoadingView />;
    }
    return (
      <CenteredMessage
        icon="📡"
        title="Sorun yüklenemedi"
        body={error ?? 'Bilinmeyen bir hata oluştu.'}
        action={{ label: 'Tekrar dene', onPress: retry }}
      />
    );
  }

  return <IncidentBody incident={incident} error={error} refreshing={refreshing} onRefresh={refresh} />;
}

function goBack() {
  if (router.canGoBack()) router.back();
  else router.replace('/');
}

function IncidentBody({
  incident,
  error,
  refreshing,
  onRefresh,
}: {
  incident: IncidentDetail;
  error: string | null;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const done = incident.work_status === 'done';
  const title = typeLabel(incident.type);
  const firstSeen = timeAgo(incident.first_seen);
  const lastSeen = timeAgo(incident.last_seen);

  return (
    <ThemedView style={styles.fill}>
      <Stack.Screen options={{ title }} />
      <ScrollView
        style={styles.fill}
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.five }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.tint} />}>
        {error ? (
          <ThemedText type="small" style={{ color: theme.danger }}>
            Güncellenemedi: {error}
          </ThemedText>
        ) : null}

        {done ? <DoneBanner /> : null}

        <IncidentHeader type={incident.type} address={incident.address} department={incident.department} />

        <View style={styles.facts}>
          {incident.report_count > 0 ? (
            <Fact icon="👥">
              {incident.report_count} kişi bildirdi
            </Fact>
          ) : null}
          {firstSeen || lastSeen ? (
            <Fact icon="🕒">
              {[firstSeen && `İlk görülme: ${firstSeen}`, lastSeen && `Son: ${lastSeen}`]
                .filter(Boolean)
                .join(' · ')}
            </Fact>
          ) : null}
          {incident.message ? <Fact icon="ℹ️">{incident.message}</Fact> : null}
        </View>

        {incident.i_reported || incident.my_answer ? (
          <View style={styles.badges}>
            {incident.i_reported ? <Badge>Bunu sen bildirdin</Badge> : null}
            {incident.my_answer ? (
              <Badge>Cevabın: {incident.my_answer === 'yes' ? 'Evet' : 'Hayır'}</Badge>
            ) : null}
          </View>
        ) : null}

        <SectionCard title="Güven">
          <ConfidenceChip status={incident.status} confidence={incident.confidence} />
        </SectionCard>

        <SectionCard title="Belediye">
          <WorkStatusSteps workStatus={incident.work_status} />
        </SectionCard>

        <IncidentMiniMap lon={incident.lon} lat={incident.lat} color={incidentColor(incident)} title={title} />
        <Pressable
          onPress={() => openInMaps(incident.lon, incident.lat, incident.address || title)}
          accessibilityRole="button"
          style={({ pressed }) => [styles.mapButton, { borderColor: theme.tint }, pressed && styles.pressed]}>
          <ThemedText type="smallBold" style={{ color: theme.tint }}>
            Haritada aç
          </ThemedText>
        </Pressable>
      </ScrollView>
    </ThemedView>
  );
}

function Fact({ icon, children }: { icon: string; children: ReactNode }) {
  return (
    <View style={styles.fact}>
      <ThemedText type="small" style={styles.factIcon}>
        {icon}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary" style={styles.factText}>
        {children}
      </ThemedText>
    </View>
  );
}

function Badge({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.badge, { backgroundColor: theme.backgroundSelected }]}>
      <ThemedText type="smallBold">{children}</ThemedText>
    </View>
  );
}

function LoadingView() {
  const theme = useTheme();
  return (
    <ThemedView style={[styles.fill, styles.center]}>
      <ActivityIndicator size="large" color={theme.tint} />
    </ThemedView>
  );
}

function CenteredMessage({
  icon,
  title,
  body,
  action,
}: {
  icon: string;
  title: string;
  body: string;
  action: { label: string; onPress: () => void };
}) {
  const theme = useTheme();
  return (
    <ThemedView style={[styles.fill, styles.center]}>
      <ThemedText style={styles.bigIcon}>{icon}</ThemedText>
      <ThemedText type="smallBold" style={styles.centerTitle}>
        {title}
      </ThemedText>
      <ThemedText type="small" themeColor="textSecondary" style={styles.centerText}>
        {body}
      </ThemedText>
      <Pressable
        onPress={action.onPress}
        accessibilityRole="button"
        style={({ pressed }) => [styles.mapButton, { borderColor: theme.tint }, pressed && styles.pressed]}>
        <ThemedText type="smallBold" style={{ color: theme.tint }}>
          {action.label}
        </ThemedText>
      </Pressable>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: Spacing.four,
    gap: Spacing.two,
  },
  content: {
    padding: Spacing.three,
    gap: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  facts: {
    gap: Spacing.one,
  },
  fact: {
    flexDirection: 'row',
    gap: Spacing.two,
    alignItems: 'flex-start',
  },
  factIcon: {
    width: 22,
    textAlign: 'center',
  },
  factText: {
    flex: 1,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  badge: {
    paddingVertical: Spacing.one,
    paddingHorizontal: Spacing.three,
    borderRadius: 999,
  },
  mapButton: {
    alignSelf: 'center',
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.four,
    borderRadius: Spacing.four,
    borderWidth: 1,
  },
  pressed: {
    opacity: 0.6,
  },
  bigIcon: {
    fontSize: 40,
    lineHeight: 48,
  },
  centerTitle: {
    fontSize: 18,
    lineHeight: 24,
    textAlign: 'center',
  },
  centerText: {
    textAlign: 'center',
    marginBottom: Spacing.two,
  },
});
