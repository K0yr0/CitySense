import type { Metadata } from "next";
import IncidentDetailView from "@/components/incidents/IncidentDetailView";

export async function generateMetadata(props: PageProps<"/incidents/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  return { title: `Incident #${id}` };
}

export default async function IncidentPage(props: PageProps<"/incidents/[id]">) {
  const { id } = await props.params;
  return <IncidentDetailView id={Number(id)} />;
}
