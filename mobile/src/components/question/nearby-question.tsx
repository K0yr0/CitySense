/**
 * M4: "Is there a pothole here? Yes / No" — a compact, Google Maps style prompt above the tab bar
 * when the user comes within 25 m of an open problem. Closes itself after 15 s.
 *
 * Mounted once in app/_layout.tsx above every screen. Renders nothing when signed out, when
 * location permission is denied, or when there is nothing to ask. Logic: hooks/use-nearby-question.
 * The citizen sees only the question, the type and the address; never sensor data.
 */
import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { TypeIcon } from '@/components/icon';
import { questionFor } from '@/components/question/question-text';
import { useNearbyQuestion, type NearbyQuestionState } from '@/hooks/use-nearby-question';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { questionText } from '@/i18n/question';
import { useText } from '@/lib/i18n';
import { useSession } from '@/lib/session';

/** Room left for the bottom tab bar (plus the safe-area inset). */
const TAB_BAR_SPACE = 60;

/** The question closes by itself (like "Not now") if nobody answers within this time. */
const AUTO_DISMISS_MS = 15_000;

export function NearbyQuestion() {
  const { status, user } = useSession();
  if (status !== 'signedIn') return null;
  // Keyed by user: signing in as someone else starts from a clean state.
  return <NearbyQuestionOverlay key={user?.id ?? 'me'} />;
}

function NearbyQuestionOverlay() {
  const question = useNearbyQuestion();
  if (question.phase === 'hidden' || !question.incident) return null;
  // Keyed by incident: each new question gets a fresh countdown and appear animation.
  return <QuestionCard key={question.incident.id} question={question} />;
}

/** Google Maps style: short question, two big buttons, closes itself after AUTO_DISMISS_MS. */
function QuestionCard({ question }: { question: NearbyQuestionState }) {
  const theme = useTheme();
  const s = useText(questionText);
  const c = useText(commonText);
  const insets = useSafeAreaInsets();
  const [appear] = useState(() => new Animated.Value(0));
  const [countdown] = useState(() => new Animated.Value(1));
  const { incident, phase, message, tone, answer, skip } = question;

  // Slide in with a light vibration, so it is noticed while walking or riding.
  useEffect(() => {
    Animated.timing(appear, { toValue: 1, duration: 220, useNativeDriver: Platform.OS !== 'web' }).start();
    if (Platform.OS !== 'web') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
    }
  }, [appear]);

  // Countdown bar; when it runs out while still asking, the question closes like "Not now".
  useEffect(() => {
    if (phase !== 'asking') {
      countdown.stopAnimation();
      return;
    }
    const run = Animated.timing(countdown, { toValue: 0, duration: AUTO_DISMISS_MS, useNativeDriver: false });
    run.start(({ finished }) => {
      if (finished) skip();
    });
    return () => run.stop();
  }, [phase, countdown, skip]);

  if (!incident) return null;
  const sending = phase === 'sending';
  const closing = phase === 'closing';
  const toneColor =
    tone === 'success' ? theme.success : tone === 'error' ? theme.danger : theme.textSecondary;

  return (
    <View pointerEvents="box-none" style={StyleSheet.absoluteFill}>
      <Animated.View
        accessibilityLiveRegion="polite"
        style={[
          styles.card,
          {
            bottom: insets.bottom + TAB_BAR_SPACE,
            backgroundColor: theme.background,
            borderColor: theme.backgroundSelected,
            opacity: appear,
            transform: [{ translateY: appear.interpolate({ inputRange: [0, 1], outputRange: [40, 0] }) }],
          },
        ]}>
        {closing ? (
          <Text style={[styles.closing, { color: toneColor }]}>{message}</Text>
        ) : (
          <>
            <View style={styles.header}>
              <View style={[styles.iconBubble, { backgroundColor: theme.backgroundElement }]}>
                <TypeIcon type={incident.type} size={22} color={theme.tint} />
              </View>
              <View style={styles.headerText}>
                <Text numberOfLines={2} style={[styles.question, { color: theme.text }]}>
                  {questionFor(incident.type, s)}
                </Text>
                {incident.address ? (
                  <Text numberOfLines={1} style={[styles.address, { color: theme.textSecondary }]}>
                    {incident.address}
                  </Text>
                ) : null}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={s.closeA11y}
                onPress={skip}
                disabled={sending}
                hitSlop={10}
                style={[styles.close, { backgroundColor: theme.backgroundElement }]}>
                <Text style={[styles.closeText, { color: theme.textSecondary }]}>✕</Text>
              </Pressable>
            </View>

            {message ? <Text style={[styles.message, { color: toneColor }]}>{message}</Text> : null}

            <View style={styles.buttons}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={s.yesA11y}
                disabled={sending}
                onPress={() => void answer('yes')}
                style={({ pressed }) => [
                  styles.button,
                  { backgroundColor: theme.tint, opacity: pressed || sending ? 0.6 : 1 },
                ]}>
                {sending ? (
                  <ActivityIndicator size="small" color="#ffffff" />
                ) : (
                  <Text style={[styles.buttonText, { color: '#ffffff' }]}>✓  {c.yes}</Text>
                )}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={s.noA11y}
                disabled={sending}
                onPress={() => void answer('no')}
                style={({ pressed }) => [
                  styles.button,
                  { backgroundColor: theme.backgroundSelected, opacity: pressed || sending ? 0.6 : 1 },
                ]}>
                <Text style={[styles.buttonText, { color: theme.text }]}>✕  {c.no}</Text>
              </Pressable>
            </View>

            <View style={[styles.track, { backgroundColor: theme.backgroundElement }]}>
              <Animated.View
                style={[
                  styles.bar,
                  {
                    backgroundColor: theme.tint,
                    width: countdown.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }),
                  },
                ]}
              />
            </View>
          </>
        )}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: 'absolute',
    left: 12,
    right: 12,
    alignSelf: 'center',
    maxWidth: 520,
    marginHorizontal: 'auto',
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    paddingTop: 14,
    paddingHorizontal: 14,
    paddingBottom: 12,
    gap: 12,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconBubble: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, gap: 2 },
  question: { fontSize: 17, lineHeight: 22, fontWeight: '700' },
  address: { fontSize: 13, lineHeight: 18 },
  close: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  closeText: { fontSize: 14, fontWeight: '700' },
  message: { fontSize: 14, lineHeight: 20, fontWeight: '500' },
  buttons: { flexDirection: 'row', gap: 10 },
  button: { flex: 1, minHeight: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  buttonText: { fontSize: 16, fontWeight: '700' },
  track: { height: 3, borderRadius: 2, overflow: 'hidden' },
  bar: { height: 3, borderRadius: 2 },
  closing: { fontSize: 16, lineHeight: 22, fontWeight: '600', textAlign: 'center', paddingBottom: 2 },
});
