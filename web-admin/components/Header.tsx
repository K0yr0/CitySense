"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "@/lib/auth";
import { useDemoState } from "@/lib/demo";
import { setDarkTheme, useDarkTheme } from "@/lib/theme";
import { IconChart, IconList, IconLogout, IconMap, IconMoon, IconSun } from "./icons";

const NAV = [
  { href: "/", label: "Map", Icon: IconMap },
  { href: "/incidents", label: "Incidents", Icon: IconList },
  { href: "/stats", label: "Stats", Icon: IconChart },
];

/** CitySense emblem (Stitch): navy disc with radar rings, a light ring around it. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <circle cx="16" cy="16" r="15" fill="var(--accent)" stroke="var(--line-strong)" strokeWidth="2" />
      <circle cx="16" cy="16" r="8" fill="none" stroke="var(--accent-ink)" strokeWidth="2.2" />
      <circle cx="16" cy="16" r="3" fill="var(--accent-ink)" />
    </svg>
  );
}

export function DemoBadge() {
  const { mock, failing } = useDemoState();
  if (!mock && failing.length === 0) return null;
  const title = mock
    ? "NEXT_PUBLIC_USE_MOCK=1: showing built-in fixtures"
    : `Backend unreachable for: ${failing.join(", ")}. Showing built-in fixtures.`;
  return (
    <span title={title} className="whitespace-nowrap rounded-md border border-warn bg-warn-soft px-2.5 py-1 text-xs font-bold uppercase tracking-wide text-warn-ink">
      Demo<span className="hidden sm:inline"> data</span>
    </span>
  );
}

/** Light is the default; the dark theme is a per-browser choice. */
export function ThemeToggle() {
  const dark = useDarkTheme();
  const label = dark ? "Switch to light theme" : "Switch to dark theme";
  return (
    <button
      type="button"
      onClick={() => setDarkTheme(!dark)}
      title={label}
      aria-label={label}
      className="grid h-9 w-9 place-items-center rounded-md border border-line text-ink-2 hover:bg-surface-2 hover:text-ink"
    >
      {dark ? <IconSun width={18} height={18} /> : <IconMoon width={18} height={18} />}
    </button>
  );
}

function UserMenu({ email, name }: { email: string; name: string | null }) {
  const label = name || email;
  return (
    <div className="flex items-center gap-3 sm:border-l sm:border-line sm:pl-4">
      <span className="hidden h-9 w-9 shrink-0 place-items-center rounded-full bg-accent text-sm sm:grid font-bold uppercase text-accent-ink" aria-hidden="true">
        {label.charAt(0)}
      </span>
      <span className="hidden min-w-0 flex-col leading-tight lg:flex">
        <span className="max-w-[13rem] truncate text-sm font-semibold text-ink" title={email}>
          {label}
        </span>
        <span className="text-xs text-muted">City administrator</span>
      </span>
      <button
        type="button"
        onClick={signOut}
        title={`Signed in as ${email}`}
        aria-label="Sign out"
        className="flex h-9 items-center gap-1.5 whitespace-nowrap rounded-md border border-line px-2.5 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
      >
        <IconLogout width={16} height={16} />
        <span className="hidden sm:inline">Sign out</span>
      </button>
    </div>
  );
}

export default function Header() {
  const path = usePathname();
  const session = useSession();
  // The sign-in screen has its own full-page brand panel.
  if (session === null) return null;
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface">
      <div className="flex h-16 items-center justify-between gap-2 px-2.5 sm:gap-4 sm:px-6">
        <div className="flex shrink-0 items-center gap-5">
          <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="CitySense home">
            <Logo size={34} />
            <span className="hidden text-xl font-extrabold tracking-tight min-[480px]:inline">CitySense</span>
            <span className="hidden rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 text-[0.6875rem] font-bold uppercase tracking-wider text-ink-2 sm:inline">
              Admin
            </span>
          </Link>
          <p className="hidden min-w-0 truncate border-l border-line pl-5 text-sm font-medium text-muted 2xl:block">
            Warsaw&apos;s buses verify its citizens — and its citizens verify its buses
          </p>
        </div>

        {session && (
          <nav className="flex items-center gap-0.5 rounded-lg border border-line bg-surface-2 p-1 text-[0.8125rem] font-semibold sm:gap-1 sm:text-sm" aria-label="Main">
            {NAV.map(({ href, label, Icon }) => {
              const active = href === "/" ? path === "/" : path.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`flex items-center gap-2 rounded-md px-2 py-1.5 sm:px-4 ${active ? "bg-accent text-accent-ink shadow-sm" : "text-ink-2 hover:bg-surface hover:text-ink"}`}
                >
                  <Icon width={16} height={16} className="hidden sm:block" />
                  {label}
                </Link>
              );
            })}
          </nav>
        )}

        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          <DemoBadge />
          <span className="hidden sm:block">
            <ThemeToggle />
          </span>
          {session && <UserMenu email={session.user.email} name={session.user.name} />}
        </div>
      </div>
    </header>
  );
}
