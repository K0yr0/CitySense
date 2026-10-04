"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getIncidents } from "@/lib/api";
import { facetCounts, type Filters, filtersQuery, hasFilters, matches } from "@/lib/filters";
import { downloadText, incidentsCsv } from "@/lib/csv";
import { saveQueueOrder } from "@/lib/queueNav";
import { DEPARTMENTS, deptLabel, STATUSES, statusLabel, timeAgo, typeLabel, WORK_STATUSES, workLabel } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import QuickWork from "./QuickWork";
import type { IncidentSummary, WorkStatus } from "@/lib/types";
import { IconArrowRight, IconPin, IconRadar, IconX } from "../icons";
import { LoadingLabel, Skeleton } from "../Skeleton";
import { IncidentBadges, ScoreBar, Segmented, SourceTag, StatusChip, verificationText, WorkChip } from "../ui";

// The whole queue is loaded once and filtered here, so every filter can show live counts.
const QUEUE_LIMIT = 1000;

const COLS = "lg:grid-cols-[2rem_minmax(0,1fr)_8rem_4.5rem_5.5rem_12rem_9.5rem]";

function Row({ i, rank, now, onWork }: { i: IncidentSummary; rank: number; now: number; onWork: (id: number, to: WorkStatus) => void }) {
  return (
    <li
      className={`group relative grid grid-cols-[1.5rem_minmax(0,1fr)] items-start gap-x-4 gap-y-2 px-4 py-4 hover:bg-surface-2 ${COLS} lg:items-center lg:px-6`}
    >
      <span className="pt-0.5 font-mono text-xs text-muted lg:pt-0">{rank}</span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {/* Stretched link: the whole row opens the incident, the buttons stay clickable on top. */}
          <Link href={`/incidents/${i.id}`} className="text-[0.95rem] font-bold leading-tight text-ink after:absolute after:inset-0 after:content-['']">
            {typeLabel(i.type)}
          </Link>
          <span className="text-muted" aria-hidden="true">
            ·
          </span>
          <span className="min-w-0 text-[0.95rem] font-medium text-ink lg:truncate">{i.address ?? `#${i.id}`}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
          <SourceTag incident={i} />
          <span aria-hidden="true">·</span>
          <span className="font-mono">#{i.id}</span>
          <span aria-hidden="true">·</span>
          <span>{deptLabel(i.department)}</span>
          <span aria-hidden="true">·</span>
          <span>last seen {timeAgo(i.last_seen, now)}</span>
        </div>
        <div className="mt-1.5 flex flex-wrap gap-1.5 empty:hidden">
          <IncidentBadges incident={i} />
        </div>
      </div>
      <div className="col-start-2 lg:col-start-auto">
        <ScoreBar score={i.score} />
      </div>
      <span className="col-start-2 font-mono text-sm lg:col-start-auto lg:text-center lg:font-semibold">
        <span className={i.report_count ? "text-ink" : "text-muted"}>{i.report_count}</span>
        <span className="font-sans text-xs text-muted lg:hidden"> reports · {i.sensor_rides} sensor rides</span>
      </span>
      <span className={`hidden text-center font-mono text-sm font-semibold lg:block ${i.sensor_rides ? "text-ink" : "text-muted"}`}>{i.sensor_rides}</span>
      <div className="col-start-2 min-w-0 lg:col-start-auto">
        <StatusChip status={i.status} confidence={i.confidence} />
        <div className="mt-1 text-xs text-muted lg:truncate">{verificationText(i)}</div>
      </div>
      <div className="col-start-2 flex items-start justify-between gap-2 lg:col-start-auto">
        <div className="relative z-10 min-w-0">
          <WorkChip work={i.work_status} />
          {i.work_status !== "todo" && i.work_status_changed_at && (
            <div className="mt-1 text-xs text-muted">{timeAgo(i.work_status_changed_at, now)}</div>
          )}
          <QuickWork key={i.work_status} incident={i} onChanged={onWork} />
        </div>
        <IconArrowRight width={16} height={16} className="mt-1 hidden shrink-0 text-muted group-hover:text-accent lg:block" />
      </div>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className={`grid grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2 px-4 py-5 ${COLS} lg:px-6`}>
      <Skeleton className="h-4 w-4" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-3.5 w-1/2" />
      </div>
      <Skeleton className="col-start-2 h-4 w-24 lg:col-start-auto" />
      <Skeleton className="hidden h-4 w-6 justify-self-center lg:block" />
      <Skeleton className="hidden h-4 w-6 justify-self-center lg:block" />
      <Skeleton className="col-start-2 h-5 w-28 lg:col-start-auto" />
      <Skeleton className="col-start-2 h-5 w-24 lg:col-start-auto" />
    </li>
  );
}

function FilterRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-center">
      <span className="w-28 shrink-0 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted">{label}</span>
      {children}
    </div>
  );
}

