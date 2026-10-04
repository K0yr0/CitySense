import type { Metadata } from "next";
import { Suspense } from "react";
import IncidentQueue from "@/components/incidents/IncidentQueue";

export const metadata: Metadata = { title: "Incident queue" };

export default function IncidentsPage() {
  // IncidentQueue reads its filters from the URL (useSearchParams), which needs a Suspense boundary.
  return (
    <Suspense fallback={<main className="flex-1 px-6 py-16 text-center text-sm text-muted">Loading incidents…</main>}>
      <IncidentQueue />
    </Suspense>
  );
}
