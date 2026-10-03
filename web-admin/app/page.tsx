import { Suspense } from "react";
import MapShell from "@/components/map/MapShell";
import StatsBar from "@/components/StatsBar";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <StatsBar />
      {/* MapShell reads ?incident= (useSearchParams), which needs a Suspense boundary. */}
      <Suspense fallback={<div className="relative min-h-[460px] flex-1 bg-surface-2" />}>
        <MapShell />
      </Suspense>
    </main>
  );
}
