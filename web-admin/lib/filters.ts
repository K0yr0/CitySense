// Incident filters shared by the queue and the city map. They live in the URL
// (?department=ZDM&status=verified&work=todo&q=plac), so a filtered view can move between the two.
import { deptLabel, typeLabel } from "./format";
import type { IncidentSummary } from "./types";

export interface Filters {
  department: string;
  status: string;
  work: string;
  q: string;
}

export type Facet = Exclude<keyof Filters, "q">;

export const FILTER_KEYS: (keyof Filters)[] = ["department", "status", "work", "q"];

export function filtersFrom(params: { get(key: string): string | null }): Filters {
  return {
    department: params.get("department") ?? "",
    status: params.get("status") ?? "",
    work: params.get("work") ?? "",
    q: (params.get("q") ?? "").trim(),
  };
}

export function hasFilters(f: Filters): boolean {
  return Boolean(f.department || f.status || f.work || f.q);
}

/** Query string with only the filter keys (other params, e.g. ?incident=, are dropped). */
export function filtersQuery(f: Filters): string {
  const q = new URLSearchParams();
  for (const k of FILTER_KEYS) if (f[k]) q.set(k, f[k]);
  return q.toString();
}

/** `skip` ignores one facet, for counting that facet's options under the other active filters. */
export function matches(i: IncidentSummary, f: Filters, skip?: Facet): boolean {
  if (skip !== "department" && f.department && i.department !== f.department) return false;
  if (skip !== "status" && f.status && i.status !== f.status) return false;
  if (skip !== "work" && f.work && i.work_status !== f.work) return false;
  if (f.q) {
    const q = f.q.toLowerCase().replace(/^#/, "");
    const hay = `${i.id} ${i.address ?? ""} ${typeLabel(i.type)} ${deptLabel(i.department)}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}

/** Counts per option of one facet, given the other active filters (so the numbers always add up). */
export function facetCounts(list: IncidentSummary[], f: Filters, facet: Facet, key: (i: IncidentSummary) => string) {
  const counts = new Map<string, number>();
  let all = 0;
  for (const i of list) {
    if (!matches(i, f, facet)) continue;
    all += 1;
    counts.set(key(i), (counts.get(key(i)) ?? 0) + 1);
  }
  return { all, of: (v: string) => counts.get(v) ?? 0 };
}
