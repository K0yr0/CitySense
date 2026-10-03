/**
 * "Is this problem still there? Yes / No" on the tapped problem's card.
 *
 * Same rule as the 25 m question (ROADMAP decision): an answer counts only when the person is
 * within 25 m of the problem with GPS accuracy of 25 m or better, once per problem, weighted by
 * trust. The distance is checked here first, so a far-away tap never reaches the server.
 * Hidden for problems that are fixed or closed.
 */
import * as Location from 'expo-location';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import { useRequireSignIn } from '@/hooks/use-require-sign-in';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { mapText } from '@/i18n/map';
import { questionText } from '@/i18n/question';
import { ApiError, answerIncident, getIncident, type Answer, type PublicIncident } from '@/lib/api';
import { distanceM } from '@/lib/geo';
import { useText } from '@/lib/i18n';
import { useSession } from '@/lib/session';

/** Answer radius and the GPS accuracy it needs (metres), as on the server. */
const RADIUS_M = 25;
const FIX_TIMEOUT_MS = 15_000;
const OPEN_STATUSES = new Set(['candidate', 'likely']);

type Note = { text: string; tone: 'info' | 'success' | 'error' };

async function currentFix(): Promise<{ lat: number; lon: number; accuracy: number } | null> {
  const perm = await Location.getForegroundPermissionsAsync();
  const granted = perm.granted || (await Location.requestForegroundPermissionsAsync()).granted;
  if (!granted) return null;
  const pos = await Promise.race([
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
    new Promise<null>((resolve) => setTimeout(() => resolve(null), FIX_TIMEOUT_MS)),
  ]);
  if (!pos) return null;
  return { lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy ?? Infinity };
}

export function IncidentPoll({ incident }: { incident: PublicIncident }) {
  const theme = useTheme();
  const p = useText(mapText).poll;
  const q = useText(questionText);
  const c = useText(commonText);
  const { status: session } = useSession();
  const requireSignIn = useRequireSignIn();
  const [mine, setMine] = useState<Answer | null>(null);
  const [busy, setBusy] = useState<Answer | null>(null);
  const [note, setNote] = useState<Note | null>(null);

  // Signed in: ask the server whether this person already answered (once per problem).
  useEffect(() => {
    if (session !== 'signedIn') return;
    let alive = true;
    getIncident(incident.id)
      .then((detail) => alive && setMine(detail.my_answer))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [incident.id, session]);

  if (!OPEN_STATUSES.has(incident.status) || incident.work_status === 'done') return null;

  async function send(answer: Answer) {
    if (!requireSignIn()) return;
    setBusy(answer);
    setNote({ text: p.locating, tone: 'info' });
    try {
      const fix = await currentFix();
      if (!fix) return setNote({ text: q.noFix, tone: 'error' });
      if (fix.accuracy > RADIUS_M) return setNote({ text: p.lowAccuracy(Math.round(fix.accuracy)), tone: 'error' });
      const away = distanceM({ latitude: fix.lat, longitude: fix.lon }, { latitude: incident.lat, longitude: incident.lon });
      if (away > RADIUS_M) return setNote({ text: p.tooFar(Math.round(away)), tone: 'error' });

      const result = await answerIncident(incident.id, answer, { lon: fix.lon, lat: fix.lat, accuracy_m: fix.accuracy });
      setMine(answer);
      const trust = result.contributor_trust;
      setNote({ text: trust != null ? q.thanksTrust(`${Math.round(trust * 100)}%`) : q.thanks, tone: 'success' });
    } catch (e) {
      const status = e instanceof ApiError ? e.status : undefined;
      const text =
        status === 401 ? q.sessionExpired
        : status === 403 ? q.tooFar
        : status === 409 ? q.noLongerValid
        : status === 422 ? q.lowAccuracy
        : status === 404 ? q.gone
        : q.sendFailed;
      setNote({ text, tone: 'error' });
    } finally {
      setBusy(null);
    }
  }

  const noteColor = note?.tone === 'success' ? theme.success : note?.tone === 'error' ? theme.danger : theme.textSecondary;

  return (
    <View style={[styles.poll, { borderTopColor: theme.backgroundSelected }]}>
      <ThemedText type="smallBold">{p.title}</ThemedText>
      {mine ? (
        <ThemedText type="small" themeColor="textSecondary">
          {p.answered(mine === 'yes' ? c.yes : c.no)}
        </ThemedText>
      ) : (
        <>
          <View style={styles.buttons}>
            {(['yes', 'no'] as const).map((a) => (
              <Pressable
                key={a}
                onPress={() => void send(a)}
                disabled={busy !== null}
                accessibilityRole="button"
                accessibilityLabel={a === 'yes' ? q.yesA11y : q.noA11y}
                style={({ pressed }) => [
                  styles.button,
                  { backgroundColor: a === 'yes' ? theme.tint : theme.backgroundSelected },
                  (pressed || busy !== null) && styles.pressed,
                ]}>
                {busy === a ? (
                  <ActivityIndicator size="small" color={a === 'yes' ? 'white' : theme.text} />
                ) : (
                  <ThemedText type="smallBold" style={a === 'yes' ? styles.yesText : undefined}>
                    {a === 'yes' ? c.yes : c.no}
                  </ThemedText>
                )}
              </Pressable>
            ))}
          </View>
          {!note && (
            <ThemedText type="small" themeColor="textSecondary">
              {p.hint}
            </ThemedText>
          )}
        </>
      )}
      {note && (
        <ThemedText type="small" style={{ color: noteColor }} accessibilityLiveRegion="polite">
          {note.text}
        </ThemedText>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  poll: {
    gap: Spacing.two,
    paddingTop: Spacing.two,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  buttons: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  button: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 40,
    borderRadius: Spacing.three,
  },
  yesText: {
    color: 'white',
  },
  pressed: {
    opacity: 0.6,
  },
});
