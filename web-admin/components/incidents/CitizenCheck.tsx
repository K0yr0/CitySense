"use client";

import { useState, useSyncExternalStore } from "react";
import { respondToIncident } from "@/lib/api";
import { myAnswer, rememberAnswer, subscribeAnswers } from "@/lib/contributor";
import { fmtPct, statusLabel } from "@/lib/format";
import type { CitizenAnswer, CitizenResponseResult, IncidentSummary } from "@/lib/types";
import { IconCheck, IconX } from "../icons";

/** Chart box "Citizen Response YES / NO": answers are weighted by the contributor's trust. */
export default function CitizenCheck({
  incident,
  onDone,
  compact = false,
}: {
  incident: IncidentSummary;
  onDone?: () => void;
  compact?: boolean;
}) {
  // The answer this browser gave earlier (localStorage; null during server rendering).
  const answer = useSyncExternalStore(subscribeAnswers, () => myAnswer(incident.id), () => null);
  const [busy, setBusy] = useState<CitizenAnswer | null>(null);
  const [result, setResult] = useState<CitizenResponseResult | null>(null);
  const [failed, setFailed] = useState(false);

  const closed = incident.status === "dismissed" || incident.status === "closed";
  if (closed) {
    return <p className="text-ink-2">{incident.status === "dismissed" ? "Dismissed after checks found nothing." : "Handled by the city."}</p>;
  }

  const send = async (a: CitizenAnswer) => {
    setBusy(a);
    setFailed(false);
    try {
      const r = await respondToIncident(incident.id, a);
      if (!r) throw new Error("no response");
      rememberAnswer(incident.id, a);
      setResult(r);
      onDone?.();
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };

  const btn = (a: CitizenAnswer, label: string, Icon: typeof IconCheck) => {
    const on = answer === a;
    return (
      <button
        type="button"
        onClick={() => send(a)}
        disabled={busy !== null}
        aria-pressed={on}
        className={`flex flex-1 items-center justify-center gap-2 rounded-xl border px-4 py-3 text-base font-semibold transition-colors disabled:opacity-60 ${
          on ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-surface text-ink hover:bg-surface-2"
        }`}
      >
        <Icon width={18} height={18} /> {busy === a ? "Sending…" : label}
      </button>
    );
  };

  return (
    <div>
      {!compact && <p className="mb-3 text-lg font-medium">Is this problem still there?</p>}
      <div className="flex gap-2.5">
        {btn("yes", "Yes, still there", IconCheck)}
        {btn("no", "No, it's not", IconX)}
      </div>
      {result ? (
        <p className="mt-3 rounded-xl bg-accent-soft px-3.5 py-2.5 font-medium text-accent" role="status">
          Thanks! Confidence is now {fmtPct(result.confidence)} ({statusLabel(result.status)}).
          {result.contributor_trust != null && ` Your trust: ${result.contributor_trust.toFixed(2)}.`}
        </p>
      ) : answer ? (
        <p className="mt-2 text-sm text-muted">You answered {answer === "yes" ? "YES" : "NO"}. You can change your answer.</p>
      ) : null}
      {failed && <p className="mt-2 text-sm font-medium text-warn-ink">Could not send your answer. Please try again.</p>}
      {!compact && (
        <p className="mt-2 text-sm text-muted">
          Answers are weighted by trust. Your trust goes up when your answers match the final outcome (verified or dismissed), so
          your future answers count for more.
        </p>
      )}
    </div>
  );
}
