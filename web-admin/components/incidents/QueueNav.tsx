"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useQueueOrder } from "@/lib/queueNav";
import { IconArrowLeft, IconArrowRight } from "../icons";

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

  const step = "inline-flex items-center gap-1.5 rounded-lg border border-line-strong px-3 py-1.5 text-sm font-semibold hover:bg-surface-2";
  return (
    <nav className="flex flex-wrap items-center justify-between gap-3" aria-label="Incident navigation">
      <Link href={back} className="inline-flex items-center gap-1.5 text-base font-medium text-ink-2 hover:text-accent">
        <IconArrowLeft width={18} height={18} /> Incident queue{query ? " (filtered)" : ""}
      </Link>
      {at >= 0 && ids.length > 1 && (
        <div className="flex items-center gap-2">
          <span className="tabular hidden text-sm text-muted sm:inline" title="Keyboard: K previous, J next">
            {at + 1} of {ids.length}
          </span>
          {prev !== null ? (
            <Link href={`/incidents/${prev}`} className={step} aria-keyshortcuts="k">
              <IconArrowLeft width={16} height={16} /> Previous
            </Link>
          ) : (
            <span className={`${step} cursor-default opacity-40`} aria-disabled="true">
              <IconArrowLeft width={16} height={16} /> Previous
            </span>
          )}
          {next !== null ? (
            <Link href={`/incidents/${next}`} className={step} aria-keyshortcuts="j">
              Next <IconArrowRight width={16} height={16} />
            </Link>
          ) : (
            <span className={`${step} cursor-default opacity-40`} aria-disabled="true">
              Next <IconArrowRight width={16} height={16} />
            </span>
          )}
        </div>
      )}
    </nav>
  );
}
