"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { SOURCE_LABEL, SOURCE_VAR, timeAgo, type SourceKind } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { IconLayers } from "../icons";

export interface LayerToggles {
  segments: boolean;
  incidents: boolean;
  vehicles: boolean;
  hideDone: boolean; // hide incidents the city already marked done
}

// Same three classes as the map (lib/format healthClass), plus "not measured".
const HEALTH_KEY: { label: string; color: string; quiet?: boolean }[] = [
  { label: "Good", color: "var(--good)" },
  { label: "Worn", color: "var(--warn)" },
  { label: "Poor", color: "var(--crit)" },
  { label: "Not measured", color: "var(--line-strong)", quiet: true },
];

function Layer({ checked, onToggle, title, count, children }: { checked: boolean; onToggle: () => void; title: string; count?: number; children: ReactNode }) {
  return (
    <div className="space-y-2 border-t border-line pt-3.5 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between">
        <label className="flex cursor-pointer items-center gap-2 font-bold text-ink">
          <input type="checkbox" checked={checked} onChange={onToggle} className="h-3.5 w-3.5 accent-[var(--accent)]" />
          {title}
        </label>
        {count !== undefined && <span className="font-mono text-[0.6875rem] font-medium text-muted">{count.toLocaleString("en-US")}</span>}
      </div>
      <div className={`space-y-1.5 pl-5 text-[0.6875rem] ${checked ? "" : "opacity-40"}`}>{children}</div>
    </div>
  );
}

/** Stitch "Overlay 1": floating layers panel, top-left, collapsible. */
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
        className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-xs font-bold uppercase tracking-wider text-ink shadow-lg"
      >
        <IconLayers width={16} height={16} /> Layers
        {filter && <span className="rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 text-[0.625rem] normal-case tracking-normal text-accent">filtered</span>}
      </button>
    );
  }

  return (
    <aside
      className="absolute left-4 top-4 z-10 flex max-h-[calc(100%-2rem)] w-72 max-w-[calc(100%-2rem)] flex-col overflow-hidden rounded-xl border border-line bg-surface/95 text-xs shadow-lg backdrop-blur"
      aria-label="Map layers"
    >
      <div className="flex items-center justify-between border-b border-line bg-surface-2 px-3.5 py-2.5">
        <h2 className="text-[0.6875rem] font-bold uppercase tracking-wider text-ink">Layers</h2>
        <button type="button" onClick={() => setOpen(false)} className="text-muted hover:text-ink" aria-label="Collapse layers">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M18 15l-6-6-6 6" />
          </svg>
        </button>
      </div>

      <div className="space-y-3.5 overflow-y-auto p-3.5">
        <Layer checked={toggles.segments} onToggle={() => flip("segments")} title="Road & track health" count={counts.segments}>
          <ul className="grid grid-cols-2 gap-x-2 gap-y-1.5">
            {HEALTH_KEY.map((k) => (
              <li key={k.label} className="flex items-center gap-1.5">
                <span className="h-1 w-3 rounded-full" style={{ background: k.color }} />
                <span className={k.quiet ? "text-muted" : "text-ink-2"}>{k.label}</span>
              </li>
            ))}
          </ul>
          <p className="text-[0.625rem] leading-tight text-muted">
            Thicker = tram track. Faded = measured long ago. Latest: {latestMeasurement ? timeAgo(latestMeasurement, now) : "—"}.
          </p>
        </Layer>

        <Layer checked={toggles.incidents} onToggle={() => flip("incidents")} title="Incidents" count={counts.incidents}>
          <ul className="space-y-1">
            {(["report", "sensor", "both"] as SourceKind[]).map((k) => (
              <li key={k} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: SOURCE_VAR[k] }} />
                <span className="text-ink-2">{SOURCE_LABEL[k]}</span>
              </li>
            ))}
          </ul>
          <p className="text-[0.625rem] leading-tight text-muted">The icon shows the type; larger = higher priority.</p>
          <label className="flex cursor-pointer items-center gap-1.5 pt-0.5 text-ink-2">
            <input type="checkbox" checked={toggles.hideDone} onChange={() => flip("hideDone")} className="h-3 w-3 accent-[var(--accent)]" />
            Hide finished work
          </label>
          {filter && (
            <div className="mt-1 flex items-center justify-between gap-2 rounded border border-line bg-surface-2 p-2 text-[0.625rem]">
              <div className="min-w-0">
                <span className="block text-[0.5625rem] font-bold uppercase tracking-wider text-muted">From the queue</span>
                <span className="font-semibold text-ink">{filter.label}</span>
              </div>
              <div className="flex shrink-0 items-center gap-1.5 font-bold text-accent">
                <Link href={filter.listHref} className="hover:underline">
                  List
                </Link>
                <span aria-hidden="true">·</span>
                <button type="button" onClick={filter.onClear} className="text-muted hover:underline">
                  Clear
                </button>
              </div>
            </div>
          )}
        </Layer>

        <Layer checked={toggles.vehicles} onToggle={() => flip("vehicles")} title="Live ZTM vehicles" count={counts.vehicles}>
          <div className="flex items-center gap-4 text-ink-2">
            <span className="flex items-center gap-1.5 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-ink" /> Tram
            </span>
            <span className="flex items-center gap-1.5 font-medium">
              <span className="h-2.5 w-2.5 rounded-full bg-muted" /> Bus
            </span>
          </div>
          <p className="text-[0.625rem] text-muted">Zoom in for line numbers. Every 15 s{ago !== null ? ` · ${ago} s ago` : ""}.</p>
        </Layer>
      </div>
    </aside>
  );
}
