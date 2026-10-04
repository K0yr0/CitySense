import type { Department, IncidentStatus, IncidentSummary, IssueType, WorkStatus } from "./types";

export const TYPE_LABEL: Record<IssueType, string> = {
  road_damage: "Road damage",
  tram_track: "Tram track defect",
  streetlight: "Streetlight out",
  flooding: "Flooding",
  waste: "Litter", // same word as the citizen app
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

/** Deck.gl colours for incident sources (= --report / --sensor / --both); CVD-validated in both themes. */
export function sourceRGBA(kind: SourceKind, dark: boolean): RGBA {
  const light = { report: [37, 99, 235], sensor: [13, 148, 136], both: [234, 88, 12] } as const;
  const night = { report: [59, 130, 246], sensor: [13, 148, 136], both: [234, 88, 12] } as const;
  const c = (dark ? night : light)[kind];
  return [c[0], c[1], c[2], 235];
}

/** How recent a health measurement is: fresh (< 1 h), today (< 24 h), older (< 7 d) or stale. */
export type Freshness = "fresh" | "today" | "older" | "stale";

export function freshness(iso: string | null | undefined, now: number): Freshness {
  const t = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(t)) return "stale";
  const h = (now - t) / 3_600_000;
  return h < 1 ? "fresh" : h < 24 ? "today" : h < 24 * 7 ? "older" : "stale";
}

/** Map opacity per freshness: old measurements fade so the live picture stands out. */
export const FRESHNESS_ALPHA: Record<Freshness, number> = { fresh: 235, today: 190, older: 120, stale: 70 };

/*
 * W6: the admin map shows the same picture as the citizen app. Classes, cut-offs, colours and words
 * below are copied from mobile/src/lib/labels.ts + mobile/src/i18n (labels, map) and
 * backend/api/mobile.py (GOOD_AT 0.7, FAIR_AT 0.4). Change them only together with A.
 */
export type HealthClass = "good" | "fair" | "poor" | "unknown";

export const HEALTH_CLASSES: HealthClass[] = ["good", "fair", "poor", "unknown"];

export function healthClass(h: number | null | undefined): HealthClass {
  if (h === null || h === undefined || Number.isNaN(h)) return "unknown";
  return h >= 0.7 ? "good" : h >= 0.4 ? "fair" : "poor";
}

export const HEALTH_HEX: Record<HealthClass, string> = { good: "#1F9D55", fair: "#F2B300", poor: "#D93025", unknown: "#9AA0A6" };

export const HEALTH_CLASS_LABEL: Record<HealthClass, string> = { good: "Good", fair: "Fair", poor: "Poor", unknown: "Not measured" };

export function healthWord(h: number | null | undefined): string {
  return HEALTH_CLASS_LABEL[healthClass(h)];
}

function hexRGBA(hex: string, alpha = 255): RGBA {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255, alpha];
}

/** Deck.gl colour per health class (same hex in both themes, like the app). */
export function healthClassRGBA(c: HealthClass): RGBA {
  return hexRGBA(HEALTH_HEX[c], c === "unknown" ? 150 : 240);
}

/** Pin colour by confidence status; work done overrides with green (app: incidentColor). */
export const PIN_STATUS_HEX: Record<IncidentStatus, string> = {
  candidate: "#9AA0A6",
  likely: "#F29900",
  verified: "#D93025",
  dismissed: "#5F6368",
  closed: "#5F6368",
};
export const WORK_HEX: Record<WorkStatus, string> = { todo: "#9AA0A6", in_progress: "#1A73E8", done: "#1F9D55" };

export function pinHex(i: Pick<IncidentSummary, "status" | "work_status">): string {
  return i.work_status === "done" ? WORK_HEX.done : (PIN_STATUS_HEX[i.status] ?? PIN_STATUS_HEX.candidate);
}

export function pinRGBA(i: Pick<IncidentSummary, "status" | "work_status">): RGBA {
  return hexRGBA(pinHex(i));
}

/** The app's citizen-facing words, used on the map so both apps say the same thing. */
export const APP_STATUS_LABEL: Record<IncidentStatus, string> = {
  candidate: "Unconfirmed",
  likely: "Likely",
  verified: "Verified",
  dismissed: "Not found",
  closed: "Closed",
};
export const APP_WORK_LABEL: Record<WorkStatus, string> = { todo: "Not started", in_progress: "City is working on it", done: "Fixed" };

/** "Reported by 3 people" (app: map.card.reportedBy / noReports). */
export function reportedBy(n: number): string {
  if (n <= 0) return "No reports yet";
  return `Reported by ${n} ${n === 1 ? "person" : "people"}`;
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

/** Hours -> "45 min" / "18 h" / "2.5 d". */
export function fmtDuration(hours: number | null | undefined): string {
  if (typeof hours !== "number" || !Number.isFinite(hours)) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours)} h`;
  return `${(hours / 24).toFixed(1)} d`;
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
