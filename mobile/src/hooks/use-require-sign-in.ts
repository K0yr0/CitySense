/**
 * Gate for actions that need an account (reporting, answering the 25 m question).
 *
 *   const requireSignIn = useRequireSignIn();
 *   const onSubmit = () => { if (!requireSignIn()) return; ... };
 *
 * Returns true when signed in. When signed out it opens the /sign-in modal and returns false.
 * While the stored session is still loading it returns false without navigating.
 */
import { useRouter } from 'expo-router';
import { useCallback } from 'react';

import { useSession } from '@/lib/session';

export function useRequireSignIn(): () => boolean {
  const { status } = useSession();
  const router = useRouter();

  return useCallback(() => {
    if (status === 'signedIn') return true;
    if (status === 'signedOut') router.push('/sign-in');
    return false;
  }, [status, router]);
}
