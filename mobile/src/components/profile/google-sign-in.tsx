/**
 * Google sign-in button (M2) on expo-auth-session's Google provider.
 *
 * Client ids come from mobile/.env (EXPO_PUBLIC_GOOGLE_{WEB,IOS,ANDROID}_CLIENT_ID); the backend
 * must list the same ids in GOOGLE_CLIENT_IDS so it accepts the token's audience.
 * The provider throws when the current platform has no client id, so render
 * <GoogleSignInButton> only when `googleUnavailableReason()` is null.
 */
import Constants, { ExecutionEnvironment } from 'expo-constants';
import * as Google from 'expo-auth-session/providers/google';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';

import { ActionButton } from '@/components/profile/action-button';
import { profileText } from '@/i18n/profile';
import { text, useText } from '@/lib/i18n';

// Read each variable literally: Expo inlines EXPO_PUBLIC_* only for static `process.env.X` access.
const CLIENT_IDS = {
  web: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || undefined,
  ios: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || undefined,
  android: process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID || undefined,
};

function platformClientId(): string | undefined {
  if (Platform.OS === 'ios') return CLIENT_IDS.ios;
  if (Platform.OS === 'android') return CLIENT_IDS.android;
  return CLIENT_IDS.web;
}

/** Why Google sign-in cannot run here (one line in the current language), or null when it can. */
export function googleUnavailableReason(): string | null {
  if (Platform.OS !== 'web' && Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return text(profileText).googleExpoGo;
  }
  if (!platformClientId()) {
    const name =
      Platform.OS === 'ios' ? 'IOS' : Platform.OS === 'android' ? 'ANDROID' : 'WEB';
    return text(profileText).googleNotConfigured(`EXPO_PUBLIC_GOOGLE_${name}_CLIENT_ID`);
  }
  return null;
}

type Props = {
  disabled?: boolean;
  loading?: boolean;
  /** The popup/browser opened; the caller shows a spinner until onIdToken or onError. */
  onStart: () => void;
  /** User closed the browser without signing in. */
  onCancel: () => void;
  onIdToken: (idToken: string) => void;
  onError: (message: string) => void;
};

export function GoogleSignInButton({ disabled, loading, onStart, onCancel, onIdToken, onError }: Props) {
  const s = useText(profileText);
  const [request, response, promptAsync] = Google.useIdTokenAuthRequest(
    {
      webClientId: CLIENT_IDS.web,
      iosClientId: CLIENT_IDS.ios,
      androidClientId: CLIENT_IDS.android,
      selectAccount: true,
    },
    // Web: Google redirects the popup to /sign-in, where WebBrowser.maybeCompleteAuthSession() closes it.
    { path: 'sign-in' },
  );

  // Each response is handled once, even if the callbacks change identity.
  const handled = useRef<typeof response>(null);
  useEffect(() => {
    if (!response || handled.current === response) return;
    handled.current = response;
    if (response.type === 'success') {
      const idToken = response.params.id_token || response.authentication?.idToken;
      if (idToken) onIdToken(idToken);
      else onError(text(profileText).googleNoIdToken);
    } else if (response.type === 'error') {
      onError(response.error?.message || response.params.error_description || text(profileText).googleFailed);
    } else if (response.type === 'cancel' || response.type === 'dismiss') {
      onCancel();
    }
  }, [response, onIdToken, onError, onCancel]);

  const start = async () => {
    onStart();
    try {
      const result = await promptAsync();
      // On native a successful result still needs the code exchange; `response` reports it.
      if (result.type === 'cancel' || result.type === 'dismiss' || result.type === 'locked') onCancel();
    } catch (e) {
      onError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <ActionButton
      label={s.googleButton}
      onPress={start}
      disabled={disabled || !request}
      loading={loading}
    />
  );
}
