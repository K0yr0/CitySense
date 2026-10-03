/**
 * M2 sign-in modal: Google (one tap) or demo sign-in by email (backend AUTH_DEV_LOGIN=1).
 * The device's anonymous contributor token is sent along, so trust earned before signing in
 * carries over to the account (lib/session.tsx, backend/auth/store.py).
 */
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useEffect, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ActionButton } from '@/components/profile/action-button';
import { GoogleSignInButton, googleUnavailableReason } from '@/components/profile/google-sign-in';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { MaxContentWidth, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { ApiError } from '@/lib/api';
import { useSession } from '@/lib/session';

// Web: Google redirects its popup back to this route; this closes the popup and hands over the result.
WebBrowser.maybeCompleteAuthSession();

const EMAIL_RE = /^[^@\s]+@[^@\s]+$/;
const GOOGLE_TIMEOUT_MS = 60000;

function googleErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 503) return 'Google girişi sunucuda ayarlı değil (GOOGLE_CLIENT_IDS).';
    if (e.status === 401) return 'Google hesabı doğrulanamadı. Tekrar dene.';
  }
  return e instanceof Error ? e.message : String(e);
}

function devErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return 'Demo girişi bu sunucuda kapalı (AUTH_DEV_LOGIN=1 gerekli).';
    if (e.status === 422) return 'Geçerli bir e-posta adresi yaz.';
  }
  return e instanceof Error ? e.message : String(e);
}

export default function SignInScreen() {
  const router = useRouter();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const { status, user, signInDev, signInWithGoogleIdToken } = useSession();

  const [email, setEmail] = useState('');
  const [devBusy, setDevBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const googleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const googleReason = googleUnavailableReason();
  const busy = devBusy || googleBusy;

  const finish = useCallback(() => {
    if (router.canGoBack()) router.back();
    else router.replace('/');
  }, [router]);

  const stopGoogle = useCallback(() => {
    if (googleTimer.current) clearTimeout(googleTimer.current);
    googleTimer.current = null;
    setGoogleBusy(false);
  }, []);

  useEffect(() => stopGoogle, [stopGoogle]);

  const onGoogleStart = useCallback(() => {
    setError(null);
    setGoogleBusy(true);
    if (googleTimer.current) clearTimeout(googleTimer.current);
    // The native code exchange can fail without a result; never leave the button spinning.
    googleTimer.current = setTimeout(() => {
      googleTimer.current = null;
      setGoogleBusy(false);
      setError('Google yanıt vermedi. Tekrar dene.');
    }, GOOGLE_TIMEOUT_MS);
  }, []);

  const onGoogleError = useCallback(
    (message: string) => {
      stopGoogle();
      setError(message);
    },
    [stopGoogle],
  );

  const onIdToken = useCallback(
    async (idToken: string) => {
      try {
        await signInWithGoogleIdToken(idToken);
        finish(); // the unmount cleanup clears the timer
      } catch (e) {
        stopGoogle();
        setError(googleErrorMessage(e));
      }
    },
    [signInWithGoogleIdToken, stopGoogle, finish],
  );

  const onDevSignIn = async () => {
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setError('Geçerli bir e-posta adresi yaz.');
      return;
    }
    setError(null);
    setDevBusy(true);
    try {
      await signInDev(value);
      finish();
    } catch (e) {
      setDevBusy(false);
      setError(devErrorMessage(e));
    }
  };

  return (
    <ThemedView style={styles.flex}>
      <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + Spacing.four }]}>
          <View style={styles.intro}>
            <ThemedText type="subtitle">CityEcho&apos;ya giriş</ThemedText>
            <ThemedText themeColor="textSecondary">
              Haritaya bakmak serbest. Sorun bildirmek ve çevrendeki sorulara cevap vermek için giriş yap.
            </ThemedText>
            <ThemedText type="small">Giriş yapmadan kazandığın güven puanı hesabına taşınır.</ThemedText>
          </View>

          {status === 'signedIn' && user && !busy && (
            <ThemedView type="backgroundElement" style={styles.card}>
              <ThemedText type="small">Zaten giriş yaptın: {user.email}</ThemedText>
              <ActionButton label="Kapat" variant="secondary" onPress={finish} />
            </ThemedView>
          )}

          <ThemedView type="backgroundElement" style={styles.card}>
            <ThemedText type="smallBold">Google</ThemedText>
            {googleReason ? (
              <>
                <ActionButton label="Google ile giriş yap" onPress={() => {}} disabled />
                <ThemedText type="small" themeColor="textSecondary">
                  {googleReason}
                </ThemedText>
              </>
            ) : (
              <GoogleSignInButton
                disabled={busy}
                loading={googleBusy}
                onStart={onGoogleStart}
                onCancel={stopGoogle}
                onIdToken={onIdToken}
                onError={onGoogleError}
              />
            )}
          </ThemedView>

          <ThemedView type="backgroundElement" style={styles.card}>
            <ThemedText type="smallBold">Demo girişi</ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              Yalnızca test ve sunum için: Google olmadan bir e-posta ile giriş.
            </ThemedText>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="ornek@eposta.pl"
              placeholderTextColor={theme.textSecondary}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              keyboardType="email-address"
              textContentType="emailAddress"
              returnKeyType="go"
              onSubmitEditing={onDevSignIn}
              editable={!busy}
              accessibilityLabel="E-posta"
              style={[
                styles.input,
                { color: theme.text, backgroundColor: theme.background, borderColor: theme.backgroundSelected },
              ]}
            />
            <ActionButton
              label="Demo girişi"
              variant="secondary"
              onPress={onDevSignIn}
              disabled={busy || !email.trim()}
              loading={devBusy}
            />
          </ThemedView>

          {error && (
            <ThemedText type="small" style={{ color: theme.danger }} accessibilityRole="alert">
              {error}
            </ThemedText>
          )}

          <ThemedText type="small" themeColor="textSecondary" style={styles.privacy}>
            Yalnızca e-posta ve adın saklanır; konum geçmişi tutulmaz.
          </ThemedText>
        </ScrollView>
      </KeyboardAvoidingView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  content: {
    padding: Spacing.three,
    gap: Spacing.three,
    width: '100%',
    maxWidth: MaxContentWidth,
    alignSelf: 'center',
  },
  intro: {
    gap: Spacing.two,
  },
  card: {
    padding: Spacing.three,
    borderRadius: Spacing.three,
    gap: Spacing.two,
  },
  input: {
    minHeight: 48,
    borderWidth: 1,
    borderRadius: Spacing.two,
    paddingHorizontal: Spacing.three,
    fontSize: 16,
  },
  privacy: {
    textAlign: 'center',
  },
});
