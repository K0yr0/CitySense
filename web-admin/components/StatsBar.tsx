"use client";

import { Fragment } from "react";
import { getStats } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";

/**
 * One compact line above the map (Stitch "live numbers strip"): Reports → Incidents → Verified →
 * Found before any report → Avg verification, numbers in mono. Polls /stats every 10 s.
 */
export default function StatsBar() {
  const { data, updatedAt } = useApi("stats", getStats, 10_000);
  const now = useNow(5000);
  const avg = data?.avg_verification_min;
  const steps = [
    { label: "reports", value: fmtNumber(data?.reports_total), hint: "citizen reports, 19115 + web" },
    { label: "incidents", value: fmtNumber(data?.incidents_total), hint: "after merging duplicates" },
    { label: "verified", value: fmtNumber(data?.verified_total), hint: "confidence ≥ 85%: sensors and citizens agree" },
    { label: "found before any report", value: fmtNumber(data?.found_before_report), hint: "detected by vehicle sensors first", strong: true },
    { label: "avg verification", value: avg != null ? `${Math.round(avg)} min` : "—", hint: "report → sensor confirmation" },
  ];
  const ago = updatedAt ? Math.max(0, Math.round((now - updatedAt) / 1000)) : null;

  return (
    <div className="border-b border-line bg-surface">
      <div className="flex min-h-9 flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-1.5 text-xs text-ink-2">
        <ol className="flex flex-wrap items-center gap-x-2 gap-y-1" aria-label="City-wide funnel">
          {steps.map((s, idx) => (
            <Fragment key={s.label}>
              {idx > 0 && (
                <li aria-hidden="true" className="hidden font-bold text-line-strong sm:block">
                  →
                </li>
              )}
              <li
                className={`flex items-baseline gap-1.5 whitespace-nowrap ${s.strong ? "rounded-full border border-line-strong bg-surface-2 px-2.5 py-0.5 font-medium text-ink" : ""}`}
                title={s.hint}
              >
                <span className={`font-mono font-bold ${s.strong ? "text-accent" : "text-sm text-ink"}`}>{data ? s.value : "…"}</span>
                <span className={s.strong ? "" : "text-muted"}>{s.label}</span>
              </li>
            </Fragment>
          ))}
        </ol>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 font-medium ${data ? "text-good-ink" : "text-muted"}`}>
            <span className={`inline-block h-2 w-2 rounded-full ${data ? "live-dot bg-good" : "bg-line-strong"}`} />
            {ago === null ? "Connecting…" : `Live · ${ago} s ago`}
          </span>
          {data && (
            <>
              <span className="hidden text-line-strong xl:inline" aria-hidden="true">
                |
              </span>
              <span className="hidden items-center gap-1.5 font-medium text-muted xl:flex">
                <b className="font-mono text-ink">{fmtNumber(data.rides_total)}</b> rides ·<b className="font-mono text-ink">{fmtNumber(data.contributors_total)}</b>{" "}
                contributors ·<b className="font-mono text-ink">{fmtNumber(data.segments_measured)}</b> segments
              </span>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
