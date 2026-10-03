/**
 * Sign-in state (M2). Wrap the app in <SessionProvider>, read it with useSession().
 *
 * - `contributor`: an anonymous random token created on first launch and kept on the device.
 *   It is sent at login so trust earned before signing in carries over to the account
 *   (backend/auth/store.py link_contributor).
 * - The session token is stored on the device and handed to lib/api.ts (setAuthToken).
 * - Viewing the map needs no sign-in; reporting and answering do.
 */
import * as Crypto from 'expo-crypto';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { ApiError, getUser, loginDev, loginWithGoogle, setAuthToken, type Session, type User } from '@/lib/api';
import { getItem, removeItem, setItem } from '@/lib/storage';

const TOKEN_KEY = 'cityecho.session_token';
const USER_KEY = 'cityecho.session_user';
const CONTRIBUTOR_KEY = 'cityecho.contributor';

export type SessionStatus = 'loading' | 'signedOut' | 'signedIn';

export type SessionValue = {
  status: SessionStatus;
  user: User | null;
  /** Anonymous device token (trust carry-over). Null only while loading. */
  contributor: string | null;
  signInWithGoogleIdToken: (idToken: string) => Promise<User>;
  /** Demo / local sign-in (backend AUTH_DEV_LOGIN=1). */
  signInDev: (email: string) => Promise<User>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

async function deviceContributor(): Promise<string> {
  const existing = await getItem(CONTRIBUTOR_KEY);
  if (existing && existing.length >= 8) return existing;
  const fresh = `dev-${Crypto.randomUUID()}`;
  await setItem(CONTRIBUTOR_KEY, fresh);
  return fresh;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>('loading');
  const [user, setUser] = useState<User | null>(null);
  const [contributor, setContributor] = useState<string | null>(null);

  const clear = useCallback(async () => {
    setAuthToken(null);
    await Promise.all([removeItem(TOKEN_KEY), removeItem(USER_KEY)]);
    setUser(null);
    setStatus('signedOut');
  }, []);

  // Restore: device token + stored session. A stored user is shown at once (offline-friendly);
  // a 401 from /users/me signs out, other errors keep the session.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [token, storedUser, device] = await Promise.all([
        getItem(TOKEN_KEY),
        getItem(USER_KEY),
        deviceContributor(),
      ]);
      if (cancelled) return;
      setContributor(device);
      if (!token) {
        setStatus('signedOut');
        return;
      }
      setAuthToken(token);
      try {
        if (storedUser) setUser(JSON.parse(storedUser) as User);
      } catch {
        // corrupt cache: refreshed below
      }
      setStatus('signedIn');
      try {
        const fresh = await getUser();
        if (cancelled) return;
        setUser(fresh);
        await setItem(USER_KEY, JSON.stringify(fresh));
      } catch (e) {
        if (!cancelled && e instanceof ApiError && e.status === 401) await clear();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clear]);

  const accept = useCallback(async (session: Session) => {
    setAuthToken(session.token);
    await Promise.all([setItem(TOKEN_KEY, session.token), setItem(USER_KEY, JSON.stringify(session.user))]);
    setUser(session.user);
    setStatus('signedIn');
    return session.user;
  }, []);

  const signInWithGoogleIdToken = useCallback(
    async (idToken: string) => accept(await loginWithGoogle(idToken, contributor ?? undefined)),
    [accept, contributor],
  );

  const signInDev = useCallback(
    async (email: string) => accept(await loginDev(email.trim(), contributor ?? undefined)),
    [accept, contributor],
  );

  const value = useMemo<SessionValue>(
    () => ({ status, user, contributor, signInWithGoogleIdToken, signInDev, signOut: clear }),
    [status, user, contributor, signInWithGoogleIdToken, signInDev, clear],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error('useSession must be used inside <SessionProvider>');
  return value;
}
