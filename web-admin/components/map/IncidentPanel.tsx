"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { APP_STATUS_LABEL, APP_WORK_LABEL, deptLabel, fmtPct, pinHex, PIN_STATUS_HEX, reportedBy, timeAgo, typeLabel, WORK_HEX } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { useDarkTheme } from "@/lib/theme";
import { incidentPinUrl } from "@/lib/mapIcons";
import type { IncidentSummary } from "@/lib/types";
import { IconArrowRight, IconX } from "../icons";
import { ConfidenceMeter, IncidentBadges, ScoreBar, SourceTag, verificationText } from "../ui";

function Fact({ label, children, mono = true }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[0.6875rem] text-muted">{label}</dt>
      <dd className={`font-bold leading-tight text-ink ${mono ? "font-mono" : ""}`}>{children}</dd>
    </div>
  );
}

/** Stitch "Overlay 2": the selected incident, top-right on desktop and a bottom sheet on phones. */
export default function IncidentPanel({ incident: i, onClose }: { incident: IncidentSummary; onClose: () => void }) {
  const now = useNow();
  const dark = useDarkTheme();
  return (
    <aside
      className="absolute inset-x-3 bottom-3 z-10 max-h-[70%] overflow-y-auto rounded-xl border border-line bg-surface/95 text-ink shadow-lg backdrop-blur md:inset-x-auto md:bottom-auto md:right-4 md:top-4 md:max-h-[calc(100%-6rem)] md:w-[22.5rem]"
      aria-label="Selected incident"
    >
      <div className="flex items-center justify-between border-b border-line bg-surface-2/50 px-5 pb-2 pt-4">
        <SourceTag incident={i} pill />
        <button type="button" onClick={onClose} className="grid h-6 w-6 place-items-center rounded text-muted hover:bg-surface-2 hover:text-ink" aria-label="Close incident panel">
          <IconX width={16} height={16} />
        </button>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div className="flex items-start gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- same SVG data URL as the map pin */}
          <img src={incidentPinUrl(i, dark)} alt="" width={28} height={35} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-xl font-bold leading-snug tracking-tight">{typeLabel(i.type)}</h2>
            <p className="mt-0.5 text-xs font-medium text-muted">{i.address ?? `${i.lat.toFixed(5)}, ${i.lon.toFixed(5)}`}</p>
          </div>
        </div>

        {/* Same lines as the citizen app's card (mobile map.card), so both apps say the same thing. */}
        <ul className="space-y-1.5 text-sm" title={`Pin colour ${pinHex(i)}`}>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PIN_STATUS_HEX[i.status] }} />
            Status: <span className="font-semibold">{APP_STATUS_LABEL[i.status]}</span> ({fmtPct(i.confidence)})
          </li>
          <li className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: WORK_HEX[i.work_status] }} />
            Repair: <span className="font-semibold">{APP_WORK_LABEL[i.work_status]}</span>
          </li>
          <li className="pl-[1.125rem] text-xs text-muted">{reportedBy(i.report_count)}</li>
        </ul>

        <div className="flex flex-wrap items-center gap-1.5 empty:hidden">
          <IncidentBadges incident={i} />
        </div>

        <ConfidenceMeter label="Confidence" value={i.confidence} status={i.status} />

        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-ink-2">Priority score</span>
          <ScoreBar score={i.score} />
        </div>

        <dl className="grid grid-cols-2 gap-3 border-y border-line py-3 text-xs">
          <Fact label="Department" mono={false}>
            {deptLabel(i.department)}
          </Fact>
          <Fact label="Citizen reports">{i.report_count}</Fact>
          <Fact label="Sensor rides">{i.sensor_rides}</Fact>
          <Fact label="Max severity">{i.max_severity != null ? i.max_severity.toFixed(2) : "—"}</Fact>
          <Fact label="First seen">{timeAgo(i.first_seen, now)}</Fact>
          <Fact label="Last seen">{timeAgo(i.last_seen, now)}</Fact>
        </dl>

        <div className="flex flex-wrap items-center gap-2 rounded border border-line bg-surface-2 p-2.5 text-xs">
          <span className="font-medium text-muted">Verification:</span>
          <span className="font-semibold">{verificationText(i)}</span>
        </div>

        <Link
          href={`/incidents/${i.id}`}
          className="flex items-center justify-center gap-2 rounded bg-accent px-4 py-2.5 text-xs font-bold text-accent-ink hover:bg-accent-hover"
        >
          Open incident #{i.id} <IconArrowRight width={14} height={14} />
        </Link>
      </div>
    </aside>
  );
}
