"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";
import { ApiError, loginDev, loginWithGoogle } from "@/lib/api";
import { DEV_LOGIN, GOOGLE_CLIENT_ID } from "@/lib/auth";
import { USE_MOCK } from "@/lib/demo";
import { usePrefersDark } from "@/lib/hooks";
import { Logo } from "../Header";

// Minimal typing for Google Identity Services (https://accounts.google.com/gsi/client).
interface GoogleId {
  initialize(cfg: { client_id: string; callback: (r: { credential?: string }) => void; ux_mode?: "popup" }): void;
  renderButton(el: HTMLElement, opts: Record<string, string | number>): void;
}
declare global {
  interface Window {
    google?: { accounts: { id: GoogleId } };
  }
}

const GSI_SRC = "https://accounts.google.com/gsi/client";

function loadGsi(): Promise<GoogleId> {
  if (window.google?.accounts?.id) return Promise.resolve(window.google.accounts.id);
  return new Promise((resolve, reject) => {
    let s = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (!s) {
      s = document.createElement("script");
      s.src = GSI_SRC;
      s.async = true;
      document.head.appendChild(s);
    }
    s.addEventListener("load", () => (window.google ? resolve(window.google.accounts.id) : reject(new Error("Google script loaded without API"))));
    s.addEventListener("error", () => reject(new Error("Could not load Google Sign-In")));
  });
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return "Email sign-in is turned off on the backend (AUTH_DEV_LOGIN=0).";
    if (err.status === 503) return "Google sign-in is not configured on the backend (GOOGLE_CLIENT_IDS).";
    return err.message;
  }
  if (err instanceof Error && err.name === "AbortError") return "The backend did not answer in time.";
  return "Could not reach the backend. Is it running?";
}

function GoogleButton({ onToken }: { onToken: (idToken: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const dark = usePrefersDark();
  const [failed, setFailed] = useState<string | null>(null);
  const onCredential = useEffectEvent((idToken: string) => onToken(idToken));

  useEffect(() => {
    let alive = true;
    loadGsi()
      .then((gsi) => {
        if (!alive || !ref.current) return;
        gsi.initialize({ client_id: GOOGLE_CLIENT_ID, ux_mode: "popup", callback: (r) => r.credential && onCredential(r.credential) });
        ref.current.replaceChildren();
        gsi.renderButton(ref.current, { theme: dark ? "filled_black" : "outline", size: "large", text: "signin_with", shape: "pill", width: 320 });
      })
      .catch((e: Error) => alive && setFailed(e.message));
    return () => {
      alive = false;
    };
  }, [dark]);

  if (failed) return <p className="text-sm font-medium text-warn-ink">{failed}</p>;
  return <div ref={ref} className="flex min-h-11 justify-center" />;
}

/** Full-page sign-in. The whole web admin is for municipal staff only (role = admin). */
export default function LoginView() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const showGoogle = Boolean(GOOGLE_CLIENT_ID) && !USE_MOCK;
  const showEmail = DEV_LOGIN || USE_MOCK;

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(describe(err));
    } finally {
      setBusy(false);
    }
  };

  const onEmail = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim()) run(() => loginDev(email.trim().toLowerCase()));
  };

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-7 shadow-sm">
        <div className="flex items-center gap-3">
          <Logo size={40} />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">CityEcho admin</h1>
            <p className="text-ink-2">Warsaw municipal dashboard</p>
          </div>
        </div>
        <p className="mt-5 text-lg text-ink-2">
          Sign in with a city account. Only emails on the admin list can open the incident queue, workflow and live map.
        </p>

        <div className="mt-6 flex flex-col gap-4">
          {showGoogle && <GoogleButton onToken={(t) => run(() => loginWithGoogle(t))} />}

          {showGoogle && showEmail && (
            <div className="flex items-center gap-3 text-sm text-muted">
              <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
            </div>
          )}

          {showEmail && (
            <form onSubmit={onEmail} className="flex flex-col gap-2.5">
              <label htmlFor="login-email" className="text-sm font-semibold text-ink-2">
                {USE_MOCK ? "Demo mode: any email signs in as admin" : "Email (local testing, AUTH_DEV_LOGIN=1)"}
              </label>
              <input
                id="login-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@um.warszawa.pl"
                className="rounded-xl border border-line-strong bg-surface px-3.5 py-2.5 text-base outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-accent px-4 py-3 text-base font-semibold text-accent-ink hover:bg-accent-hover disabled:opacity-60"
              >
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
          )}

          {!showGoogle && !showEmail && (
            <p className="rounded-xl bg-warn-soft px-3.5 py-2.5 font-medium text-warn-ink">
              No sign-in method is configured. Set NEXT_PUBLIC_GOOGLE_CLIENT_ID (or NEXT_PUBLIC_AUTH_DEV_LOGIN=1 for local testing).
            </p>
          )}

          {error && (
            <p className="rounded-xl bg-crit-soft px-3.5 py-2.5 font-medium text-crit-ink" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
