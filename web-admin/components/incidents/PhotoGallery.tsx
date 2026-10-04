"use client";

import { useEffect, useState } from "react";
import { photoUrl } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { IncidentReport } from "@/lib/types";
import { IconCamera, IconX } from "../icons";

/** Every citizen photo of the incident (anonymised by the backend), with a full-size viewer. */
export default function PhotoGallery({ reports, alt }: { reports: IncidentReport[]; alt: string }) {
  const photos = reports.flatMap((r) => {
    const src = photoUrl(r.photo_url);
    return src ? [{ src, report: r }] : [];
  });
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    if (open === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
      if (e.key === "ArrowRight") setOpen((i) => (i === null ? i : (i + 1) % photos.length));
      if (e.key === "ArrowLeft") setOpen((i) => (i === null ? i : (i - 1 + photos.length) % photos.length));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, photos.length]);

  if (!photos.length)
    return (
      <div className="flex flex-col items-center rounded-lg border border-dashed border-line-strong bg-surface-2/50 px-4 py-6 text-center">
        <IconCamera width={24} height={24} className="text-muted" />
        <p className="mt-2 text-sm font-medium text-ink">No photos were attached to the reports.</p>
      </div>
    );
  const current = open === null ? null : photos[open];

  return (
    <>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {photos.map((p, i) => (
          <li key={p.report.id}>
            <button type="button" onClick={() => setOpen(i)} className="group block w-full overflow-hidden rounded-lg border border-line text-left">
              {/* eslint-disable-next-line @next/next/no-img-element -- served by the backend, any size */}
              <img src={p.src} alt={`${alt}, report #${p.report.id}`} className="aspect-[4/3] w-full object-cover transition-transform group-hover:scale-[1.03]" />
            </button>
            <p className="mt-1 font-mono text-[0.6875rem] text-muted">{formatDateTime(p.report.created_at)}</p>
          </li>
        ))}
      </ul>

      {current && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Photo viewer"
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/80 p-4"
          onClick={() => setOpen(null)}
        >
          <button type="button" onClick={() => setOpen(null)} className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20" aria-label="Close photo">
            <IconX />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={current.src} alt={`${alt}, report #${current.report.id}`} className="max-h-[80vh] max-w-full rounded-xl object-contain" onClick={(e) => e.stopPropagation()} />
          <p className="max-w-2xl text-center text-white/90" onClick={(e) => e.stopPropagation()}>
            {current.report.summary_en ?? current.report.raw_text}
            <span className="block text-sm text-white/60">
              Report #{current.report.id} · {formatDateTime(current.report.created_at)} · {open! + 1} / {photos.length} (← → to browse)
            </span>
          </p>
        </div>
      )}
    </>
  );
}
