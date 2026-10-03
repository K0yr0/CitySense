import { assess, VERIFIED_AT } from "@/lib/confidence";
import { fmtPct, statusLabel } from "@/lib/format";
import type { IncidentSummary } from "@/lib/types";
import { ConfidenceMeter } from "../ui";

// The most confidence citizen answers alone can reach (the engine caps the crowd's points).
const CROWD_MAX = assess([], 0, Array.from({ length: 50 }, () => ({ yes: true, trust: 1 }))).confidence;

/** Sensor confidence + trust-weighted citizen confidence -> confidence engine -> status. */
export default function ConfidenceBreakdown({ incident: i }: { incident: IncidentSummary }) {
  const sensorNote = i.sensor_rides || i.sensor_misses
    ? `${i.sensor_rides} detecting ride${i.sensor_rides === 1 ? "" : "s"}, ${i.sensor_misses} clean pass${i.sensor_misses === 1 ? "" : "es"}`
    : "no vehicle has measured it yet";
  const citizenNote = i.yes_count || i.no_count ? `${i.yes_count} yes · ${i.no_count} no, weighted by trust` : "no answers yet";
  // Crowd-only incidents cannot pass the citizen cap; say so instead of leaving people guessing.
  const crowdOnly = !i.has_sensor && i.status === "likely" && CROWD_MAX < VERIFIED_AT;

  return (
    <div className="flex flex-col gap-4">
      <div>
        <ConfidenceMeter label="Sensor confidence" value={i.sensor_confidence} status={i.status} />
        <p className="mt-1 text-sm text-muted">{sensorNote}</p>
      </div>
      <div>
        <ConfidenceMeter label="Citizen confidence" value={i.citizen_confidence} status={i.status} />
        <p className="mt-1 text-sm text-muted">{citizenNote}</p>
      </div>
      <div className="rounded-xl bg-surface-2 p-3.5">
        <ConfidenceMeter label="Confidence engine" value={i.confidence} status={i.status} />
        <p className="mt-2 text-base">
          <span className="font-semibold">{statusLabel(i.status)}</span>
          <span className="text-ink-2"> at {fmtPct(i.confidence)}. Likely from 60%, verified from 85%.</span>
          {crowdOnly && <span className="text-ink-2"> Citizen answers alone stop at likely; a vehicle sensor pass can verify it.</span>}
        </p>
      </div>
    </div>
  );
}
