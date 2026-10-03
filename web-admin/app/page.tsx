import MapShell from "@/components/map/MapShell";
import StatsBar from "@/components/StatsBar";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col">
      <StatsBar />
      <MapShell />
    </main>
  );
}
