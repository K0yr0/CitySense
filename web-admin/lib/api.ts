// Typed client for the CityEcho FastAPI backend (docs/ARCHITECTURE.md §6).
// NEXT_PUBLIC_USE_MOCK=1 -> fixtures only. Otherwise every call falls back to fixtures when the
// request fails, and the header shows a "Demo data" badge (see lib/demo.ts).
import { getSession, setSession, signOut, type Session } from "./auth";
import { markFallback, markLive, USE_MOCK } from "./demo";
import * as mock from "./mock";
import type {
  IncidentDetail,
  IncidentSummary,
  Mode,
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

/** FastAPI errors are {"detail": "..."}; fall back to the raw body or the status text. */
async function errorMessage(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  try {
    const detail = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
  } catch {
    /* not JSON */
  }
  return text || res.statusText;
}

/** fetch with the session token, a timeout and ApiError on non-2xx. A rejected token signs the admin out. */
async function send<T>(path: string, init: RequestInit | undefined, timeoutMs: number): Promise<T> {
  const token = getSession()?.token;
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { ...init, headers, signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) {
      if (res.status === 401 && token) signOut();
      throw new ApiError(res.status, await errorMessage(res));
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

async function request<T>(
  endpoint: string,
  path: string,
  init: RequestInit | undefined,
  fallback: () => T,
  timeoutMs = 8000,
): Promise<T> {
  if (USE_MOCK) return fallback();
  try {
    const data = await send<T>(path, init, timeoutMs);
    markLive(endpoint);
    return data;
  } catch (err) {
    console.warn(`[cityecho] ${endpoint} failed, serving demo data`, err);
    markFallback(endpoint);
    return fallback();
  }
}

// ---------------------------------------------------------------- admin login (docs/ARCHITECTURE.md §8)

const MOCK_ADMIN: Session = { token: "mock", user: { id: 1, email: "admin@cityecho.demo", name: "Demo admin", role: "admin" } };

function adminOnly(session: Session): Session {
  if (session.user.role !== "admin") {
    throw new ApiError(403, `${session.user.email} is not an admin. Ask the team to add it to ADMIN_EMAILS.`);
  }
  setSession(session);
  return session;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }, 15000);
}

/** Exchange a Google ID token (Google Identity Services) for our session. Throws ApiError; non-admins are rejected. */
export async function loginWithGoogle(idToken: string): Promise<Session> {
  if (USE_MOCK) return adminOnly(MOCK_ADMIN);
  return adminOnly(await postJson<Session>("/auth/google", { id_token: idToken }));
}

/** Local testing without Google (backend AUTH_DEV_LOGIN=1). In mock mode any email signs in as the demo admin. */
export async function loginDev(email: string): Promise<Session> {
  if (USE_MOCK) return adminOnly({ ...MOCK_ADMIN, user: { ...MOCK_ADMIN.user, email } });
  return adminOnly(await postJson<Session>("/auth/dev", { email }));
}

/**
 * Re-check a stored session against GET /admin/ping: an expired token (401) or an email removed from
 * ADMIN_EMAILS (403) signs the admin out. Network errors keep the session (the UI falls back to demo data).
 */
export async function checkSession(): Promise<void> {
  if (USE_MOCK || !getSession()) return;
  try {
    await send("/admin/ping", undefined, 8000);
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) signOut();
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

export async function getVehicles(kind?: VehicleKind): Promise<Vehicle[]> {
  if (!kind) {
    const [trams, buses] = await Promise.all([getVehicles("tram"), getVehicles("bus")]);
    return [...trams, ...buses];
  }
  const r = await request(`vehicles-${kind}`, `/vehicles/live${query({ kind })}`, undefined, () => ({ vehicles: mock.mockVehicles(kind) }));
  return (r.vehicles ?? []).map((v) => ({ ...v, kind: v.kind ?? kind }));
}
