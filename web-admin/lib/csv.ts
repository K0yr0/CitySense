// "Export CSV" of the incident queue (Stitch footer): the rows as currently filtered and sorted.
import { deptLabel, statusLabel, typeLabel, workLabel } from "./format";
import type { IncidentSummary } from "./types";

const COLUMNS: [string, (i: IncidentSummary, rank: number) => string | number | null][] = [
  ["rank", (_, r) => r],
  ["id", (i) => i.id],
  ["type", (i) => typeLabel(i.type)],
  ["address", (i) => i.address],
  ["department", (i) => deptLabel(i.department)],
  ["score", (i) => i.score.toFixed(3)],
  ["confidence_status", (i) => statusLabel(i.status)],
  ["confidence_pct", (i) => Math.round(i.confidence * 100)],
  ["city_work", (i) => workLabel(i.work_status)],
  ["reports", (i) => i.report_count],
  ["sensor_rides", (i) => i.sensor_rides],
  ["found_before_report", (i) => (i.found_before_report ? "yes" : "no")],
  ["first_seen", (i) => i.first_seen],
  ["last_seen", (i) => i.last_seen],
  ["lat", (i) => i.lat],
  ["lon", (i) => i.lon],
];

function cell(v: string | number | null): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function incidentsCsv(list: IncidentSummary[]): string {
  const rows = list.map((i, n) => COLUMNS.map(([, get]) => cell(get(i, n + 1))).join(","));
  return [COLUMNS.map(([h]) => h).join(","), ...rows].join("\n");
}

/** Save text as a file in the browser (UTF-8 with BOM so Excel shows Polish letters). */
export function downloadText(filename: string, text: string, type = "text/csv") {
  const url = URL.createObjectURL(new Blob(["﻿", text], { type: `${type};charset=utf-8` }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
