"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import type { Mode, RideResult } from "@/lib/types";
import { isRideResult } from "@/lib/types";
import { IconAlert, IconCheck } from "../icons";
import { Segmented } from "../ui";
import { CHUNK_MS, ensureMotionPermission, RideRecorder, type RecorderSnapshot } from "./recorder";

type Phase = "idle" | "starting" | "recording" | "finishing" | "done";

const noop = () => () => undefined;

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-xl bg-surface-2 px-3.5 py-2.5">
      <div className="text-sm text-muted">{label}</div>
      <div className="tabular text-2xl font-semibold">{children}</div>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 300;
  const h = 64;
  const max = 8;
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * w},${h / 2 - (Math.max(-max, Math.min(max, v)) / max) * (h / 2 - 2)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-16 w-full" aria-label="Live vibration">
      <line x1="0" x2={w} y1={h / 2} y2={h / 2} stroke="var(--line)" strokeWidth="1" />
      {values.length > 1 && <polyline points={pts} fill="none" stroke="var(--sensor)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />}
    </svg>
  );
}

function mmss(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function ResultCard({ result }: { result: RideResult }) {
  const verified = result.verified_incident_ids ?? [];
  return (
    <section className="rounded-2xl border border-line bg-surface p-5" role="status" aria-live="polite">
      <p className="text-sm font-semibold uppercase tracking-wide text-muted">Ride #{result.ride_id} processed</p>
      {verified.length > 0 ? (
        <p className="mt-2 flex items-start gap-3 text-2xl font-semibold leading-snug text-good-ink">
          <IconCheck width={30} height={30} className="mt-0.5 shrink-0" />
          This ride verified {verified.length} citizen report{verified.length === 1 ? "" : "s"}.
        </p>
      ) : (
        <p className="mt-2 text-2xl font-semibold leading-snug">Thanks! Your ride is now part of the city health map.</p>
      )}
      <div className="mt-4 grid grid-cols-2 gap-2.5">
        <Stat label="Bumps detected">{result.bumps}</Stat>
        <Stat label="Dark gaps">{result.dark_gaps}</Stat>
        <Stat label="Segments covered">{result.segments_covered}</Stat>
        <Stat label="Incidents touched">{result.incident_ids?.length ?? 0}</Stat>
      </div>
      {(result.incident_ids?.length ?? 0) > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {result.incident_ids.map((id) => (
            <Link key={id} href={`/incidents/${id}`} className="rounded-lg border border-line-strong px-3 py-1.5 font-semibold hover:bg-surface-2">
              #{id}
              {verified.includes(id) ? " ✓ verified" : ""}
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export default function RideView() {
  const [rec] = useState(() => new RideRecorder());
  const [line, setLine] = useState("17");
  const [mode, setMode] = useState<Mode>("tram");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [snap, setSnap] = useState<RecorderSnapshot | null>(null);
  const [result, setResult] = useState<RideResult | null>(null);
  const secure = useSyncExternalStore(noop, () => window.isSecureContext, () => true);

  // Refresh live stats while recording; stop sensors if the page unmounts.
  useEffect(() => {
    if (phase !== "recording") return;
    const t = setInterval(() => setSnap(rec.snapshot()), 250);
    return () => clearInterval(t);
  }, [phase, rec]);
  useEffect(() => () => rec.abort(), [rec]);

  const start = async () => {
    setError(null);
    setResult(null);
    setPhase("starting");
    const problem = await ensureMotionPermission();
    if (problem) {
      setError(problem);
      setPhase("idle");
      return;
    }
    rec.start(line.trim() || "?", mode);
    setSnap(rec.snapshot());
    setPhase("recording");
  };

  const stop = async () => {
    setPhase("finishing");
    setSnap(rec.snapshot());
    const res = await rec.stop();
    if (res && isRideResult(res)) setResult(res);
    else setError("The ride was sent but the server did not return a result.");
    setPhase("done");
  };

  const recording = phase === "recording";
  const busy = phase === "starting" || phase === "finishing";

  return (
    <main className="mx-auto w-full max-w-lg flex-1 px-4 py-6 sm:py-8">
      <h1 className="text-3xl font-bold tracking-tight">Ride recorder</h1>
      <p className="mt-1 text-lg text-ink-2">Turn this phone into a road and track sensor. Keep it flat on a seat or the floor, screen on.</p>

      <div className={`mt-4 flex gap-3 rounded-xl px-4 py-3 text-base ${secure ? "bg-surface-2 text-ink-2" : "bg-warn-soft text-warn-ink"}`}>
        <IconAlert className="mt-0.5 shrink-0" />
        <p>
          Motion sensors and GPS only work over <strong>HTTPS</strong> on phones.
          {secure ? " This page is secure." : " Open this page through an HTTPS tunnel (npm run dev:https, ngrok or cloudflared)."}
        </p>
      </div>

      <div className="mt-6 flex flex-col gap-4">
        <div className="flex flex-col gap-2">
          <label htmlFor="line" className="text-lg font-semibold">
            Line
          </label>
          <input
            id="line"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            disabled={recording || busy}
            placeholder="17"
            autoComplete="off"
            className="w-full rounded-xl border border-line-strong bg-surface px-4 py-3 text-2xl font-semibold focus:border-accent focus:outline-none disabled:opacity-60"
          />
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-lg font-semibold">Vehicle</span>
          <div className={recording || busy ? "pointer-events-none opacity-60" : ""}>
            <Segmented
              label="Vehicle mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: "tram", label: "Tram" },
                { value: "road", label: "Bus / road" },
              ]}
            />
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={recording ? stop : start}
        disabled={busy}
        className={`mt-6 h-20 w-full rounded-2xl text-2xl font-bold transition-colors disabled:opacity-60 ${
          recording ? "bg-crit text-white hover:opacity-90" : "bg-accent text-accent-ink hover:bg-accent-hover"
        }`}
      >
        {phase === "starting" ? "Starting…" : phase === "finishing" ? "Processing ride…" : recording ? "Stop & send" : phase === "done" ? "Start a new ride" : "Start recording"}
      </button>

      {error && (
        <p className="mt-4 rounded-xl bg-crit-soft px-4 py-3 text-base font-medium text-crit-ink" role="alert">
          {error}
        </p>
      )}

      {snap && (recording || phase === "finishing") && (
        <section className="mt-6 rounded-2xl border border-line bg-surface p-5" aria-live="off">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-lg font-semibold">
              <span className="live-dot inline-block h-3 w-3 rounded-full bg-crit" /> Recording
            </span>
            <span className="tabular text-2xl font-semibold">{mmss(snap.elapsedS)}</span>
          </div>
          <div className="mt-3">
            <Sparkline values={snap.vibration} />
            <p className="text-sm text-muted">Vibration (|a| − g), last ~5 s</p>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2.5">
            <Stat label="Sample rate">{snap.hz ? `${snap.hz} Hz` : "—"}</Stat>
            <Stat label="Speed">{snap.fix ? `${Math.round(snap.fix.speedKmh)} km/h` : "—"}</Stat>
            <Stat label="Samples sent">{snap.sent.toLocaleString("en-US")}</Stat>
            <Stat label="GPS accuracy">{snap.fix ? `±${Math.round(snap.fix.accuracy)} m` : "—"}</Stat>
          </div>
          <p className="mt-3 text-sm text-ink-2">
            {snap.gpsError
              ? `GPS: ${snap.gpsError}`
              : snap.waitingForGps
                ? "Waiting for a GPS fix… samples start once the phone knows where it is."
                : snap.hz === 0
                  ? "No motion events yet. On iPhone, allow Motion & Orientation access."
                  : `Streaming to the server every ${CHUNK_MS / 1000} s (${snap.chunks} chunks).`}
          </p>
        </section>
      )}

      {result && (
        <div className="mt-6">
          <ResultCard result={result} />
        </div>
      )}
    </main>
  );
}
