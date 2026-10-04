"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "@/lib/auth";
import { useDemoState } from "@/lib/demo";
import { IconLogout } from "./icons";

const NAV = [
  { href: "/", label: "Map" },
  { href: "/incidents", label: "Incidents" },
  { href: "/stats", label: "Stats" },
];

/** CityEcho emblem (Stitch): navy disc with radar rings, a light ring around it. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <circle cx="16" cy="16" r="15" fill="var(--accent)" stroke="var(--line-strong)" strokeWidth="2" />
      <circle cx="16" cy="16" r="8" fill="none" stroke="var(--accent-ink)" strokeWidth="2.2" />
      <circle cx="16" cy="16" r="3" fill="var(--accent-ink)" />
    </svg>
  );
}

function DemoBadge() {
  const { mock, failing } = useDemoState();
  if (!mock && failing.length === 0) return null;
  const title = mock
    ? "NEXT_PUBLIC_USE_MOCK=1: showing built-in fixtures"
    : `Backend unreachable for: ${failing.join(", ")}. Showing built-in fixtures.`;
  return (
    <span title={title} className="whitespace-nowrap rounded border border-warn bg-warn-soft px-2 py-0.5 text-[0.6875rem] font-bold uppercase tracking-wide text-warn-ink">
      Demo<span className="hidden sm:inline"> data</span>
    </span>
  );
}

function UserMenu({ email, name }: { email: string; name: string | null }) {
  const label = name || email;
  return (
    <div className="flex items-center gap-2 border-l border-line pl-2 sm:pl-3">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent text-[0.625rem] font-bold uppercase text-accent-ink" aria-hidden="true">
        {label.charAt(0)}
      </span>
      <span className="hidden max-w-[12rem] truncate text-xs font-medium text-ink-2 lg:inline" title={email}>
        {label}
      </span>
      <button
        type="button"
        onClick={signOut}
        title={`Signed in as ${email}`}
        aria-label="Sign out"
        className="ml-1 flex items-center gap-1 whitespace-nowrap rounded p-1 text-xs font-medium text-muted hover:text-ink"
      >
        <IconLogout width={15} height={15} />
        <span className="hidden sm:inline">Sign out</span>
      </button>
    </div>
  );
}

export default function Header() {
  const path = usePathname();
  const session = useSession();
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface">
      <div className="flex h-14 items-center justify-between gap-2 px-3 sm:gap-4 sm:px-4">
        <div className="flex min-w-0 items-center gap-4">
          <Link href="/" className="flex shrink-0 items-center gap-2" aria-label="CityEcho home">
            <Logo />
            <span className="hidden text-lg font-extrabold tracking-tight min-[480px]:inline">CityEcho</span>
            <span className="hidden rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 text-[0.625rem] font-bold uppercase tracking-wider text-ink-2 sm:inline">
              Admin
            </span>
          </Link>
          <p className="hidden min-w-0 truncate border-l border-line pl-3 text-xs font-medium text-muted xl:block">
            Warsaw&apos;s buses verify its citizens — and its citizens verify its buses
          </p>
        </div>

        {session && (
          <nav className="flex items-center gap-1 rounded-md border border-line bg-surface-2 p-1 text-xs font-semibold" aria-label="Main">
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded px-2.5 py-1 sm:px-3.5 ${active ? "bg-accent text-accent-ink" : "text-ink-2 hover:bg-surface hover:text-ink"}`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
        )}

        <div className="flex items-center gap-2 sm:gap-3">
          <DemoBadge />
          {session && <UserMenu email={session.user.email} name={session.user.name} />}
        </div>
      </div>
    </header>
  );
}
