import type { ReactNode } from "react";
import { fmtScore, scorePct, SOURCE_LABEL, SOURCE_VAR, sourceKind, statusLabel, vehicleLabel } from "@/lib/format";
import type { IncidentStatus, IncidentSummary } from "@/lib/types";
import { IconCheck, IconClock, IconEyeOff, IconRadar } from "./icons";

export function Card({ title, children, className = "", action }: { title?: ReactNode; children: ReactNode; className?: string; action?: ReactNode }) {
  return (
    <section className={`rounded-2xl border border-line bg-surface p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-ink-2">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ScoreBar({ score, wide = false }: { score: number; wide?: boolean }) {
  return (
    <div className="flex items-center gap-2.5" title={`Priority score ${fmtScore(score)} (0–1.5)`}>
      <span className="tabular w-11 text-right text-lg font-semibold">{fmtScore(score)}</span>
      <span className={`h-2 overflow-hidden rounded-full bg-accent-soft ${wide ? "w-40" : "w-20"}`}>
        <span className="block h-full rounded-full bg-accent" style={{ width: `${scorePct(score)}%` }} />
      </span>
    </div>
  );
}

const STATUS_STYLE: Record<IncidentStatus, string> = {
  open: "bg-surface-2 text-ink-2 border-line-strong",
  awaiting_verification: "bg-warn-soft text-warn-ink border-transparent",
  confirmed: "bg-good-soft text-good-ink border-transparent",
  no_anomaly: "bg-surface-2 text-muted border-line",
  closed: "bg-surface-2 text-muted border-line",
};

export function StatusChip({ status }: { status: IncidentStatus | null | undefined }) {
  const s = status ?? "open";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-medium ${STATUS_STYLE[s] ?? STATUS_STYLE.open}`}>
      {s === "confirmed" && <IconCheck width={15} height={15} />}
      {s === "awaiting_verification" && <IconClock width={15} height={15} />}
      {statusLabel(s)}
    </span>
  );
}

export function SourceTag({ incident }: { incident: Pick<IncidentSummary, "has_sensor" | "has_report"> }) {
  const k = sourceKind(incident);
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-2">
      <span className="inline-block h-3 w-3 rounded-full ring-2 ring-surface" style={{ background: SOURCE_VAR[k] }} />
      {SOURCE_LABEL[k]}
    </span>
  );
}

function Badge({ children, tone }: { children: ReactNode; tone: "accent" | "good" | "warn" | "neutral" }) {
  const cls = {
    accent: "bg-accent-soft text-accent",
    good: "bg-good-soft text-good-ink",
    warn: "bg-warn-soft text-warn-ink",
    neutral: "bg-surface-2 text-muted",
  }[tone];
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-sm font-semibold ${cls}`}>{children}</span>;
}

/** "Found before any report", "Verified by tram 17", "Tram 17 verifying · ~6 min", … */
export function IncidentBadges({ incident }: { incident: IncidentSummary }) {
  const v = vehicleLabel(incident.verify_vehicle);
  return (
    <>
      {incident.found_before_report && (
        <Badge tone="accent">
          <IconRadar width={15} height={15} /> Found before any report
        </Badge>
      )}
      {incident.status === "confirmed" && incident.verify_vehicle && (
        <Badge tone="good">
          <IconCheck width={15} height={15} /> Verified by {incident.verify_vehicle}
        </Badge>
      )}
      {incident.status === "awaiting_verification" && v && (
        <Badge tone="warn">
          <IconClock width={15} height={15} /> {v} verifying{incident.verify_eta_min != null ? ` · ~${incident.verify_eta_min} min` : ""}
        </Badge>
      )}
      {incident.status === "no_anomaly" && (
        <Badge tone="neutral">
          <IconEyeOff width={15} height={15} /> No anomaly{v ? ` (${v})` : ""}
        </Badge>
      )}
    </>
  );
}

/** One-line verification state for tables. */
export function verificationText(i: IncidentSummary): string {
  const v = vehicleLabel(i.verify_vehicle);
  switch (i.status) {
    case "confirmed":
      return i.sensor_confirmed || i.has_sensor ? `Confirmed by sensor${v ? ` · ${v}` : ""}` : "Confirmed";
    case "awaiting_verification":
      return v ? `${v} · ETA ~${i.verify_eta_min ?? "?"} min` : "Awaiting a vehicle";
    case "no_anomaly":
      return v ? `${v} found nothing` : "No anomaly found";
    case "closed":
      return "Closed";
    default:
      if (i.has_sensor && !i.has_report) return `Sensor-detected · ${i.sensor_rides} ride${i.sensor_rides === 1 ? "" : "s"}`;
      return "Not requested yet";
  }
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
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
            className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors ${
              on ? "border-accent bg-accent text-accent-ink" : "border-line-strong bg-surface text-ink-2 hover:bg-surface-2"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
