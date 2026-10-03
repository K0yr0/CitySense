"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";

// MapLibre + deck.gl touch window/WebGL, so the map only ever renders in the browser.
const CityMap = dynamic(() => import("./CityMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-lg text-muted">Loading map…</div>,
});

/** The city map. `/?incident=ID` opens it focused on that incident (link from the incident page). */
export default function MapShell() {
  const raw = Number(useSearchParams().get("incident"));
  const focusId = Number.isInteger(raw) && raw > 0 ? raw : null;
  return (
    <div className="relative min-h-[460px] flex-1 bg-surface-2">
      {/* key: a new deep link remounts the map so it flies to the new incident */}
      <CityMap key={focusId ?? "city"} focusId={focusId} />
    </div>
  );
}
