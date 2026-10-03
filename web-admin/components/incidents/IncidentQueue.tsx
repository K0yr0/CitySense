"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getIncidents } from "@/lib/api";
import { facetCounts, type Filters, filtersQuery, hasFilters, matches } from "@/lib/filters";
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

const COLS = "lg:grid-cols-[2.5rem_minmax(0,1fr)_9rem_5rem_7rem_13rem_8.5rem]";

function Row({ i, rank, now, onWork }: { i: IncidentSummary; rank: number; now: number; onWork: (id: number, to: WorkStatus) => void }) {
  return (
    <li
      className={`group relative grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-x-4 gap-y-2 px-4 py-4 hover:bg-surface-2 ${COLS} lg:items-center lg:px-6`}
    >
      <span className="tabular pt-0.5 text-lg font-semibold text-muted lg:pt-0">{rank}</span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          {/* Stretched link: the whole row opens the incident, the buttons below stay clickable on top. */}
          <Link href={`/incidents/${i.id}`} className="text-xl font-bold leading-tight after:absolute after:inset-0 after:content-['']">
            {typeLabel(i.type)}
          </Link>
          <span className="min-w-0 text-lg text-ink-2 lg:truncate">{i.address ?? `#${i.id}`}</span>
        </div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <SourceTag incident={i} />
          <span className="text-sm text-muted">
            #{i.id} · {deptLabel(i.department)} · last seen {timeAgo(i.last_seen, now)}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 empty:hidden">
          <IncidentBadges incident={i} />
        </div>
      </div>
      <div className="col-start-2 lg:col-start-auto">
        <ScoreBar score={i.score} />
      </div>
      <span className="tabular col-start-2 text-base lg:col-start-auto lg:text-right lg:text-lg lg:font-semibold">
        {i.report_count}
        <span className="lg:hidden"> reports · {i.sensor_rides} sensor rides</span>
      </span>
      <span className="tabular hidden text-right text-lg font-semibold lg:block">{i.sensor_rides}</span>
      <div className="col-start-2 min-w-0 lg:col-start-auto">
        <StatusChip status={i.status} confidence={i.confidence} />
        <div className="mt-1 text-sm text-ink-2 lg:truncate">{verificationText(i)}</div>
      </div>
      <div className="col-start-2 flex items-start justify-between gap-2 lg:col-start-auto">
        <div className="relative z-10 min-w-0">
          <WorkChip work={i.work_status} />
          {i.work_status !== "todo" && i.work_status_changed_at && (
            <div className="mt-1 text-sm text-muted">{timeAgo(i.work_status_changed_at, now)}</div>
          )}
          <QuickWork key={i.work_status} incident={i} onChanged={onWork} />
        </div>
        <IconArrowRight className="mt-1 hidden shrink-0 text-muted group-hover:text-accent lg:block" />
      </div>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className={`grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2 px-4 py-5 ${COLS} lg:px-6`}>
      <Skeleton className="h-5 w-5" />
      <div className="flex flex-col gap-2">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
      <Skeleton className="col-start-2 h-4 w-28 lg:col-start-auto" />
      <Skeleton className="hidden h-5 w-8 justify-self-end lg:block" />
      <Skeleton className="hidden h-5 w-8 justify-self-end lg:block" />
      <Skeleton className="col-start-2 h-6 w-32 lg:col-start-auto" />
      <Skeleton className="col-start-2 h-6 w-24 lg:col-start-auto" />
    </li>
  );
}

function FilterRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 md:flex-row md:items-center">
      <span className="w-32 shrink-0 text-sm font-semibold uppercase tracking-wide text-muted">{label}</span>
      {children}
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
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Incident queue</h1>
          <p className="mt-1 text-lg text-ink-2">All departments, sorted by priority score: sensor severity, number of reports, urgency and who is affected.</p>
        </div>
        {data && all.length > 0 && (
          <div className="flex gap-6 text-right">
            {[
              [list.length, filtered ? `of ${all.length} incidents` : "incidents"],
              [inProgress, "work in progress"],
              [awaiting, "awaiting a vehicle"],
              [found, "found before a report"],
            ].map(([n, label]) => (
              <div key={label}>
                <div className="tabular text-2xl font-semibold">{n}</div>
                <div className="text-sm text-ink-2">{label}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
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
          <label htmlFor="queue-search" className="w-32 shrink-0 text-sm font-semibold uppercase tracking-wide text-muted">
            Search
          </label>
          <div className="flex flex-1 items-center gap-3">
            <input
              id="queue-search"
              type="search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setFilter("q", e.target.value.trim());
              }}
              placeholder="Street, #id or type"
              className="w-full max-w-sm rounded-xl border border-line-strong bg-surface px-3.5 py-2 text-base outline-none focus:border-accent"
            />
            <div className="ml-auto flex items-center gap-1">
              {filtered && (
                <button type="button" onClick={clearAll} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-surface-2">
                  <IconX width={16} height={16} /> Clear filters
                </button>
              )}
              <Link href={mapHref} className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-line-strong px-3 py-1.5 text-sm font-semibold hover:bg-surface-2">
                <IconPin width={16} height={16} /> {filtered ? `Show these ${list.length} on the map` : "Show on the map"}
              </Link>
            </div>
          </div>
        </div>
      </div>

      <p role="status" aria-live="polite" className="empty:hidden">
        {notice && (
          <span className="mt-4 flex items-center gap-3 rounded-xl bg-accent-soft px-4 py-2.5 font-medium text-accent">
            #{notice.id} moved to {workLabel(notice.to).toLowerCase()}.
            <Link href={`/incidents/${notice.id}`} className="underline">
              Open it
            </Link>
            <button type="button" onClick={() => setNotice(null)} className="ml-auto rounded p-0.5 hover:bg-surface" aria-label="Dismiss">
              <IconX width={16} height={16} />
            </button>
          </span>
        )}
      </p>

      <section className={`mt-5 overflow-hidden rounded-2xl border border-line bg-surface transition-opacity ${stale ? "opacity-60" : ""}`}>
        <div className={`hidden gap-x-4 border-b border-line px-6 py-3 text-sm font-semibold uppercase tracking-wide text-muted lg:grid ${COLS}`}>
          <span>#</span>
          <span>Incident</span>
          <span>Score</span>
          <span className="text-right">Reports</span>
          <span className="text-right">Sensor rides</span>
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
            <span className="grid h-14 w-14 place-items-center rounded-full bg-accent-soft text-accent">
              <IconRadar width={28} height={28} />
            </span>
            {filtered ? (
              <>
                <h2 className="mt-4 text-2xl font-semibold">Nothing matches these filters</h2>
                <p className="mt-1 max-w-md text-lg text-ink-2">Try another department or status, or clear the filters.</p>
                <button
                  type="button"
                  onClick={clearAll}
                  className="mt-5 rounded-xl border border-line-strong px-4 py-2 text-base font-semibold hover:bg-surface-2"
                >
                  Clear filters
                </button>
              </>
            ) : (
              <>
                <h2 className="mt-4 text-2xl font-semibold">No incidents yet</h2>
                <p className="mt-1 max-w-md text-lg text-ink-2">
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
      </section>
    </main>
  );
}
