import type { ReactNode } from "react";
import { LIKELY_AT, VERIFIED_AT } from "@/lib/confidence";
import { fmtPct, fmtScore, pctOf, scorePct, SOURCE_LABEL, SOURCE_VAR, sourceKind, STATUS_HINT, statusLabel, vehicleLabel, workLabel } from "@/lib/format";
import type { IncidentStatus, IncidentSummary, WorkStatus } from "@/lib/types";
import { IconCheck, IconClock, IconEyeOff, IconRadar } from "./icons";

// Shared building blocks, styled after the Stitch design system: white cards with 1px slate borders,
// confidence as filled pills, city work as outlined 4 px tags, numbers in monospace.

export function Card({ title, children, className = "", action }: { title?: ReactNode; children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <section className={`rounded-2xl border border-line bg-surface p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-sm font-bold text-ink">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ScoreBar({ score, wide = false }: { score: number; wide?: boolean }) {
  return (
    <div className="flex items-center gap-2" title={`Priority score ${fmtScore(score)} (0–1.5)`}>
      <span className="w-10 text-right font-mono text-sm font-bold text-ink">{fmtScore(score)}</span>
      <span className={`h-2 overflow-hidden rounded-full border border-line bg-surface-2 ${wide ? "w-36" : "w-14"}`}>
        <span className="block h-full rounded-full bg-accent" style={{ width: `${scorePct(score)}%` }} />
      </span>
    </div>
  );
}

const STATUS_STYLE: Record<IncidentStatus, string> = {
  candidate: "bg-surface-2 text-ink-2 border-line-strong",
  likely: "bg-warn-soft text-warn-ink border-warn/40",
  verified: "bg-good-soft text-good-ink border-good/40",
  dismissed: "bg-surface-2 text-muted border-line",
  closed: "bg-surface-2 text-muted border-line",
};

/** Confidence status (engine): a filled pill with the %, never confused with the outlined work tag. */
export function StatusChip({ status, confidence }: { status: IncidentStatus | null | undefined; confidence?: number | null }) {
  const s = status ?? "candidate";
  const showPct = confidence != null && s !== "closed";
  return (
    <span
      title={STATUS_HINT[s]}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[s] ?? STATUS_STYLE.candidate}`}
    >
      {s === "verified" && <IconCheck width={12} height={12} strokeWidth={2.5} />}
      {s === "dismissed" && <IconEyeOff width={12} height={12} />}
      {statusLabel(s)}
      {showPct && <span className="font-mono opacity-90">· {fmtPct(confidence)}</span>}
    </span>
  );
}

const WORK_STYLE: Record<WorkStatus, string> = {
  todo: "border-line-strong bg-surface text-ink-2",
  in_progress: "border-accent bg-accent-soft/50 text-accent",
  done: "border-good bg-good-soft/60 text-good-ink",
};

