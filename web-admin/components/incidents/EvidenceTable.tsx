import { formatDateTime, vehicleLabel } from "@/lib/format";
import type { Evidence } from "@/lib/types";
import { IconChart } from "../icons";

function what(e: Evidence): string {
  const d = e.details as { kind?: string; speed_kmh?: number; raw_peak?: number; expected_lux?: number; observed_lux?: number };
  if (d.kind === "dark_gap") return `Dark gap · ${d.observed_lux ?? "?"} lux (expected ${d.expected_lux ?? "?"})`;
  const parts = ["Bump"];
  if (typeof d.speed_kmh === "number") parts.push(`${Math.round(d.speed_kmh)} km/h`);
  if (typeof d.raw_peak === "number") parts.push(`peak ${d.raw_peak.toFixed(1)} m/s²`);
  return parts.join(" · ");
}

/** Every sensor detection linked to the incident: which ride and vehicle, when, what it felt. */
export default function EvidenceTable({ evidence }: { evidence: Evidence[] }) {
  const rows = evidence.filter((e) => e.source === "sensor").sort((a, b) => Date.parse(b.ts) - Date.parse(a.ts));
  if (!rows.length)
    return (
      <div className="flex flex-col items-center rounded-lg border border-dashed border-line-strong bg-surface-2/50 px-4 py-6 text-center">
        <IconChart width={24} height={24} className="text-muted" />
        <p className="mt-2 text-sm font-medium text-ink">No sensor detections yet.</p>
      </div>
    );
  return (
    <div className="-mx-5 overflow-x-auto px-5">
      <table className="w-full min-w-[34rem] text-left text-sm">
        <thead className="text-[0.6875rem] uppercase tracking-wider text-muted">
          <tr className="border-b border-line">
            <th className="py-2 pr-3 font-semibold">When</th>
            <th className="py-2 pr-3 font-semibold">Vehicle</th>
            <th className="py-2 pr-3 font-semibold">Ride</th>
            <th className="py-2 pr-3 font-semibold">Signal</th>
            <th className="py-2 text-right font-semibold">Severity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((e) => (
            <tr key={e.id}>
              <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs">{formatDateTime(e.ts)}</td>
              <td className="whitespace-nowrap py-2 pr-3 font-medium">{vehicleLabel(e.vehicle) || "—"}</td>
              <td className="py-2 pr-3 font-mono text-xs text-ink-2">{e.ride_id != null ? `#${e.ride_id}` : "—"}</td>
              <td className="py-2 pr-3 text-ink-2">{what(e)}</td>
              <td className="py-2 text-right">
                <span className="inline-flex items-center gap-2">
                  <span className="h-1.5 w-12 overflow-hidden rounded-full bg-surface-2">
                    <span className="block h-full rounded-full bg-sensor" style={{ width: `${Math.round(Math.min(1, e.severity) * 100)}%` }} />
                  </span>
                  <span className="font-mono text-xs font-semibold">{e.severity.toFixed(2)}</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
