/**
 * M3 · Report a problem: text (required), optional photo, optional location.
 * After sending, a short status card (category, department, "N other people reported this", work state).
 * Reading the form is free; sending requires sign-in.
 */
import { router } from 'expo-router';
import { HeaderHeightContext } from 'expo-router/react-navigation';
import { useContext, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from 'react-native';

import { ActionButton } from '@/components/report/action-button';
import { LocationField } from '@/components/report/location-field';
import { PhotoPicker, type ReportPhoto } from '@/components/report/photo-picker';
import { ReportResult } from '@/components/report/report-result';
import { SignInNotice } from '@/components/report/sign-in-notice';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useLocation } from '@/hooks/use-location';
import { useTheme } from '@/hooks/use-theme';
import { reportText } from '@/i18n/report';
import { ApiError, submitReport, type MobileReport, type NewReport } from '@/lib/api';
import { useText } from '@/lib/i18n';
import { useSession } from '@/lib/session';

const MIN_TEXT = 5;
const MAX_TEXT = 2000;

export default function ReportScreen() {
  const theme = useTheme();
  const s = useText(reportText);
  const headerHeight = useContext(HeaderHeightContext) ?? 0;
  const { status, signOut } = useSession();
  const location = useLocation({ requestOnMount: true });
  const scrollRef = useRef<ScrollView>(null);

  const [text, setText] = useState('');
  const [photo, setPhoto] = useState<ReportPhoto | null>(null);
  const [attachLocation, setAttachLocation] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [result, setResult] = useState<MobileReport | null>(null);

  const signedIn = status === 'signedIn';
  const trimmed = text.trim();
  const textOk = trimmed.length >= MIN_TEXT;

  const submit = async () => {
    if (submitting) return;
    if (!signedIn) {
      router.push('/sign-in');
      return;
    }
    if (!textOk) {
      setError(s.tooShort(MIN_TEXT));
      return;
    }
    setError(null);
    setSessionExpired(false);
    setSubmitting(true);
    const report: NewReport = { text: trimmed };
    if (attachLocation && location.coords) {
      report.lon = location.coords.longitude;
      report.lat = location.coords.latitude;
    }
    if (photo) report.photo = photo;
    try {
      const sent = await submitReport(report);
      setResult(sent);
      scrollRef.current?.scrollTo({ y: 0, animated: false });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        // Token expired or revoked: drop it so the sign-in notice shows; the draft stays.
        setSessionExpired(true);
        await signOut();
      } else if (e instanceof ApiError) {
        setError(s.sendFailed(e.detail ?? e.message));
      } else {
        setError(s.sendFailed(e instanceof Error ? e.message : String(e)));
      }
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setText('');
    setPhoto(null);
    setError(null);
    setSessionExpired(false);
    setResult(null);
    if (attachLocation) void location.refresh();
  };

  const submitLabel =
    status === 'loading' ? s.sessionLoading : signedIn ? s.send : s.signInToSend;

  return (
    <ThemedView style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.screen}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={headerHeight}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive">
          <View style={styles.inner}>
            {result ? (
              <ReportResult report={result} onNew={reset} />
            ) : (
              <>
                <View style={styles.intro}>
                  <ThemedText type="smallBold" style={styles.heading}>
                    {s.heading}
                  </ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {s.intro}
                  </ThemedText>
                </View>

                {status === 'signedOut' ? (
                  <SignInNotice
                    message={sessionExpired ? s.sessionExpired : undefined}
                  />
                ) : null}

                <View style={styles.field}>
                  <ThemedText type="smallBold">{s.textLabel}</ThemedText>
                  <TextInput
                    value={text}
                    onChangeText={(value) => {
                      setText(value);
                      if (error) setError(null);
                    }}
                    placeholder={s.placeholder}
                    placeholderTextColor={theme.textSecondary}
                    multiline
                    maxLength={MAX_TEXT}
                    editable={!submitting}
                    textAlignVertical="top"
                    accessibilityLabel={s.textA11y}
                    style={[
                      styles.input,
                      { color: theme.text, backgroundColor: theme.backgroundElement, borderColor: theme.backgroundSelected },
                    ]}
                  />
                  {trimmed.length > 0 && !textOk ? (
                    <ThemedText type="small" themeColor="textSecondary">
                      {s.minChars(MIN_TEXT)}
                    </ThemedText>
                  ) : null}
                </View>

                <PhotoPicker photo={photo} onChange={setPhoto} disabled={submitting} />

                <LocationField
                  location={location}
                  attach={attachLocation}
                  onAttachChange={setAttachLocation}
                  disabled={submitting}
                />

                {error ? (
                  <View style={[styles.error, { borderColor: theme.danger }]}>
                    <ThemedText type="small" style={{ color: theme.danger }}>
                      {error}
                    </ThemedText>
                  </View>
                ) : null}

                <ActionButton
                  label={submitLabel}
                  onPress={submit}
                  loading={submitting}
                  disabled={status === 'loading' || (signedIn && !textOk)}
                  accessibilityHint={signedIn ? s.sendHint : s.signInHint}
                />
              </>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  content: {
    padding: Spacing.three,
    paddingBottom: Spacing.five,
  },
  inner: {
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
    gap: Spacing.four,
  },
  intro: {
    gap: Spacing.one,
  },
  heading: {
    fontSize: 20,
    lineHeight: 28,
  },
  field: {
    gap: Spacing.two,
  },
  input: {
    minHeight: 120,
    borderRadius: 12,
    borderWidth: 1,
    padding: Spacing.three,
    paddingTop: Spacing.three,
    fontSize: 16,
    lineHeight: 22,
  },
  error: {
    borderWidth: 1,
    borderRadius: 12,
    padding: Spacing.three,
  },
});
