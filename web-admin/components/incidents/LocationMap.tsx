"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import type { IncidentSummary } from "@/lib/types";
import { IconArrowRight, IconPin } from "../icons";
import { Card } from "../ui";

// MapLibre + deck.gl need the browser (WebGL), so the map is client-only.
const LocationMapInner = dynamic(() => import("./LocationMapInner"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-muted">Loading map…</div>,
});

/** "Where is it?": a small map around the incident and a link to the full city map focused on it. */
export default function LocationMap({ incident: i }: { incident: IncidentSummary }) {
  return (
    <Card
      title={
        <span className="inline-flex items-center gap-2">
          <IconPin width={18} height={18} /> Location
        </span>
      }
      action={
        <Link href={`/?incident=${i.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-accent hover:underline">
          Open on city map <IconArrowRight width={16} height={16} />
        </Link>
      }
    >
      <div className="relative h-64 overflow-hidden rounded-xl border border-line bg-surface-2">
        <LocationMapInner incident={i} />
      </div>
      <p className="tabular mt-2 text-sm text-muted">
        {i.address ? `${i.address} · ` : ""}
        {i.lat.toFixed(5)}, {i.lon.toFixed(5)} · road and track colours show measured health
      </p>
    </Card>
  );
}
