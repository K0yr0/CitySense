import { formatDateTime, timeAgo } from "@/lib/format";
import type { TimelineEvent, TimelineKind } from "@/lib/types";
import { IconCheck, IconClock, IconEyeOff, IconMessage, IconRadar } from "../icons";

const KIND: Record<TimelineKind, { cls: string; Icon: typeof IconCheck }> = {
  first_report: { cls: "bg-report text-white", Icon: IconMessage },
  report: { cls: "bg-report text-white", Icon: IconMessage },
  sensor: { cls: "bg-sensor text-white", Icon: IconRadar },
  proactive: { cls: "bg-accent text-accent-ink", Icon: IconRadar },
  verification_requested: { cls: "bg-warn text-black", Icon: IconClock },
  confirmed: { cls: "bg-good text-white", Icon: IconCheck },
  no_anomaly: { cls: "bg-line-strong text-ink", Icon: IconEyeOff },
};

/** Evidence timeline: first report → verification requested → sensor confirmation. */
export default function Timeline({ events, now }: { events: TimelineEvent[]; now: number }) {
  if (!events.length) return <p className="text-ink-2">No events yet.</p>;
  return (
    <ol className="relative">
      {events.map((e, idx) => {
        const k = KIND[e.kind] ?? KIND.report;
        const last = idx === events.length - 1;
        return (
          <li key={`${e.ts}-${idx}`} className="relative flex gap-3 pb-5 last:pb-0">
            {!last && <span className="absolute left-[0.9rem] top-8 bottom-0 w-px bg-line-strong" aria-hidden="true" />}
            <span className={`relative z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ring-surface ${k.cls}`}>
              <k.Icon width={15} height={15} />
            </span>
            <div className="min-w-0 pt-0.5">
              <div className="text-base font-medium leading-snug">{e.label}</div>
              <div className="text-sm text-muted">
                {formatDateTime(e.ts)} · {timeAgo(e.ts, now)}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
