"use client";

import Link from "next/link";
import { useState } from "react";
import { getIncidents } from "@/lib/api";
import { DEPARTMENTS, deptLabel, STATUSES, statusLabel, timeAgo, typeLabel } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import type { IncidentSummary } from "@/lib/types";
import { IconArrowRight, IconRadar } from "../icons";
import { IncidentBadges, ScoreBar, Segmented, SourceTag, StatusChip, verificationText } from "../ui";

const DEPT_OPTIONS = [{ value: "", label: "All departments" }, ...DEPARTMENTS.map((d) => ({ value: d as string, label: d as string }))];
const STATUS_OPTIONS = [{ value: "", label: "Any status" }, ...STATUSES.map((s) => ({ value: s as string, label: statusLabel(s) }))];

function Row({ i, rank, now }: { i: IncidentSummary; rank: number; now: number }) {
  return (
    <li>
      <Link
        href={`/incidents/${i.id}`}
        className="group grid grid-cols-[2rem_minmax(0,1fr)] items-start gap-x-4 gap-y-2 px-4 py-4 hover:bg-surface-2 lg:grid-cols-[2.5rem_minmax(0,1fr)_10rem_5.5rem_7.5rem_15rem] lg:items-center lg:px-6"
      >
        <span className="tabular pt-0.5 text-lg font-semibold text-muted lg:pt-0">{rank}</span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-xl font-bold leading-tight">{typeLabel(i.type)}</span>
            <span className="min-w-0 text-lg text-ink-2 lg:truncate">{i.address ?? `#${i.id}`}</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
            <SourceTag incident={i} />
            <span className="text-sm text-muted">
              {deptLabel(i.department)} · last seen {timeAgo(i.last_seen, now)}
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
        <div className="col-start-2 flex items-center justify-between gap-2 lg:col-start-auto">
          <div className="min-w-0">
            <StatusChip status={i.status} />
            <div className="mt-1 text-sm text-ink-2 lg:truncate">{verificationText(i)}</div>
          </div>
          <IconArrowRight className="hidden shrink-0 text-muted group-hover:text-accent lg:block" />
        </div>
      </Link>
    </li>
  );
}

export default function IncidentQueue() {
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const now = useNow();
  const { data, loading, stale, error } = useApi(`incidents:${department}:${status}`, () => getIncidents({ department, status, limit: 200 }), 15_000);
  const list = data ?? [];
  const filtered = Boolean(department || status);
  const found = list.filter((i) => i.found_before_report).length;
  const awaiting = list.filter((i) => i.status === "awaiting_verification").length;

  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Incident queue</h1>
          <p className="mt-1 text-lg text-ink-2">Sorted by priority score: sensor severity, number of reports, urgency and who is affected.</p>
        </div>
        {data && list.length > 0 && (
          <div className="flex gap-6 text-right">
            <div>
              <div className="text-2xl font-semibold">{list.length}</div>
              <div className="text-sm text-ink-2">incidents</div>
            </div>
            <div>
              <div className="text-2xl font-semibold">{awaiting}</div>
              <div className="text-sm text-ink-2">awaiting a vehicle</div>
            </div>
            <div>
              <div className="text-2xl font-semibold">{found}</div>
              <div className="text-sm text-ink-2">found before a report</div>
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <span className="w-28 shrink-0 text-sm font-semibold uppercase tracking-wide text-muted">Department</span>
          <Segmented label="Department" value={department} options={DEPT_OPTIONS} onChange={setDepartment} />
        </div>
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <span className="w-28 shrink-0 text-sm font-semibold uppercase tracking-wide text-muted">Status</span>
          <Segmented label="Status" value={status} options={STATUS_OPTIONS} onChange={setStatus} />
        </div>
      </div>

      <section className={`mt-5 overflow-hidden rounded-2xl border border-line bg-surface transition-opacity ${stale ? "opacity-60" : ""}`}>
        <div className="hidden grid-cols-[2.5rem_minmax(0,1fr)_10rem_5.5rem_7.5rem_15rem] gap-x-4 border-b border-line px-6 py-3 text-sm font-semibold uppercase tracking-wide text-muted lg:grid">
          <span>#</span>
          <span>Incident</span>
          <span>Score</span>
          <span className="text-right">Reports</span>
          <span className="text-right">Sensor rides</span>
          <span>Verification</span>
        </div>

        {loading && <p className="px-6 py-16 text-center text-lg text-muted">Loading incidents…</p>}

        {!loading && list.length === 0 && (
          <div className="flex flex-col items-center px-6 py-16 text-center">
            <span className="grid h-14 w-14 place-items-center rounded-full bg-accent-soft text-accent">
              <IconRadar width={28} height={28} />
            </span>
            {filtered ? (
              <>
                <h2 className="mt-4 text-2xl font-semibold">Nothing matches these filters</h2>
                <p className="mt-1 max-w-md text-lg text-ink-2">
                  No {status ? statusLabel(status).toLowerCase() : ""} incidents{department ? ` for ${department}` : ""} right now. That is good news.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setDepartment("");
                    setStatus("");
                  }}
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
                <div className="mt-5 flex gap-3">
                  <Link href="/report" className="rounded-xl bg-accent px-4 py-2 text-base font-semibold text-accent-ink hover:bg-accent-hover">
                    Report a problem
                  </Link>
                  <Link href="/ride" className="rounded-xl border border-line-strong px-4 py-2 text-base font-semibold hover:bg-surface-2">
                    Record a ride
                  </Link>
                </div>
              </>
            )}
          </div>
        )}

        {list.length > 0 && (
          <ol className="divide-y divide-line">
            {list.map((i, idx) => (
              <Row key={i.id} i={i} rank={idx + 1} now={now} />
            ))}
          </ol>
        )}
      </section>
    </main>
  );
}
