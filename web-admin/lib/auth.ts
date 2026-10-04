// Admin session for the web admin (docs/ARCHITECTURE.md §8.1): {token, user} from POST /auth/google or /auth/dev,
// kept in localStorage and sent as "Authorization: Bearer <token>". Login calls live in lib/api.ts.
import { useSyncExternalStore } from "react";

export type Role = "citizen" | "admin";

/** GET /users/me, and the `user` of every login response. */
export interface User {
  id: number;
  email: string;
  name: string | null;
  role: Role;
}

export interface Session {
  token: string;
  user: User;
}

/** Google Sign-In for the web (must also be listed in the backend's GOOGLE_CLIENT_IDS). */
export const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";
/** Show the "sign in with email" form (backend needs AUTH_DEV_LOGIN=1). Local testing only. */
export const DEV_LOGIN = process.env.NEXT_PUBLIC_AUTH_DEV_LOGIN === "1";

const KEY = "citysense.admin.session";
const listeners = new Set<() => void>();
let cached: Session | null | undefined; // undefined = not read from storage yet

function isSession(x: unknown): x is Session {
  const s = x as Session | null;
  return !!s && typeof s.token === "string" && !!s.user && typeof s.user.email === "string";
}

function read(): Session | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) || "null");
    return isSession(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  if (cached === undefined) cached = read();
  return cached;
}

export function setSession(next: Session | null): void {
  cached = next;
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage blocked: the session lives in memory for this tab */
  }
  listeners.forEach((l) => l());
}

export const signOut = () => setSession(null);

function subscribe(l: () => void) {
  // Signing in or out in another tab updates this one too.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== KEY) return;
    cached = read();
    l();
  };
  listeners.add(l);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(l);
    window.removeEventListener("storage", onStorage);
  };
}

/** The current session; `undefined` while rendering on the server / before hydration. */
export function useSession(): Session | null | undefined {
  return useSyncExternalStore(subscribe, getSession, () => undefined);
}
