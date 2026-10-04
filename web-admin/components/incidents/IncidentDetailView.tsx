"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { getIncident, photoUrl, requestVerification } from "@/lib/api";
import { deptLabel, formatDateTime, timeAgo, typeLabel, vehicleLabel } from "@/lib/format";
import { useApi, useNow } from "@/lib/hooks";
import type { IncidentDetail, VerifyResult } from "@/lib/types";
import { IconAlert, IconCamera, IconChart } from "../icons";
import { LoadingLabel, Skeleton } from "../Skeleton";
import { Card, IncidentBadges, SourceTag, StatusChip, verificationText, WorkChip } from "../ui";
import ConfidenceBreakdown from "./ConfidenceBreakdown";
import CitizenAnswers from "./CitizenAnswers";
import EvidenceTable from "./EvidenceTable";
import LocationMap from "./LocationMap";
import QueueNav from "./QueueNav";
import PhotoGallery from "./PhotoGallery";
import SignalChart from "./SignalChart";
import Timeline from "./Timeline";
import WorkflowCard from "./WorkflowCard";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2 text-xs last:border-b-0">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-mono font-semibold text-ink">{children}</dd>
    </div>
  );
}

const REPORTS_SHOWN = 5;

/** All merged citizen reports (newest first), with the original text and the English triage summary. */
function ReportsCard({ incident: inc, now }: { incident: IncidentDetail; now: number }) {
  const [all, setAll] = useState(false);
  const list = all ? inc.reports : inc.reports.slice(0, REPORTS_SHOWN);
  return (
    <section className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="text-base font-semibold text-ink">Citizen reports ({inc.report_count})</h2>
        {inc.reports.length > 1 && <span className="text-xs text-muted">Sorted newest first</span>}
      </div>
      {inc.reports.length === 0 ? (
        <p className="p-5 text-sm text-ink-2">No citizen has reported this yet. It was found by vehicle sensors.</p>
      ) : (
        <ul className="divide-y divide-line">
          {list.map((r) => (
            <li key={r.id} className="flex items-start justify-between gap-4 p-5 hover:bg-surface-2/60">
              <div className="min-w-0 flex-1 space-y-1.5">
                <p lang="pl" className="text-sm font-semibold italic text-ink">
                  &ldquo;{r.raw_text}&rdquo;
                </p>
                {r.summary_en && <p className="text-xs text-ink-2">{r.summary_en}</p>}
                <p className="pt-1 text-[0.6875rem] text-muted">
                  <span className="font-mono">#{r.id}</span> · {formatDateTime(r.created_at)} · {timeAgo(r.created_at, now)}
                  {r.urgency != null && (
                    <>
                      {" "}
                      · urgency <span className={`font-medium ${r.urgency >= 4 ? "text-warn-ink" : ""}`}>{r.urgency}/5</span>
                    </>
                  )}
                </p>
              </div>
              {r.photo_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={photoUrl(r.photo_url) ?? ""} alt="" className="h-14 w-14 shrink-0 rounded-md border border-line object-cover" />
              )}
            </li>
          ))}
        </ul>
      )}
      {(inc.reports.length > REPORTS_SHOWN || (inc.reports.length > 0 && inc.reports.length < inc.report_count)) && (
        <div className="flex flex-col items-center gap-2 border-t border-line p-4">
          {inc.reports.length > REPORTS_SHOWN && (
            <button type="button" onClick={() => setAll(!all)} className="rounded-lg border border-line-strong bg-surface px-3 py-1.5 text-xs font-medium hover:bg-surface-2">
              {all ? "Show fewer" : `Show all ${inc.reports.length} reports`}
            </button>
          )}
          {inc.reports.length > 0 && inc.reports.length < inc.report_count && (
            <p className="text-xs text-muted">
              Showing {inc.reports.length} of {inc.report_count} merged reports.
            </p>
          )}
        </div>
      )}
    </section>
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
    <Card title={<span className="eyebrow">Verification</span>}>
      <p className="text-sm font-bold text-ink">{verificationText(incident)}</p>
      {awaiting && incident.verify_vehicle && (
        <p className="mt-1 text-xs text-ink-2">
          {vehicleLabel(incident.verify_vehicle)} will measure this spot on its next pass
          {incident.verify_eta_min != null ? ` in about ${incident.verify_eta_min} min` : ""}.
        </p>
      )}
      {result && (
        <p className="mt-3 rounded-lg border border-accent/20 bg-accent-soft px-3 py-2 text-xs font-medium text-accent" role="status">
          {result.vehicle
            ? `${vehicleLabel(result.vehicle)} asked to verify${result.eta_min != null ? `, ETA ~${result.eta_min} min` : ""}.`
            : "No vehicle is passing this spot soon; the request stays open."}
        </p>
      )}
      {measured || resolved ? (
        // Nothing to do here: say why instead of showing a dead button.
        <p className="mt-2 text-xs text-muted">
          {measured ? "Vehicle sensors already measured this spot, so no verification ride is needed." : "Confidence is final for this incident."}
        </p>
      ) : (
        <>
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="mt-3 w-full rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-accent-ink hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Requesting…" : awaiting ? "Request again" : "Request verification"}
          </button>
          <p className="mt-2 text-[0.6875rem] text-muted">Asks the next tram or bus through this segment to record it. A clean pass lowers confidence.</p>
        </>
      )}
    </Card>
  );
}

