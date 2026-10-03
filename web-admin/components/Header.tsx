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

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="var(--accent)" />
      <circle cx="16" cy="16" r="4" fill="var(--accent-ink)" />
      <path d="M9.5 9.5a9 9 0 0 0 0 13M22.5 9.5a9 9 0 0 1 0 13" stroke="var(--accent-ink)" strokeWidth="2.4" fill="none" strokeLinecap="round" />
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
    <span title={title} className="whitespace-nowrap rounded-full border border-warn bg-warn-soft px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-warn-ink sm:px-2.5">
      Demo<span className="hidden sm:inline"> data</span>
    </span>
  );
}

function UserMenu({ email, name }: { email: string; name: string | null }) {
  return (
    <div className="flex items-center gap-2 border-l border-line pl-1.5 sm:pl-4">
      <span className="hidden max-w-[14rem] truncate text-sm text-ink-2 xl:inline" title={email}>
        {name || email}
      </span>
      <button
        type="button"
        onClick={signOut}
        title={`Signed in as ${email}`}
        aria-label="Sign out"
        className="flex items-center gap-1.5 whitespace-nowrap rounded-lg p-1.5 text-[0.9rem] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink sm:px-3"
      >
        <IconLogout width={18} height={18} />
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
      <div className="flex h-16 items-center gap-2 px-3 sm:gap-4 sm:px-4 lg:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="CityEcho home">
          <Logo />
          <span className="hidden text-xl font-bold tracking-tight min-[480px]:inline">CityEcho</span>
          <span className="hidden rounded-md bg-accent-soft px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-accent sm:inline">Admin</span>
        </Link>
        <p className="hidden min-w-0 truncate border-l border-line pl-4 text-[0.95rem] text-ink-2 2xl:block">
          Warsaw&apos;s buses verify its citizens — and its citizens verify its buses
        </p>
        {session && (
          <nav className="ml-auto flex items-center gap-0.5 sm:gap-1" aria-label="Main">
            {NAV.map((n) => {
              const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-2 py-1.5 text-[0.9rem] font-medium sm:px-3.5 sm:text-[0.95rem] ${
                    active ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  }`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
        )}
        <div className={`flex items-center gap-2 sm:gap-3 ${session ? "" : "ml-auto"}`}>
          <DemoBadge />
          {session && <UserMenu email={session.user.email} name={session.user.name} />}
        </div>
      </div>
    </header>
  );
}
