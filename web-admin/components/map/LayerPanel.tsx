"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { SOURCE_LABEL, SOURCE_VAR, timeAgo, type SourceKind } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { IconLayers, IconX } from "../icons";

export interface LayerToggles {
  segments: boolean;
  incidents: boolean;
  vehicles: boolean;
  hideDone: boolean; // hide incidents the city already marked done
}

function Row({ checked, onToggle, title, count, children }: { checked: boolean; onToggle: () => void; title: string; count?: number; children: ReactNode }) {
  return (
    <div className="border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
      <label className="flex cursor-pointer items-center gap-3">
        <input type="checkbox" checked={checked} onChange={onToggle} className="h-5 w-5 accent-[var(--accent)]" />
        <span className="flex-1 text-base font-semibold">{title}</span>
        {count !== undefined && <span className="tabular text-sm text-muted">{count.toLocaleString("en-US")}</span>}
      </label>
      <div className={`mt-2 pl-8 text-sm text-ink-2 ${checked ? "" : "opacity-40"}`}>{children}</div>
    </div>
  );
}

export default function LayerPanel({
  toggles,
  onChange,
  counts,
  vehiclesUpdatedAt,
  latestMeasurement,
  filter,
  open,
  setOpen,
}: {
  toggles: LayerToggles;
  onChange: (t: LayerToggles) => void;
  counts: { segments?: number; incidents?: number; vehicles?: number };
  vehiclesUpdatedAt: number;
  latestMeasurement: string | null;
  /** Active queue filter ("Show on the map"), or null. */
  filter: { label: string; listHref: string; onClear: () => void } | null;
  open: boolean;
  setOpen: (open: boolean) => void;
}) {
  const now = useNow(5000);
  const flip = (k: keyof LayerToggles) => onChange({ ...toggles, [k]: !toggles[k] });
  const ago = vehiclesUpdatedAt ? Math.max(0, Math.round((now - vehiclesUpdatedAt) / 1000)) : null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute left-3 top-3 z-10 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-base font-semibold shadow-sm"
      >
        <IconLayers /> Layers
        {filter && <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs font-semibold text-accent">filtered</span>}
      </button>
    );
  }

  return (
    <aside className="absolute left-3 top-3 z-10 w-[19rem] max-w-[calc(100%-1.5rem)] rounded-2xl border border-line bg-surface p-4 shadow-sm" aria-label="Map layers">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Layers</h2>
        <button type="button" onClick={() => setOpen(false)} className="rounded-md p-1 text-muted hover:bg-surface-2" aria-label="Hide layer panel">
          <IconX width={18} height={18} />
        </button>
      </div>

      <Row checked={toggles.segments} onToggle={() => flip("segments")} title="Road & track health" count={counts.segments}>
        <div className="h-2.5 rounded-full" style={{ background: "linear-gradient(90deg, var(--crit), var(--warn), var(--good))" }} />
        <div className="mt-1 flex justify-between text-xs text-muted">
          <span>Poor</span>
          <span>Good</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="inline-block h-1.5 w-5 rounded-full bg-line-strong" /> Not measured
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="inline-block h-2 w-5 rounded-full bg-muted" /> Tram
          </span>
          <span className="flex items-center gap-1.5 whitespace-nowrap">
            <span className="inline-block h-1 w-5 rounded-full bg-muted" /> Road
          </span>
        </div>
        <p className="mt-1.5 text-xs text-muted">
          Faded = measured long ago. Latest measurement {latestMeasurement ? timeAgo(latestMeasurement, now) : "—"}.
        </p>
      </Row>

      <Row checked={toggles.incidents} onToggle={() => flip("incidents")} title="Incidents" count={counts.incidents}>
        {filter && (
          <div className="mb-2.5 rounded-lg bg-accent-soft px-2.5 py-2 text-accent">
            <div className="text-xs font-semibold uppercase tracking-wide">From the queue</div>
            <div className="font-medium text-ink">{filter.label}</div>
            <div className="mt-1 flex gap-3 text-sm font-semibold">
              <Link href={filter.listHref} className="underline">
                List
              </Link>
              <button type="button" onClick={filter.onClear} className="underline">
                Clear
              </button>
            </div>
          </div>
        )}
        <ul className="space-y-1">
          {(["report", "sensor", "both"] as SourceKind[]).map((k) => (
            <li key={k} className="flex items-center gap-2">
              <span className="inline-block h-3.5 w-3.5 rounded-full ring-2 ring-surface" style={{ background: SOURCE_VAR[k] }} />
              {SOURCE_LABEL[k]}
            </li>
          ))}
        </ul>
        <p className="mt-1.5 text-xs text-muted">Larger dot = higher priority score</p>
        <label className="mt-2 flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" checked={toggles.hideDone} onChange={() => flip("hideDone")} className="h-4 w-4 accent-[var(--accent)]" />
          Hide finished work
        </label>
      </Row>

      <Row checked={toggles.vehicles} onToggle={() => flip("vehicles")} title="Live ZTM vehicles" count={counts.vehicles}>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-ink" /> Tram
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-muted" /> Bus
          </span>
        </div>
        <p className="mt-1.5 text-xs text-muted">Refreshed every 15 s{ago !== null ? ` · updated ${ago} s ago` : ""}</p>
      </Row>
    </aside>
  );
}
