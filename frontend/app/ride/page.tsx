import type { Metadata } from "next";
import RideView from "@/components/ride/RideView";

export const metadata: Metadata = { title: "Ride recorder" };

export default function RidePage() {
  return <RideView />;
}
