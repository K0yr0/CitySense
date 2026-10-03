import type { ReactNode } from "react";
import { LIKELY_AT, VERIFIED_AT } from "@/lib/confidence";
import { fmtPct, fmtScore, pctOf, scorePct, SOURCE_LABEL, SOURCE_VAR, sourceKind, STATUS_HINT, statusLabel, vehicleLabel } from "@/lib/format";
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
  candidate: "bg-surface-2 text-ink-2 border-line-strong",
  likely: "bg-warn-soft text-warn-ink border-transparent",
  verified: "bg-good-soft text-good-ink border-transparent",
  dismissed: "bg-surface-2 text-muted border-line",
  closed: "bg-surface-2 text-muted border-line",
};

/** Candidate / Likely / Verified (+ confidence %), from the confidence engine. */
export function StatusChip({ status, confidence }: { status: IncidentStatus | null | undefined; confidence?: number | null }) {
  const s = status ?? "candidate";
  const showPct = confidence != null && s !== "closed";
  return (
    <span
      title={STATUS_HINT[s]}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-sm font-medium ${STATUS_STYLE[s] ?? STATUS_STYLE.candidate}`}
    >
      {s === "verified" && <IconCheck width={15} height={15} />}
      {s === "dismissed" && <IconEyeOff width={15} height={15} />}
      {statusLabel(s)}
      {showPct && <span className="tabular opacity-80">· {fmtPct(confidence)}</span>}
    </span>
  );
}

const METER_FILL: Record<IncidentStatus, string> = {
  candidate: "bg-line-strong",
  likely: "bg-warn",
  verified: "bg-good",
  dismissed: "bg-muted",
  closed: "bg-muted",
};

/** Confidence bar with the Likely (60 %) and Verified (85 %) thresholds marked. */
export function ConfidenceMeter({ value, status, label }: { value: number | null; status?: IncidentStatus; label?: string }) {
  const pct = value == null ? 0 : pctOf(value);
  return (
    <div>
      {label && (
        <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
          <span className="text-ink-2">{label}</span>
          <span className="tabular font-semibold">{value == null ? "no data yet" : `${pct}%`}</span>
        </div>
      )}
      <div className="relative h-2.5 rounded-full bg-surface-2" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label ?? "Confidence"}>
        <div className={`h-full rounded-full ${METER_FILL[status ?? "candidate"]}`} style={{ width: `${value == null ? 0 : Math.max(2, pct)}%` }} />
        {[LIKELY_AT, VERIFIED_AT].map((t) => (
          <span key={t} className="absolute -top-0.5 h-3.5 w-0.5 rounded bg-ink/40" style={{ left: `${t * 100}%` }} aria-hidden="true" />
        ))}
      </div>
    </div>
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

/** "Found before any report", "Verified by tram 17", "Tram 17 verifying · ~6 min", "No anomaly on 2 passes". */
export function IncidentBadges({ incident }: { incident: IncidentSummary }) {
  const v = vehicleLabel(incident.verify_vehicle);
  const open = incident.status === "candidate" || incident.status === "likely";
  return (
    <>
      {incident.found_before_report && (
        <Badge tone="accent">
          <IconRadar width={15} height={15} /> Found before any report
        </Badge>
      )}
      {incident.status === "verified" && incident.has_sensor && incident.verify_vehicle && (
        <Badge tone="good">
          <IconCheck width={15} height={15} /> Verified by {incident.verify_vehicle}
        </Badge>
      )}
      {incident.awaiting_verification && v && (
        <Badge tone="warn">
          <IconClock width={15} height={15} /> {v} verifying{incident.verify_eta_min != null ? ` · ~${incident.verify_eta_min} min` : ""}
        </Badge>
      )}
      {open && incident.sensor_misses > 0 && (
        <Badge tone="neutral">
          <IconEyeOff width={15} height={15} /> No anomaly on {incident.sensor_misses} pass{incident.sensor_misses === 1 ? "" : "es"}
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
