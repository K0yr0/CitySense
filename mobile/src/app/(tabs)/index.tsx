/**
 * M1 · Map: full-screen map with road health as colour only, open incidents as pins,
 * and the user's current position with its GPS accuracy ring. Looking at the map is free
 * (no sign-in). No sensor data, evidence or timelines are shown to the citizen.
 */
import { useIsFocused } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import { useRef, useState } from 'react';
import { Platform, StyleSheet, useColorScheme, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { IncidentCard } from '@/components/map/incident-card';
import { IncidentMap } from '@/components/map/incident-map';
import { Banner, Chip, HealthLegend, LocateButton } from '@/components/map/map-controls';
import type { IncidentMapHandle } from '@/components/map/types';
import { useMapData } from '@/components/map/use-map-data';
import { Spacing } from '@/constants/theme';
import { useLocation } from '@/hooks/use-location';
import type { PublicIncident } from '@/lib/api';
import { WARSAW_REGION } from '@/lib/geo';
import { useText } from '@/lib/i18n';
import { commonText } from '@/i18n/common';
import { mapText } from '@/i18n/map';

/** Constant object: <Tabs.Screen> re-applies options whenever their identity changes. */
const SCREEN_OPTIONS = { headerShown: false } as const;

/** The 25 m question is only asked with GPS accuracy at or below this (ROADMAP). */
const QUESTION_ACCURACY_M = 25;

/** Zoom used when centring on the user (~600 m tall). */
const USER_ZOOM = { latitudeDelta: 0.006, longitudeDelta: 0.006 };

const IS_WEB = Platform.OS === 'web';

export default function MapScreen() {
  const insets = useSafeAreaInsets();
  const dark = useColorScheme() === 'dark';
  const focused = useIsFocused();
  const mapRef = useRef<IncidentMapHandle>(null);
  const s = useText(mapText);
  const c = useText(commonText);

  const data = useMapData(WARSAW_REGION);
  const [selected, setSelected] = useState<PublicIncident | null>(null);
  const [showIncidents, setShowIncidents] = useState(true);
  const [showSegments, setShowSegments] = useState(true);

  // Location is only requested when the user taps the button; then it follows the user
  // while this tab is focused (no location history is kept anywhere).
  const [following, setFollowing] = useState(false);
  const [locating, setLocating] = useState(false);
  const location = useLocation({ watch: following && focused, requestOnMount: false });

  async function locate() {
    setLocating(true);
    const coords = await location.refresh();
    setLocating(false);
    if (!coords) return;
    setFollowing(true);
    mapRef.current?.animateTo({ ...coords, ...USER_ZOOM });
  }

  // Keep the card in sync with refreshed data; keep the last copy if it scrolled out of the box.
  const current = selected ? (data.incidents.find((i) => i.id === selected.id) ?? selected) : null;
  const card = showIncidents ? current : null;

  const user = following && location.coords ? { coords: location.coords, accuracy: location.accuracy } : null;
  const accuracy = user?.accuracy ?? null;

  const firstLoad = data.loading && data.incidents.length === 0 && data.segments.length === 0;
  const topInset = insets.top + Spacing.two + 44;
  const sideInsets = { left: insets.left + Spacing.three, right: insets.right + Spacing.three };

  return (
    <View style={styles.container}>
      <Tabs.Screen options={SCREEN_OPTIONS} />

      <IncidentMap
        ref={mapRef}
        initialRegion={WARSAW_REGION}
        segments={data.segments}
        incidents={data.incidents}
        showSegments={showSegments}
        showIncidents={showIncidents}
        selectedId={card?.id ?? null}
        user={user}
        dark={dark}
        topInset={topInset}
        bottomInset={IS_WEB ? 160 : 64}
        onRegionChangeComplete={data.setRegion}
        onSelectIncident={setSelected}
      />

      <View pointerEvents="box-none" style={[styles.top, sideInsets, { top: insets.top + Spacing.two }]}>
        {!IS_WEB && showSegments && <HealthLegend />}
        {data.error ? (
          <Banner tone="error" actionLabel={c.retry} onAction={data.reload}>
            {s.loadFailed(data.error)}
          </Banner>
        ) : firstLoad ? (
          <Banner>{c.loading}</Banner>
        ) : (
          !IS_WEB && showSegments && data.zoomedOut && <Banner>{s.zoomInForColors}</Banner>
        )}
      </View>

      <View pointerEvents="box-none" style={[styles.bottom, sideInsets]}>
        {location.error ? (
          <Banner tone="error">{location.error}</Banner>
        ) : (
          user &&
          accuracy != null && (
            <Banner>
              {accuracy > QUESTION_ACCURACY_M
                ? s.accuracyTooLow(Math.round(accuracy), QUESTION_ACCURACY_M)
                : s.accuracy(Math.round(accuracy))}
            </Banner>
          )
        )}

        <View pointerEvents="box-none" style={styles.controls}>
          <View pointerEvents="box-none" style={styles.chips}>
            <Chip active={showIncidents} onPress={() => setShowIncidents((v) => !v)}>
              {showIncidents ? '● ' : '○ '}
              {s.layers.incidents}
            </Chip>
            {!IS_WEB && (
              <Chip active={showSegments} onPress={() => setShowSegments((v) => !v)}>
                {showSegments ? '● ' : '○ '}
                {s.layers.roadColors}
              </Chip>
            )}
          </View>
          {!IS_WEB && <LocateButton onPress={locate} busy={locating} active={user !== null} />}
        </View>

        {card && <IncidentCard incident={card} onClose={() => setSelected(null)} />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  top: {
    position: 'absolute',
    gap: Spacing.two,
    alignItems: 'center',
  },
  bottom: {
    position: 'absolute',
    bottom: Spacing.three,
    gap: Spacing.two,
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: Spacing.two,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
    flexShrink: 1,
  },
});
