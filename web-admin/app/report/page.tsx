import type { Metadata } from "next";
import ReportForm from "@/components/report/ReportForm";

export const metadata: Metadata = { title: "Report a problem" };

export default function ReportPage() {
  return <ReportForm />;
}
