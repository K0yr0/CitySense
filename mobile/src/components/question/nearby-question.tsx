/**
 * M4: "Do you see a pothole within 25 m of you? Yes / No" — a card floating above the tab bar.
 *
 * Mounted once in app/_layout.tsx above every screen. Renders nothing when signed out, when
 * location permission is denied, or when there is nothing to ask. Logic: hooks/use-nearby-question.
 * The citizen sees only the question, the type and the address; never sensor data.
 */
import { useEffect, useState } from 'react';
import { ActivityIndicator, Animated, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { questionFor } from '@/components/question/question-text';
import { useNearbyQuestion, type NearbyQuestionState } from '@/hooks/use-nearby-question';
import { useTheme } from '@/hooks/use-theme';
import { commonText } from '@/i18n/common';
import { questionText } from '@/i18n/question';
import { useText } from '@/lib/i18n';
import { TYPE_ICONS } from '@/lib/labels';
import { useSession } from '@/lib/session';

/** Room left for the bottom tab bar (plus the safe-area inset). */
const TAB_BAR_SPACE = 60;

export function NearbyQuestion() {
  const { status, user } = useSession();
  if (status !== 'signedIn') return null;
  // Keyed by user: signing in as someone else starts from a clean state.
  return <NearbyQuestionOverlay key={user?.id ?? 'me'} />;
}

function NearbyQuestionOverlay() {
  const question = useNearbyQuestion();
  if (question.phase === 'hidden' || !question.incident) return null;
  return <QuestionCard question={question} />;
}

function QuestionCard({ question }: { question: NearbyQuestionState }) {
  const theme = useTheme();
  const s = useText(questionText);
  const c = useText(commonText);
  const insets = useSafeAreaInsets();
  const [appear] = useState(() => new Animated.Value(0));
  const { incident, phase, message, tone, answer, skip } = question;

  useEffect(() => {
    Animated.timing(appear, {
      toValue: 1,
      duration: 220,
      useNativeDriver: Platform.OS !== 'web',
    }).start();
  }, [appear]);

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
              <Text style={styles.icon}>{TYPE_ICONS[incident.type] ?? TYPE_ICONS.other}</Text>
              <View style={styles.headerText}>
                <Text style={[styles.question, { color: theme.text }]}>{questionFor(incident.type, s)}</Text>
                {incident.address ? (
                  <Text numberOfLines={1} style={[styles.address, { color: theme.textSecondary }]}>
                    {incident.address}
                  </Text>
                ) : null}
              </View>
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
                <Text style={[styles.buttonText, { color: '#ffffff' }]}>{c.yes}</Text>
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
                <Text style={[styles.buttonText, { color: theme.text }]}>{c.no}</Text>
              </Pressable>
            </View>

            <View style={styles.footer}>
              {sending ? (
                <ActivityIndicator size="small" color={theme.textSecondary} />
              ) : (
                <Pressable accessibilityRole="button" onPress={skip} hitSlop={8}>
                  <Text style={[styles.skip, { color: theme.textSecondary }]}>{s.notNow}</Text>
                </Pressable>
              )}
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
    padding: 16,
    gap: 12,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  icon: { fontSize: 28, lineHeight: 34 },
  headerText: { flex: 1, gap: 2 },
  question: { fontSize: 17, lineHeight: 23, fontWeight: '700' },
  address: { fontSize: 14, lineHeight: 20 },
  message: { fontSize: 14, lineHeight: 20, fontWeight: '500' },
  buttons: { flexDirection: 'row', gap: 10 },
  button: { flex: 1, minHeight: 46, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  buttonText: { fontSize: 16, fontWeight: '700' },
  footer: { alignItems: 'center', minHeight: 20, justifyContent: 'center' },
  skip: { fontSize: 14, textDecorationLine: 'underline' },
  closing: { fontSize: 16, lineHeight: 22, fontWeight: '600', textAlign: 'center' },
});
