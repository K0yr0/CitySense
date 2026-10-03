"use client";

import { Fragment } from "react";
import { getStats } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import { IconArrowRight } from "./icons";

/**
 * One compact line above the map: Reports → Incidents → Verified → Found before any report → Avg verification.
 * Polls /stats every 10 s. The full numbers live on the Stats page.
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
      <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 px-4 py-2 lg:px-6">
        <ol className="flex flex-1 flex-wrap items-center gap-x-3 gap-y-1" aria-label="City-wide funnel">
          {steps.map((s, idx) => (
            <Fragment key={s.label}>
              {idx > 0 && (
                <li aria-hidden="true" className="hidden text-line-strong sm:block">
                  <IconArrowRight width={16} height={16} />
                </li>
              )}
              <li className={`flex items-baseline gap-1.5 whitespace-nowrap ${s.strong ? "rounded-md bg-accent-soft px-2 py-0.5" : ""}`} title={s.hint}>
                <span className={`tabular text-xl font-semibold leading-tight tracking-tight ${s.strong ? "text-accent" : ""}`}>{data ? s.value : "…"}</span>
                <span className="text-sm text-ink-2">{s.label}</span>
              </li>
            </Fragment>
          ))}
        </ol>
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className={`inline-block h-2 w-2 rounded-full ${data ? "live-dot bg-good" : "bg-line-strong"}`} />
            {ago === null ? "Connecting…" : `Live · ${ago} s ago`}
          </span>
          {data && (
            <span className="tabular hidden xl:inline">
              {fmtNumber(data.rides_total)} rides · {fmtNumber(data.contributors_total)} contributors · {fmtNumber(data.segments_measured)} segments
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
