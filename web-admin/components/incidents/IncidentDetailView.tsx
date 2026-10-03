"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { getIncident, photoUrl, requestVerification } from "@/lib/api";
import { deptLabel, formatDateTime, timeAgo, typeLabel, vehicleLabel } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import type { IncidentDetail, VerifyResult } from "@/lib/types";
import { IconAlert, IconArrowLeft, IconCamera } from "../icons";
import { Card, IncidentBadges, ScoreBar, SourceTag, StatusChip, verificationText, WorkChip } from "../ui";
import ConfidenceBreakdown from "./ConfidenceBreakdown";
import CitizenAnswers from "./CitizenAnswers";
import EvidenceTable from "./EvidenceTable";
import PhotoGallery from "./PhotoGallery";
import SignalChart from "./SignalChart";
import Timeline from "./Timeline";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2 last:border-b-0">
      <dt className="text-ink-2">{label}</dt>
      <dd className="tabular text-right font-semibold">{children}</dd>
    </div>
  );
}

const REPORTS_SHOWN = 5;

/** All merged citizen reports (newest first), with the original text and the English triage summary. */
function ReportsCard({ incident: inc, now }: { incident: IncidentDetail; now: number }) {
  const [all, setAll] = useState(false);
  const list = all ? inc.reports : inc.reports.slice(0, REPORTS_SHOWN);
  return (
    <Card title={`Citizen reports (${inc.report_count})`}>
      {inc.reports.length === 0 ? (
        <p className="text-lg text-ink-2">No citizen has reported this yet. It was found by vehicle sensors.</p>
      ) : (
        <ul className="divide-y divide-line">
          {list.map((r) => (
            <li key={r.id} className="flex gap-4 py-3 first:pt-0 last:pb-0">
              <div className="min-w-0 flex-1">
                <p lang="pl" className="text-lg leading-snug">&ldquo;{r.raw_text}&rdquo;</p>
                {r.summary_en && <p className="mt-1 text-ink-2">{r.summary_en}</p>}
                <p className="mt-1 text-sm text-muted">
                  #{r.id} · {formatDateTime(r.created_at)} · {timeAgo(r.created_at, now)}
                  {r.urgency != null ? ` · urgency ${r.urgency}/5` : ""}
                </p>
              </div>
              {r.photo_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photoUrl(r.photo_url) ?? ""} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" />
              )}
            </li>
          ))}
        </ul>
      )}
      {inc.reports.length > REPORTS_SHOWN && (
        <button type="button" onClick={() => setAll(!all)} className="mt-3 rounded-lg border border-line-strong px-3 py-1.5 text-sm font-semibold hover:bg-surface-2">
          {all ? "Show fewer" : `Show all ${inc.reports.length} reports`}
        </button>
      )}
      {inc.reports.length > 0 && inc.reports.length < inc.report_count && (
        <p className="mt-3 text-sm text-muted">
          Showing {inc.reports.length} of {inc.report_count} merged reports.
        </p>
      )}
    </Card>
  );
}

