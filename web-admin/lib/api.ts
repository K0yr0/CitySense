// Typed client for the CityEcho FastAPI backend (docs/ARCHITECTURE.md §6).
// NEXT_PUBLIC_USE_MOCK=1 -> fixtures only. Otherwise every call falls back to fixtures when the
// request fails, and the header shows a "Demo data" badge (see lib/demo.ts).
import { contributorToken } from "./contributor";
import { markFallback, markLive, USE_MOCK } from "./demo";
import * as mock from "./mock";
import type {
  CitizenAnswer,
  CitizenResponseResult,
  IncidentDetail,
  IncidentSummary,
  Mode,
  ReportStatus,
  RideResult,
  RideStreamAck,
  RideStreamRequest,
  Segment,
  Stats,
  Vehicle,
  VehicleKind,
  VerifyResult,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function query(params: Record<string, string | number | boolean | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(
  endpoint: string,
  path: string,
  init: RequestInit | undefined,
  fallback: () => T,
  timeoutMs = 8000,
): Promise<T> {
  if (USE_MOCK) return fallback();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { ...init, signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new ApiError(res.status, (await res.text().catch(() => "")) || res.statusText);
    const data = (await res.json()) as T;
    markLive(endpoint);
    return data;
  } catch (err) {
    console.warn(`[cityecho] ${endpoint} failed, serving demo data`, err);
    markFallback(endpoint);
    return fallback();
  } finally {
    clearTimeout(timer);
  }
}

/** Resolve a backend-relative photo URL ("/photos/x.jpg"). */
export function photoUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^(https?:|data:|blob:)/.test(path)) return path;
  return `${API_URL}${path.startsWith("/") ? "" : "/"}${path}`;
}

export async function getStats(): Promise<Stats> {
  return request("stats", "/stats", undefined, mock.mockStats, 5000);
}

export async function getSegments(params: { bbox?: string; mode?: Mode; measuredOnly?: boolean } = {}): Promise<Segment[]> {
  const q = query({ bbox: params.bbox, mode: params.mode, measured_only: params.measuredOnly ? "true" : undefined });
  const r = await request("segments", `/segments${q}`, undefined, () => ({ segments: mock.mockSegments(params) }), 15000);
  return r.segments ?? [];
}

export async function getIncidents(params: { department?: string; status?: string; limit?: number } = {}): Promise<IncidentSummary[]> {
  const q = query({ department: params.department, status: params.status, limit: params.limit ?? 200 });
  const r = await request("incidents", `/incidents${q}`, undefined, () => ({ incidents: mock.mockIncidents(params) }));
  return [...(r.incidents ?? [])].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

export async function getIncident(id: number): Promise<IncidentDetail | null> {
  return request(`incident`, `/incidents/${id}`, undefined, () => mock.mockIncidentDetail(id));
}

export async function requestVerification(id: number): Promise<VerifyResult> {
  return request("verify", `/incidents/${id}/verify`, { method: "POST" }, () => mock.mockVerify(id), 15000);
}

export async function submitReport(input: { text: string; lon?: number | null; lat?: number | null; photo?: File | null }): Promise<ReportStatus> {
  const form = new FormData();
  form.set("text", input.text);
  if (input.lon != null && input.lat != null) {
    form.set("lon", String(input.lon));
    form.set("lat", String(input.lat));
  }
  if (input.photo) form.set("photo", input.photo, input.photo.name || "photo.jpg");
  form.set("contributor", contributorToken());
  return request("reports", "/reports", { method: "POST", body: form }, () => mock.mockSubmitReport(input.text, input.lon, input.lat), 45000);
}

/** Citizen answer to "Is this problem still there?", weighted by this browser's trust. */
export async function respondToIncident(id: number, answer: CitizenAnswer): Promise<CitizenResponseResult | null> {
  return request(
    "responses",
    `/incidents/${id}/responses`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answer, contributor: contributorToken() }) },
    () => mock.mockRespond(id, answer),
    15000,
  );
}

export async function getReportStatus(id: number): Promise<ReportStatus | null> {
  return request("report-status", `/reports/${id}/status`, undefined, () => null);
}

export async function getVehicles(kind?: VehicleKind): Promise<Vehicle[]> {
  if (!kind) {
    const [trams, buses] = await Promise.all([getVehicles("tram"), getVehicles("bus")]);
    return [...trams, ...buses];
  }
  const r = await request(`vehicles-${kind}`, `/vehicles/live${query({ kind })}`, undefined, () => ({ vehicles: mock.mockVehicles(kind) }));
  return (r.vehicles ?? []).map((v) => ({ ...v, kind: v.kind ?? kind }));
}

export async function streamRide(body: RideStreamRequest): Promise<RideStreamAck | RideResult> {
  return request(
    "rides",
    "/rides/stream",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    () => mock.mockRideStream(body),
    body.final ? 120000 : 10000,
  );
}
