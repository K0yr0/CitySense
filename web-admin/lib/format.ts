import type { Department, IncidentStatus, IncidentSummary, IssueType, WorkStatus } from "./types";

export const TYPE_LABEL: Record<IssueType, string> = {
  road_damage: "Road damage",
  tram_track: "Tram track defect",
  streetlight: "Streetlight out",
  flooding: "Flooding",
  waste: "Waste",
  other: "Other",
};

export const STATUS_LABEL: Record<IncidentStatus, string> = {
  candidate: "Candidate",
  likely: "Likely",
  verified: "Verified",
  dismissed: "Dismissed",
  closed: "Closed",
};

/** One line per status for tooltips / legends (thresholds from lib/confidence.ts). */
export const STATUS_HINT: Record<IncidentStatus, string> = {
  candidate: "Confidence below 60%: needs more answers or a sensor pass",
  likely: "Confidence 60–85%: probably real",
  verified: "Confidence 85% or more: sensors and citizens agree",
  dismissed: "Confidence below 10%: checks found nothing",
  closed: "Handled by the city",
};

export const DEPARTMENTS: Department[] = ["ZDM", "Tramwaje Warszawskie", "MPWiK", "Straż Miejska", "inne"];
export const STATUSES: IncidentStatus[] = ["candidate", "likely", "verified", "dismissed", "closed"];

/** City work (set by the admin), separate from the confidence status above. */
export const WORK_STATUSES: WorkStatus[] = ["todo", "in_progress", "done"];

export const WORK_LABEL: Record<WorkStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};

export function workLabel(w: string | null | undefined): string {
  return (w && WORK_LABEL[w as WorkStatus]) || WORK_LABEL.todo;
}

/** 0–1 -> "74%". Confidence is never certain, so anything below 1 shows at most 99%. */
export function pctOf(x: number): number {
  const p = Math.round(Math.min(1, Math.max(0, x)) * 100);
  return x < 1 ? Math.min(99, p) : p;
}

export function fmtPct(x: number | null | undefined): string {
  return typeof x === "number" && Number.isFinite(x) ? `${pctOf(x)}%` : "—";
}

export function deptLabel(d: Department | string | null | undefined): string {
  if (!d) return "—";
  return d === "inne" ? "Other" : d;
}

export function typeLabel(t: string | null | undefined): string {
  return (t && TYPE_LABEL[t as IssueType]) || "Other";
}

export function statusLabel(s: string | null | undefined): string {
  return (s && STATUS_LABEL[s as IncidentStatus]) || "—";
}

/** "tram 17" -> "Tram 17" */
export function vehicleLabel(v: string | null | undefined): string {
  if (!v) return "";
  return v.charAt(0).toUpperCase() + v.slice(1);
}

export type SourceKind = "report" | "sensor" | "both";

export function sourceKind(i: Pick<IncidentSummary, "has_sensor" | "has_report">): SourceKind {
  if (i.has_sensor && i.has_report) return "both";
  return i.has_sensor ? "sensor" : "report";
}

export const SOURCE_LABEL: Record<SourceKind, string> = {
  report: "Citizen reports only",
  sensor: "Sensors only",
  both: "Sensors + reports",
};

/** CSS custom property holding the source colour (defined in globals.css). */
export const SOURCE_VAR: Record<SourceKind, string> = {
  report: "var(--report)",
  sensor: "var(--sensor)",
  both: "var(--both)",
};

type RGBA = [number, number, number, number];

/** Deck.gl colours for incident sources; validated categorical slots (blue / aqua / orange). */
export function sourceRGBA(kind: SourceKind, dark: boolean): RGBA {
  const light = { report: [42, 120, 214], sensor: [27, 175, 122], both: [235, 104, 52] } as const;
  const night = { report: [57, 135, 229], sensor: [25, 158, 112], both: [217, 89, 38] } as const;
  const c = (dark ? night : light)[kind];
  return [c[0], c[1], c[2], 235];
}

const HEALTH_STOPS: [number, [number, number, number]][] = [
  [0, [208, 59, 59]], // critical
  [0.5, [250, 178, 25]], // warning
  [1, [12, 163, 12]], // good
];

/** Segment health 0..1 -> red..amber..green; null -> grey. */
export function healthRGBA(h: number | null | undefined, dark: boolean): RGBA {
  if (h === null || h === undefined || Number.isNaN(h)) {
    return dark ? [120, 120, 115, 150] : [150, 149, 143, 150];
  }
  const x = Math.min(1, Math.max(0, h));
  const i = x <= 0.5 ? 0 : 1;
  const [x0, c0] = HEALTH_STOPS[i];
  const [x1, c1] = HEALTH_STOPS[i + 1];
  const f = (x - x0) / (x1 - x0);
  return [
    Math.round(c0[0] + (c1[0] - c0[0]) * f),
    Math.round(c0[1] + (c1[1] - c0[1]) * f),
    Math.round(c0[2] + (c1[2] - c0[2]) * f),
    230,
  ];
}

export function healthWord(h: number | null | undefined): string {
  if (h === null || h === undefined) return "Not measured";
  if (h >= 0.75) return "Good";
  if (h >= 0.45) return "Worn";
  return "Poor";
}

export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const s = Math.round((now - t) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} d ago`;
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtScore(s: number | null | undefined): string {
  return typeof s === "number" && Number.isFinite(s) ? s.toFixed(2) : "—";
}

export function fmtNumber(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? n.toLocaleString("en-US") : "—";
}

/** Score is ≈ 0–1.5; the bar maps that range to 0–100 %. */
export function scorePct(s: number | null | undefined): number {
  if (typeof s !== "number" || !Number.isFinite(s)) return 0;
  return Math.max(2, Math.min(100, (s / 1.5) * 100));
}
