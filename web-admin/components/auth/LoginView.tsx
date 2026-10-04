"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";
import { ApiError, loginDev, loginWithGoogle } from "@/lib/api";
import { DEV_LOGIN, GOOGLE_CLIENT_ID } from "@/lib/auth";
import { USE_MOCK } from "@/lib/demo";
import { useDarkTheme } from "@/lib/theme";
import { DemoBadge, Logo, ThemeToggle } from "../Header";
import { IconAlert, IconArrowRight, IconLayers, IconRadar, IconShield } from "../icons";

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
  const dark = useDarkTheme();
  const [failed, setFailed] = useState<string | null>(null);
  const onCredential = useEffectEvent((idToken: string) => onToken(idToken));

  useEffect(() => {
    let alive = true;
    loadGsi()
      .then((gsi) => {
        if (!alive || !ref.current) return;
        gsi.initialize({ client_id: GOOGLE_CLIENT_ID, ux_mode: "popup", callback: (r) => r.credential && onCredential(r.credential) });
        ref.current.replaceChildren();
        gsi.renderButton(ref.current, { theme: dark ? "filled_black" : "outline", size: "large", text: "signin_with", shape: "rectangular", width: 340 });
      })
      .catch((e: Error) => alive && setFailed(e.message));
    return () => {
      alive = false;
    };
  }, [dark]);

  if (failed) return <p className="text-sm font-medium text-warn-ink">{failed}</p>;
  return <div ref={ref} className="flex min-h-11 justify-center" />;
}

const POINTS = [
  { Icon: IconLayers, title: "One queue for every report", text: "19115 reports and vehicle sensor rides are merged into a single incident." },
  { Icon: IconRadar, title: "Verified by public transport", text: "Buses and trams confirm road and track defects on their regular routes." },
  { Icon: IconShield, title: "All city departments", text: "ZDM, Tramwaje Warszawskie, MPWiK and Straż Miejska in one place." },
];

/** Left half of the sign-in page: who this is for and what it does. Always navy, in both themes. */
function BrandPanel() {
  return (
    <section className="relative hidden w-[46%] max-w-[46rem] flex-col justify-between overflow-hidden bg-brand p-12 text-white lg:flex xl:p-16">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
          backgroundSize: "36px 36px",
        }}
        aria-hidden="true"
      />
      <svg className="pointer-events-none absolute -bottom-40 -right-40 h-[34rem] w-[34rem] text-white/10" viewBox="0 0 200 200" aria-hidden="true">
        {[96, 72, 48, 24].map((r) => (
          <circle key={r} cx="100" cy="100" r={r} fill="none" stroke="currentColor" strokeWidth="1" />
        ))}
        <circle cx="100" cy="100" r="6" fill="currentColor" />
      </svg>

      <div className="relative flex items-center gap-3">
        <span className="grid h-11 w-11 place-items-center rounded-lg bg-white/10 ring-1 ring-white/20">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <circle cx="16" cy="16" r="14" fill="none" stroke="#fff" strokeWidth="2" opacity="0.5" />
            <circle cx="16" cy="16" r="8" fill="none" stroke="#fff" strokeWidth="2.2" />
            <circle cx="16" cy="16" r="3" fill="#fff" />
          </svg>
        </span>
        <span className="text-2xl font-extrabold tracking-tight">CityEcho</span>
        <span className="rounded border border-white/30 px-1.5 py-0.5 text-[0.6875rem] font-bold uppercase tracking-wider text-white/80">Admin</span>
      </div>

      <div className="relative max-w-xl">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-white/60">Warsaw city health</p>
        <h2 className="mt-4 text-4xl font-bold leading-tight tracking-tight xl:text-[2.75rem]">
          Warsaw&apos;s buses verify its citizens — and its citizens verify its buses.
        </h2>
        <ul className="mt-10 flex flex-col gap-6">
          {POINTS.map(({ Icon, title, text }) => (
            <li key={title} className="flex gap-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white/10 ring-1 ring-white/15">
                <Icon width={20} height={20} />
              </span>
              <span>
                <span className="block font-semibold">{title}</span>
                <span className="block text-sm leading-relaxed text-white/70">{text}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative font-mono text-xs text-white/50">Sensor data is simulated · Warsaw municipal dashboard</p>
    </section>
  );
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
    <main className="flex flex-1 bg-bg">
      <BrandPanel />

      <section className="flex flex-1 flex-col bg-bg lg:bg-surface">
        <div className="flex items-center justify-between gap-3 px-6 py-5 sm:px-10">
          <span className="flex items-center gap-2 lg:invisible">
            <Logo size={32} />
            <span className="text-lg font-extrabold tracking-tight">CityEcho</span>
          </span>
          <span className="flex items-center gap-3">
            <DemoBadge />
            <ThemeToggle />
          </span>
        </div>

        <div className="flex flex-1 items-center justify-center px-6 pb-16 sm:px-10">
          <div className="w-full max-w-[26rem] rounded-xl border border-line bg-surface p-8 shadow-lg lg:border-0 lg:bg-transparent lg:p-0 lg:shadow-none">
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-muted">Admin console</p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight">Sign in</h1>
            <p className="mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              Use your city account. Only emails on the admin list can open the incident queue, the work flow and the live map.
            </p>

            <div className="mt-8 flex flex-col gap-5">
              {showGoogle && <GoogleButton onToken={(t) => run(() => loginWithGoogle(t))} />}

              {showGoogle && showEmail && (
                <div className="flex items-center gap-3 text-xs font-semibold uppercase tracking-wider text-muted">
                  <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
                </div>
              )}

              {showEmail && (
                <form onSubmit={onEmail} className="flex flex-col gap-2">
                  <label htmlFor="login-email" className="text-sm font-semibold text-ink">
                    Work email
                  </label>
                  <input
                    id="login-email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@um.warszawa.pl"
                    className="h-12 rounded-lg border border-line-strong bg-surface px-4 text-base outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                  />
                  <p className="text-xs text-muted">{USE_MOCK ? "Demo mode: any email signs in as admin." : "Local testing only (AUTH_DEV_LOGIN=1)."}</p>
                  <button
                    type="submit"
                    disabled={busy}
                    className="mt-3 flex h-12 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-base font-semibold text-accent-ink hover:bg-accent-hover disabled:opacity-60"
                  >
                    {busy ? "Signing in…" : "Sign in"}
                    {!busy && <IconArrowRight width={18} height={18} />}
                  </button>
                </form>
              )}

              {!showGoogle && !showEmail && (
                <p className="rounded-lg border border-warn/40 bg-warn-soft px-4 py-3 text-sm font-medium text-warn-ink">
                  No sign-in method is configured. Set NEXT_PUBLIC_GOOGLE_CLIENT_ID (or NEXT_PUBLIC_AUTH_DEV_LOGIN=1 for local testing).
                </p>
              )}

              {error && (
                <p className="flex items-start gap-2.5 rounded-lg border border-crit/30 bg-crit-soft px-4 py-3 text-sm font-medium text-crit-ink" role="alert">
                  <IconAlert width={18} height={18} className="mt-px shrink-0" />
                  <span>{error}</span>
                </p>
              )}
            </div>

            <p className="mt-10 border-t border-line pt-5 text-xs leading-relaxed text-muted">
              For municipal staff only. Need access? Ask the CityEcho team to add your email to the admin list.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
