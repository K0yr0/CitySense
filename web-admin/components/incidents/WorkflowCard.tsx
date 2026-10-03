"use client";

import { useState } from "react";
import { ApiError, getWork, setWork } from "@/lib/api";
import { formatDateTime, timeAgo, WORK_STATUSES, workLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { IncidentSummary, WorkInfo, WorkStatus } from "@/lib/types";
import { IconCheck } from "../icons";
import { Card } from "../ui";

const NEXT: Record<WorkStatus, { to: WorkStatus; label: string } | null> = {
  todo: { to: "in_progress", label: "Start work" },
  in_progress: { to: "done", label: "Mark as done" },
  done: null,
};

function Stepper({ current }: { current: WorkStatus }) {
  const at = WORK_STATUSES.indexOf(current);
  return (
    <ol className="flex items-center gap-1.5" aria-label="City work status">
      {WORK_STATUSES.map((w, idx) => {
        const reached = idx <= at;
        const now = idx === at;
        return (
          <li key={w} className="flex flex-1 flex-col gap-1.5" aria-current={now ? "step" : undefined}>
            <span className={`h-2 rounded-full ${reached ? (current === "done" ? "bg-good" : "bg-accent") : "bg-surface-2"}`} />
            <span className={`text-sm ${now ? "font-semibold text-ink" : reached ? "text-ink-2" : "text-muted"}`}>{workLabel(w)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function who(h: { by_name: string | null; by_email: string | null }): string {
  return h.by_name || h.by_email || "unknown";
}

/**
 * W3: city work flow, separate from the confidence status. To do -> In progress -> Done, with who and when.
 * Done stops the "is it still there?" question in the mobile app and settles contributor trust.
 */
export default function WorkflowCard({ incident, onChanged, now }: { incident: IncidentSummary; onChanged: () => void; now: number }) {
  // The incident row is polled by the page; when someone else changes the work status, the key
  // changes and the card refetches its history.
  const { data, error, reload } = useApi(`work:${incident.id}:${incident.work_status}:${incident.work_status_changed_at}`, () => getWork(incident.id));
  const [saved, setSaved] = useState<WorkInfo | null>(null);
  const [note, setNote] = useState("");
  const [confirmDone, setConfirmDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  // Our last save shows at once; the fetched state wins as soon as it is at least as new (history only grows).
  const info = saved && (!data || saved.history.length > data.history.length) ? saved : data;
  const current: WorkStatus = info?.work_status ?? incident.work_status;
  const next = NEXT[current];

  const change = async (to: WorkStatus) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await setWork(incident.id, to, note);
      setSaved(r);
      setNote("");
      setConfirmDone(false);
      const settled = r.settled_contributors ?? 0;
      setMessage({
        ok: true,
        text:
          to === "done"
            ? `Marked as done. The app stops asking about it${settled ? `; trust updated for ${settled} contributor${settled === 1 ? "" : "s"}` : ""}.`
            : `Moved to ${workLabel(to).toLowerCase()}.`,
      });
      reload();
      onChanged();
    } catch (err) {
      setMessage({ ok: false, text: err instanceof ApiError ? `Not saved: ${err.message}` : "Not saved: the backend could not be reached." });
    } finally {
      setBusy(false);
    }
  };

  const history = info?.history ?? [];

  return (
    <Card title="City work" action={<span className="text-sm text-muted">separate from confidence</span>}>
      <Stepper current={current} />
      {error && !info && (
        <p className="mt-3 rounded-xl bg-crit-soft px-3.5 py-2.5 text-sm font-medium text-crit-ink" role="alert">
          Could not load the work history ({error.message || "backend unreachable"}). Showing the status from the incident list.
        </p>
      )}
      {info?.changed_at && (
        <p className="mt-3 text-sm text-ink-2">
          {workLabel(current)} since {formatDateTime(info.changed_at)}
          {info.changed_by ? ` · by ${info.changed_by.name || info.changed_by.email}` : ""}
        </p>
      )}

      <label htmlFor={`work-note-${incident.id}`} className="mt-4 block text-sm font-semibold text-ink-2">
        Note <span className="font-normal text-muted">(optional: crew, work order)</span>
      </label>
      <input
        id={`work-note-${incident.id}`}
        value={note}
        maxLength={500}
        onChange={(e) => setNote(e.target.value)}
        className="mt-1 w-full rounded-xl border border-line-strong bg-surface px-3 py-2 text-base outline-none focus:border-accent"
      />

      {confirmDone ? (
        <div className="mt-3 rounded-xl border border-good bg-good-soft p-3.5">
          <p className="font-medium text-good-ink">Mark as done?</p>
          <p className="mt-1 text-sm text-ink-2">
            The mobile app stops asking citizens about it, and everyone who answered gets their trust settled as if it was real. Later
            NO answers about the repaired spot count against nobody.
          </p>
          <div className="mt-3 flex gap-2">
            <button type="button" disabled={busy} onClick={() => change("done")} className="flex-1 rounded-xl bg-good px-4 py-2.5 font-semibold text-white disabled:opacity-60">
              {busy ? "Saving…" : "Yes, it is fixed"}
            </button>
            <button type="button" disabled={busy} onClick={() => setConfirmDone(false)} className="rounded-xl border border-line-strong px-4 py-2.5 font-semibold hover:bg-surface-2">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          {next && (
            <button
              type="button"
              disabled={busy}
              onClick={() => (next.to === "done" ? setConfirmDone(true) : change(next.to))}
              className="flex-1 rounded-xl bg-accent px-4 py-3 text-base font-semibold text-accent-ink hover:bg-accent-hover disabled:opacity-60"
            >
              {busy ? "Saving…" : next.label}
            </button>
          )}
          {current === "todo" && (
            <button type="button" disabled={busy} onClick={() => setConfirmDone(true)} className="rounded-xl border border-line-strong px-4 py-3 font-semibold hover:bg-surface-2">
              Already done
            </button>
          )}
          {current !== "todo" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => change(current === "done" ? "in_progress" : "todo")}
              className="rounded-xl border border-line-strong px-4 py-3 font-semibold hover:bg-surface-2"
            >
              {current === "done" ? "Reopen" : "Back to to do"}
            </button>
          )}
          {note.trim() && (
            <button type="button" disabled={busy} onClick={() => change(current)} className="rounded-xl border border-line-strong px-4 py-3 font-semibold hover:bg-surface-2">
              Add note only
            </button>
          )}
        </div>
      )}

      {message && (
        <p role="status" className={`mt-3 rounded-xl px-3.5 py-2.5 font-medium ${message.ok ? "bg-accent-soft text-accent" : "bg-crit-soft text-crit-ink"}`}>
          {message.text}
        </p>
      )}

      <div className="mt-4 border-t border-line pt-3">
        <h3 className="text-sm font-semibold text-ink-2">History</h3>
        {history.length === 0 ? (
          <p className="mt-1 text-sm text-muted">No changes yet. New incidents start as to do.</p>
        ) : (
          <ol className="mt-2 flex flex-col gap-2.5">
            {history.map((h, n) => (
              <li key={`${h.at}-${n}`} className="flex gap-2.5">
                <span className={`mt-1 grid h-5 w-5 shrink-0 place-items-center rounded-full ${h.to_status === "done" ? "bg-good text-white" : h.to_status === "in_progress" ? "bg-accent text-accent-ink" : "bg-line-strong"}`}>
                  {h.to_status === "done" && <IconCheck width={12} height={12} />}
                </span>
                <div className="min-w-0">
                  <div className="text-base">
                    {h.from_status === h.to_status ? "Note" : <>{h.from_status ? `${workLabel(h.from_status)} → ` : ""}<span className="font-semibold">{workLabel(h.to_status)}</span></>}
                  </div>
                  <div className="text-sm text-muted" title={formatDateTime(h.at)}>
                    {who(h)} · {timeAgo(h.at, now)}
                  </div>
                  {h.note && <div className="mt-0.5 text-sm text-ink-2">&ldquo;{h.note}&rdquo;</div>}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}
