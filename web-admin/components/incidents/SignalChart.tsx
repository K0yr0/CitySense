"use client";

import { CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Signal } from "@/lib/types";

interface Point {
  t: number;
  v: number;
}

const fmtT = (t: number) => `${t > 0 ? "+" : ""}${t.toFixed(2)} s`;

function SignalTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-line-strong bg-surface px-3 py-2 shadow-sm">
      <div className="tabular text-base font-semibold">{p.v.toFixed(2)} m/s²</div>
      <div className="tabular text-sm text-muted">{fmtT(p.t)} from peak</div>
    </div>
  );
}

/** High-passed acceleration around the strongest bump, with the peak marked. */
export default function SignalChart({ signal }: { signal: Signal }) {
  const fs = signal.fs || 100;
  const data: Point[] = signal.values.map((v, i) => ({ t: (i - signal.peak_index) / fs, v }));
  const peak = data[Math.min(Math.max(0, signal.peak_index), data.length - 1)];
  if (!peak) return <p className="text-muted">No samples in this signal.</p>;
  const tick = { fill: "var(--muted)", fontSize: 13 };
  const t0 = data[0].t;
  const t1 = data[data.length - 1].t;
  const xTicks: number[] = [];
  for (let t = Math.ceil(t0 * 2) / 2; t <= t1 + 1e-9; t += 0.5) xTicks.push(Math.round(t * 10) / 10);

  return (
    <figure>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 30, right: 20, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              domain={["dataMin", "dataMax"]}
              ticks={xTicks}
              tickFormatter={(t: number) => `${t > 0 ? "+" : ""}${t.toFixed(1)} s`}
              tickMargin={8}
              tick={tick}
              stroke="var(--line-strong)"
            />
            <YAxis
              tick={tick}
              stroke="var(--line-strong)"
              width={56}
              tickFormatter={(v: number) => v.toFixed(0)}
              label={{ value: "m/s²", angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 13, dx: 6 }}
            />
            <Tooltip cursor={{ stroke: "var(--muted)", strokeWidth: 1 }} content={<SignalTooltip />} isAnimationActive={false} />
            <ReferenceLine x={peak.t} stroke="var(--line-strong)" strokeWidth={1} />
            <Line
              dataKey="v"
              type="monotone"
              stroke="var(--sensor)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              activeDot={{ r: 5, stroke: "var(--surface)", strokeWidth: 2, fill: "var(--sensor)" }}
            />
            <ReferenceDot
              x={peak.t}
              y={peak.v}
              r={7}
              fill="var(--ink)"
              stroke="var(--surface)"
              strokeWidth={2}
              label={{ value: `Peak ${peak.v.toFixed(1)} m/s²`, position: "top", fill: "var(--ink)", fontSize: 14, fontWeight: 600, offset: 12 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 text-sm text-ink-2">
        High-passed acceleration magnitude, ±{(data.length / 2 / fs).toFixed(1)} s around the strongest bump ({fs} Hz).
      </figcaption>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted hover:text-ink">Show data table</summary>
        <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-line">
          <table className="tabular w-full text-left">
            <thead className="sticky top-0 bg-surface-2 text-muted">
              <tr>
                <th className="px-3 py-1 font-medium">Time from peak</th>
                <th className="px-3 py-1 text-right font-medium">m/s²</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p, i) => (
                <tr key={i} className={i === signal.peak_index ? "font-semibold" : ""}>
                  <td className="px-3 py-0.5">{fmtT(p.t)}</td>
                  <td className="px-3 py-0.5 text-right">{p.v.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
