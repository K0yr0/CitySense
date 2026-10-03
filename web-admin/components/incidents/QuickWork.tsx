"use client";

import { useState } from "react";
import { ApiError, setWork } from "@/lib/api";
import type { IncidentSummary, WorkStatus } from "@/lib/types";

/**
 * One-click next step of the city work flow, straight from the queue row:
 * to do -> "Start work", in progress -> "Mark done" (asks to confirm: it settles contributor trust).
 * Reopening and notes stay on the incident page.
 */
export default function QuickWork({ incident, onChanged }: { incident: IncidentSummary; onChanged: (id: number, to: WorkStatus) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const to: WorkStatus | null = incident.work_status === "todo" ? "in_progress" : incident.work_status === "in_progress" ? "done" : null;
  if (!to) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await setWork(incident.id, to);
      setConfirming(false);
      onChanged(incident.id, to);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Not saved");
    } finally {
      setBusy(false);
    }
  };

  const btn = "rounded-lg px-2.5 py-1 text-sm font-semibold disabled:opacity-60";
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
      {confirming ? (
        <>
          <button type="button" disabled={busy} onClick={run} className={`${btn} bg-good text-white`}>
            {busy ? "Saving…" : "Confirm done"}
          </button>
          <button type="button" disabled={busy} onClick={() => setConfirming(false)} className={`${btn} border border-line-strong hover:bg-surface-2`}>
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => (to === "done" ? setConfirming(true) : run())}
          className={`${btn} border border-line-strong text-ink-2 hover:border-accent hover:text-accent`}
          title={to === "done" ? "Mark as done: the app stops asking about it and contributor trust is settled" : "Move to in progress"}
        >
          {busy ? "Saving…" : to === "done" ? "Mark done" : "Start work"}
        </button>
      )}
      {error && (
        <span role="alert" className="text-sm font-medium text-crit-ink">
          {error}
        </span>
      )}
    </div>
  );
}
