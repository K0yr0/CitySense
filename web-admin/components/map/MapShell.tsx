"use client";

import dynamic from "next/dynamic";

// MapLibre + deck.gl touch window/WebGL, so the map only ever renders in the browser.
const CityMap = dynamic(() => import("./CityMap"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 grid place-items-center text-lg text-muted">Loading map…</div>,
});

export default function MapShell() {
  return (
    <div className="relative min-h-[460px] flex-1 bg-surface-2">
      <CityMap />
    </div>
  );
}
