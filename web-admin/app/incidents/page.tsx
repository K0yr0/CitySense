import type { Metadata } from "next";
import IncidentQueue from "@/components/incidents/IncidentQueue";

export const metadata: Metadata = { title: "Incident queue" };

export default function IncidentsPage() {
  return <IncidentQueue />;
}
