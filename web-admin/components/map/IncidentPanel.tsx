"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { deptLabel, timeAgo, typeLabel } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import type { IncidentSummary } from "@/lib/types";
import { IconArrowRight, IconX } from "../icons";
import { ConfidenceMeter, IncidentBadges, ScoreBar, SourceTag, StatusChip, verificationText, WorkChip } from "../ui";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="tabular text-base font-semibold">{children}</dd>
    </div>
  );
}

export default function IncidentPanel({ incident: i, onClose }: { incident: IncidentSummary; onClose: () => void }) {
  const now = useNow();
  return (
    <aside
      className="absolute inset-x-3 bottom-3 z-10 max-h-[70%] overflow-y-auto rounded-2xl border border-line bg-surface p-5 shadow-lg md:inset-x-auto md:bottom-auto md:right-3 md:top-3 md:max-h-[calc(100%-7rem)] md:w-[25rem]"
      aria-label="Selected incident"
    >
      <div className="flex items-start justify-between gap-3">
        <SourceTag incident={i} />
        <button type="button" onClick={onClose} className="-m-1 rounded-md p-1 text-muted hover:bg-surface-2" aria-label="Close incident panel">
          <IconX />
        </button>
      </div>
      <h2 className="mt-2 text-2xl font-bold leading-tight">{typeLabel(i.type)}</h2>
      <p className="mt-0.5 text-lg text-ink-2">{i.address ?? `${i.lat.toFixed(5)}, ${i.lon.toFixed(5)}`}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        <StatusChip status={i.status} confidence={i.confidence} />
        <WorkChip work={i.work_status} />
        <IncidentBadges incident={i} />
      </div>

      <div className="mt-4">
        <ConfidenceMeter label="Confidence" value={i.confidence} status={i.status} />
      </div>

      <div className="mt-4">
        <div className="mb-1 text-sm text-muted">Priority score</div>
        <ScoreBar score={i.score} wide />
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <Fact label="Department">{deptLabel(i.department)}</Fact>
        <Fact label="Citizen reports">{i.report_count}</Fact>
        <Fact label="Sensor rides">{i.sensor_rides}</Fact>
        <Fact label="Max severity">{i.max_severity != null ? i.max_severity.toFixed(2) : "—"}</Fact>
        <Fact label="First seen">{timeAgo(i.first_seen, now)}</Fact>
        <Fact label="Last seen">{timeAgo(i.last_seen, now)}</Fact>
      </dl>

      <div className="mt-4 rounded-xl bg-surface-2 px-3.5 py-2.5 text-base">
        <span className="text-muted">Verification: </span>
        <span className="font-medium">{verificationText(i)}</span>
      </div>

      <Link
        href={`/incidents/${i.id}`}
        className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-base font-semibold text-accent-ink hover:bg-accent-hover"
      >
        Open incident #{i.id} <IconArrowRight />
      </Link>
    </aside>
  );
}
