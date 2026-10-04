import { formatDateTime, timeAgo } from "@/lib/format";
import type { TimelineEvent, TimelineKind } from "@/lib/types";
import { IconCheck, IconClock, IconEyeOff, IconMessage, IconRadar, IconX } from "../icons";

const KIND: Record<TimelineKind, { cls: string; Icon: typeof IconCheck }> = {
  first_report: { cls: "bg-report text-white", Icon: IconMessage },
  report: { cls: "bg-report text-white", Icon: IconMessage },
  sensor: { cls: "bg-sensor text-white", Icon: IconRadar },
  proactive: { cls: "bg-accent text-accent-ink", Icon: IconRadar },
  verification_requested: { cls: "bg-warn text-black", Icon: IconClock },
  sensor_miss: { cls: "bg-line-strong text-ink", Icon: IconEyeOff },
  response: { cls: "bg-report text-white", Icon: IconCheck },
  verified: { cls: "bg-good text-white", Icon: IconCheck },
  dismissed: { cls: "bg-line-strong text-ink", Icon: IconEyeOff },
};
const NO_ANSWER = { cls: "bg-line-strong text-ink", Icon: IconX };

/** Evidence timeline: reports, citizen answers, sensor hits and misses, verified / dismissed. */
export default function Timeline({ events, now }: { events: TimelineEvent[]; now: number }) {
  if (!events.length) return <p className="text-xs text-muted">No events yet.</p>;
  return (
    <ol className="relative">
      {events.map((e, idx) => {
        // A NO answer must not look like a confirmation.
        const k = e.kind === "response" && /\bNO\b/.test(e.label) ? NO_ANSWER : (KIND[e.kind] ?? KIND.report);
        const last = idx === events.length - 1;
        return (
          <li key={`${e.ts}-${idx}`} className="relative flex gap-3 pb-4 last:pb-0">
            {!last && <span className="absolute bottom-0 left-[0.6rem] top-6 w-0.5 bg-line" aria-hidden="true" />}
            <span className={`relative z-10 grid h-5 w-5 shrink-0 place-items-center rounded-full ring-4 ring-surface ${k.cls}`}>
              <k.Icon width={11} height={11} strokeWidth={2.5} />
            </span>
            <div className="min-w-0">
              <div className="text-xs font-semibold leading-snug text-ink">{e.label}</div>
              <div className="text-[0.6875rem] text-muted">
                {formatDateTime(e.ts)} · {timeAgo(e.ts, now)}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
