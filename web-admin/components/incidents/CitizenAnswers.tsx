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
        <div className="rounded-xl bg-good-soft px-3.5 py-2.5">
          <div className="tabular text-2xl font-semibold text-good-ink">{i.yes_count}</div>
          <div className="text-sm text-ink-2">YES, still there</div>
        </div>
        <div className="rounded-xl bg-surface-2 px-3.5 py-2.5">
          <div className="tabular text-2xl font-semibold">{i.no_count}</div>
          <div className="text-sm text-ink-2">NO, not there</div>
        </div>
      </div>
      <p className="mt-2 text-sm text-muted">
        {reportYes > 0 ? `${reportYes} YES from the reports themselves, ` : ""}
        {i.responses.length} explicit answer{i.responses.length === 1 ? "" : "s"} from the app. Each answer counts by the contributor&apos;s trust.
      </p>

      {i.responses.length > 0 && (
        <ul className="mt-3 divide-y divide-line">
          {i.responses.slice(0, SHOW).map((r, n) => (
            <li key={`${r.created_at}-${n}`} className="flex items-center gap-3 py-2">
              <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ${r.answer === "yes" ? "bg-good-soft text-good-ink" : "bg-surface-2 text-ink-2"}`}>
                {r.answer === "yes" ? <IconCheck width={15} height={15} /> : <IconX width={15} height={15} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-medium">{r.answer === "yes" ? "Yes" : "No"}</div>
                <div className="text-sm text-muted" title={formatDateTime(r.created_at)}>
                  {timeAgo(r.created_at, now)}
                  {r.settled ? " · scored" : ""}
                </div>
              </div>
              <span className="tabular text-sm text-ink-2" title="Contributor trust (0–1): how often their past answers matched the outcome">
                trust {r.trust != null ? r.trust.toFixed(2) : "—"}
              </span>
            </li>
          ))}
        </ul>
      )}
      {i.responses.length > SHOW && <p className="mt-1 text-sm text-muted">+ {i.responses.length - SHOW} more in the timeline.</p>}
    </div>
  );
}
