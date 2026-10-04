import { formatDateTime, timeAgo } from "@/lib/format";
import type { IncidentDetail } from "@/lib/types";
import { IconCheck, IconX } from "../icons";

const SHOW = 8;

/** Citizen YES/NO answers ("is it still there?") from the mobile app, weighted by each contributor's trust. Read only. */
export default function CitizenAnswers({ incident: i, now }: { incident: IncidentDetail; now: number }) {
  const explicitYes = i.responses.filter((r) => r.answer === "yes").length;
  const reportYes = Math.max(0, i.yes_count - explicitYes); // every located report counts as its author's YES
  return (
    <div>
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-good/40 bg-good-soft px-3.5 py-3">
          <div className="font-mono text-2xl font-bold text-good-ink">{i.yes_count}</div>
          <div className="mt-1 text-[0.6875rem] font-medium uppercase tracking-wide text-good-ink">YES, still there</div>
        </div>
        <div className="rounded-lg border border-line bg-surface-2 px-3.5 py-3">
          <div className="font-mono text-2xl font-bold">{i.no_count}</div>
          <div className="mt-1 text-[0.6875rem] font-medium uppercase tracking-wide text-ink-2">NO, not there</div>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">
        {reportYes > 0 ? `${reportYes} YES from the reports themselves, ` : ""}
        {i.responses.length} explicit answer{i.responses.length === 1 ? "" : "s"} from the app. Each answer counts by the contributor&apos;s trust.
      </p>

      {i.responses.length > 0 && (
        <ul className="mt-3 space-y-2 border-t border-line pt-3">
          {i.responses.slice(0, SHOW).map((r, n) => (
            <li key={`${r.created_at}-${n}`} className="flex items-center justify-between gap-3 text-xs">
              <span className="flex min-w-0 items-center gap-2">
                <span className={`grid h-4 w-4 shrink-0 place-items-center rounded-full ${r.answer === "yes" ? "bg-good-soft text-good-ink" : "bg-surface-2 text-ink-2"}`}>
                  {r.answer === "yes" ? <IconCheck width={10} height={10} strokeWidth={3} /> : <IconX width={10} height={10} strokeWidth={3} />}
                </span>
                <span className="font-medium text-ink">{r.answer === "yes" ? "Yes" : "No"}</span>
                <span className="text-muted" title={formatDateTime(r.created_at)}>
                  {timeAgo(r.created_at, now)}
                  {r.settled ? " · scored" : ""}
                </span>
              </span>
              <span className="font-mono text-[0.6875rem] text-muted" title="Contributor trust (0–1): how often their past answers matched the outcome">
                trust {r.trust != null ? r.trust.toFixed(2) : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {i.responses.length > SHOW && <p className="mt-2 text-xs text-muted">+ {i.responses.length - SHOW} more in the timeline.</p>}
    </div>
  );
}