function VerificationCard({ incident, onDone }: { incident: IncidentDetail; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<VerifyResult | null>(null);
  const measured = incident.has_sensor;
  const awaiting = incident.awaiting_verification;
  const resolved = !(incident.status === "candidate" || incident.status === "likely");

  const run = async () => {
    setBusy(true);
    try {
      setResult(await requestVerification(incident.id));
      onDone();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Verification">
      <p className="text-lg font-medium">{verificationText(incident)}</p>
      {awaiting && incident.verify_vehicle && (
        <p className="mt-1 text-ink-2">
          {vehicleLabel(incident.verify_vehicle)} will measure this spot on its next pass
          {incident.verify_eta_min != null ? ` in about ${incident.verify_eta_min} min` : ""}.
        </p>
      )}
      {result && (
        <p className="mt-3 rounded-xl bg-accent-soft px-3.5 py-2.5 font-medium text-accent" role="status">
          {result.vehicle
            ? `${vehicleLabel(result.vehicle)} asked to verify${result.eta_min != null ? `, ETA ~${result.eta_min} min` : ""}.`
            : "No vehicle is passing this spot soon; the request stays open."}
        </p>
      )}
      <button
        type="button"
        onClick={run}
        disabled={busy || measured || resolved}
        className="mt-4 w-full rounded-xl bg-accent px-4 py-3 text-base font-semibold text-accent-ink hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Requesting…" : measured ? "Already measured by sensors" : resolved ? "Already resolved" : awaiting ? "Request again" : "Request verification"}
      </button>
      {!measured && !resolved && (
        <p className="mt-2 text-sm text-muted">Asks the next tram or bus through this segment to record it. A clean pass lowers confidence.</p>
      )}
    </Card>
  );
}

export default function IncidentDetailView({ id }: { id: number }) {
  const now = useNow();
  const { data: inc, loading, reload } = useApi(`incident:${id}`, () => getIncident(id), 15_000);

  if (loading) return <main className="flex-1 px-6 py-16 text-center text-lg text-muted">Loading incident…</main>;
  if (!inc) {
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center px-6 py-16 text-center">
        <IconAlert width={36} height={36} className="text-muted" />
        <h1 className="mt-3 text-2xl font-semibold">Incident #{Number.isFinite(id) ? id : "?"} not found</h1>
        <p className="mt-1 text-lg text-ink-2">It may have been merged into another incident or closed.</p>
        <Link href="/incidents" className="mt-5 rounded-xl bg-accent px-4 py-2 font-semibold text-accent-ink">
          Back to the queue
        </Link>
      </main>
    );
  }

  const photoCount = inc.reports.filter((r) => r.photo_url).length;
  const summary = inc.summary ?? inc.reports[0]?.summary_en ?? null;

  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <Link href="/incidents" className="inline-flex items-center gap-1.5 text-base font-medium text-ink-2 hover:text-accent">
        <IconArrowLeft width={18} height={18} /> Incident queue
      </Link>

      <header className="mt-4 flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <SourceTag incident={inc} />
            <span className="text-sm text-muted">#{inc.id}</span>
          </div>
          <h1 className="mt-1.5 text-3xl font-bold leading-tight tracking-tight lg:text-4xl">{typeLabel(inc.type)}</h1>
          <p className="mt-1 text-xl text-ink-2">{inc.address ?? `${inc.lat.toFixed(5)}, ${inc.lon.toFixed(5)}`}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusChip status={inc.status} confidence={inc.confidence} />
            <WorkChip work={inc.work_status} />
            <IncidentBadges incident={inc} />
          </div>
        </div>
        <div className="flex gap-8 rounded-2xl border border-line bg-surface px-5 py-4">
          <div>
            <div className="text-sm text-muted">Priority score</div>
            <ScoreBar score={inc.score} wide />
          </div>
          <div>
            <div className="text-sm text-muted">Sent to</div>
            <div className="text-lg font-semibold">{deptLabel(inc.department)}</div>
          </div>
        </div>
      </header>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-5 lg:col-span-2">
          {summary && (
            <Card title="Summary">
              <p className="text-lg leading-relaxed">{summary}</p>
            </Card>
          )}

          {inc.signal ? (
            <Card title="Sensor signal" action={<span className="text-sm text-muted">{inc.sensor_rides} ride{inc.sensor_rides === 1 ? "" : "s"} · max severity {inc.max_severity?.toFixed(2) ?? "—"}</span>}>
              <SignalChart signal={inc.signal} />
            </Card>
          ) : (
            <Card title="Sensor signal">
              <p className="text-lg text-ink-2">
                {inc.has_sensor
                  ? "Sensor evidence without an acceleration trace (for example a dark gap in the light signal)."
                  : "No vehicle has measured this spot yet. Request a verification ride to get a signal."}
              </p>
            </Card>
          )}

          {inc.has_sensor && (
            <Card title={`Sensor detections (${inc.sensor_count})`} action={<span className="text-sm text-muted">{inc.sensor_rides} distinct ride{inc.sensor_rides === 1 ? "" : "s"}</span>}>
              <EvidenceTable evidence={inc.evidence} />
            </Card>
          )}

          <ReportsCard incident={inc} now={now} />

          {photoCount > 0 && (
            <Card title={<span className="inline-flex items-center gap-2"><IconCamera width={18} height={18} /> Photos, anonymised ({photoCount})</span>}>
              <PhotoGallery reports={inc.reports} alt={`Citizen photo of ${typeLabel(inc.type).toLowerCase()}`} />
            </Card>
          )}
        </div>

        <div className="flex min-w-0 flex-col gap-5">
          <Card title="Confidence">
            <ConfidenceBreakdown incident={inc} />
          </Card>
          <VerificationCard incident={inc} onDone={reload} />
          <Card title="Citizen answers">
            <CitizenAnswers incident={inc} now={now} />
          </Card>
          <Card title="Evidence timeline">
            <Timeline events={inc.timeline} now={now} />
          </Card>
          <Card title="Facts">
            <dl>
              <Fact label="Department">{deptLabel(inc.department)}</Fact>
              <Fact label="Citizen reports">{inc.report_count}</Fact>
              <Fact label="Sensor detections">{inc.sensor_count}</Fact>
              <Fact label="Distinct rides">{inc.sensor_rides}</Fact>
              <Fact label="Clean passes">{inc.sensor_misses}</Fact>
              <Fact label="Citizen answers">{`${inc.yes_count} yes · ${inc.no_count} no`}</Fact>
              <Fact label="Max urgency">{inc.max_urgency != null ? `${inc.max_urgency}/5` : "—"}</Fact>
              <Fact label="First seen">{formatDateTime(inc.first_seen)}</Fact>
              <Fact label="Last seen">{timeAgo(inc.last_seen, now)}</Fact>
              <Fact label="Location">
                <span className="text-sm font-normal">
                  {inc.lat.toFixed(5)}, {inc.lon.toFixed(5)}
                </span>
              </Fact>
            </dl>
          </Card>
        </div>
      </div>
    </main>
  );
}
