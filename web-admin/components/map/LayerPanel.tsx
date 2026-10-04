"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { APP_STATUS_LABEL, APP_WORK_LABEL, HEALTH_CLASS_LABEL, HEALTH_CLASSES, HEALTH_HEX, PIN_STATUS_HEX, timeAgo, WORK_HEX } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { IconLayers } from "../icons";

export interface LayerToggles {
  segments: boolean;
  incidents: boolean;
  vehicles: boolean;
  showDone: boolean; // pins the city already fixed (green, like the app)
  showClosed: boolean; // dismissed / closed incidents (not on the app's map)
}

// Pin colours, in the app's words (lib/format: same hex as mobile/src/lib/labels.ts).
const PIN_KEY: { label: string; color: string }[] = [
  { label: APP_STATUS_LABEL.candidate, color: PIN_STATUS_HEX.candidate },
  { label: APP_STATUS_LABEL.likely, color: PIN_STATUS_HEX.likely },
  { label: APP_STATUS_LABEL.verified, color: PIN_STATUS_HEX.verified },
  { label: APP_WORK_LABEL.done, color: WORK_HEX.done },
];

/** Road colour key at the top of the map: the same bar as the citizen app (colour classes only). */
export function HealthLegend({ className = "" }: { className?: string }) {
  return (
    <ul
      aria-label="Road colours"
      className={`absolute left-4 top-[4.25rem] z-10 flex items-center gap-3.5 rounded-full border border-line bg-surface/95 px-4 py-2 text-xs font-medium text-ink shadow-lg backdrop-blur xl:left-1/2 xl:top-4 xl:-translate-x-1/2 ${className}`}
    >
      {HEALTH_CLASSES.map((h) => (
        <li key={h} className="flex items-center gap-1.5 whitespace-nowrap">
          <span className="h-2.5 w-4 rounded-full" style={{ background: HEALTH_HEX[h] }} />
          {HEALTH_CLASS_LABEL[h]}
        </li>
      ))}
    </ul>
  );
}

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
        <Layer checked={toggles.segments} onToggle={() => flip("segments")} title="Road colours" count={counts.segments}>
          <p className="leading-snug text-ink-2">Good · Fair · Poor · Not measured, same colours as the citizen app.</p>
          <p className="text-[0.625rem] leading-tight text-muted">
            Thicker = tram track. Faded = measured long ago (admin only). Latest: {latestMeasurement ? timeAgo(latestMeasurement, now) : "—"}.
          </p>
        </Layer>

        <Layer checked={toggles.incidents} onToggle={() => flip("incidents")} title="Problems" count={counts.incidents}>
          <ul className="grid grid-cols-2 gap-x-2 gap-y-1">
            {PIN_KEY.map((k) => (
              <li key={k.label} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: k.color }} />
                <span className="text-ink-2">{k.label}</span>
              </li>
            ))}
          </ul>
          <p className="text-[0.625rem] leading-tight text-muted">Pin colour = confidence (green once fixed), as in the app. The icon shows the type; larger = higher priority.</p>
          <div className={filter ? "space-y-1.5 opacity-50" : "space-y-1.5"} title={filter ? "The queue filter decides which problems are shown" : undefined}>
            <label className="flex cursor-pointer items-center gap-1.5 pt-0.5 text-ink-2">
              <input type="checkbox" checked={toggles.showDone} onChange={() => flip("showDone")} className="h-3 w-3 accent-[var(--accent)]" disabled={Boolean(filter)} />
              Show fixed problems
            </label>
            <label className="flex cursor-pointer items-center gap-1.5 text-ink-2">
              <input type="checkbox" checked={toggles.showClosed} onChange={() => flip("showClosed")} className="h-3 w-3 accent-[var(--accent)]" disabled={Boolean(filter)} />
              Show not found / closed <span className="text-muted">(admin only)</span>
            </label>
          </div>
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
