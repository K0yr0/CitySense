"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { submitReport } from "@/lib/api";
import { deptLabel, typeLabel, vehicleLabel } from "@/lib/format";
import type { ReportStatus } from "@/lib/types";
import { IconArrowRight, IconCamera, IconCheck, IconCrosshair, IconX } from "../icons";
import type { Pin } from "./PinMap";

const PinMap = dynamic(() => import("./PinMap"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-muted">Loading map…</div>,
});

const PLACEHOLDER =
  "Np. Głęboka dziura w jezdni na Marszałkowskiej przy Świętokrzyskiej, tuż przed przejściem dla pieszych. Samochody omijają ją po torowisku.";

function StatusView({ status, onReset }: { status: ReportStatus; onReset: () => void }) {
  const rows: [string, string][] = [
    ["Category", typeLabel(status.category)],
    ["Sent to", deptLabel(status.department)],
    ["Others reporting this", String(status.others_count)],
  ];
  if (status.sensor_confirmed) rows.push(["Sensor check", "Already confirmed by vehicle sensors"]);
  else if (status.verify_vehicle) rows.push(["Sensor check", `${vehicleLabel(status.verify_vehicle)} · ~${status.verify_eta_min ?? "?"} min`]);

  return (
    <section className="rounded-2xl border border-line bg-surface p-6" role="status" aria-live="polite">
      <span className="grid h-14 w-14 place-items-center rounded-full bg-good-soft text-good-ink">
        <IconCheck width={30} height={30} />
      </span>
      <p className="mt-2 text-sm font-semibold uppercase tracking-wide text-muted">Report received · #{status.report_id}</p>
      <p className="mt-2 text-2xl font-semibold leading-snug sm:text-3xl">{status.message}</p>
      <dl className="mt-5 divide-y divide-line border-y border-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-4 py-2.5">
            <dt className="text-ink-2">{k}</dt>
            <dd className="text-right text-lg font-semibold">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        {status.incident_id != null && (
          <Link
            href={`/incidents/${status.incident_id}`}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-base font-semibold text-accent-ink hover:bg-accent-hover"
          >
            Follow incident #{status.incident_id} <IconArrowRight />
          </Link>
        )}
        <button type="button" onClick={onReset} className="flex-1 rounded-xl border border-line-strong px-4 py-3 text-base font-semibold hover:bg-surface-2">
          Report another problem
        </button>
      </div>
    </section>
  );
}

export default function ReportForm() {
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [pin, setPin] = useState<Pin | null>(null);
  const [flyKey, setFlyKey] = useState(0);
  const [geoMsg, setGeoMsg] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<ReportStatus | null>(null);

  const pickPhoto = (f: File | null) => {
    if (preview) URL.revokeObjectURL(preview);
    setPhoto(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const locate = () => {
    if (!("geolocation" in navigator)) return setGeoMsg("This browser has no geolocation. Drop a pin on the map instead.");
    if (!window.isSecureContext) return setGeoMsg("Location needs HTTPS on phones. Drop a pin on the map instead.");
    setLocating(true);
    setGeoMsg(null);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPin({ lon: p.coords.longitude, lat: p.coords.latitude });
        setFlyKey((k) => k + 1);
        setGeoMsg(`Located within ±${Math.round(p.coords.accuracy)} m. Drag the pin if needed.`);
        setLocating(false);
      },
      (err) => {
        setGeoMsg(err.code === err.PERMISSION_DENIED ? "Location permission denied. Drop a pin on the map instead." : "Could not get your location. Drop a pin on the map instead.");
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 },
    );
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      setStatus(await submitReport({ text: text.trim(), lon: pin?.lon, lat: pin?.lat, photo }));
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setText("");
    pickPhoto(null);
    setPin(null);
    setGeoMsg(null);
    setStatus(null);
  };

  return (
    <main className="mx-auto w-full max-w-xl flex-1 px-4 py-6 sm:py-8">
      <h1 className="text-3xl font-bold tracking-tight">Report a problem</h1>
      <p className="mt-1 text-lg text-ink-2">Potholes, tram tracks, broken lights, flooding, rubbish. Write in Polish or English.</p>

      {status ? (
        <div className="mt-6">
          <StatusView status={status} onReset={reset} />
        </div>
      ) : (
        <form onSubmit={submit} className="mt-6 flex flex-col gap-6">
          <div>
            <label htmlFor="text" className="text-lg font-semibold">
              What&apos;s the problem?
            </label>
            <textarea
              id="text"
              required
              rows={5}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={PLACEHOLDER}
              lang="pl"
              className="mt-2 w-full resize-y rounded-xl border border-line-strong bg-surface px-4 py-3 text-lg leading-snug placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>

          <div>
            <span className="text-lg font-semibold">Photo <span className="font-normal text-muted">(optional)</span></span>
            {preview ? (
              <div className="relative mt-2">
                {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview */}
                <img src={preview} alt="Selected photo" className="max-h-64 w-full rounded-xl object-cover" />
                <button
                  type="button"
                  onClick={() => pickPhoto(null)}
                  className="absolute right-2 top-2 rounded-full bg-surface p-1.5 shadow"
                  aria-label="Remove photo"
                >
                  <IconX />
                </button>
              </div>
            ) : (
              <label className="mt-2 flex cursor-pointer items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line-strong px-4 py-5 text-lg font-medium text-ink-2 hover:border-accent hover:text-accent">
                <IconCamera /> Add a photo
                <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => pickPhoto(e.target.files?.[0] ?? null)} />
              </label>
            )}
            <p className="mt-1.5 text-sm text-muted">Faces and number plates are blurred before anything is stored.</p>
          </div>

          <div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-lg font-semibold">Where is it?</span>
              <button
                type="button"
                onClick={locate}
                disabled={locating}
                className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-surface px-3.5 py-2 text-base font-semibold hover:bg-surface-2 disabled:opacity-60"
              >
                <IconCrosshair /> {locating ? "Locating…" : "Use my location"}
              </button>
            </div>
            <div className="mt-2 h-60 overflow-hidden rounded-xl border border-line-strong">
              <PinMap pin={pin} onPin={setPin} flyKey={flyKey} />
            </div>
            <p className="mt-1.5 text-sm text-muted" aria-live="polite">
              {geoMsg ??
                (pin
                  ? `Pin at ${pin.lat.toFixed(5)}, ${pin.lon.toFixed(5)}. Drag to adjust.`
                  : "Tap the map to drop a pin, or just name the street in your description.")}
            </p>
          </div>

          <button
            type="submit"
            disabled={submitting || !text.trim()}
            className="rounded-xl bg-accent px-4 py-4 text-lg font-semibold text-accent-ink hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Sending…" : "Send report"}
          </button>
        </form>
      )}
    </main>
  );
}