function Kpi({ value, label }: { value: number; label: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="font-mono text-3xl font-extrabold leading-none tracking-tight text-ink">{value}</div>
      <div className="mt-1.5 text-xs font-medium uppercase tracking-wider text-muted">{label}</div>
    </div>
  );
}

/** W1: priority queue of every department, filtered by department, confidence status and city work status. */
export default function IncidentQueue() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  // The search box is typed into, so it is local state (mirrored to the URL) to stay responsive.
  // When the URL changes from outside (back / forward), the box follows it.
  const urlQ = params.get("q") ?? "";
  const [q, setQ] = useState(urlQ);
  const [seenUrlQ, setSeenUrlQ] = useState(urlQ);
  if (urlQ !== seenUrlQ) {
    setSeenUrlQ(urlQ);
    if (urlQ !== q.trim()) setQ(urlQ);
  }
  const filters: Filters = {
    department: params.get("department") ?? "",
    status: params.get("status") ?? "",
    work: params.get("work") ?? "",
    q: q.trim(),
  };
  const now = useNow();
  const { data, loading, stale, error, reload } = useApi("incidents:queue", () => getIncidents({ limit: QUEUE_LIMIT }), 15_000);

  // After a quick work change: refresh the queue and say what happened (the row may leave a filtered view).
  const [notice, setNotice] = useState<{ id: number; to: WorkStatus } | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onWork = (id: number, to: WorkStatus) => {
    reload();
    setNotice({ id, to });
    clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 8000);
  };
  useEffect(() => () => clearTimeout(noticeTimer.current), []);

  // Filters live in the URL, so going to an incident and back keeps them (and a filtered view can be shared).
  const setFilter = (key: keyof Filters, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };
  const clearAll = () => {
    setQ("");
    router.replace(pathname, { scroll: false });
  };

  const all = useMemo(() => data ?? [], [data]);
  const list = all.filter((i) => matches(i, filters));

  // Remember this order for "previous / next" on the incident page.
  const order = list.map((i) => i.id).join(",");
  const queryString = params.toString();
  useEffect(() => {
    if (data) saveQueueOrder({ ids: order ? order.split(",").map(Number) : [], query: queryString });
  }, [data, order, queryString]);
  const filtered = hasFilters(filters);
  const mapHref = filtered ? `/?${filtersQuery(filters)}` : "/";

  const dept = facetCounts(all, filters, "department", (i) => i.department);
  const conf = facetCounts(all, filters, "status", (i) => i.status);
  const work = facetCounts(all, filters, "work", (i) => i.work_status);

  const deptOptions = [{ value: "", label: "All", count: dept.all }, ...DEPARTMENTS.map((d) => ({ value: d as string, label: deptLabel(d), count: dept.of(d) }))]
    // "Other" only when something is routed there.
    .filter((o) => o.value !== "inne" || o.count > 0 || filters.department === "inne");
  const statusOptions = [{ value: "", label: "Any", count: conf.all }, ...STATUSES.map((s) => ({ value: s as string, label: statusLabel(s), count: conf.of(s) }))];
  const workOptions = [{ value: "", label: "Any", count: work.all }, ...WORK_STATUSES.map((w) => ({ value: w as string, label: workLabel(w), count: work.of(w) }))];

  const awaiting = list.filter((i) => i.awaiting_verification).length;
  const inProgress = list.filter((i) => i.work_status === "in_progress").length;
  const found = list.filter((i) => i.found_before_report).length;

  return (
    <>
      {/* Stitch notification banner, full width under the top bar. */}
      <div role="status" aria-live="polite" className="empty:hidden">
        {notice && (
          <div className="border-b border-report/30 bg-report/5 text-ink">
            <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-2 text-xs lg:px-6">
              <span className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-report motion-safe:animate-pulse" />
                <span>
                  Notice: <b className="font-semibold">#{notice.id}</b> moved to {workLabel(notice.to).toLowerCase()}.
                </span>
                <Link href={`/incidents/${notice.id}`} className="font-semibold text-report underline">
                  Open it
                </Link>
              </span>
              <button type="button" onClick={() => setNotice(null)} className="text-muted hover:text-ink" aria-label="Dismiss">
                <IconX width={14} height={14} />
              </button>
            </div>
          </div>
        )}
      </div>

      <main className="mx-auto w-full max-w-[1440px] flex-1 space-y-6 px-4 py-8 lg:px-6">
        <section className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Incident queue</h1>
            <p className="mt-1 text-sm text-muted">All departments, sorted by priority score: sensor severity, number of reports, urgency and who is affected.</p>
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            {data ? (
              <>
                <Kpi value={list.length} label={filtered ? `of ${all.length} incidents` : "incidents"} />
                <Kpi value={inProgress} label="work in progress" />
                <Kpi value={awaiting} label="awaiting a vehicle" />
                <Kpi value={found} label="found before a report" />
              </>
            ) : (
              Array.from({ length: 4 }, (_, n) => <Skeleton key={n} className="h-[5.25rem] rounded-xl" />)
            )}
          </div>
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-line bg-surface p-5" aria-label="Filters">
          <FilterRow label="Department">
            <Segmented label="Department" value={filters.department} options={deptOptions} onChange={(v) => setFilter("department", v)} />
          </FilterRow>
          <FilterRow label="Confidence">
            <Segmented label="Confidence status" value={filters.status} options={statusOptions} onChange={(v) => setFilter("status", v)} />
          </FilterRow>
          <FilterRow label="City work">
            <Segmented label="City work status" value={filters.work} options={workOptions} onChange={(v) => setFilter("work", v)} />
          </FilterRow>
          <div className="flex flex-col gap-2 border-t border-line pt-3 md:flex-row md:items-center">
            <label htmlFor="queue-search" className="w-28 shrink-0 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted">
              Search
            </label>
            <div className="flex flex-1 flex-wrap items-center gap-3">
              <div className="relative w-full max-w-sm">
                <svg className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <circle cx="11" cy="11" r="7" />
                  <path d="M20 20l-3.5-3.5" />
                </svg>
                <input
                  id="queue-search"
                  type="search"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setFilter("q", e.target.value.trim());
                  }}
                  placeholder="Street, #id or type"
                  className="w-full rounded-lg border border-line-strong bg-surface py-1.5 pl-8 pr-8 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
                />
                {q && (
                  <button
                    type="button"
                    onClick={() => {
                      setQ("");
                      setFilter("q", "");
                    }}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
                    aria-label="Clear search"
                  >
                    <IconX width={14} height={14} />
                  </button>
                )}
              </div>
              {filtered && (
                <button type="button" onClick={clearAll} className="text-xs font-medium text-ink-2 underline hover:text-ink">
                  Clear filters
                </button>
              )}
              <Link
                href={mapHref}
                className="ml-auto inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs font-semibold hover:bg-surface-2"
              >
                <IconPin width={15} height={15} className="text-crit" /> {filtered ? `Show these ${list.length} on the map` : "Show these on the map"}
              </Link>
            </div>
          </div>
        </section>

        <section className={`overflow-hidden rounded-xl border border-line bg-surface transition-opacity ${stale ? "opacity-60" : ""}`}>
          <div
            className={`hidden items-center gap-x-4 border-b border-line bg-surface-2 px-6 py-3 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted lg:grid ${COLS}`}
          >
            <span>#</span>
            <span>Incident</span>
            <span>Score</span>
            <span className="text-center">Reports</span>
            <span className="text-center">Sensor rides</span>
            <span>Confidence</span>
            <span>City work</span>
          </div>

          {loading && (
            <ol className="divide-y divide-line">
              <LoadingLabel>Loading incidents…</LoadingLabel>
              {Array.from({ length: 6 }, (_, n) => (
                <RowSkeleton key={n} />
              ))}
            </ol>
          )}

          {!loading && list.length === 0 && (
            <div className="flex flex-col items-center px-6 py-16 text-center">
              <span className="grid h-12 w-12 place-items-center rounded-full border border-line bg-surface-2 text-ink-2">
                <IconRadar width={24} height={24} />
              </span>
              {filtered ? (
                <>
                  <h2 className="mt-4 text-lg font-bold">Nothing matches these filters</h2>
                  <p className="mt-1 max-w-md text-sm text-muted">Try another department or status, or clear the filters.</p>
                  <button type="button" onClick={clearAll} className="mt-4 rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold hover:bg-surface-2">
                    Clear filters
                  </button>
                </>
              ) : (
                <>
                  <h2 className="mt-4 text-lg font-bold">No incidents yet</h2>
                  <p className="mt-1 max-w-md text-sm text-muted">
                    {error ? "The backend could not be reached." : "Incidents appear as soon as a citizen reports a problem or a vehicle records one."}
                  </p>
                </>
              )}
            </div>
          )}

          {list.length > 0 && (
            <ol className="divide-y divide-line">
              {list.map((i, idx) => (
                <Row key={i.id} i={i} rank={idx + 1} now={now} onWork={onWork} />
              ))}
            </ol>
          )}

          {data && (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line bg-surface-2/60 px-6 py-3.5 text-xs text-muted">
              <span>
                Showing {list.length} of {all.length} incidents based on current priority score
              </span>
              <span className="flex items-center gap-2">
                <span className="font-medium text-ink-2">Sorted by priority score</span>
                <span className="text-line-strong" aria-hidden="true">
                  |
                </span>
                <button
                  type="button"
                  disabled={!list.length}
                  onClick={() => downloadText(`citysense-incidents-${new Date().toISOString().slice(0, 10)}.csv`, incidentsCsv(list))}
                  className="font-semibold text-accent hover:underline disabled:opacity-50"
                >
                  Export CSV
                </button>
              </span>
            </div>
          )}
        </section>
      </main>
    </>
  );
}
