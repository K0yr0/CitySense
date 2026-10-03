import type { Metadata } from "next";
import StatsView from "@/components/stats/StatsView";

export const metadata: Metadata = { title: "Statistics" };

export default function StatsPage() {
  return <StatsView />;
}