/** Same layout as the page, in grey, so nothing jumps when the incident arrives. */
function DetailSkeleton() {
  const card = (h: string) => (
    <div className="rounded-2xl border border-line bg-surface p-5">
      <Skeleton className="h-4 w-32" />
      <Skeleton className={`mt-4 w-full ${h}`} />
    </div>
  );
  return (
    <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6 lg:py-8">
      <LoadingLabel>Loading incident…</LoadingLabel>
      <Skeleton className="h-5 w-40" />
      <Skeleton className="mt-6 h-4 w-48" />
      <Skeleton className="mt-3 h-10 w-80 max-w-full" />
      <Skeleton className="mt-3 h-6 w-64 max-w-full" />
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-7 w-28" />
        <Skeleton className="h-7 w-24" />
      </div>
      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-2">
          {card("h-16")}
          {card("h-64")}
          {card("h-48")}
        </div>
        <div className="flex flex-col gap-5">
          {card("h-40")}
          {card("h-32")}
        </div>
      </div>
    </main>
  );
}

export default function IncidentDetailView({ id }: { id: number }) {
  const now = useNow();
  const { data: inc, loading, reload } = useApi(`incident:${id}`, () => getIncident(id), 15_000);

  if (loading) return <DetailSkeleton />;
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
    <>
      <QueueNav id={inc.id} />
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-6 lg:px-6">
        <header className="flex flex-col gap-4 pb-2 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <SourceTag incident={inc} pill />
              <span className="font-mono text-xs text-muted">#{inc.id}</span>
            </div>
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight">{typeLabel(inc.type)}</h1>
              <p className="mt-0.5 text-base font-medium text-muted">{inc.address ?? `${inc.lat.toFixed(5)}, ${inc.lon.toFixed(5)}`}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusChip status={inc.status} confidence={inc.confidence} />
              <WorkChip work={inc.work_status} />
              <IncidentBadges incident={inc} />
            </div>
          </div>
          <div className="flex min-w-[16rem] items-center gap-6 self-start rounded-xl border border-line bg-surface p-4 md:self-auto">
            <div className="flex-1">
              <div className="mb-1 flex items-baseline justify-between">
                <span className="text-xs font-medium text-muted">Priority score</span>
                <span className="font-mono text-base font-bold">{inc.score.toFixed(2)}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-surface-2">
                <div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(100, (inc.score / 1.5) * 100)}%` }} />
              </div>
              <span className="mt-1 block text-[0.625rem] text-muted">Scale 0 – 1.5</span>
            </div>
            <div className="border-l border-line pl-5">
              <span className="block text-xs font-medium text-muted">Sent to</span>
              <span className="text-lg font-bold">{deptLabel(inc.department)}</span>
            </div>
          </div>
        </header>

        <div className="mt-4 grid items-start gap-6 lg:grid-cols-12">
          <div className="flex min-w-0 flex-col gap-6 lg:col-span-8">
            {summary && (
              <Card title={<span className="eyebrow">Summary</span>}>
                <p className="text-base leading-relaxed text-ink">{summary}</p>
              </Card>
            )}

            <LocationMap incident={inc} />

            {inc.signal ? (
              <Card title="Sensor signal" action={<span className="text-xs text-muted">{inc.sensor_rides} ride{inc.sensor_rides === 1 ? "" : "s"} · max severity {inc.max_severity?.toFixed(2) ?? "—"}</span>}>
                <SignalChart signal={inc.signal} />
              </Card>
            ) : (
              <Card title="Sensor signal">
                <div className="flex flex-col items-center rounded-lg border border-dashed border-line-strong bg-surface-2/50 px-4 py-8 text-center">
                  <IconChart width={28} height={28} className="text-muted" />
                  <p className="mt-2 text-sm font-medium text-ink">
                    {inc.has_sensor ? "Sensor evidence without an acceleration trace." : "No vehicle has measured this spot yet."}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {inc.has_sensor ? "For example a dark gap in the light signal." : "Request a verification ride from public transit to get an acceleration profile."}
                  </p>
                </div>
              </Card>
            )}

            {inc.has_sensor && (
              <Card title={`Sensor detections (${inc.sensor_count})`} action={<span className="text-xs text-muted">{inc.sensor_rides} distinct ride{inc.sensor_rides === 1 ? "" : "s"}</span>}>
                <EvidenceTable evidence={inc.evidence} />
              </Card>
            )}

            <ReportsCard incident={inc} now={now} />

            {photoCount > 0 && (
              <Card
                title={
                  <span className="inline-flex items-center gap-2">
                    <IconCamera width={16} height={16} /> Photos, anonymised ({photoCount})
                  </span>
                }
                action={<span className="text-xs text-muted">Face and plate blurred</span>}
              >
                <PhotoGallery reports={inc.reports} alt={`Citizen photo of ${typeLabel(inc.type).toLowerCase()}`} />
              </Card>
            )}
          </div>

          <div className="flex min-w-0 flex-col gap-6 lg:col-span-4">
            <WorkflowCard incident={inc} onChanged={reload} now={now} />
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
                  {inc.lat.toFixed(5)}, {inc.lon.toFixed(5)}
                </Fact>
              </dl>
            </Card>
          </div>
        </div>
      </main>
    </>
  );
}
