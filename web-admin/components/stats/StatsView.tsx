"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getAdminStats } from "@/lib/api";
import { deptLabel, fmtDuration, fmtNumber } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AdminStats, DepartmentLoad } from "@/lib/types";
import { Card } from "../ui";

// Work state colours = the WorkChip tokens (to do neutral, in progress accent, done good).
const WORK_PARTS: { key: "todo" | "in_progress" | "done"; label: string; color: string }[] = [
  { key: "todo", label: "To do", color: "var(--line-strong)" },
  { key: "in_progress", label: "In progress", color: "var(--accent)" },
  { key: "done", label: "Done", color: "var(--good)" },
];

// Trend: validated pair (light + dark) - new = accent, done = good.
const NEW_COLOR = "var(--accent)";
const DONE_COLOR = "var(--good)";

function Tile({ label, value, hint, strong = false }: { label: string; value: string; hint: string; strong?: boolean }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface px-5 py-4 ${strong ? "border-l-4 border-l-accent" : ""}`} title={hint}>
      <div className="tabular text-[2rem] font-semibold leading-none tracking-tight">{value}</div>
      <div className="mt-1.5 text-sm font-medium text-ink-2">{label}</div>
      <div className="mt-0.5 text-xs text-muted">{hint}</div>
    </div>
  );
}

/** Report -> incident -> verified -> done. Reports are merged into incidents, so bars are scaled to incidents. */
function Funnel({ s }: { s: AdminStats }) {
  const base = Math.max(1, s.incidents_total);
  const steps = [
    { label: "Incidents", value: s.incidents_total, note: s.incidents_total ? `${(s.reports_total / s.incidents_total).toFixed(1)} reports merged per incident` : "" },
    { label: "Verified", value: s.verified_total, note: `${Math.round((100 * s.verified_total) / base)}% of incidents` },
    { label: "Done", value: s.done_total, note: `${Math.round((100 * s.done_total) / base)}% of incidents fixed` },
  ];
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="tabular text-2xl font-semibold">{fmtNumber(s.reports_total)}</span>
        <span className="text-ink-2">citizen reports received</span>
      </div>
      <ol className="mt-4 flex flex-col gap-3">
        {steps.map((st) => (
          <li key={st.label} className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-3">
            <span className="text-base font-medium">{st.label}</span>
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <div className="h-6 min-w-0 flex-1 rounded-r bg-surface-2">
                  <div className="h-full rounded-r bg-accent" style={{ width: `${Math.max(1, (100 * st.value) / base)}%` }} />
                </div>
                <span className="tabular w-12 text-right text-lg font-semibold">{fmtNumber(st.value)}</span>
              </div>
              <div className="mt-0.5 text-sm text-muted">{st.note}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function DepartmentBars({ rows }: { rows: DepartmentLoad[] }) {
  const max = Math.max(1, ...rows.map((d) => d.todo + d.in_progress + d.done));
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2" aria-label="Legend">
        {WORK_PARTS.map((p) => (
          <li key={p.key} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: p.color }} /> {p.label}
          </li>
        ))}
      </ul>
      <ul className="flex flex-col gap-3">
        {rows.map((d) => {
          const sum = d.todo + d.in_progress + d.done;
          return (
            <li key={d.department} className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-x-3 gap-y-1 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)_3rem]">
              <span className="col-span-2 truncate font-medium sm:col-span-1" title={deptLabel(d.department)}>
                {deptLabel(d.department)}
              </span>
              <div className="flex h-7 gap-0.5" style={{ width: `${Math.max(2, (100 * sum) / max)}%` }}>
                {WORK_PARTS.map((p) =>
                  d[p.key] > 0 ? (
                    <div
                      key={p.key}
                      title={`${deptLabel(d.department)} · ${p.label}: ${d[p.key]}`}
                      className="tabular flex items-center justify-center overflow-hidden text-sm font-semibold first:rounded-l last:rounded-r"
                      style={{ flexGrow: d[p.key], flexBasis: 0, background: p.color, color: p.key === "todo" ? "var(--ink)" : p.key === "in_progress" ? "var(--accent-ink)" : "#fff" }}
                    >
                      {(100 * d[p.key]) / max >= 6 ? d[p.key] : ""}
                    </div>
                  ) : null,
                )}
              </div>
              <span className="tabular text-right text-ink-2">{sum}</span>
            </li>
          );
        })}
      </ul>
      <div className="-mx-5 mt-5 overflow-x-auto px-5">
        <table className="tabular w-full min-w-[32rem] text-left text-sm">
          <thead className="text-muted">
            <tr className="border-b border-line">
              <th className="py-2 pr-3 font-semibold">Department</th>
              <th className="py-2 pr-3 text-right font-semibold">To do</th>
              <th className="py-2 pr-3 text-right font-semibold">In progress</th>
              <th className="py-2 pr-3 text-right font-semibold">Done</th>
              <th className="py-2 pr-3 text-right font-semibold">Verified</th>
              <th className="py-2 text-right font-semibold">Avg repair</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((d) => (
              <tr key={d.department}>
                <td className="py-2 pr-3 font-medium">{deptLabel(d.department)}</td>
                <td className="py-2 pr-3 text-right">{d.todo}</td>
                <td className="py-2 pr-3 text-right">{d.in_progress}</td>
                <td className="py-2 pr-3 text-right">{d.done}</td>
                <td className="py-2 pr-3 text-right">{d.verified}</td>
                <td className="py-2 text-right">{fmtDuration(d.avg_repair_hours)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const dayLabel = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length || !label) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-surface px-3 py-2 shadow-sm">
      <div className="text-sm font-semibold">{dayLabel(label)}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 text-sm text-ink-2">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
          {p.name}: <span className="tabular font-semibold text-ink">{p.value}</span>
        </div>
      ))}
    </div>
  );
}

function Trend({ daily }: { daily: AdminStats["daily"] }) {
  const tick = { fill: "var(--muted)", fontSize: 13 };
  return (
    <figure>
      <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2" aria-label="Legend">
        {[
          ["New incidents", NEW_COLOR],
          ["Marked done", DONE_COLOR],
        ].map(([label, color]) => (
          <li key={label} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: color }} /> {label}
          </li>
        ))}
      </ul>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: -12 }} barGap={2} barCategoryGap="22%">
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="day" tickFormatter={dayLabel} tick={tick} stroke="var(--line-strong)" tickMargin={6} minTickGap={12} />
            <YAxis allowDecimals={false} tick={tick} stroke="var(--line-strong)" width={40} />
            <Tooltip content={<TrendTooltip />} cursor={{ fill: "var(--surface-2)" }} isAnimationActive={false} />
            <Bar dataKey="new" name="New incidents" fill={NEW_COLOR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="done" name="Marked done" fill={DONE_COLOR} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 text-sm text-ink-2">Per day (UTC): incidents first seen vs incidents the city marked done.</figcaption>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted hover:text-ink">Show data table</summary>
        <table className="tabular mt-2 w-full max-w-sm text-left">
          <thead className="text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">Day</th>
              <th className="py-1 pr-3 text-right font-medium">New</th>
              <th className="py-1 text-right font-medium">Done</th>
            </tr>
          </thead>
          <tbody>
            {daily.map((d) => (
              <tr key={d.day}>
                <td className="py-0.5 pr-3">{dayLabel(d.day)}</td>
                <td className="py-0.5 pr-3 text-right">{d.new}</td>
                <td className="py-0.5 text-right">{d.done}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

/** W5: how the city keeps up - funnel, repair times, department load, 14-day trend. */
export default function StatsView() {
  const { data: s, loading } = useApi("admin-stats", getAdminStats, 30_000);

  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <h1 className="text-3xl font-bold tracking-tight">Statistics</h1>
      <p className="mt-1 text-lg text-ink-2">From citizen report to repaired street, across all departments.</p>

      {loading || !s ? (
        <p className="py-16 text-center text-lg text-muted">Loading statistics…</p>
      ) : (
        <>
          <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label="Average repair time" value={fmtDuration(s.avg_repair_hours)} hint={`first seen → marked done · median ${fmtDuration(s.median_repair_hours)}`} strong />
            <Tile label="Average verification" value={s.avg_verification_min != null ? `${Math.round(s.avg_verification_min)} min` : "—"} hint="vehicle asked → sensor confirmed" />
            <Tile label="Work in progress" value={fmtNumber(s.in_progress_total)} hint="crews on it right now" />
            <Tile label="Found before any report" value={fmtNumber(s.found_before_report)} hint="detected by vehicle sensors first" />
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-2">
            <Card title="Report → incident → verified → done">
              <Funnel s={s} />
            </Card>
            <Card title="Last 14 days">
              <Trend daily={s.daily} />
            </Card>
          </div>

          <Card title="Load per department" className="mt-5">
            {s.departments.length ? <DepartmentBars rows={s.departments} /> : <p className="text-lg text-ink-2">No incidents yet.</p>}
          </Card>
        </>
      )}
    </main>
  );
}
