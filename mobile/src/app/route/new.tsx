/**
 * M5 · Add a favourite route: start/end pins on a map, or a bus/tram line.
 * Static segment `new` wins over the dynamic `route/[id]` in Expo Router, so /route/new lands here.
 */
import { router, Stack } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PointPicker } from '@/components/routes/point-picker';
import { modeLabel } from '@/components/routes/route-geometry';
import { RoutesSignInGate } from '@/components/routes/sign-in-prompt';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useLocation } from '@/hooks/use-location';
import { useTheme } from '@/hooks/use-theme';
import { ApiError, createRoute, getLines, type LonLat, type Mode, type NewRoute, type TransitLine } from '@/lib/api';
import { distanceM, toLatLng } from '@/lib/geo';
import { useSession } from '@/lib/session';

type Kind = 'points' | 'line';

type LinesState = { mode: Mode; lines: TransitLine[] | null; error: boolean };

function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const theme = useTheme();
  return (
    <View style={[styles.segmented, { backgroundColor: theme.backgroundElement }]} accessibilityRole="tablist">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => onChange(o.value)}
            style={[styles.segment, active && { backgroundColor: theme.background }]}>
            <ThemedText type="smallBold" style={active ? { color: theme.tint } : undefined} themeColor="textSecondary">
              {o.label}
            </ThemedText>
          </Pressable>
        );
      })}
    </View>
  );
}

function saveErrorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return 'Oturumun sona ermiş. Lütfen yeniden giriş yap.';
    if (e.status === 409) return 'Kaydedilebilecek en fazla rota sayısına ulaştın. Önce bir rotayı sil.';
    if (e.status === 422) return 'Rota bilgileri geçersiz. Başlangıç ve bitiş farklı olmalı.';
  }
  return e instanceof Error ? e.message : String(e);
}

