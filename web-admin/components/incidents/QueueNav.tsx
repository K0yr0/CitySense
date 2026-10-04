"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQueueOrder } from "@/lib/queueNav";
import { IconArrowLeft } from "../icons";

function typing(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  return !!t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
}

/**
 * Back to the (same filtered) queue, plus previous / next incident in the queue's order.
 * Keyboard: J = next, K = previous (like a mail client), not while typing or with a dialog open.
 */
export default function QueueNav({ id }: { id: number }) {
  const router = useRouter();
  const { ids, query } = useQueueOrder();
  const at = ids.indexOf(id);
  const prev = at > 0 ? ids[at - 1] : null;
  const next = at >= 0 && at < ids.length - 1 ? ids[at + 1] : null;
  const back = query ? `/incidents?${query}` : "/incidents";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e) || document.querySelector("[role=dialog]")) return;
      const to = e.key === "j" ? next : e.key === "k" ? prev : null;
      if (to !== null) router.push(`/incidents/${to}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, router]);

  const step = "inline-flex items-center gap-1 border border-line-strong bg-surface px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2";
  return (
    <nav className="border-b border-line bg-surface" aria-label="Incident navigation">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm lg:px-6">
        <Link href={back} className="group inline-flex items-center gap-1.5 font-semibold text-accent hover:text-accent-hover">
          <IconArrowLeft width={16} height={16} className="text-ink-2 transition-transform group-hover:-translate-x-0.5" /> Incident queue{query ? " (filtered)" : ""}
        </Link>
        {at >= 0 && ids.length > 1 && (
          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-xs text-muted sm:inline" title="Keyboard: K previous, J next">
              {at + 1} of {ids.length}
            </span>
            <div className="inline-flex" role="group">
              {prev !== null ? (
                <Link href={`/incidents/${prev}`} className={`${step} rounded-l-md`} aria-keyshortcuts="k">
                  ← Previous
                </Link>
              ) : (
                <span className={`${step} cursor-default rounded-l-md opacity-40`} aria-disabled="true">
                  ← Previous
                </span>
              )}
              {next !== null ? (
                <Link href={`/incidents/${next}`} className={`${step} -ml-px rounded-r-md`} aria-keyshortcuts="j">
                  Next →
                </Link>
              ) : (
                <span className={`${step} -ml-px cursor-default rounded-r-md opacity-40`} aria-disabled="true">
                  Next →
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
