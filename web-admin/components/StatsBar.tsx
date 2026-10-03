"use client";

import { Fragment } from "react";
import { getStats } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import { IconArrowRight } from "./icons";

/** Funnel: Reports → Incidents → Verified → Found before any report → Avg verification. Polls /stats every 10 s. */
export default function StatsBar() {
  const { data, updatedAt } = useApi("stats", getStats, 10_000);
  const now = useNow(5000);
  const avg = data?.avg_verification_min;
  const steps = [
    { label: "Reports received", value: fmtNumber(data?.reports_total), hint: "citizen reports, 19115 + web" },
    { label: "Incidents", value: fmtNumber(data?.incidents_total), hint: "after merging duplicates" },
    { label: "Verified", value: fmtNumber(data?.verified_total), hint: "confidence ≥ 85%: sensors and citizens agree" },
    { label: "Found before any report", value: fmtNumber(data?.found_before_report), hint: "detected by vehicle sensors first", strong: true },
    { label: "Avg verification", value: avg != null ? `${Math.round(avg)} min` : "—", hint: "report → sensor confirmation" },
  ];
  const ago = updatedAt ? Math.max(0, Math.round((now - updatedAt) / 1000)) : null;

  return (
    <div className="border-b border-line bg-surface">
      <div className="flex flex-col gap-2 px-4 py-3 lg:flex-row lg:items-center lg:gap-6 lg:px-6">
        <ol className="grid flex-1 grid-cols-3 gap-x-4 gap-y-2 md:flex md:items-center md:gap-3" aria-label="City-wide funnel">
          {steps.map((s, idx) => (
            <Fragment key={s.label}>
              {idx > 0 && (
                <li aria-hidden="true" className="hidden text-line-strong md:block">
                  <IconArrowRight width={26} height={26} />
                </li>
              )}
              <li className={`min-w-0 md:flex-1 ${s.strong ? "md:border-l-4 md:border-accent md:pl-3" : ""}`} title={s.hint}>
                <div className="text-[1.6rem] font-semibold leading-none tracking-tight md:text-[2rem]">{data ? s.value : "…"}</div>
                <div className="mt-1 text-sm font-medium leading-snug text-ink-2">{s.label}</div>
              </li>
            </Fragment>
          ))}
        </ol>
        <div className="flex items-center gap-2 text-sm text-muted lg:flex-col lg:items-end lg:gap-0.5">
          <span className="flex items-center gap-2">
            <span className={`inline-block h-2.5 w-2.5 rounded-full ${data ? "live-dot bg-good" : "bg-line-strong"}`} />
            {ago === null ? "Connecting…" : `Live · ${ago} s ago`}
          </span>
          {data && (
            <span className="tabular">
              {fmtNumber(data.rides_total)} rides · {fmtNumber(data.contributors_total)} contributors · {fmtNumber(data.segments_measured)} segments
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
