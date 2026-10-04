"use client";

import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { filtersFrom, filtersQuery } from "@/lib/filters";

// MapLibre + deck.gl touch window/WebGL, so the map only ever renders in the browser.
const CityMap = dynamic(() => import("./CityMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-sm text-muted">Loading map…</div>,
});

/**
 * The city map. `/?incident=ID` opens it focused on that incident (link from the incident page);
 * the queue filters (`?department=…&status=…&work=…&q=…`) show only the matching incidents.
 */
export default function MapShell() {
  const params = useSearchParams();
  const raw = Number(params.get("incident"));
  const focusId = Number.isInteger(raw) && raw > 0 ? raw : null;
  const filters = filtersFrom(params);
  return (
    <div className="relative min-h-[460px] flex-1 bg-surface-2">
      {/* key: a new deep link or filter remounts the map so it flies / fits to the new view */}
      <CityMap key={`${focusId ?? "city"}:${filtersQuery(filters)}`} focusId={focusId} filters={filters} />
    </div>
  );
}