/** City work status (to do / in progress / done): an outlined 4 px tag, the "civic stepper" of Stitch. */
export function WorkChip({ work }: { work: WorkStatus | null | undefined }) {
  const w = work ?? "todo";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border-[1.5px] px-2 py-0.5 text-xs font-semibold ${WORK_STYLE[w] ?? WORK_STYLE.todo}`}>
      {w === "done" ? (
        <IconCheck width={12} height={12} strokeWidth={2.5} />
      ) : (
        <span className={`h-1.5 w-1.5 rounded-full ${w === "in_progress" ? "bg-accent" : "border border-ink-2"}`} />
      )}
      {workLabel(w)}
    </span>
  );
}

const METER_FILL: Record<IncidentStatus, string> = {
  candidate: "bg-muted",
  likely: "bg-warn",
  verified: "bg-good",
  dismissed: "bg-line-strong",
  closed: "bg-line-strong",
};

/** Confidence bar with the Likely (60 %) and Verified (85 %) thresholds marked. */
export function ConfidenceMeter({ value, status, label }: { value: number | null; status?: IncidentStatus; label?: string }) {
  const pct = value == null ? 0 : pctOf(value);
  return (
    <div>
      {label && (
        <div className="mb-1 flex items-baseline justify-between gap-3 text-xs font-semibold text-ink-2">
          <span>{label}</span>
          <span className="font-mono font-bold text-ink">{value == null ? "no data yet" : `${pct}%`}</span>
        </div>
      )}
      <div
        className="relative h-2 overflow-hidden rounded-full border border-line bg-surface-2"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-label={label ?? "Confidence"}
      >
        <div className={`h-full rounded-full ${METER_FILL[status ?? "candidate"]}`} style={{ width: `${value == null ? 0 : Math.max(2, pct)}%` }} />
        {[LIKELY_AT, VERIFIED_AT].map((t) => (
          <span key={t} className="absolute inset-y-0 w-0.5 bg-surface/90" style={{ left: `${t * 100}%` }} aria-hidden="true" />
        ))}
      </div>
    </div>
  );
}

/** Where the evidence comes from. `pill` = tinted outlined pill (cards), default = dot + text (rows). */
export function SourceTag({ incident, pill = false }: { incident: Pick<IncidentSummary, "has_sensor" | "has_report">; pill?: boolean }) {
  const k = sourceKind(incident);
  if (pill) {
    return (
      <span
        className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold text-ink"
        style={{
          background: `color-mix(in srgb, ${SOURCE_VAR[k]} 9%, transparent)`,
          borderColor: `color-mix(in srgb, ${SOURCE_VAR[k]} 40%, transparent)`,
        }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: SOURCE_VAR[k] }} />
        {SOURCE_LABEL[k]}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: SOURCE_VAR[k] }} />
      {SOURCE_LABEL[k]}
    </span>
  );
}

function Badge({ children, tone }: { children: ReactNode; tone: "accent" | "good" | "warn" | "neutral" }) {
  const cls = {
    accent: "border-line-strong bg-surface-2 text-ink",
    good: "border-good/40 bg-good-soft text-good-ink",
    warn: "border-warn/40 bg-warn-soft text-warn-ink",
    neutral: "border-line bg-surface-2 text-muted",
  }[tone];
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded border px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
}

/** "Found before any report", "Verified by tram 17", "Tram 17 verifying · ~6 min", "No anomaly on 2 passes". */
export function IncidentBadges({ incident }: { incident: IncidentSummary }) {
  const v = vehicleLabel(incident.verify_vehicle);
  const open = incident.status === "candidate" || incident.status === "likely";
  return (
    <>
      {incident.found_before_report && (
        <Badge tone="accent">
          <IconRadar width={13} height={13} className="text-both" /> Found before any report
        </Badge>
      )}
      {incident.status === "verified" && incident.has_sensor && incident.verify_vehicle && (
        <Badge tone="good">
          <IconCheck width={12} height={12} strokeWidth={2.5} /> Verified by {incident.verify_vehicle}
        </Badge>
      )}
      {incident.awaiting_verification && v && (
        <Badge tone="warn">
          <IconClock width={13} height={13} /> {v} verifying{incident.verify_eta_min != null ? ` · ~${incident.verify_eta_min} min` : ""}
        </Badge>
      )}
      {open && incident.sensor_misses > 0 && (
        <Badge tone="neutral">
          <IconEyeOff width={13} height={13} /> No anomaly on {incident.sensor_misses} pass{incident.sensor_misses === 1 ? "" : "es"}
        </Badge>
      )}
    </>
  );
}

/** One-line verification state for tables. */
export function verificationText(i: IncidentSummary): string {
  const v = vehicleLabel(i.verify_vehicle);
  if (i.status === "verified") return i.has_sensor ? `Verified by sensor${v ? ` · ${v}` : ""}` : "Verified by citizens";
  if (i.status === "dismissed") return "Dismissed: checks found nothing";
  if (i.status === "closed") return "Closed";
  if (i.awaiting_verification) return v ? `${v} · ETA ~${i.verify_eta_min ?? "?"} min` : "Awaiting a vehicle";
  if (i.sensor_misses > 0) return `${i.sensor_misses} clean pass${i.sensor_misses === 1 ? "" : "es"}, confidence down`;
  if (i.has_sensor && !i.has_report) return `Sensor-detected · ${i.sensor_rides} ride${i.sensor_rides === 1 ? "" : "s"}`;
  return "Not requested yet";
}

/** Single-choice filter chips (Stitch: navy filled when on, quiet slate otherwise; counts in mono). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`rounded-full px-3 py-1 text-[0.8125rem] font-semibold transition-colors ${
              on ? "bg-accent text-accent-ink" : "bg-surface-2 text-ink-2 hover:bg-line"
            } ${!on && o.count === 0 ? "opacity-50" : ""}`}
          >
            {o.label}
            {o.count !== undefined && <span className={`ml-1.5 font-mono text-xs ${on ? "opacity-80" : "text-muted"}`}>{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