export default function NewRouteScreen() {
  const { status } = useSession();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { refresh: locate } = useLocation({ requestOnMount: false });

  const [kind, setKind] = useState<Kind>('points');
  const [name, setName] = useState('');
  const [start, setStart] = useState<LonLat | null>(null);
  const [end, setEnd] = useState<LonLat | null>(null);
  const [mode, setMode] = useState<Mode>('tram');
  const [line, setLine] = useState('');
  const [linesState, setLinesState] = useState<LinesState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (kind !== 'line') return;
    let cancelled = false;
    getLines(mode).then(
      (lines) => {
        if (!cancelled) setLinesState({ mode, lines, error: false });
      },
      () => {
        if (!cancelled) setLinesState({ mode, lines: [], error: true });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [kind, mode]);

  if (status !== 'signedIn') {
    return (
      <>
        <Stack.Screen options={{ headerShown: true, title: 'Rota ekle' }} />
        <RoutesSignInGate status={status} />
      </>
    );
  }

  const lines = linesState?.mode === mode ? linesState : null;
  const trimmedLine = line.trim();
  const defaultName = kind === 'points' ? 'Ev → İş' : trimmedLine ? `${modeLabel(mode)} ${trimmedLine}` : `${modeLabel(mode)} hattı`;
  const tooClose = !!(start && end && distanceM(toLatLng(start), toLatLng(end)) < 20);
  const canSave = !saving && (kind === 'points' ? !!start && !!end && !tooClose : trimmedLine.length > 0);

  const save = async () => {
    if (!canSave) return;
    const routeName = (name.trim() || defaultName).slice(0, 100);
    let body: NewRoute;
    if (kind === 'points') {
      if (!start || !end) return;
      body = { name: routeName, kind: 'points', start, end, mode: 'road' };
    } else {
      body = { name: routeName, kind: 'line', line: trimmedLine.slice(0, 20), mode };
    }
    setSaving(true);
    setError(null);
    try {
      const created = await createRoute(body);
      router.replace(`/route/${created.id}`);
    } catch (e) {
      setError(saveErrorText(e));
      setSaving(false);
    }
  };

  const inputStyle = [styles.input, { color: theme.text, borderColor: theme.backgroundSelected }];

  return (
    <ThemedView style={styles.flex}>
      <Stack.Screen options={{ headerShown: true, title: 'Rota ekle' }} />
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.five }]}>
          <Segmented<Kind>
            value={kind}
            onChange={(k) => {
              setKind(k);
              setError(null);
            }}
            options={[
              { value: 'points', label: 'Başlangıç–bitiş' },
              { value: 'line', label: 'Otobüs-tramvay hattı' },
            ]}
          />

          <View style={styles.field}>
            <ThemedText type="smallBold">Rota adı</ThemedText>
            <TextInput
              value={name}
              onChangeText={setName}
              placeholder={defaultName}
              placeholderTextColor={theme.textSecondary}
              maxLength={100}
              returnKeyType="done"
              style={inputStyle}
            />
          </View>

          {kind === 'points' ? (
            <View style={styles.field}>
              <ThemedText type="smallBold">Başlangıç ve bitiş</ThemedText>
              <PointPicker
                start={start}
                end={end}
                locate={locate}
                onChange={(s, e) => {
                  setStart(s);
                  setEnd(e);
                }}
              />
              {tooClose && (
                <ThemedText type="small" style={{ color: theme.danger }}>
                  Başlangıç ve bitiş birbirine çok yakın.
                </ThemedText>
              )}
            </View>
          ) : (
            <View style={styles.field}>
              <ThemedText type="smallBold">Araç</ThemedText>
              <Segmented<Mode>
                value={mode}
                onChange={(m) => {
                  setMode(m);
                  setLine('');
                }}
                options={[
                  { value: 'tram', label: '🚋 Tramvay' },
                  { value: 'road', label: '🚌 Otobüs' },
                ]}
              />

              <ThemedText type="smallBold" style={styles.subLabel}>
                Hat
              </ThemedText>
              {!lines ? (
                <ActivityIndicator color={theme.tint} style={styles.linesLoading} />
              ) : lines.lines && lines.lines.length > 0 ? (
                <View style={styles.chips}>
                  {lines.lines.map((l) => {
                    const active = l.line === trimmedLine;
                    return (
                      <Pressable
                        key={`${l.mode}-${l.line}`}
                        accessibilityRole="button"
                        accessibilityState={{ selected: active }}
                        onPress={() => setLine(l.line)}
                        style={[
                          styles.chip,
                          { borderColor: active ? theme.tint : theme.backgroundSelected },
                          active && { backgroundColor: theme.tint },
                        ]}>
                        <ThemedText type="smallBold" style={active ? styles.chipActiveText : undefined}>
                          {l.line}
                        </ThemedText>
                      </Pressable>
                    );
                  })}
                </View>
              ) : (
                <ThemedText type="small" themeColor="textSecondary">
                  {lines.error
                    ? 'Hat listesi alınamadı. Hat numarasını aşağıya yazabilirsin.'
                    : `Henüz ölçüm yapılmış ${modeLabel(mode).toLowerCase()} hattı yok. Hat numarasını aşağıya yazabilirsin.`}
                </ThemedText>
              )}

              <TextInput
                value={line}
                onChangeText={setLine}
                placeholder={mode === 'tram' ? 'Hat numarası, ör. 17' : 'Hat numarası, ör. 175'}
                placeholderTextColor={theme.textSecondary}
                autoCapitalize="characters"
                autoCorrect={false}
                maxLength={20}
                style={inputStyle}
              />
              <ThemedText type="small" themeColor="textSecondary">
                Yol durumu, bu hattaki araçların geçtiği yollardan hesaplanır.
              </ThemedText>
            </View>
          )}

          {error && (
            <ThemedText type="small" style={{ color: theme.danger }}>
              {error}
            </ThemedText>
          )}

          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: !canSave }}
            disabled={!canSave}
            onPress={save}
            style={({ pressed }) => [
              styles.save,
              { backgroundColor: theme.tint },
              !canSave && styles.disabled,
              pressed && styles.pressed,
            ]}>
            {saving ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <ThemedText type="smallBold" style={styles.saveText}>
                Kaydet
              </ThemedText>
            )}
          </Pressable>
          {kind === 'points' && (!start || !end) && (
            <ThemedText type="small" themeColor="textSecondary" style={styles.center}>
              Kaydetmek için başlangıç ve bitiş noktası seç.
            </ThemedText>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    padding: Spacing.three,
    gap: Spacing.four,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  segmented: { flexDirection: 'row', borderRadius: Spacing.three, padding: Spacing.one },
  segment: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two + 4,
  },
  field: { gap: Spacing.two },
  subLabel: { marginTop: Spacing.two },
  input: {
    borderWidth: 1,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingVertical: Spacing.two + 2,
    fontSize: 16,
  },
  linesLoading: { alignSelf: 'flex-start', marginVertical: Spacing.two },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.two },
  chip: {
    minWidth: 48,
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: Spacing.four,
    paddingVertical: Spacing.one + 2,
    paddingHorizontal: Spacing.three,
  },
  chipActiveText: { color: '#ffffff' },
  save: { alignItems: 'center', paddingVertical: Spacing.three, borderRadius: Spacing.three },
  saveText: { color: '#ffffff', fontSize: 16 },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.7 },
  center: { textAlign: 'center' },
});
